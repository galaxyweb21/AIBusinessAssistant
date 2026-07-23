from django.db import models
from business.models import Business
from catalog.models import Category
from django.conf import settings

from django.utils import timezone
from decimal import Decimal
from django.db import transaction
from django.contrib.auth.models import User
import uuid
from django.utils.text import slugify


MOVEMENT_TYPES = (

    ("opening", "Opening Stock"),

    ("purchase", "Purchase"),

    ("sale", "Sale"),

    ("return", "Sales Return"),

    ("supplier_return", "Supplier Return"),

    ("restock", "Restock"),

    ("adjustment", "Stock Adjustment"),

    ("damage", "Damaged"),

    ("expired", "Expired"),

    ("transfer_in", "Transfer In"),

    ("transfer_out", "Transfer Out"),

    ("production", "Production"),

)

DIRECTION = (

    ("IN","Stock In"),

    ("OUT","Stock Out"),

)

UNIT_CHOICES = (
    ("pcs", "Pieces"),
    ("box", "Box"),
    ("pack", "Pack"),
    ("kg", "Kilogram"),
    ("g", "Gram"),
    ("ltr", "Litre"),
    ("ml", "Millilitre"),
    ("carton", "Carton"),
    ("bag", "Bag"),
    ("roll", "Roll"),
)

STATUS_CHOICES = (
    ("active", "Active"),
    ("inactive", "Inactive"),
)


