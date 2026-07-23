from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CategoryForm
from .models import Category
from django.db.models import Sum
from accounts.get_business import get_business
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from accounts.models import StaffProfile


@login_required
def category_list(request):

    business = get_business(request)

    form = CategoryForm()

    categories = (
        Category.objects
            .filter(business=business)
            .annotate(product_count=Count("products"))
    )

    search = request.GET.get("search", "").strip()

    if search:
        categories = categories.filter(name__icontains=search)

    status = request.GET.get("status", "all")

    if status == "active":
        categories = categories.filter(is_active=True)

    elif status == "inactive":
        categories = categories.filter(is_active=False)

    elif status == "empty":
        categories = categories.filter(product_count=0)

    elif status == "used":
        categories = categories.filter(product_count__gt=0)

    context = {

        "categories": categories,
        "total_categories": categories.count(),
        "active_categories":
            Category.objects.filter(
                business=business,
                is_active=True
            ).count(),

        "inactive_categories":
            Category.objects.filter(
                business=business,
                is_active=False
            ).count(),

        "products_assigned": categories.aggregate(
            total=Sum("product_count")
        )["total"] or 0,

        "empty_categories":
            categories.filter(
                product_count=0
            ).count(),

        "search": search or "",
        "status": status or "all",
        "form": form,
    }

    return render(request, "catalog/categories/category_list.html", context)


@login_required
def category_create(request):

    business = get_business(request)

    if request.method == "POST":

        form = CategoryForm(request.POST, request.FILES)

        if form.is_valid():
            category = form.save(commit=False)
            category.business = business
            category.save()

            messages.success(request, "Category created successfully.")
            return redirect("category_list")

    else:

        form = CategoryForm()

    context = {
        "form": form,
        "title": "Create Category",
    }

    return render(request, "catalog/categories/category_form.html", context)


@login_required
def edit_category(request, pk):

    category = get_object_or_404(
        Category,
        pk=pk,
        business=request.user.staffprofile.business
    )

    if request.method == "POST":
        form = CategoryForm(
            request.POST,
            request.FILES,
            instance=category
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Category updated successfully."
            )

            return redirect("category_list")

    else:
        form = CategoryForm(instance=category)

    return render(
        request,
        "catalog/categories/edit_category.html",
        {
            "form": form,
            "category": category,
        },
    )


@login_required
def delete_category(request, pk):

    category = get_object_or_404(
        Category,
        pk=pk,
        business=request.user.staffprofile.business
    )

    if request.method == "POST":

        category.delete()

        messages.success(
            request,
            "Category deleted successfully."
        )

        return redirect("category_list")

    return render(
        request,
        "catalog/categories/delete_category.html",
        {
            "category": category
        }
    )


@login_required
@require_POST
def reorder_categories(request):

    data = json.loads(request.body)

    business = request.user.staffprofile.business

    with transaction.atomic():

        for item in data:

            Category.objects.filter(

                id=item["id"],
                business=business

            ).update(

                sort_order=item["position"]

            )

    return JsonResponse({

        "success": True

    })