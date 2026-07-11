from rest_framework import serializers

class DashboardSerializer(serializers.Serializer):
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_profit = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_sales = serializers.IntegerField()
    best_product = serializers.CharField()
    low_stock_count = serializers.IntegerField()