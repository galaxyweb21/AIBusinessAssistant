from .models import *
from inventory.models import Inventory

from collections import defaultdict, OrderedDict

from datetime import timedelta

from django.utils import timezone

from decimal import Decimal
from django.db.models import Sum
from django.db.models.functions import Coalesce


def update_business_metrics(business, sale=None):

    today = timezone.now().date()
    week_start = today - timedelta(days=7)
    month_start = today - timedelta(days=30)

    # ==============================
    # BASE SALES (SOURCE OF TRUTH)
    # ==============================
    completed_sales = Sale.objects.filter(
        business=business,
        status="Completed"
    )

    sale_items = SaleItem.objects.filter(
        sale__business=business,
        sale__status="Completed"
    )

    # ==============================
    # TOTALS
    # ==============================
    total_revenue = sale_items.aggregate(
        total=Sum('total')
    )['total'] or Decimal('0.00')

    total_profit = sale_items.aggregate(
        total=Sum('profit')
    )['total'] or Decimal('0.00')

    # ==============================
    # PERIODS (FROM SALE ITEMS)
    # ==============================
    weekly_sales = sale_items.filter(
        created_at__gte=week_start
    ).aggregate(
        total=Sum('total')
    )['total'] or Decimal('0.00')

    monthly_sales = sale_items.filter(
        created_at__gte=month_start
    ).aggregate(
        total=Sum('total')
    )['total'] or Decimal('0.00')

    # ==============================
    # SAVE SNAPSHOT
    # ==============================
    metric, created = SalesMetric.objects.get_or_create(
        business=business,
        date=today
    )

    metric.total_revenue = total_revenue
    metric.total_profit = total_profit
    metric.weekly_sales = weekly_sales
    metric.monthly_sales = monthly_sales
    metric.daily_sales = total_revenue

    metric.save()

    return metric