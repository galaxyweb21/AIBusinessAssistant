from inventory.models import Inventory
from django import forms
from .models import *


class SaleForm(forms.ModelForm):

    class Meta:

        model = Sale

        fields = [
            'customer',
            'payment_method',
            'tax',
            'discount'
        ]

        widgets = {

            'customer': forms.Select(attrs={
                'class': 'form-control sales-input'
            }),

            'payment_method': forms.Select(attrs={
                'class': 'form-control sales-input'
            }),

            'tax': forms.Select(attrs={
                'class': 'form-control sales-input'
            }),

            'discount': forms.Select(attrs={
                'class': 'form-control sales-input'
            }),

        }


class TaxForm(forms.ModelForm):

    class Meta:

        model = Tax

        fields = ['name', 'tax_percentage', 'active']


class DiscountForm(forms.ModelForm):

    class Meta:
        model = Discount
        fields = [
            'name',
            'percentage',
            'start_date',
            'end_date',
            'active',
        ]

        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Christmas Sale'
            }),

            'percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),

            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),

            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),

            'active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }