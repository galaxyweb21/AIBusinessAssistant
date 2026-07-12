"""
URL configuration for AIBusinessAssistant project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, reverse_lazy, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from accounts.forms import UserPasswordChangeForm

from django.http import HttpResponse

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('dashboard.urls')),
    path('accounts/', include('accounts.urls')),
    path('business/', include('business.urls')),
    path('inventory/', include('inventory.urls')),
    path('sales/', include('sales.urls')),

    path('', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='user-login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='accounts/logout.html'), name='user-logout'),
    path('change_password/', PasswordChangeView.as_view(template_name='accounts/change_password.html',
                                                        success_url=reverse_lazy('password_change_done'),
                                                        form_class=UserPasswordChangeForm
                                                        ), name='change_password'),
    path('change_password/done/',
         PasswordChangeDoneView.as_view(template_name='accounts/password_change_done.html'
                                        ), name='password_change_done'),
    path('password_reset/',
         auth_views.PasswordResetView.as_view(template_name='accounts/password_reset.html'),
         name='password_reset'),
    path('password_reset_done/',
         auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'),
         name='password_reset_done'),
    path('password_reset_confirm/<uidb64>/<token>',
         auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('password_reset_complete/',
         auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'),
         name='password_reset_complete'),


]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
