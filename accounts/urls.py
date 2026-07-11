from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, reverse_lazy, include
from accounts import views as views
from . import views

# from user.forms import UserPasswordChangeForm

# from user import UsersViews

urlpatterns = [
    path('index/', views.index, name="index"),
    path('register_business/', views.register_business, name="register_business"),
    path('business_profile/', views.business_profile, name="business_profile"),
    path('register_staff/', views.register_staff, name="register_staff"),
    path("staff/list/", views.staff_list_view, name="staff_list"),
    path('staff/update/<int:staff_id>/', views.update_staff, name='update_staff'),
    path('staff/delete/<int:staff_id>/', views.delete_staff, name='delete_staff'),
    path('staff/deactivate/<int:staff_id>/', views.deactivate_staff, name='deactivate_staff'),
    path("staff/reactivate/<int:staff_id>/", views.reactivate_staff, name="reactivate_staff"),
    path('staff_profile/', views.staff_profile, name="staff_profile"),

]