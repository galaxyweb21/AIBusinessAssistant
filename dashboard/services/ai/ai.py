from groq import Groq
from django.conf import settings
from dashboard.models import (AIChatHistory, AIRecommendation)
from sales.models import Sale, SaleItem
from dashboard.services.ai.ai_context import build_business_context

from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

client = Groq(api_key=settings.GROQ_API_KEY)


# =========================================
# INTENT DETECTION (FIXED)
# =========================================

def is_data_question(question: str) -> bool:

    q = question.lower().strip()

    business_data_keywords = [

        # sales
        "sales",
        "sale",
        "revenue",
        "profit",
        "income",
        "order",
        "orders",

        # inventory
        "inventory",
        "stock",
        "product",
        "products",
        "item",
        "items",
        "catalog",
        "sku",
        "barcode",

        "low stock",
        "running low",
        "out of stock",

        # supplier
        "supplier",
        "suppliers",
        "vendor",
        "vendors",
        "purchase",
        "purchases",

        # finance
        "payment",
        "expense",
        "expenses",
        "balance",

        # analytics
        "highest",
        "lowest",
        "top selling",
        "best selling",
        "most profitable",

        # counting
        "how many",
        "total",

        # date filters
        "today",
        "yesterday",
        "this week",
        "this month",
    ]

    return any(
        keyword in q
        for keyword in business_data_keywords
    )


def detect_ai_mode(user_message: str) -> str:
    message = user_message.lower().strip()

    # ==================================
    # BUSINESS IDEAS / GENERAL ADVICE
    # ==================================

    idea_keywords = [

        "business idea",
        "business ideas",
        "best business",
        "start business",
        "profitable business",
        "business in ghana",
        "what business",
        "what can i do"

    ]

    if any(

            keyword in message

            for keyword in idea_keywords

    ):
        return "idea_mode"

    # ==================================
    # CREDIT ANALYSIS
    # ==================================

    credit_keywords = [

        "loan",
        "credit",
        "borrow",
        "risk",
        "repayment"

    ]

    if any(

            keyword in message

            for keyword in credit_keywords

    ):
        return "credit_mode"

    advisor_keywords = [

        "marketing",
        "advertising",
        "business growth",
        "grow sales",
        "increase sales",
        "customer retention",
        "pricing",
        "business strategy",
        "cash flow",
        "management",
        "business advice",
        "business consultant",
        "startup",
        "entrepreneurship",
        "operations"
    ]

    if any(
            keyword in message
            for keyword in advisor_keywords
    ):
        return "advisor_mode"

    business_keywords = [
        "sales",
        "revenue",
        "profit",
        "stock",
        "inventory",
        "customer",
        "trend",
        "risk",
        "opportunity",
    ]

    is_business_analysis = any(
        word in user_message.lower()
        for word in business_keywords
    )

    # ==================================
    # ERP BUSINESS DATA
    # ==================================

    if is_data_question(message):
        return "data_mode"

    # ==================================
    # GENERAL CHAT
    # ==================================

    return "general_mode"


# =========================================
# SYSTEM PROMPTS (STRICT FIXED VERSION)
# =========================================

DATA_SYSTEM_PROMPT = """
You are an Enterprise Business Intelligence Advisor.

You MUST ONLY use BUSINESS DATA.

================ STRICT RULES ================

1. NEVER invent products.
2. NEVER invent suppliers.
3. NEVER invent revenue.
4. NEVER invent stock quantities.
5. NEVER invent names.
6. NEVER use prior chat history as facts.

================ RESPONSE STYLE ================

For business performance questions such as:

- sales
- revenue
- profit
- inventory
- stock
- customers
- trends
- performance
- business growth

ALWAYS use:

### 📈 Summary
Provide the direct answer first.

### 💡 Recommendations
Provide 2–3 practical actions.

### ⚠️ Risks
Mention risks if applicable.

### 🚀 Opportunities
Mention growth opportunities.

### 📌 Advisor Note
Provide a short business conclusion.

Never start answers with:

"Based on the provided business data..."

Never mention BUSINESS DATA.

Speak like a CEO advisor.

================ PRODUCT RULES ================

If the user asks:

- what products do I have
- list my products
- show inventory
- inventory items
- product list

You MUST answer ONLY from ALL PRODUCTS.

Never rename products.

================ FALLBACK ================

If data is unavailable:

Data not available in current business records.
"""

