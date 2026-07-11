from decimal import Decimal
from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from sales.models import Sale, SaleItem


def build_sales_context(business):

    today = timezone.now().date()

    # =========================================
    # DATE RANGES
    # =========================================

    week_start = today - timedelta(days=7)

    last_week_start = week_start - timedelta(days=7)

    month_start = today.replace(day=1)

    # =========================================
    # SALES QUERYSET
    # =========================================

    sales = Sale.objects.filter(
        business=business
    )

    # =========================================
    # TOTAL REVENUE
    # =========================================

    total_revenue = sales.aggregate(
        total=Coalesce(
            Sum("total"),
            Decimal("0.00")
        )
    )["total"]

    # =========================================
    # WEEKLY SALES
    # =========================================

    weekly_sales = sales.filter(
        created_at__date__gte=week_start
    )

    weekly_revenue = weekly_sales.aggregate(
        total=Coalesce(
            Sum("total"),
            Decimal("0.00")
        )
    )["total"]

    # =========================================
    # LAST WEEK SALES
    # =========================================

    last_week_sales = sales.filter(
        created_at__date__gte=last_week_start,
        created_at__date__lt=week_start
    )

    last_week_revenue = last_week_sales.aggregate(
        total=Coalesce(
            Sum("total"),
            Decimal("0.00")
        )
    )["total"]

    # =========================================
    # MONTHLY SALES
    # =========================================

    monthly_sales = sales.filter(
        created_at__date__gte=month_start
    )

    monthly_revenue = monthly_sales.aggregate(
        total=Coalesce(
            Sum("total"),
            Decimal("0.00")
        )
    )["total"]

    # =========================================
    # TOTAL PROFIT
    # =========================================

    total_profit = SaleItem.objects.filter(
        sale__business=business
    ).aggregate(
        total=Coalesce(
            Sum("profit"),
            Decimal("0.00")
        )
    )["total"]

    # =========================================
    # TOP SELLING PRODUCT
    # =========================================

    top_product = (
        SaleItem.objects.filter(
            sale__business=business
        )
        .values(
            "product__product_name"
        )
        .annotate(
            total_qty=Coalesce(
                Sum("quantity"),
                0
            )
        )
        .order_by("-total_qty")
        .first()
    )

    top_product_name = (
        top_product["product__product_name"]
        if top_product
        else "None"
    )

    top_product_qty = (
        top_product["total_qty"]
        if top_product
        else 0
    )

    # =========================================
    # HIGHEST SALES
    # =========================================

    highest_sale_all_time = sales.order_by(
        "-total"
    ).first()

    highest_sale_week = weekly_sales.order_by(
        "-total"
    ).first()

    highest_sale_all_time_value = (
        highest_sale_all_time.total
        if highest_sale_all_time
        else Decimal("0.00")
    )

    highest_sale_week_value = (
        highest_sale_week.total
        if highest_sale_week
        else Decimal("0.00")
    )

    # =========================================
    # SALES COUNTS
    # =========================================

    total_sales_count = sales.count()

    weekly_sales_count = weekly_sales.count()

    monthly_sales_count = monthly_sales.count()

    # =========================================
    # SALES TREND
    # =========================================

    if weekly_revenue > last_week_revenue:
        sales_trend = "UP"

    elif weekly_revenue < last_week_revenue:
        sales_trend = "DOWN"

    else:
        sales_trend = "STABLE"

    # =========================================
    # RECENT SALES
    # =========================================

    recent_sales = sales.order_by(
        "-created_at"
    )[:10]

    recent_sales_list = []

    for sale in recent_sales:

        recent_sales_list.append(
            f"Receipt {sale.receipt_number} - "
            f"GHS {sale.total}"
        )

    # =========================================
    # RETURN CONTEXT
    # =========================================

    return f"""
================ SALES DATA ================

TOTAL REVENUE:
GHS {total_revenue}

TOTAL PROFIT:
GHS {total_profit}

TOTAL SALES COUNT:
{total_sales_count}

THIS WEEK SALES:
GHS {weekly_revenue}

THIS WEEK TOTAL ORDERS:
{weekly_sales_count}

LAST WEEK SALES:
GHS {last_week_revenue}

THIS MONTH SALES:
GHS {monthly_revenue}

THIS MONTH TOTAL ORDERS:
{monthly_sales_count}

SALES TREND:
{sales_trend}

HIGHEST SALE THIS WEEK:
GHS {highest_sale_week_value}

HIGHEST SALE ALL TIME:
GHS {highest_sale_all_time_value}

TOP SELLING PRODUCT:
{top_product_name}

TOP SELLING PRODUCT QTY:
{top_product_qty}

RECENT SALES:
{", ".join(recent_sales_list) if recent_sales_list else "No sales found"}

============================================
"""