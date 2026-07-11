from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from sales.models import Sale, SaleItem
from inventory.models import Inventory


def get_business_metrics(business):

    today = date.today()

    last_week = today - timedelta(days=7)

    # ==========================
    # SALES
    # ==========================

    sales = Sale.objects.filter(
        business=business,
        status='Completed'
    )

    weekly_sales = sales.filter(
        created_at__date__gte=last_week
    )

    total_revenue = sales.aggregate(
        total=Coalesce(
            Sum('total'),
            Decimal('0')
        )
    )['total']

    highest_sale = weekly_sales.order_by(
        '-total'
    ).first()

    highest_sale_amount = (
        highest_sale.total
        if highest_sale
        else 0
    )

    # ==========================
    # LOW STOCK
    # ==========================

    low_stock = Inventory.objects.filter(
        business=business,
        stock_quantity__lte=5
    )

    low_stock_items = list(

        low_stock.values(
            'product_name',
            'stock_quantity'
        )

    )

    # ==========================
    # TOP PRODUCT
    # ==========================

    top_product = (

        SaleItem.objects.filter(
            sale__business=business
        )
        .values(
            'product__product_name'
        )
        .annotate(
            qty=Sum(
                'quantity'
            )
        )
        .order_by(
            '-qty'
        )
        .first()

    )

    return {

        "total_revenue": total_revenue,

        "highest_sale_last_week":
            highest_sale_amount,

        "low_stock_items":
            low_stock_items,

        "top_product":
            top_product
    }