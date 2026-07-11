from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import Coalesce

from sales.models import Sale
from inventory.models import Inventory
from dashboard.models import BusinessAlert


def generate_business_alerts(business):

    today = timezone.now()

    last_7_days = today - timedelta(days=6)
    previous_7_days = today - timedelta(days=13)

    # =====================================
    # CLEAR DYNAMIC ALERTS
    # (critical fix)
    # =====================================

    BusinessAlert.objects.filter(
        business=business,
        title__in=[
            "Low Stock Warning",
            "Out of Stock Alert",
            "Revenue Drop Detected",
            "Strong Sales Performance"
        ]
    ).delete()

    # =====================================
    # SALES
    # =====================================

    recent_sales = Sale.objects.filter(
        business=business,
        status='Completed',
        created_at__range=[last_7_days, today]
    )

    previous_sales = Sale.objects.filter(
        business=business,
        status='Completed',
        created_at__range=[previous_7_days, last_7_days]
    )

    recent_revenue = recent_sales.aggregate(
        total=Coalesce(
            Sum("total"),
            Decimal("0.00")
        )
    )["total"]

    previous_revenue = previous_sales.aggregate(
        total=Coalesce(
            Sum("total"),
            Decimal("0.00")
        )
    )["total"]

    # =====================================
    # REVENUE DROP ALERT
    # =====================================

    if previous_revenue > 0:

        change = (
            (recent_revenue - previous_revenue)
            / previous_revenue
        ) * 100

        if change < -20:

            BusinessAlert.objects.create(
                business=business,
                title="Revenue Drop Detected",
                message=(
                    f"Revenue dropped by "
                    f"{abs(round(change,1))}% "
                    f"compared to last week."
                ),
                alert_type="danger"
            )

    # =====================================
    # LOW STOCK
    # =====================================

    low_stock_items = Inventory.objects.filter(
        business=business,
        stock_quantity__gt=0,
        stock_quantity__lte=5
    )

    for item in low_stock_items:

        BusinessAlert.objects.create(
            business=business,
            title="Low Stock Warning",
            message=(
                f"{item.product_name} "
                f"is running low "
                f"({item.stock_quantity} left)"
            ),
            alert_type="warning"
        )

    # =====================================
    # OUT OF STOCK
    # =====================================

    out_stock_items = Inventory.objects.filter(
        business=business,
        stock_quantity__lte=0
    )

    for item in out_stock_items:

        BusinessAlert.objects.create(
            business=business,
            title="Out of Stock Alert",
            message=(
                f"{item.product_name} "
                f"is OUT OF STOCK"
            ),
            alert_type="danger"
        )

    # =====================================
    # POSITIVE SALES ALERT
    # =====================================

    if (
        recent_revenue > previous_revenue
        and recent_revenue > 0
    ):

        BusinessAlert.objects.create(
            business=business,
            title="Strong Sales Performance",
            message="Sales improved compared to last week.",
            alert_type="success"
        )