IDEA_SYSTEM_PROMPT = """
You are a senior Ghana business consultant.

Recommend:

- profitable businesses
- startup opportunities
- side businesses
- retail opportunities
- service businesses
- digital businesses

Rules:

- Tailor recommendations for Ghana.
- Avoid unrealistic income claims.
- Explain startup requirements.
- Mention risks.
- Mention approximate capital requirements when useful.
- Give practical advice.
"""

CREDIT_SYSTEM_PROMPT = """
You are a credit analyst.

Return:
Credit Score:
Risk:
Decision:
Reason:
"""

GENERAL_SYSTEM_PROMPT = """
You are an expert Business Consultant.

Primary country:
Ghana

You help with:

- business growth
- sales improvement
- marketing
- inventory management
- pricing strategy
- customer retention
- supplier management
- entrepreneurship
- startup ideas
- operations management
- cash flow management
- retail management
- pharmacy management
- SME growth

RULES:

- Provide practical advice.
- Tailor answers for Ghana when relevant.
- Do not invent user business data.
- Do not invent revenue figures.
- Do not invent inventory quantities.
- If business data is required, ask the user or use supplied records.
- Give actionable recommendations.
- Prefer concise and professional responses.

You are both:
1. Business consultant
2. ERP assistant
"""


# =========================================
# MAIN AI FUNCTION
# =========================================

def analyze_with_ai(business, user_message, user):
    mode = detect_ai_mode(user_message)

    context = ""
    memory = ""

    system_prompt = GENERAL_SYSTEM_PROMPT
    response_rules = ""

    # ==========================================
    # DATA MODE
    # ==========================================
    if mode == "data_mode":
        system_prompt = DATA_SYSTEM_PROMPT

        context = build_business_context(
            business,
            user
        )

        final_input = f"""
    You are an expert business advisor.

    BUSINESS DATA:
    {context}

    USER QUESTION:
    {user_message}

    Instructions:

    If the user asks for figures:
    - Start with a short heading.
    - Give the exact answer first.
    - Then provide 2–3 practical recommendations.
    - Mention risks or opportunities if applicable.

    Format:

    📊 Heading

    • Answer

    Recommendations:
    • Recommendation 1
    • Recommendation 2
    • Recommendation 3

    Risks/Opportunities:
    • Point 1

    Do NOT say:
    "Based on the provided business data"
    "According to the context"

    Never expose raw business context.
    """

    # ==========================================
    # IDEA MODE
    # ==========================================
    elif mode == "idea_mode":

        system_prompt = IDEA_SYSTEM_PROMPT

        response_rules = """
                    - You MUST use clean Markdown formatting to make the response highly readable.
                    - Use clear Markdown headings (###) for distinct business categories.
                    - For each business idea, follow this exact structure with double line breaks between points:

                      ### 🚀 [Business Idea Name]
                      • **Overview**: Brief description of the opportunity in Ghana.
                      • **Capital Requirement**: Approximate GHS amount.
                      • **Key Risks**: Mention 1-2 practical risks.
                      • **Why it's valuable**: Explain the profit potential.

                    - Do NOT bunch all the ideas into a single paragraph. 
                    - Leave an empty line between each section.
                    """

    # ==========================================
    # CREDIT MODE
    # ==========================================
    elif mode == "credit_mode":

        system_prompt = CREDIT_SYSTEM_PROMPT

        response_rules = """
        - Provide professional funding guidance.
        - Suggest realistic financing options.
        - Mention requirements and risks.
        - Avoid guaranteeing approval.
        """

    # ==========================================
    # ADVISOR MODE
    # ==========================================
    elif mode == "advisor_mode":

        system_prompt = GENERAL_SYSTEM_PROMPT

        response_rules = """
        - Act like an experienced business advisor.
        - Give practical recommendations.
        - Explain reasoning clearly.
        - Be concise and professional.
        """

    # ==========================================
    # CHAT MEMORY
    # ==========================================
    if mode != "data_mode":

        recent_chats = (
            AIChatHistory.objects.filter(
                business=business,
                user=user
            )
            .order_by("-created_at")[:5]
        )

        for chat in reversed(recent_chats):

            memory += (
                f"\nUser: {chat.user_message}\n"
                f"AI: {chat.ai_response}\n"
            )

        # Build dynamic context with memory and rules for general/idea/advisor chats
        final_input = f"""
        {response_rules}

        CHAT HISTORY MEMORY:
        {memory}

        USER QUESTION:
        {user_message}
        """

    # ==========================================
    # ENTERPRISE DATA SHORTCUTS
    # ==========================================
    try:

        lower_msg = user_message.lower()

        if mode == "data_mode":

            if "sales this week" in lower_msg:
                return generate_weekly_sales_response(business)

            elif "sales this month" in lower_msg:
                return generate_monthly_sales_response(business)

            elif (
                    "best selling" in lower_msg
                    or "top selling" in lower_msg
                    or "best-selling" in lower_msg
            ):
                return generate_best_sellers_response(business)

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": final_input}
            ],
            temperature=0.3,
            max_tokens=700
        )

        result = response.choices[0].message.content.strip()

        AIChatHistory.objects.create(
            business=business,
            user=user,
            user_message=user_message,
            ai_response=result
        )

        save_ai_recommendations(
            business=business,
            user=user,
            ai_response=result
        )

        return result


    except Exception as e:

        import traceback

        print("AI ERROR:", str(e))

        traceback.print_exc()

        return f"⚠️ AI processing failed: {str(e)}"


