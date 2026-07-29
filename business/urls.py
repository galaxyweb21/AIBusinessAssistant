from django.urls import path
from .views import *
from business import views as views

urlpatterns = [
    # path('dashboard/', DashboardAPIView.as_view(), name='dashboard-api'),
    path("api/sidebar-counts/", views.sidebar_counts_api, name="sidebar_counts_api"),

]