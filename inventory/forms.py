from django import forms
from .models import *
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.forms import UserCreationForm
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from django.contrib.auth.forms import UserChangeForm


class DateInput(forms.DateInput):
    input_type = 'date'


class TimeInput(forms.TimeInput):
    input_type = 'time'


class BootstrapStylesMixin:
    form_fields = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.form_fields:
            for fieldname in self.form_fields:
                self.fields[fieldname].widget.attrs = {'class': 'form-control'}
        else:
            raise ValueError('The form_field should be set')


class InventoryForm(forms.ModelForm):

    class Meta:
        model = Inventory
        fields = [
            # General
            "category",
            "product_name",
            "brand",
            "description",
            # Identification
            "sku",
            "barcode",
            "qr_code",
            "unit",
            # Prices
            "cost_price",
            "selling_price",
            # Inventory
            "stock_quantity",
            "minimum_stock",
            "maximum_stock",
            "reorder_level",
            "reorder_quantity",
            # Media
            "product_image",
            # Options
            "featured",
            "track_stock",
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "status": forms.Select(),
            "unit": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)

        placeholders = {
            "product_name": "Product name",
            "brand": "Brand",
            "sku": "Auto generated",
            "barcode": "Scan or enter barcode",
            "cost_price": "0.00",
            "selling_price": "0.00",
            "stock_quantity": "0",
            "minimum_stock": "5",
            "maximum_stock": "100",
            "reorder_level": "10",
            "reorder_quantity": "50",
        }

        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-control")

            if name in placeholders:
                field.widget.attrs["placeholder"] = placeholders[name]

        self.fields["sku"].help_text = "Leave blank to generate automatically."

        if business:
            self.fields["category"].queryset = (
                Category.objects.filter(business=business, is_active=True)
                .order_by("name")
            )
            self.fields["category"].empty_label = "Choose category"

        if self.instance.pk:
            self.fields["barcode"].widget.attrs["readonly"] = True
            self.fields["qr_code"].widget.attrs["readonly"] = True

    @property
    def sections(self):
        return {
            "general": ["category", "product_name", "brand", "description"],
            "identity": ["sku", "barcode", "qr_code", "unit"],
            "pricing": ["cost_price", "selling_price"],
            "inventory": [
                "stock_quantity",
                "minimum_stock",
                "maximum_stock",
                "reorder_level",
                "reorder_quantity",
            ],
            "media": ["product_image"],
            "options": ["featured", "track_stock", "status"],
        }


class UpdateInventoryForm(forms.ModelForm):

    class Meta:
        model = Inventory
        fields = [
            "product_name", "category", "brand", "sku", "barcode", "unit", "description", "cost_price",
            "selling_price", "minimum_stock", "maximum_stock", "reorder_level", "reorder_quantity",
            "track_stock", "featured", "status", "product_image",
        ]

    def clean_product_name(self):
        product_name = self.cleaned_data.get('product_name')

        if not product_name:
            raise forms.ValidationError('This field is required')

        return product_name

    def clean_cost_price(self):
        cost_price = self.cleaned_data.get('cost_price')

        if not cost_price:
            raise forms.ValidationError('This field is required')

        return cost_price

    def clean_selling_price(self):
        selling_price = self.cleaned_data.get('selling_price')

        if not selling_price:
            raise forms.ValidationError('This field is required')

        return selling_price

    def __init__(self, *args, **kwargs):

        business = kwargs.pop("business", None)

        super().__init__(*args, **kwargs)

        if business:
            self.fields["category"].queryset = (
                Category.objects.filter(
                    business=business,
                    is_active=True
                )
                    .order_by("name")
            )


class SupplierForm(forms.ModelForm):

    class Meta:
        model = Supplier
        fields = [
            "name", "phone", "email", "address", "country",
            "payment_terms", "credit_limit", "rating",
            "is_active", "notes",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "payment_terms": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)

        placeholders = {
            "name": "Supplier name",
            "phone": "e.g. 024 123 4567",
            "email": "supplier@example.com",
            "address": "Street, city, region",
            "country": "e.g. Ghana",
            "credit_limit": "0.00",
        }

        for field_name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-control")
            if field_name in placeholders:
                field.widget.attrs["placeholder"] = placeholders[field_name]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if self.business:
            duplicate = Supplier.objects.filter(
                business=self.business,
                name__iexact=name,
            )
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)

            if duplicate.exists():
                raise forms.ValidationError(
                    f'A supplier named "{name}" already exists.'
                )

        return name


class RestockForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity to Add",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "e.g. 50",
            "autofocus": True,
        }),
    )
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.none(),
        required=False,
        label="Supplier (optional)",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    invoice_number = forms.CharField(
        required=False,
        max_length=80,
        label="Invoice / Reference No. (optional)",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "e.g. INV-2031",
        }),
    )
    purchase_cost = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label="Unit Cost (optional)",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0.00",
            "step": "0.01",
        }),
    )
    note = forms.CharField(
        required=False,
        label="Note (optional)",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "e.g. Received from supplier delivery #4521",
        }),
    )

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        # Scope the supplier dropdown to this business only — without this,
        # every business's suppliers would appear as options.
        if business:
            self.fields["supplier"].queryset = Supplier.objects.filter(
                business=business, is_active=True
            ).order_by("name")


class DamageForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity Damaged",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "e.g. 5",
            "autofocus": True,
        }),
    )
    note = forms.CharField(
        required=False,
        label="Reason / Note (optional)",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "e.g. Water damage during storage",
        }),
    )

    def __init__(self, *args, **kwargs):
        self.item = kwargs.pop("item", None)
        super().__init__(*args, **kwargs)

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if self.item and quantity > self.item.stock_quantity:
            raise forms.ValidationError(
                f"Only {self.item.stock_quantity} unit(s) currently in stock — "
                f"cannot mark {quantity} as damaged."
            )
        return quantity


class SupplierPaymentForm(forms.Form):
    amount_paid = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount Paid",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0.00",
            "step": "0.01",
        }),
    )
    payment_method = forms.ChoiceField(
        choices=[
            ("cash", "Cash"),
            ("bank", "Bank Transfer"),
            ("mobile_money", "Mobile Money"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    external_reference = forms.CharField(
        required=False,
        max_length=50,
        label="Bank / MoMo Reference (optional)",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "e.g. transaction ID",
        }),
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        self.purchase = kwargs.pop("purchase", None)
        super().__init__(*args, **kwargs)

    def clean_amount_paid(self):
        amount = self.cleaned_data["amount_paid"]
        if self.purchase and amount > self.purchase.balance:
            raise forms.ValidationError(
                f"Payment exceeds remaining balance of Gh¢{self.purchase.balance}."
            )
        return amount