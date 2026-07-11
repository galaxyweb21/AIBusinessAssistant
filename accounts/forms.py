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


class LoginForm(forms.ModelForm):
    # export_to_CSV = forms.BooleanField(required=False)
    # medicine = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['username', 'password']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username:
            raise forms.ValidationError('This field is required')

        return username

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not password:
            raise forms.ValidationError('This field is required')

        return password


class ProfileForm(forms.ModelForm):

    class Meta:
        model = StaffProfile
        fields = ['address', 'contact']

        widgets = {

            'address': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Address'
            }),

            'contact': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Phone Number'
            }),
        }

    def clean_address(self):
        address = self.cleaned_data.get('address')

        if not address:
            raise forms.ValidationError('This field is required')

        return address

    def clean_contact(self):
        contact = self.cleaned_data.get('contact')

        if not contact:
            raise forms.ValidationError('This field is required')

        return contact


class CreateUserForm(UserCreationForm):

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control auth-input',
            'placeholder': 'Email Address'
        })
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'password1',
            'password2'
        ]

        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Username'
            }),

            'first_name': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'First Name'
            }),

            'last_name': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Last Name'
            }),
        }

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control auth-input',
            'placeholder': 'Password'
        })
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control auth-input',
            'placeholder': 'Confirm Password'
        })
    )

    # VALIDATIONS
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username:
            raise forms.ValidationError('This field is required')
        return username

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name')
        if not first_name:
            raise forms.ValidationError('This field is required')
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name')
        if not last_name:
            raise forms.ValidationError('This field is required')
        return last_name

    def clean_email(self):
        email = self.cleaned_data.get('email')

        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                f'{email} already exists'
            )

        return email


class UpdateUserForm(UserChangeForm):

    password = None

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email'
        ]


class StaffProfileForm(forms.ModelForm):

    class Meta:
        model = StaffProfile
        fields = ['address', 'contact', 'role_type']

        widgets = {

            'address': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Address'
            }),

            'contact': forms.TextInput(attrs={
                'class': 'form-control auth-input',
                'placeholder': 'Phone Number'
            }),
            'role_type': forms.Select(attrs={
                'class': 'form-control auth-input'
            }),
        }

    def clean_address(self):
        address = self.cleaned_data.get('address')

        if not address:
            raise forms.ValidationError('This field is required')

        return address

    def clean_contact(self):
        contact = self.cleaned_data.get('contact')

        if not contact:
            raise forms.ValidationError('This field is required')

        return contact

    def clean_role_type(self):
        role_type = self.cleaned_data.get('role_type')

        if not role_type:
            raise forms.ValidationError('This field is required')

        return role_type

class UserPasswordChangeForm(BootstrapStylesMixin, PasswordChangeForm):
    form_fields = ['old_password', 'new_password1', 'new_password2']
