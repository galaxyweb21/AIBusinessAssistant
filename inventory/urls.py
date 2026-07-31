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
    path('inventory/<int:pk>/update/', views.update_inventory, name="update_inventory"),
    # path('update_inventory/<str:pk>/', views.update_inventory, name="update_inventory"),
    # path('delete_inventory/<str:pk>/', views.delete_inventory, name="delete_inventory"),

    path('inventory/<int:pk>/delete/', views.delete_inventory, name="delete_inventory"),
    path('view_inventory/', views.view_inventory, name="view_inventory"),
    path('restock_inventory/<int:pk>/', views.restock_inventory, name='restock_inventory'),
    path('damaged_inventory/<int:pk>/', views.damaged_inventory, name='damaged_inventory'),
    path('inventory-history/', views.inventory_history, name='inventory_history'),
    path("inventory/history/export/csv/", views.export_inventory_history_csv, name="export_inventory_history_csv"),
    path("inventory/history/export/pdf/", views.export_inventory_history_pdf, name="export_inventory_history_pdf",),

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

    path("purchases/", views.purchase_list, name="purchase_list"),

    path("purchase-orders/", views.purchase_order_list, name="purchase_order_list"),
    path("purchase-orders/create/", views.create_purchase_order, name="create_purchase_order"),
    path("purchase-orders/<int:pk>/", views.view_purchase_order, name="view_purchase_order"),

    # Goods Receipts (GRN)
    path("goods-receipts/", views.goods_receipt_list, name="goods_receipt_list"),
    path("goods-receipts/create/", views.create_goods_receipt, name="create_goods_receipt"),
    # create GRN from PO
    path("purchase-orders/<int:po_pk>/receive/", views.create_goods_receipt, name="receive_purchase_order"),
    path("goods-receipts/<int:pk>/", views.view_goods_receipt, name="view_goods_receipt"),

# Add these URL patterns
    path('procurement/pending-count/', views.pending_po_count_api, name='pending_po_count_api'),
    path('inventory/low-stock-count/', views.low_stock_count_api, name='low_stock_count_api'),


    path("generate-sku/", views.generate_sku, name="generate_sku"),
    path("generate-barcode/", views.generate_barcode, name="generate_barcode"),
    path("generate-qr/", views.generate_qr, name="generate_qr"),

    path("inventory/expiry/", views.expiry_dashboard, name="expiry_dashboard"),
    path("inventory/expiry/add/", views.add_batch, name="add_batch"),
    path("inventory/expiry/<int:pk>/dispose/", views.dispose_batch, name="dispose_batch"),
    path("inventory/expiry/export/csv/", views.export_expiry_csv, name="export_expiry_csv"),

    path("inventory/<int:pk>/intelligence/", views.product_intelligence, name="product_intelligence"),

    path("select/", views.label_select, name="select"),
    path("print/", views.label_print, name="print"),
    path("templates/", views.template_list, name="template_list"),
    path("templates/add/", views.template_create, name="template_create"),
    path("templates/<int:pk>/edit/", views.template_edit, name="template_edit"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),

    # Warehouses
    path("warehouses/", views.warehouse_list, name="warehouse_list"),
    path("warehouses/add/", views.warehouse_create, name="warehouse_create"),
    path("warehouses/<int:pk>/edit/", views.warehouse_edit, name="warehouse_edit"),
    path("warehouses/<int:pk>/delete/", views.warehouse_delete, name="warehouse_delete"),

    # Per-product warehouse stock breakdown
    path("products/<int:product_id>/warehouse-stock/", views.product_warehouse_stock, name="product_warehouse_stock",),

    # Stock transfers
    path("transfers/", views.transfer_list, name="transfer_list"),
    path("transfers/new/", views.transfer_create, name="transfer_create"),
    path("transfers/<int:pk>/", views.transfer_detail, name="transfer_detail"),
    path("transfers/<int:pk>/dispatch/", views.transfer_dispatch, name="transfer_dispatch"),
    path("transfers/<int:pk>/receive/", views.transfer_receive, name="transfer_receive"),
    path("transfers/<int:pk>/cancel/", views.transfer_cancel, name="transfer_cancel"),


    path("purchase-orders/<int:po_pk>/receive/", views.create_goods_receipt, name="receive_purchase_order"),

]