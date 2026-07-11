from decimal import Decimal
from collections import defaultdict, OrderedDict
from datetime import timedelta

from django.utils import timezone

from sales.models import Sale
from inventory.models import Inventory


# ======================================
# SALES FORECAST
# ======================================


def generate_sales_forecast(business):

    today = timezone.now().date()

    start_date = today - timedelta(days=29)

    # =====================================
    # SALES
    # =====================================
    sales = Sale.objects.filter(
        business=business,
        status='Completed',
        created_at__date__range=[
            start_date,
            today
        ]
    ).prefetch_related('items')

    # =====================================
    # REVENUE MAP
    # =====================================
    revenue_map = OrderedDict()

    current = start_date

    while current <= today:

        revenue_map[current] = Decimal('0.00')

        current += timedelta(days=1)

    # =====================================
    # CALCULATE DAILY REVENUE
    # =====================================
    for sale in sales:

        day = sale.created_at.date()

        for item in sale.items.all():

            revenue_map[day] += Decimal(
                str(item.total)
            )

    # =====================================
    # LABELS + VALUES
    # =====================================
    labels = []

    actual_sales = []

    for day, revenue in revenue_map.items():

        labels.append(
            day.strftime('%d %b')
        )

        actual_sales.append(
            float(revenue)
        )

    # =====================================
    # SIMPLE FORECAST
    # =====================================
    average_sales = Decimal('0.00')

    if actual_sales:

        average_sales = (
            sum(
                Decimal(str(x))
                for x in actual_sales
            )
            /
            len(actual_sales)
        )

    forecast = []

    for value in actual_sales:

        blended = (
            Decimal(str(value))
            + average_sales
        ) / Decimal('2')

        forecast.append(
            round(float(blended), 2)
        )

    # =====================================
    # RESPONSE
    # =====================================
    return {

        "labels": labels,

        "actual_sales": actual_sales,

        "forecast_sales": forecast,
    }


# ======================================
# INVENTORY FORECAST
# ======================================

def generate_inventory_forecast(business):

    products = Inventory.objects.filter(
        business=business
    )

    risky_products = []

    for item in products:

        recent_sales = Sale.objects.filter(
            business=business,
            product_name=item.product_name
        )

        total_sold = sum(s.quantity for s in recent_sales)

        if total_sold <= 0:
            continue

        avg_daily_sales = total_sold / 30

        if avg_daily_sales <= 0:
            continue

        estimated_days_left = (
            item.stock_quantity / avg_daily_sales
        )

        if estimated_days_left <= 7:
            risky_products.append({
                "product": item.product_name,
                "days_left": round(estimated_days_left, 1)
            })

    return risky_products


# ======================================
# BUSINESS RISK ENGINE
# ======================================

def generate_business_risks(business):

    risks = []

    low_stock = Inventory.objects.filter(
        business=business,
        stock_quantity__lte=5
    )

    if low_stock.exists():
        risks.append(
            "Multiple products are reaching critical stock levels."
        )

    sales_count = Sale.objects.filter(
        business=business
    ).count()

    if sales_count < 5:
        risks.append(
            "Very low sales activity detected."
        )

    inventory_count = Inventory.objects.filter(
        business=business
    ).count()

    if inventory_count == 0:
        risks.append(
            "Inventory database is empty."
        )

    return risks
