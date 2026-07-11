from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

from sales.models import Sale
from inventory.models import Inventory


def generate_ai_insights(business):

    today = timezone.now()
    last_30_days = today - timedelta(days=30)

    sales = Sale.objects.filter(
        business=business,
        status='Completed',
        created_at__gte=last_30_days
    ).prefetch_related('items')

    total_revenue = Decimal('0.00')
    total_profit = Decimal('0.00')
    total_items_sold = 0

    for sale in sales:

        total_revenue += Decimal(
            str(
                sale.total or 0
            )
        )

        for item in sale.items.all():

            total_profit += Decimal(
                str(
                    item.profit or 0
                )
            )

            total_items_sold += (
                item.quantity or 0
            )

    low_stock_count = Inventory.objects.filter(
        business=business,
        stock_quantity__gt=0,
        stock_quantity__lte=5
    ).count()

    profit_margin = Decimal('0')

    if total_revenue > 0:

        profit_margin = (
            total_profit /
            total_revenue
        ) * 100

    insights=[]

    # ========================
    # Revenue
    # ========================

    if total_revenue > 0:

        insights.append({

            "type":"success",

            "icon":"fas fa-chart-line",

            "title":"Revenue Generated",

            "message":
            f"You generated GH¢{round(total_revenue,2)} in sales over the last 30 days."

        })

    # ========================
    # Profit
    # ========================

    if profit_margin >= 40:

        insights.append({

            "type":"success",

            "icon":"fas fa-coins",

            "title":"Strong Profit Margin",

            "message":
            f"Current profit margin is {round(profit_margin,1)}%."

        })

    elif total_revenue > 0:

        insights.append({

            "type":"warning",

            "icon":"fas fa-coins",

            "title":"Low Profit Margin",

            "message":
            "Profit margin is below expected level."

        })

    # ========================
    # Stock
    # ========================

    if low_stock_count > 0:

        insights.append({

            "type":"danger",

            "icon":"fas fa-exclamation-triangle",

            "title":"Low Stock Alert",

            "message":
            f"{low_stock_count} products require restocking."

        })

    # ========================
    # Sales Volume
    # ========================

    if total_items_sold > 0:

        insights.append({

            "type":"info",

            "icon":"fas fa-box-open",

            "title":"Sales Activity",

            "message":
            f"{total_items_sold} items sold recently."

        })

    return insights