class Inventory(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    product_name = models.CharField(max_length=50)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    stock_quantity = models.IntegerField(default=0)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)

    # ==========================================
    # PRODUCT MASTER
    # ==========================================
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    barcode = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    qr_code = models.CharField(max_length=120, blank=True, null=True)
    brand = models.CharField(max_length=120, blank=True)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default="pcs")
    description = models.TextField(blank=True)
    minimum_stock = models.PositiveIntegerField(default=0)
    maximum_stock = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=0)
    reorder_quantity = models.PositiveIntegerField(default=0)
    track_stock = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    product_image = models.ImageField(upload_to="product/", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f"SKU-{uuid.uuid4().hex[:8].upper()}"

        if not self.barcode:
            self.barcode = self.sku.replace("SKU-", "")

        if not self.qr_code:
            self.qr_code = self.barcode

        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.minimum_stock

    @property
    def is_out_of_stock(self):
        return self.stock_quantity <= 0

    @property
    def profit(self):
        return self.selling_price - self.cost_price

    @property
    def stock_value(self):
        return self.stock_quantity * self.cost_price

    @property
    def retail_value(self):
        return self.stock_quantity * self.selling_price

    def __str__(self):
        return f"{self.product_name} ({self.sku})"


class Supplier(models.Model):

    business = models.ForeignKey('business.Business', on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    country = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    # =========================
    # FINANCIAL (ERP CORE)
    # =========================
    total_purchases = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    total_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    # =========================
    # OPERATIONAL METRICS
    # =========================
    total_items_supplied = models.PositiveIntegerField(default=0)

    last_supply_date = models.DateTimeField(blank=True, null=True)

    payment_terms = models.CharField(
        max_length=50,
        choices=[
            ("cash", "Cash"),
            ("credit", "Credit"),
            ("30_days", "30 Days"),
            ("60_days", "60 Days"),
        ],
        default="cash"
    )

    rating = models.PositiveSmallIntegerField(default=0)

    # =========================
    # SYSTEM FIELDS
    # =========================
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("business", "name")

    def __str__(self):
        return self.name

    # =========================
    # BUSINESS LOGIC HELPERS
    # =========================
    @property
    def balance_due(self):
        return self.total_purchases - self.total_paid

    @property
    def is_over_credit_limit(self):
        return self.balance_due > self.credit_limit


class InventoryStockHistory(models.Model):

    ACTION_CHOICES = [
        ("restock", "Restock"),
        ("sale", "Sale Deduction"),
        ("adjustment", "Manual Adjustment"),
        ('damaged', 'Damaged'),
        ('returned', 'Returned'),
        ('transfer', 'Transfer'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    inventory = models.ForeignKey(
        Inventory,
        on_delete=models.CASCADE,
        related_name="history"
    )

    previous_stock = models.IntegerField()
    quantity = models.IntegerField()
    new_stock = models.IntegerField()

    action_type = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES
    )
    reference_number = models.TextField(blank=True, null=True)

    # =====================================================
    # ENTERPRISE RECEIVING INFORMATION
    # =====================================================

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restocks"
    )

    invoice_number = models.CharField(
        max_length=80,
        blank=True
    )

    purchase_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    warehouse = models.CharField(
        max_length=120,
        blank=True
    )

    reference = models.CharField(
        max_length=120,
        blank=True
    )

    received_date = models.DateField(
        null=True,
        blank=True
    )

    received_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    remarks = models.TextField(
        blank=True
    )

    note = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.inventory.product_name} - {self.action_type}"

    @property
    def total_cost(self):
        return self.purchase_cost * self.quantity

    @property
    def supplier_name(self):
        if self.supplier:
            return self.supplier.name
        return "-"

    @property
    def received_by_name(self):
        if self.received_by:
            return self.received_by.get_full_name() or self.received_by.username
        return "-"

    def __str__(self):
        return (
            f"{self.inventory.product_name} "
            f"(+{self.quantity}) "
            f"- {self.created_at:%d %b %Y}"
        )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Inventory Restock"
        verbose_name_plural = "Inventory Restocks"


class Purchase(models.Model):

    business = models.ForeignKey(
        'business.Business',
        on_delete=models.CASCADE
    )

    supplier = models.ForeignKey(
        'Supplier',
        on_delete=models.CASCADE
    )

    reference_number = models.CharField(
        max_length=50,
        unique=True
    )

    # =========================
    # FINANCIALS
    # =========================

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    purchase_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    purchase_tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    payment_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("partial", "Partial"),
            ("paid", "Paid"),
        ],
        default="pending"
    )

    # =========================
    # PURCHASE WORKFLOW
    # =========================

    status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("pending", "Pending"),
            ("received", "Received"),
            ("cancelled", "Cancelled")
        ],
        default="draft"
    )

    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.reference_number

    @property
    def balance(self):

        balance = (
                self.total_cost -
                self.paid_amount
        )

        return max(
            balance,
            Decimal("0.00")
        )

    @property
    def amount_due(self):

        return self.balance

    @property
    def payment_percentage(self):

        if self.total_cost <= 0:
            return Decimal("0")

        return round(
            (
                    self.paid_amount /
                    self.total_cost
            ) * 100,
            2
        )

    from decimal import Decimal

    from decimal import Decimal

    def calculate_totals(
            self,
            purchase_discount=None,
            purchase_tax=None
    ):

        subtotal = Decimal("0.00")

        for item in self.items.all():
            subtotal += (
                    item.total_cost or Decimal("0.00")
            )

        # Use provided values or existing values
        if purchase_discount is None:
            purchase_discount = (
                    self.purchase_discount or Decimal("0.00")
            )

        if purchase_tax is None:
            purchase_tax = (
                    self.purchase_tax_percent or Decimal("0.00")
            )

        purchase_discount = Decimal(
            str(purchase_discount)
        )

        purchase_tax = Decimal(
            str(purchase_tax)
        )

        # Prevent discount exceeding subtotal
        if purchase_discount > subtotal:
            purchase_discount = subtotal

        taxable_amount = (
                subtotal - purchase_discount
        )

        tax_amount = (
                taxable_amount *
                purchase_tax /
                Decimal("100")
        )

        grand_total = (
                taxable_amount +
                tax_amount
        )

        self.subtotal = subtotal
        self.purchase_discount = purchase_discount
        self.purchase_tax_percent = purchase_tax
        self.total_cost = grand_total

        self.save(
            update_fields=[
                "subtotal",
                "purchase_discount",
                "purchase_tax_percent",
                "total_cost",
            ]
        )

        return grand_total

    def post_purchase(self, user=None):

        with transaction.atomic():

            for item in self.items.all():

                inventory = item.product

                previous_stock = inventory.stock_quantity
                new_stock = previous_stock + item.quantity

                inventory.stock_quantity = new_stock
                inventory.save()

                InventoryStockHistory.objects.create(
                    business=self.business,
                    inventory=inventory,
                    previous_stock=previous_stock,
                    quantity_changed=item.quantity,
                    new_stock=new_stock,
                    action_type="restock",
                    performed_by=user,
                    reference_number=self.reference_number,
                    note=f"Purchase received: {self.reference_number}"
                )

            self.status = "received"
            self.save(update_fields=["status"])

            supplier = self.supplier

            supplier.total_purchases += (
                self.total_cost or Decimal("0.00")
            )

            supplier.total_items_supplied += sum(
                i.quantity
                for i in self.items.all()
            )

            supplier.last_supply_date = timezone.now()

            supplier.save()


