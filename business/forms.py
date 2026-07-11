from django import forms
from .models import *
from django.contrib.auth.models import User
from datetime import date, datetime
from dateutil.relativedelta import relativedelta


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


class BusinessForm(forms.ModelForm):

    class Meta:
        model = Business
        fields = ['name', 'description', 'business_type', 'logo']

        widgets = {

            'name': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Business Name'
            }),

            'description': forms.Textarea(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Business Description',
                'rows': 5
            }),

            'business_type': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Business Type',
            }),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')

        if not name:
            raise forms.ValidationError('This field is required')

        # CHECK IF ANOTHER BUSINESS ALREADY USES THIS NAME
        existing_business = Business.objects.filter(
            name__iexact=name
        ).exclude(id=self.instance.id).first()

        if existing_business:
            raise forms.ValidationError(
                f'Sorry "{name}" already exists.'
            )

        return name

    def clean_description(self):
        description = self.cleaned_data.get('description')

        if not description:
            raise forms.ValidationError('This field is required')

        return description

    def clean_business_type(self):
        business_type = self.cleaned_data.get('business_type')

        if not business_type:
            raise forms.ValidationError('This field is required')

        return business_type
