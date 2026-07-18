from django.contrib.auth.decorators import login_required
# from django.db.models import (
#     Sum,
#     F,
#     DecimalField,
#     ExpressionWrapper,
# )
from django.shortcuts import get_object_or_404, render

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .utils import *
from accounts.models import StaffProfile
from dashboard.services.forecasting import *

from sales.utils import update_business_metrics

from dashboard.models import BusinessAlert
from dashboard.services.alerts import generate_business_alerts
from dashboard.services.ai.ai import analyze_with_ai


def get_user_business(user):

    # OWNER ACCOUNT
    business = Business.objects.filter(
        owner=user
    ).first()

    if business:
        return business


    # STAFF ACCOUNT
    staff = StaffProfile.objects.filter(
        staff=user
    ).select_related(
        "business"
    ).first()

    if staff:
        return staff.business


    return None

# =========================================
# API DASHBOARD
# =========================================

class DashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business = get_user_business(
            request.user
        )

        if not business:
            return Response({
                "error": "No business assigned"
            }, status=404)

        # 🔥 FORCE UPDATE BEFORE READ (IMPORTANT)
        update_business_metrics(business)

        data = get_dashboard_data(business)

        return Response(data)


class InventoryModalAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        business = get_user_business(
            request.user
        )

        if not business:
            return Response({
                "error": "No business assigned"
            }, status=404)

        stock_type = request.GET.get("type")

        qs = Inventory.objects.filter(business=business)

        if stock_type == "low":
            qs = qs.filter(stock_quantity__gt=0, stock_quantity__lte=5)

        elif stock_type == "out":
            qs = qs.filter(stock_quantity__lte=0)

        data = []

        for item in qs:
            data.append({
                "id": item.id,
                "product_name": item.product_name,
                "stock_quantity": item.stock_quantity,

                # 🔥 NEW: status for colors
                "status": (
                    "out" if item.stock_quantity <= 0 else
                    "low" if item.stock_quantity <= 5 else
                    "ok"
                )
            })

        return Response(data)

# =========================================
# DASHBOARD VIEW
# =========================================

@login_required
def index(request):
    business = get_user_business(
        request.user
    )

    if not business:
        return render(
            request,
            "dashboard/index.html",
            {
                "error": "No business assigned to your account."
            }
        )

    dashboard_data = get_dashboard_data(
        business
    )

    ai_insights = AIRecommendation.objects.filter(
        business=business
    )[:6]

    context = {

        **dashboard_data,
        "business": business,
        "ai_insights": ai_insights,
        "title": "Dashboard",

        "today": timezone.now(),
    }

    return render(
        request,
        "dashboard/index.html",
        context
    )


@login_required
def mark_ai_read(request, pk):
    business = get_user_business(
        request.user
    )

    if not business:
        return Response({
            "error": "No business assigned"
        }, status=404)

    insight = get_object_or_404(
        AIRecommendation,
        id=pk,
        business=business
    )

    insight.is_read = True
    insight.save()

    return redirect('dashboard')


# @login_required
# def index(request):
#     uqueryset = request.user
#     # squeryset = StaffProfile.objects.get(staff_id=request.user.id)
#     try:
#         business = Business.objects.get(owner=request.user)
#     except Business.DoesNotExist:
#         return render(request, "dashboard.html", {
#             "error": "No business found"
#         })
#
#     summary = get_dashboard_data(business)
#     ai_data = get_business_insights(request.user)
#
#     context = {
#         "uqueryset": uqueryset,
#         "ai_insights": ai_data["insights"],
#         "total_revenue": summary["total_revenue"],
#         "total_profit": summary["total_profit"],
#         "total_sales": summary["total_sales"],
#         "best_product": summary["best_product"],
#         "low_stock_count": summary["low_stock_count"],
#     }
#
#     return render(request, "dashboard/index.html", context)


class SalesChartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.GET.get("period", "7days")

        business = Business.objects.filter(owner=request.user).first()

        if not business:
            return Response({
                "labels": [],
                "data": [],
                "message": "No business found"
            })

        data = get_sales_chart_data(business, period)
        return Response(data)


class TopProductsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.GET.get("period", "7days")

        business = Business.objects.filter(owner=request.user).first()

        if not business:
            return Response({
                "labels": [],
                "data": [],
                "revenue": []
            })

        data = get_top_products(business, period)
        return Response(data)


class AIInsightsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        business = Business.objects.filter(
            owner=request.user
        ).first()

        if not business:

            print("NO BUSINESS FOUND")

            return Response({
                "insights":[]
            })

        insights = get_ai_insights(
            business
        )
        #
        # print("\n========== AI RESPONSE ==========")
        # print(type(insights))
        # print(insights)
        # print("=================================\n")

        return Response({
            "insights": insights
        })


class ProfitAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.GET.get("period", "7days")

        business = Business.objects.filter(owner=request.user).first()

        if not business:
            return Response({
                "labels": [],
                "revenue": [],
                "cost": [],
                "profit": [],
                "margin": 0
            })

        data = get_profit_analytics(business, period)
        return Response(data)


class AIChatAPIView(APIView):
    permission_classes=[IsAuthenticated]

    def post(self, request):

        user = request.user

        business = get_user_business(
            request.user
        )

        if not business:
            return Response({
                "error": "No business assigned"
            }, status=404)

        message = request.data.get(
            "message",
            ""
        ).strip()

        if not message:

            return Response({

                "reply":
                "Please enter a message."

            })

        try:

            reply = analyze_with_ai(

                business=business,
                user_message=message,
                user=user

            )

            return Response({

                "reply": reply

            })

        except Exception as e:

            print(
                "\n===== AI CHAT ERROR ====="
            )

            print(str(e))

            print(
                "=========================\n"
            )

            return Response({

                "reply":
                "AI processing failed."

            }, status=500)


# ============================================
# CHAT HISTORY API
# ============================================

class AIChatHistoryAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        business = Business.objects.filter(
            owner=request.user
        ).first()

        if not business:

            return Response([])

        chats = AIChatHistory.objects.filter(

            business=business,
            user=request.user

        ).order_by('-created_at')[:50]

        data = []

        for chat in chats:

            data.append({

                "id": chat.id,

                "message": chat.user_message,

                "reply": chat.ai_response,

                "created_at": chat.created_at.strftime(
                    "%d %b %Y %I:%M %p"
                )

            })

        return Response(data)


class BusinessAlertsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        business = Business.objects.filter(
            owner=request.user
        ).first()

        if not business:
            return Response({"alerts": []})

        # GENERATE ALERTS
        generate_business_alerts(business)

        alerts = BusinessAlert.objects.filter(
            business=business
        )[:10]

        data = []

        for alert in alerts:
            data.append({
                "title": alert.title,
                "message": alert.message,
                "type": alert.alert_type,
                "created_at": alert.created_at.strftime('%d %b %Y %I:%M %p')
            })

        return Response({
            "alerts": data
        })


class SalesForecastAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        business = Business.objects.filter(
            owner_id=request.user.id
        ).first()

        if not business:
            return Response({
                "expected_revenue": 0,
                "prediction": "No business found",
                "confidence": 0
            })

        data = generate_sales_forecast(business)
        print("FORECAST RAW OUTPUT:", data)

        # 🔥 SAFETY FALLBACK (prevents GH¢0 issue)
        if not data:
            return Response({
                "expected_revenue": 0,
                "prediction": "No sales data available",
                "confidence": 0
            })

        return Response(data)


class InventoryForecastAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        business = Business.objects.filter(
            owner_id=request.user.id
        ).first()

        if not business:
            return Response([])

        data = generate_inventory_forecast(business)

        return Response(data or [])


class BusinessRiskAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        business = Business.objects.filter(
            owner=request.user
        ).first()

        if not business:
            return Response([])

        data = generate_business_risks(business)

        return Response(data)
