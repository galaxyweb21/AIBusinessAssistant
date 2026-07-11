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
        fields = ['product_name', 'stock_quantity', 'cost_price', 'selling_price', 'image']

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


class UpdateInventoryForm(forms.ModelForm):

    class Meta:
        model = Inventory
        fields = ['product_name', 'cost_price', 'selling_price', 'image']

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


class SupplierForm(forms.ModelForm):

    class Meta:
        model = Supplier
        fields = [
            "name",
            "phone",
            "email",
            "address",
            "country",
            "payment_terms",
            "credit_limit",
            "is_active",
        ]
