from sales.models import Sale
from inventory.models import Inventory
from django.db.models import Sum

def get_business_summary(business):
    sales = Sale.objects.filter(business=business)

    total_revenue = sum(s.total_revenue() for s in sales)
    total_profit = sum(s.profit() for s in sales)

    low_stock_items = Inventory.objects.filter(
        business=business,
        stock_quantity__lte=5
    )

    return {
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "low_stock_count": low_stock_items.count(),
    }