def generate_weekly_sales_response(business):

    week_start = timezone.now() - timedelta(days=7)

    sales = Sale.objects.filter(
        business=business,
        status="Completed",
        created_at__gte=week_start
    )

    total = sales.aggregate(
        total=Sum("total")
    )["total"] or Decimal("0.00")

    return f"""
📊 Weekly Sales Summary

• Total sales this week: GHS {total:,.2f}

Recommendations:
• Promote your best-selling products.
• Increase stock levels for fast-moving items.
• Use WhatsApp campaigns to sustain momentum.

Opportunities:
• Strong weekly sales indicate healthy customer demand.
"""


def generate_monthly_sales_response(business):

    month_start = timezone.now() - timedelta(days=30)

    sales = Sale.objects.filter(
        business=business,
        status="Completed",
        created_at__gte=month_start
    )

    total = sales.aggregate(
        total=Sum("total")
    )["total"] or Decimal("0.00")

    return f"""
📈 Monthly Sales Summary

• Total sales this month: GHS {total:,.2f}

Recommendations:
• Review your highest-performing products.
• Introduce targeted promotions.
• Focus marketing on profitable categories.

Opportunities:
• Monthly performance trends can guide future inventory planning.
"""


def generate_best_sellers_response(business):

    products = (
        SaleItem.objects.filter(
            sale__business=business,
            sale__status="Completed"
        )
        .values("product__product_name")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")[:3]
    )

    if not products:
        return (
            "No completed sales found yet. "
            "Start recording sales to generate insights."
        )

    response = "🏆 Top Selling Products\n\n"

    for i, item in enumerate(products, start=1):
        response += (
            f"{i}. {item['product__product_name']} "
            f"({item['total_qty']} sold)\n"
        )

    response += """
Recommendations:
• Maintain adequate stock for these products.
• Feature them prominently in promotions.
• Consider bundling them with related products.
"""

    return response


def save_ai_recommendations(business, user, ai_response):

    text = ai_response.lower()

    recommendations = []

    if "low stock" in text:

        recommendations.append({
            "title": "Low Stock Alert",
            "message": ai_response,
            "icon": "fas fa-box-open",
            "type": "warning"
        })

    elif "increase" in text or "grow" in text:

        recommendations.append({
            "title": "Growth Opportunity",
            "message": ai_response,
            "icon": "fas fa-chart-line",
            "type": "success"
        })

    elif "decline" in text or "decrease" in text:

        recommendations.append({
            "title": "Performance Warning",
            "message": ai_response,
            "icon": "fas fa-exclamation-triangle",
            "type": "danger"
        })

    else:

        recommendations.append({
            "title": "Business Insight",
            "message": ai_response,
            "icon": "fas fa-lightbulb",
            "type": "primary"
        })

    for rec in recommendations:

        AIRecommendation.objects.create(
            business=business,
            user=user,
            title=rec["title"],
            message=rec["message"],
            icon=rec["icon"],
            type=rec["type"]
        )