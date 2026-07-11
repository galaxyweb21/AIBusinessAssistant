from django.db.models import Sum, F
from sales.models import Sale
from inventory.models import Inventory


def get_business_insights(user):

    insights = []

    # =========================================
    # BUSINESS
    # =========================================
    business = getattr(user, 'business_set', None)

    if not business:
        return {
            "insights": []
        }

    business = user.business_set.first()

    if not business:
        return {
            "insights": []
        }

    # =========================================
    # SALES QUERYSET
    # =========================================
    sales = Sale.objects.filter(
        business=business
    )

    inventory = Inventory.objects.filter(
        business=business
    )

    # =========================================
    # TOTAL REVENUE
    # =========================================
    total_revenue = 0

    for sale in sales:
        total_revenue += sale.total_revenue()

    # =========================================
    # TOTAL PROFIT
    # =========================================
    total_profit = 0

    for sale in sales:
        total_profit += sale.profit()

    # =========================================
    # LOW STOCK PRODUCTS
    # =========================================
    low_stock_products = inventory.filter(
        stock_quantity__lte=5
    )

    low_stock_count = low_stock_products.count()

    # =========================================
    # TOP SELLING PRODUCT
    # =========================================
    top_product = (
        sales.values('product_name')
        .annotate(
            total_qty=Sum('quantity')
        )
        .order_by('-total_qty')
        .first()
    )

    # =========================================
    # TOTAL INVENTORY PRODUCTS
    # =========================================
    total_products = inventory.count()

    # =========================================
    # AI INSIGHTS
    # =========================================

    # REVENUE
    if total_revenue > 0:

        insights.append({
            "type": "success",
            "icon": "fas fa-chart-line",
            "title": "Revenue Generated",
            "message": f"Your business has generated Gh¢{total_revenue:,.2f} in revenue."
        })

    # PROFIT
    if total_profit > 0:

        insights.append({
            "type": "primary",
            "icon": "fas fa-wallet",
            "title": "Profit Analysis",
            "message": f"Estimated total profit is Gh¢{total_profit:,.2f}."
        })

    # LOW STOCK
    if low_stock_count > 0:

        insights.append({
            "type": "warning",
            "icon": "fas fa-exclamation-triangle",
            "title": "Low Stock Alert",
            "message": f"{low_stock_count} product(s) are running low on stock."
        })

    # TOP PRODUCT
    if top_product:

        insights.append({
            "type": "primary",
            "icon": "fas fa-crown",
            "title": "Top Selling Product",
            "message": f"{top_product['product_name']} is currently your best-selling product."
        })

    # EMPTY INVENTORY
    if total_products == 0:

        insights.append({
            "type": "danger",
            "icon": "fas fa-box-open",
            "title": "No Inventory Found",
            "message": "You have not added products to inventory yet."
        })

    # NO SALES
    if sales.count() == 0:

        insights.append({
            "type": "danger",
            "icon": "fas fa-chart-bar",
            "title": "No Sales Yet",
            "message": "No sales records found for this business."
        })

    return {
        "insights": insights,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "low_stock_count": low_stock_count,
        "top_product": top_product,
        "total_products": total_products,
    }