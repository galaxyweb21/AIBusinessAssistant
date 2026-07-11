from sales.models import *
from inventory.models import Inventory

from collections import defaultdict, OrderedDict

from datetime import timedelta

from django.utils import timezone

from decimal import Decimal
from django.db.models import Sum
from django.db.models.functions import Coalesce


def get_dashboard_data(business):

    now = timezone.now()

    week_start = now - timedelta(days=7)

    month_start = now - timedelta(days=30)

    # =========================
    # SALES
    # =========================
    sales = Sale.objects.filter(
        business=business,
        status='Completed'
    )

    total_sales = sales.count()

    total_revenue = sales.aggregate(
        total=Coalesce(
            Sum('total'),
            Decimal('0.00')
        )
    )['total']

    total_profit = SaleItem.objects.filter(
        sale__business=business,
        sale__status='Completed'
    ).aggregate(
        total=Coalesce(
            Sum('profit'),
            Decimal('0.00')
        )
    )['total']

    weekly_sales = sales.filter(
        created_at__gte=week_start
    ).aggregate(
        total=Coalesce(
            Sum('total'),
            Decimal('0.00')
        )
    )['total']

    monthly_sales = sales.filter(
        created_at__gte=month_start
    ).aggregate(
        total=Coalesce(
            Sum('total'),
            Decimal('0.00')
        )
    )['total']

    # =========================
    # INVENTORY COUNTS
    # =========================
    inventory_queryset = Inventory.objects.filter(
        business=business
    )

    low_stock_count = inventory_queryset.filter(
        stock_quantity__gt=0,
        stock_quantity__lte=5
    ).count()

    out_of_stock_count = inventory_queryset.filter(
        stock_quantity__lte=0
    ).count()

    healthy_stock_count = inventory_queryset.filter(
        stock_quantity__gt=5
    ).count()

    # =========================
    # BEST PRODUCT
    # =========================
    product_counter = defaultdict(int)

    sale_items = SaleItem.objects.filter(
        sale__business=business,
        sale__status='Completed'
    ).select_related('product')

    for item in sale_items:

        if item.product:

            product_counter[
                item.product.product_name
            ] += item.quantity

    best_product = (
        max(product_counter, key=product_counter.get)
        if product_counter else "N/A"
    )

    return {

        "total_revenue": float(total_revenue),

        "total_profit": float(total_profit),

        "total_sales": total_sales,

        "weekly_sales": float(weekly_sales),

        "monthly_sales": float(monthly_sales),

        "best_product": best_product,

        "low_stock_count": low_stock_count,

        "out_of_stock_count": out_of_stock_count,

        "healthy_stock_count": healthy_stock_count,

    }

# ==========================================
# SALES CHART
# ==========================================

def get_sales_chart_data(business, period="7days"):

    today = timezone.now().date()

    if period == "7days":

        start_date = today - timedelta(days=6)

    else:

        start_date = today - timedelta(days=29)

    sales = Sale.objects.filter(
        business=business,
        status='Completed',
        created_at__date__range=[
            start_date,
            today
        ]
    )

    daily_totals = {}

    for sale in sales:

        day = sale.created_at.date()

        if day not in daily_totals:

            daily_totals[day] = Decimal("0.00")

        daily_totals[day] += Decimal(
            str(sale.total)
        )

    # =====================================
    # FILL EMPTY DAYS
    # =====================================
    data_map = OrderedDict()

    current = start_date

    while current <= today:

        data_map[current] = daily_totals.get(
            current,
            Decimal("0.00")
        )

        current += timedelta(days=1)

    labels = [
        d.strftime("%a")
        for d in data_map.keys()
    ]

    values = [
        float(v)
        for v in data_map.values()
    ]

    return {

        "labels": labels,

        "data": values
    }


# ==========================================
# TOP PRODUCTS
# ==========================================
def get_top_products(business, period="7days"):

    today = timezone.now().date()

    if period == "7days":

        start_date = today - timedelta(days=6)

    else:

        start_date = today - timedelta(days=29)

    sales = Sale.objects.filter(
        business=business,
        status='Completed',
        created_at__date__range=[
            start_date,
            today
        ]
    ).prefetch_related('items')

    product_data = defaultdict(
        lambda: {
            "qty": 0,
            "revenue": 0
        }
    )

    for sale in sales:

        for item in sale.items.all():

            product_name = (
                item.product.product_name
            )

            product_data[product_name]["qty"] += (
                item.quantity
            )

            product_data[product_name]["revenue"] += float(
                item.total
            )

    sorted_products = sorted(
        product_data.items(),
        key=lambda x: x[1]["revenue"],
        reverse=True
    )

    labels = []

    qty = []

    revenue = []

    for product, data in sorted_products[:5]:

        labels.append(product)

        qty.append(data["qty"])

        revenue.append(data["revenue"])

    return {

        "labels": labels,

        "data": qty,

        "revenue": revenue
    }


# ==========================================
# AI INSIGHTS (FIXED)
# ==========================================

