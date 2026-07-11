from django.db import models
from business.models import Business
from inventory.models import Inventory
from datetime import date, datetime, timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.crypto import get_random_string
import secrets
from django.utils import timezone

from django.utils.timezone import now
from django.db.models import Max
import re
from django.contrib.auth.models import User


class Tax(models.Model):
    name = models.CharField(max_length=50, null=True)
    tax_percentage = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    business = models.ForeignKey('business.Business', on_delete=models.CASCADE, null=True)
    active = models.BooleanField(default=True)

    def get_rate(self):
        return self.tax_percentage / 100

    def __str__(self):
        return f"{self.name} ({self.tax_percentage}%)"


class Discount(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='discounts'
    )

    name = models.CharField(max_length=50)

    percentage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    start_date = models.DateField(
        blank=True,
        null=True
    )

    end_date = models.DateField(
        blank=True,
        null=True
    )

    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def is_valid(self):
        from django.utils import timezone

        today = timezone.now().date()

        return (
            self.active and
            (self.start_date is None or self.start_date <= today) and
            (self.end_date is None or self.end_date >= today)
        )

    def __str__(self):
        return f"{self.name} ({self.percentage}%)"


class Customer(models.Model):

    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.full_name


class Sale(models.Model):

    PAYMENT_METHODS = (
        ('Cash', 'Cash'),
        ('Mobile Money', 'Mobile Money'),
        ('Card', 'Card'),
        ('Bank Transfer', 'Bank Transfer'),
    )

    SALE_STATUS = (('Completed', 'Completed'), ('Proforma', 'Pro-forma'), ('Refunded', 'Refunded'))

    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    tax = models.ForeignKey(Tax, on_delete=models.SET_NULL, null=True, blank=True)
    discount = models.ForeignKey(Discount, on_delete=models.SET_NULL, null=True, blank=True)
    invoice_number = models.CharField(max_length=30, unique=True, blank=True, null=True)
    receipt_number = models.CharField(max_length=30, unique=True, blank=True, null=True)
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHODS, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    change = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    staff = models.ForeignKey(User, on_delete=models.DO_NOTHING, null=True, blank=True)
    status = models.CharField(max_length=20, choices=SALE_STATUS, default='Completed')
    refund_date = models.DateTimeField(null=True, blank=True)
    # is_proforma = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # =========================
    # BUSINESS CODE HELPER
    # =========================
    def get_business_code(self):
        name = self.business.name if self.business else "BUSINESS"
        words = re.findall(r'[A-Za-z]+', name.upper())

        if not words:
            return "BIZ"

        if len(words) == 1:
            return words[0][:3]

        return "".join(w[0] for w in words[:3])[:3]

    # =========================
    # SAVE
    # =========================
    def save(self, *args, **kwargs):

        if not self.invoice_number:

            date_str = now().strftime("%Y%m%d")
            business_code = self.get_business_code()

            today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)

            last_invoice = Sale.objects.filter(
                business=self.business,
                created_at__gte=today_start
            ).order_by("-id").first()

            seq = 1

            if last_invoice and last_invoice.invoice_number:
                try:
                    seq = int(last_invoice.invoice_number.split("-")[-1]) + 1
                except:
                    seq = 1

            self.invoice_number = f"INV-{business_code}-{date_str}-{seq:04d}"

        if not self.receipt_number:
            timestamp = now().strftime("%Y%m%d%H%M%S")
            self.receipt_number = f"RCPT-{timestamp}"

        super().save(*args, **kwargs)

    # =========================
    # PROPERTIES
    # =========================
    @property
    def total_items(self):
        return sum(
            i.remaining_quantity
            for i in self.items.all()
        )

    @property
    def total_profit(self):

        total = 0

        for item in self.items.all():

            remaining_qty = (
                    item.quantity -
                    item.refunded_quantity
            )

            if remaining_qty <= 0:
                continue

            total += (
                    (item.price - item.cost_price)
                    * remaining_qty
            )

        return total

    @property
    def can_refund(self):
        if self.status == 'Refunded':
            return False

        refund_window = now() - timedelta(hours=24)
        return self.created_at >= refund_window

    def __str__(self):
        return str(self.receipt_number)


class SaleItem(models.Model):

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='items'
    )

    product = models.ForeignKey(
        Inventory,
        on_delete=models.CASCADE
    )

    quantity = models.PositiveIntegerField(
        default=1
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    profit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    refunded_quantity = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True,
        blank=True
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        null=True,
        blank=True
    )

    class Meta:

        ordering = ['-id']

        verbose_name = 'Sale Item'

        verbose_name_plural = 'Sale Items'

    def save(self, *args, **kwargs):

        # =========================
        # AUTO CALCULATE TOTAL
        # =========================
        self.total = (
            self.price *
            self.quantity
        )

        # =========================
        # AUTO CALCULATE PROFIT
        # =========================
        self.profit = (
            (
                self.price -
                self.cost_price
            ) * self.quantity
        )

        super().save(*args, **kwargs)

    def __str__(self):

        return (
            f"{self.product.product_name}"
            f" x {self.quantity}"
        )

    @property
    def remaining_quantity(self):
        return max(
            0,
            self.quantity - self.refunded_quantity
        )

    @property
    def remaining_total(self):
        return (
                self.remaining_quantity *
                self.price
        )

    @property
    def remaining_profit(self):
        return (
                (self.price - self.cost_price)
                * self.remaining_quantity
        )

    @property
    def is_fully_refunded(self):
        return self.remaining_quantity <= 0

    @property
    def can_refund(self):
        return self.remaining_quantity > 0


class SalesMetric(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)

    daily_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    weekly_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monthly_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ('business', 'date')


class Refund(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)


class RefundItem(models.Model):
    refund = models.ForeignKey(Refund, related_name='items', on_delete=models.CASCADE)
    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE)

    quantity = models.PositiveIntegerField()

    unit_price = models.DecimalField(max_digits=12, decimal_places=2)



