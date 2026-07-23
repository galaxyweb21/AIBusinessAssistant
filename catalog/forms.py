from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from django import forms
from .models import Category


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


class CategoryForm(forms.ModelForm):

    class Meta:
        model = Category
        fields = ("name", "description", "icon", "color", "image", "sort_order", "is_active",)

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Category name"
            }),

            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Description..."
            }),

            "icon": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "fas fa-box"
            }),

            "color": forms.TextInput(attrs={
                "class": "form-control form-control-color",
                "type": "color"
            }),

            "image": forms.ClearableFileInput(attrs={
                "class": "form-control"
            }),

            "sort_order": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0
            }),

            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
        }