class PurchaseItem(models.Model):

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items", null=True)
    product = models.ForeignKey('Inventory', on_delete=models.CASCADE, null=True)
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):

        qty = Decimal(str(self.quantity))
        unit_cost = Decimal(str(self.unit_cost))
        discount = Decimal(str(self.discount or 0))
        tax_percent = Decimal(str(self.tax_percent or 0))

        # subtotal
        subtotal = qty * unit_cost

        # prevent negative values
        if discount > subtotal:
            discount = subtotal

        after_discount = subtotal - discount

        tax_amount = (
            after_discount *
            (tax_percent / Decimal("100"))
        )

        self.total_cost = (
            after_discount +
            tax_amount
        )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.product_name}"


class SupplierPayment(models.Model):

    supplier = models.ForeignKey(
        'Supplier',
        on_delete=models.CASCADE
    )

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payments"
    )

    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    payment_method = models.CharField(
        max_length=20,
        choices=[
            ("cash", "Cash"),
            ("bank", "Bank Transfer"),
            ("mobile_money", "Mobile Money"),
        ]
    )

    # Auto-generated system payment number
    reference = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True
    )

    # Optional user-entered bank/MoMo transaction ID
    external_reference = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    note = models.TextField(
        blank=True,
        null=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def generate_reference(self):

        today = timezone.now().strftime(
            "%Y%m%d"
        )

        last_payment = SupplierPayment.objects.filter(
            reference__startswith=f"SP-{today}"
        ).order_by(
            "-id"
        ).first()

        if last_payment:

            try:

                last_no = int(
                    last_payment.reference.split("-")[-1]
                )

            except:

                last_no = 0

        else:

            last_no = 0

        next_no = str(
            last_no + 1
        ).zfill(5)

        return f"SP-{today}-{next_no}"

    def save(self,*args,**kwargs):

        is_new = self.pk is None

        # Generate payment reference automatically
        if not self.reference:

            self.reference = (
                self.generate_reference()
            )

        super().save(*args,**kwargs)

        if is_new and self.purchase:

            purchase = self.purchase

            purchase.paid_amount += (
                self.amount_paid
            )

            # Prevent overpayment

            if purchase.paid_amount > purchase.total_cost:

                purchase.paid_amount = (
                    purchase.total_cost
                )


            if purchase.paid_amount <= 0:

                purchase.payment_status = (
                    "pending"
                )

            elif purchase.paid_amount >= purchase.total_cost:

                purchase.payment_status = (
                    "paid"
                )

            else:

                purchase.payment_status = (
                    "partial"
                )

            purchase.save(
                update_fields=[
                    "paid_amount",
                    "payment_status"
                ]
            )

    def __str__(self):

        return self.reference


class InventoryMovement(models.Model):

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="inventory_movements"
    )

    product = models.ForeignKey(
        Inventory,
        on_delete=models.CASCADE,
        related_name="movements"
    )

    movement_type = models.CharField(
        max_length=20,
        choices=MOVEMENT_TYPES
    )

    quantity = models.PositiveIntegerField()

    before_quantity = models.PositiveIntegerField(default=0)

    after_quantity = models.PositiveIntegerField(default=0)

    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    total_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00")
    )

    reference = models.CharField(
        max_length=100,
        blank=True
    )

    notes = models.TextField(
        blank=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product} - {self.movement_type}"