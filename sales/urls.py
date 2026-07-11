from django.urls import path
from . import views

urlpatterns = [

    path('sales/', views.sales, name='sales'),
    path('view_sales/', views.view_sales, name='view_sales'),
    path('update_sales/<int:pk>/', views.update_sales, name='update_sales'),
    path('refund_sale/<int:pk>/', views.refund_sale, name='refund_sale'),
    path('check-customer/', views.check_or_create_customer, name='check_or_create_customer'),
    path('receipt/<int:pk>/', views.pos_receipt, name='pos_receipt'),
    path('proforma/<int:pk>/', views.proforma_invoice, name='proforma_invoice'),
    path('customers/', views.customers, name='customers'),
    path('customers/update/<int:pk>/', views.update_customer, name='update_customer'),
    path('customers/delete/<int:pk>/', views.delete_customer, name='delete_customer'),
    path('customers_purchase/<int:pk>/', views.customers_purchase, name='customers_purchase'),
    path('sale-detail/<int:pk>/', views.sale_detail_api, name='sale-detail-api'),
    path('sales/sale-pdf/<int:sale_id>/', views.sale_pdf_view, name='sale_pdf'),
    path('sales/export/pdf/', views.sales_report_pdf, name='sales_report_pdf'),
    path("barcode-lookup/", views.barcode_lookup, name="barcode_lookup"),
    path('tax/', views.tax, name='tax'),
    path('tax/update/<int:pk>/', views.update_tax, name='update_tax'),
    path('tax/delete/<int:pk>/', views.delete_tax, name='delete_tax'),
    path("tax_list/", views.tax_list, name="tax_list"),
    path('discounts/', views.discount_list, name='discount_list'),
    path('discount/add/', views.discount, name='discount'),
    path('discount/<int:pk>/update/', views.update_discount, name='update_discount'),
    path('discount/<int:pk>/delete/', views.delete_discount, name='delete_discount'),

]