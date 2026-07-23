from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, reverse_lazy, include
from inventory import views as views
from . import views

urlpatterns = [
    path('category_create', views.category_create, name='category_create'),
    path('category_list/', views.category_list, name='category_list'),
    path("categories/reorder/", views.reorder_categories, name="reorder_categories"),
    path("categories/<int:pk>/edit/", views.edit_category, name="edit_category"),
    path("categories/<int:pk>/delete/", views.delete_category, name="delete_category"),
]