def get_ai_insights(business):

    today = timezone.now().date()

    last_7_days = today - timedelta(days=6)

    previous_7_start = today - timedelta(days=13)

    previous_7_end = today - timedelta(days=7)

    insights=[]

    recent_sales=Sale.objects.filter(
        business=business,
        status='Completed',
        created_at__date__range=[
            last_7_days,
            today
        ]
    ).prefetch_related('items')

    previous_sales=Sale.objects.filter(
        business=business,
        status='Completed',
        created_at__date__range=[
            previous_7_start,
            previous_7_end
        ]
    )

    recent_total=sum(
        sale.total or 0
        for sale in recent_sales
    )

    previous_total=sum(
        sale.total or 0
        for sale in previous_sales
    )


    # SALES CHANGE

    if previous_total>0:

        change=float(
            (
                recent_total-
                previous_total
            )
            /
            previous_total
        )*100


        if change < -10:

            insights.append({

                "type":"danger",

                "icon":"fas fa-arrow-trend-down",

                "title":"Sales Decline",

                "message":
                f"Sales dropped by {abs(round(change,1))}% compared to last week."

            })

        elif change > 10:

            insights.append({

                "type":"success",

                "icon":"fas fa-chart-line",

                "title":"Sales Growth",

                "message":
                f"Sales increased by {round(change,1)}% compared to last week."

            })


    # BEST PRODUCT

    product_map=defaultdict(int)

    for sale in recent_sales:

        for item in sale.items.all():

            product_map[
                item.product.product_name
            ] += item.quantity


    if product_map:

        best=max(
            product_map,
            key=product_map.get
        )

        insights.append({

            "type":"info",

            "icon":"fas fa-box-open",

            "title":"Best Selling Product",

            "message":
            f"{best} is your top selling product."

        })


    # LOW STOCK

    low_stock=Inventory.objects.filter(
        business=business,
        stock_quantity__lte=5
    )

    if low_stock.exists():

        products=", ".join(

            i.product_name
            for i in low_stock[:3]

        )

        insights.append({

            "type":"warning",

            "icon":"fas fa-exclamation-triangle",

            "title":"Low Stock Alert",

            "message":
            f"Low stock detected for {products}"

        })


    # print("AI INSIGHTS:",insights)

    return insights


def get_profit_analytics(business, period="7days"):

    today = timezone.now().date()

    # =====================================
    # PERIOD
    # =====================================
    if period == "7days":

        start_date = today - timedelta(days=6)

    else:

        start_date = today - timedelta(days=29)

    # =====================================
    # SALES
    # =====================================
    sales = Sale.objects.filter(
        business=business,
        created_at__date__range=[
            start_date,
            today
        ]
    ).prefetch_related('items')

    # =====================================
    # DAILY DATA
    # =====================================
    daily = {}

    for sale in sales:

        day = sale.created_at.date()

        # -----------------------------
        # INIT DAY
        # -----------------------------
        if day not in daily:

            daily[day] = {

                "revenue": Decimal("0.00"),

                "cost": Decimal("0.00"),

                "profit": Decimal("0.00")
            }

        # -----------------------------
        # LOOP SALE ITEMS
        # -----------------------------
        for item in sale.items.all():

            revenue = Decimal(
                str(item.total)
            )

            cost = (
                Decimal(str(item.cost_price))
                *
                item.quantity
            )

            profit = Decimal(
                str(item.profit)
            )

            daily[day]["revenue"] += revenue

            daily[day]["cost"] += cost

            daily[day]["profit"] += profit

    # =====================================
    # FILL EMPTY DAYS
    # =====================================
    data_map = OrderedDict()

    current = start_date

    while current <= today:

        if current in daily:

            data_map[current] = daily[current]

        else:

            data_map[current] = {

                "revenue": Decimal("0.00"),

                "cost": Decimal("0.00"),

                "profit": Decimal("0.00")
            }

        current += timedelta(days=1)

    # =====================================
    # CHART DATA
    # =====================================
    labels = []

    revenue = []

    cost = []

    profit = []

    total_revenue = Decimal("0.00")

    total_cost = Decimal("0.00")

    total_profit = Decimal("0.00")

    for day, values in data_map.items():

        labels.append(
            day.strftime("%a")
        )

        revenue.append(
            float(values["revenue"])
        )

        cost.append(
            float(values["cost"])
        )

        profit.append(
            float(values["profit"])
        )

        total_revenue += values["revenue"]

        total_cost += values["cost"]

        total_profit += values["profit"]

    # =====================================
    # PROFIT MARGIN
    # =====================================
    margin = 0

    if total_revenue > 0:

        margin = float(
            (
                total_profit
                /
                total_revenue
            ) * 100
        )

    # =====================================
    # RESPONSE
    # =====================================
    return {

        "labels": labels,

        "revenue": revenue,

        "cost": cost,

        "profit": profit,

        "margin": round(margin, 2),

        "total_revenue": float(total_revenue),

        "total_cost": float(total_cost),

        "total_profit": float(total_profit),
    }
