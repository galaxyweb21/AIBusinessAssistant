from django.urls import path
from dashboard import views as views
from . import views
from .views import InventoryModalAPIView
from dashboard.views import AIChatAPIView

urlpatterns = [
    path('dashboard/', views.DashboardAPIView.as_view(), name='dashboard-api'),
    path('index/', views.index, name='index'),
    path('sales-chart/', views.SalesChartAPIView.as_view(), name='sales-chart'),
    path('top-products/', views.TopProductsAPIView.as_view(), name='top-products'),
    path('ai-insights/', views.AIInsightsAPIView.as_view(), name='ai-insights'),
    path('profit-analytics/', views.ProfitAnalyticsAPIView.as_view(), name='profit-analytics'),
    # path('ai-chat/', views.AIChatAPIView, name='ai-chat'),
    path('ai-chat/', AIChatAPIView.as_view(), name='ai-chat'),
    path('ai-chat-history/', views.AIChatHistoryAPIView.as_view(), name='ai-chat-history'),
    path('business-alerts/', views.BusinessAlertsAPIView.as_view(), name='business-alerts'),
    path('ai-insight/<int:pk>/read/', views.mark_ai_read, name='mark_ai_read'),

    path('sales-forecast/', views.SalesForecastAPIView.as_view()),
    path('inventory-forecast/', views.InventoryForecastAPIView.as_view()),
    path('business-risks/', views.BusinessRiskAPIView.as_view()),
    path('inventory-modal/', views.InventoryModalAPIView.as_view(), name='inventory-modal'),

]