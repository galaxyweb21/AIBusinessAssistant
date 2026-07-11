from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, reverse_lazy, include
from inventory import views as views
from . import views

# from user.forms import UserPasswordChangeForm

# from user import UsersViews

urlpatterns = [
    path('inventory/', views.inventory, name="inventory"),
    path('update_inventory/<str:pk>/', views.update_inventory, name="update_inventory"),
    path('delete_inventory/<str:pk>/', views.delete_inventory, name="delete_inventory"),
    path('view_inventory/', views.view_inventory, name="view_inventory"),
    path('restock_inventory/<int:pk>/', views.restock_inventory, name='restock_inventory'),
    path('damaged_inventory/<int:pk>/', views.damaged_inventory, name='damaged_inventory'),
    path('inventory-history/', views.inventory_history, name='inventory_history'),

    path("supplier_list/", views.supplier_list, name="supplier_list"),
    path('suppliers/<int:pk>/', views.supplier_detail, name='supplier_detail'),
    path("create_supplier/", views.create_supplier, name="create_supplier"),
    path("suppliers/<int:pk>/update/", views.update_supplier, name="update_supplier"),
    path("suppliers/<int:pk>/delete/", views.delete_supplier, name="delete_supplier"),
    path("purchase/<int:purchase_id>/supplier-payment/", views.supplier_payment, name="supplier_payment"),
    path("supplier/payments/history/", views.supplier_payment_history, name="supplier_payment_history"),

    # PURCHASE CORE
    path("purchases/create/", views.create_purchase, name="create_purchase"),
    path("purchases/<int:pk>/", views.view_purchase, name="view_purchase"),
    path("purchases/<int:pk>/post/", views.post_purchase, name="post_purchase"),

]