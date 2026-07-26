from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction

from .forms import CategoryForm
from .models import Category
from accounts.get_business import get_business


from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render


@login_required
def category_list(request):
    """
    Category Management Dashboard

    Features:
    - Search categories
    - Filter by status
    - Sort categories
    - Product count statistics
    """

    business = get_business(request)

    # =====================================================
    # CATEGORY QUERY
    # =====================================================

    categories = Category.objects.filter(
        business=business
    ).annotate(
        product_count=Count("products")
    )

    # =====================================================
    # SEARCH
    # =====================================================

    search = request.GET.get(
        "search",
        ""
    ).strip()

    if search:
        categories = categories.filter(

            Q(name__icontains=search)
            |
            Q(code__icontains=search)
            |
            Q(description__icontains=search)

        )

    # =====================================================
    # STATUS FILTER
    # =====================================================

    status = request.GET.get(
        "status",
        "all"
    )

    if status == "active":

        categories = categories.filter(
            is_active=True
        )

    elif status == "inactive":

        categories = categories.filter(
            is_active=False
        )

    elif status == "used":

        categories = categories.filter(
            product_count__gt=0
        )

    elif status == "empty":
        categories = categories.filter(
            product_count=0
        )

    # =====================================================
    # SORTING
    # =====================================================

    sort = request.GET.get(
        "sort",
        "-id"
    )

    sort_options = {

        "name": "name",

        "-name": "-name",

        "created": "created_at",

        "-created": "-created_at",

        "products": "product_count",

        "-products": "-product_count",

    }

    if sort in sort_options:

        categories = categories.order_by(
            sort_options[sort]
        )

    else:

        categories = categories.order_by(
            "-id"
        )

    # =====================================================
    # GLOBAL CATEGORY STATS
    # =====================================================

    all_categories = Category.objects.filter(
        business=business
    )

    active_categories = all_categories.filter(
        is_active=True
    ).count()

    inactive_categories = all_categories.filter(
        is_active=False
    ).count()

    used_categories = Category.objects.filter(
        business=business,
        products__isnull=False
    ).distinct().count()

    empty_categories = Category.objects.filter(
        business=business
    ).annotate(
        product_count=Count("products")
    ).filter(
        product_count=0
    ).count()

    total_products = Category.objects.filter(
        business=business
    ).aggregate(
        total=Count("products")
    )["total"] or 0

    # =====================================================
    # CONTEXT
    # =====================================================

    context = {
        "categories": categories,
        "total_categories": all_categories.count(),
        "active_categories": active_categories,
        "inactive_categories": inactive_categories,
        "used_categories": used_categories,
        "empty_categories": empty_categories,
        "total_products": total_products,
        "search":  search,
        "status": status,
        "sort": sort,
        "title": "Category Management",

    }

    return render(
        request,
        "catalog/categories/category_list.html",
        context
    )


@login_required
def category_create(request):
    """
    Create a new category
    """

    business = get_business(request)

    if request.method == "POST":

        form = CategoryForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            category = form.save(commit=False)

            category.business = business

            category.save()

            # AJAX drawer save
            if request.headers.get(
                "X-Requested-With"
            ) == "XMLHttpRequest":

                return JsonResponse({

                    "success": True,

                    "message":
                    f"Category '{category.name}' created successfully!"

                })

            messages.success(
                request,
                f"Category '{category.name}' created successfully!"
            )

            return redirect(
                "category_list"
            )

        else:
            if request.headers.get(
                "X-Requested-With"
            ) == "XMLHttpRequest":

                return render(
                    request,
                    "catalog/categories/category_form.html",
                    {
                        "form": form,
                        "title":
                        "Create New Category",
                        "button_text":
                        "Create Category",
                    }
                )

            messages.error(
                request,
                "Please correct the errors below."
            )

    else:

        form = CategoryForm()

    context = {

        "form": form,
        "title": "Create New Category",
        "button_text": "Create Category",

    }

    # Drawer request
    if request.headers.get(
        "X-Requested-With"
    ) == "XMLHttpRequest":

        return render(request, "catalog/categories/category_form.html", context)

    # Normal page request

    return render(
        request,
        "catalog/categories/category.html",
        context
    )


@login_required
def edit_category(request, pk):
    """
    Edit an existing category
    """

    business = get_business(request)

    category = get_object_or_404(
        Category,
        pk=pk,
        business=business
    )

    if request.method == "POST":

        form = CategoryForm(
            request.POST,
            request.FILES,
            instance=category
        )

        if form.is_valid():

            category = form.save()

            # AJAX drawer response

            if request.headers.get(
                "X-Requested-With"
            ) == "XMLHttpRequest":

                return JsonResponse({
                    "success": True,
                    "message": f"Category '{category.name}' updated successfully!"

                })

            messages.success(request,
                f"Category '{category.name}' updated successfully!"
            )
            return redirect("category_list")

        else:

            if request.headers.get(
                "X-Requested-With"
            ) == "XMLHttpRequest":

                return render( request, "catalog/categories/category_form.html",

                    {
                    "form": form,
                    "category": category,
                    "title": f"Edit Category: {category.name}",
                    "button_text": "Update Category"

                    }
                )
            messages.error(request, "Please correct the errors below." )
    else:
        form = CategoryForm(
            instance=category
        )

    context = {
        "form": form,
        "category": category,
        "title": f"Edit Category: {category.name}",
        "button_text":
        "Update Category",
    }

    # Drawer request

    if request.headers.get(
        "X-Requested-With"
    ) == "XMLHttpRequest":

        return render(request, "catalog/categories/category_form.html", context)





    # Normal browser access

    return render(

        request,

        "catalog/categories/category.html",

        context

    )


@login_required
def delete_category(request, pk):
    """
    Delete category with AJAX confirmation modal
    """

    business = get_business(request)

    category = get_object_or_404(
        Category,
        pk=pk,
        business=business
    )

    if request.method == "POST":

        category_name = category.name

        category.delete()

        if request.headers.get(
            "X-Requested-With"
        ) == "XMLHttpRequest":

            return JsonResponse({
                "success": True,

                "message":
                f"Category '{category_name}' deleted successfully!"

            })

        messages.success(
            request,
            f"Category '{category_name}' deleted successfully!"
        )

        return redirect(
            "category_list"
        )

    context = {
        "category": category,
        "product_count": category.products.count(),
        "title": "Delete Category",

    }
    if request.headers.get(
        "X-Requested-With"
    ) == "XMLHttpRequest":

        return render(
            request,
            "catalog/categories/delete_modal.html",
            context
        )

    return render(
        request,
        "catalog/categories/delete_category.html",
        context
    )


@login_required
@require_POST
def reorder_categories(request):
    """
    API endpoint to reorder categories via drag & drop
    Expects JSON: [{"id": 1, "position": 0}, {"id": 2, "position": 1}, ...]
    """
    import json

    try:
        data = json.loads(request.body)
        business = get_business(request)

        with transaction.atomic():
            for item in data:
                Category.objects.filter(
                    id=item["id"],
                    business=business
                ).update(sort_order=item["position"])

        return JsonResponse({"success": True})

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)