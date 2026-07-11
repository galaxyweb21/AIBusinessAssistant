from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.models import User

from business.models import Business
from inventory.models import *
from inventory.forms import *
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from dashboard.services.alerts import generate_business_alerts
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.contrib.contenttypes.models import ContentType
from accounts.models import AuditLog
import json


@login_required
@transaction.atomic
def inventory(request):
    user = User.objects.get(id=request.user.id)

    business = Business.objects.get(
        owner_id=request.user.id
    )

    form = InventoryForm()

    if request.method == 'POST':

        form = InventoryForm(request.POST, request.FILES,)

        if form.is_valid():

            inventory = form.save(commit=False)

            inventory.business = business

            # PREVENT DUPLICATE PRODUCT
            if Inventory.objects.filter(
                    product_name=inventory.product_name,
                    business=business
            ).exclude(id=inventory.id).exists():
                messages.error(
                    request,
                    f'Sorry product "{inventory.product_name}" already exists.'
                )

                return redirect('inventory')

            inventory.save()

            AuditLog.objects.create(

                user=request.user,

                action="Inventory Created",

                description=(
                    f"{request.user.username} added new product "
                    f"'{inventory.product_name}' "
                    f"(Qty: {inventory.stock_quantity}) "
                    f"to inventory."
                ),

                content_type=ContentType.objects.get_for_model(Inventory),

                object_id=inventory.id,

                ip_address=request.META.get("REMOTE_ADDR")
            )

            messages.success(
                request,
                'Inventory created successfully.'
            )

            return redirect('view_inventory')

    context = {
        "form": form,
        "user": user,
        "business": business,
        "title": "Add Inventory",
    }

    return render(
        request,
        'inventory/inventory.html',
        context
    )


@login_required
@transaction.atomic
def update_inventory(request, pk):
    user = User.objects.get(id=request.user.id)

    business = Business.objects.get(
        owner_id=request.user.id
    )

    queryset = get_object_or_404(
        Inventory,
        id=pk,
        business=business
    )

    form = UpdateInventoryForm(instance=queryset)

    if request.method == 'POST':

        form = UpdateInventoryForm(request.POST, request.FILES, instance=queryset)

        if form.is_valid():

            inventory = form.save(commit=False)

            # normalize value (prevents hidden duplicates like "Rice" vs "rice")
            product_name = inventory.product_name.strip().lower()

            duplicate_exists = Inventory.objects.filter(
                product_name__iexact=product_name,
                business=business
            ).exclude(id=queryset.id).exists()

            if duplicate_exists:
                messages.error(
                    request,
                    f'Product "{inventory.product_name}" already exists in this business.'
                )
                return render(request, 'inventory/update_inventory.html', {
                    "form": form,
                    "user": user,
                    "queryset": queryset,
                    "business": business,
                    "title": "Update Inventory",
                })

            inventory.business = business
            inventory.product_name = inventory.product_name.strip()
            inventory.save()

            AuditLog.objects.create(

                user=request.user,

                action="Inventory Updated",

                description=(
                    f"{request.user.username} updated product "
                    f"'{inventory.product_name}'. "
                    f"Current stock: {inventory.stock_quantity}"
                ),

                content_type=ContentType.objects.get_for_model(Inventory),

                object_id=inventory.id,

                ip_address=request.META.get("REMOTE_ADDR")
            )

            messages.success(request, 'Inventory successfully updated.')
            return redirect('view_inventory')

    context = {
        "form": form,
        "user": user,
        "queryset": queryset,
        "business": business,
        "title": "Update Inventory",
    }

    return render(
        request,
        'inventory/update_inventory.html',
        context
    )


@login_required
@transaction.atomic
def delete_inventory(request, pk):
    business = Business.objects.get(
        owner_id=request.user.id
    )

    queryset = get_object_or_404(
        Inventory,
        id=pk,
        business=business
    )

    if request.method == 'POST':
        AuditLog.objects.create(

            user=request.user,

            action="Inventory Deleted",

            description=(
                f"{request.user.username} deleted product "
                f"'{queryset.product_name}' "
                f"from inventory."
            ),

            content_type=ContentType.objects.get_for_model(Inventory),

            object_id=queryset.id,

            ip_address=request.META.get("REMOTE_ADDR")
        )

        queryset.delete()

        queryset.delete()

        messages.success(
            request,
            'Inventory deleted successfully.'
        )

    return redirect('view_inventory')


@login_required
@transaction.atomic
def view_inventory(request):
    user = User.objects.get(id=request.user.id)

    business = Business.objects.get(
        owner_id=request.user.id
    )

    search = request.GET.get(
        'search',
        ''
    ).strip()

    queryset = Inventory.objects.filter(
        business=business
    )

    # SEARCH
    if search:
        queryset = queryset.filter(

            Q(product_name__icontains=search)

        )

    queryset = queryset.order_by('-id')

    # PAGINATION
    paginator = Paginator(
        queryset,
        10  # 10 products per page
    )

    page_number = request.GET.get(
        'page'
    )

    inventory_items = paginator.get_page(
        page_number
    )

    context = {

        "user": user,
        "business": business,

        "queryset": inventory_items,

        "search": search,

        "title": f"Inventory - {business.name}",

    }

    return render(
        request,
        'inventory/view_inventory.html',
        context
    )


@login_required
def restock_inventory(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    item = get_object_or_404(Inventory, pk=pk, business=business)
    item_history = item.history.all().order_by('-created_at')[:10]

    if request.method == "POST":

        try:
            add_qty = int(request.POST.get("quantity", 0))

            if add_qty <= 0:
                messages.error(request, "Enter a valid quantity.")
                return redirect("restock_inventory", pk=item.id)

            previous_stock = item.stock_quantity
            new_stock = previous_stock + add_qty

            item.stock_quantity = new_stock
            item.save()

            AuditLog.objects.create(

                user=request.user,

                action="Inventory Restock",

                description=(
                    f"{request.user.username} restocked "
                    f"'{item.product_name}' by {add_qty} units. "
                    f"New stock: {new_stock}"
                ),

                content_type=ContentType.objects.get_for_model(Inventory),

                object_id=item.id,

                ip_address=request.META.get("REMOTE_ADDR")
            )

            InventoryStockHistory.objects.create(
                business=business,
                inventory=item,
                previous_stock=previous_stock,
                quantity_changed=add_qty,
                new_stock=new_stock,
                action_type="restock",
                performed_by=request.user,
                note=f"Restocked {add_qty} units",
                reference_number=f"RST-{item.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            )

            generate_business_alerts(item.business)

            messages.success(request, "Stock updated successfully!")

            return redirect("view_inventory")

        except ValueError:
            messages.error(request, "Invalid quantity.")

    context = {
        "item": item,
        "item_history": item_history,
    }

    return render(request, "inventory/restock_inventory.html", context)


@login_required
def damaged_inventory(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    item = get_object_or_404(Inventory, pk=pk, business=business)
    item_history = item.history.all().order_by('-created_at')[:10]

    if request.method == "POST":

        try:
            damaged_qty = int(request.POST.get("quantity", 0))

            if damaged_qty <= 0:
                messages.error(request, "Enter a valid quantity.")
                return redirect("damaged_inventory", pk=item.id)
            elif damaged_qty > item.stock_quantity:
                messages.error(request, "Sorry damaged quantity is more than quantity in stock.")
                return redirect("damaged_inventory", pk=item.id)

            previous_stock = item.stock_quantity
            new_stock = previous_stock - damaged_qty

            item.stock_quantity = new_stock
            item.save()

            AuditLog.objects.create(

                user=request.user,

                action="Inventory Damage",

                description=(
                    f"{request.user.username} marked "
                    f"{damaged_qty} units of '{item.product_name}' as damaged. "
                    f"Remaining stock: {new_stock}"
                ),

                content_type=ContentType.objects.get_for_model(Inventory),

                object_id=item.id,

                ip_address=request.META.get("REMOTE_ADDR")
            )

            InventoryStockHistory.objects.create(
                business=business,
                inventory=item,
                previous_stock=previous_stock,
                quantity_changed=-damaged_qty,
                new_stock=new_stock,
                action_type="damaged",
                performed_by=request.user,
                note=f"Damaged {damaged_qty} units",
                reference_number=f"RST-{item.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            )

            generate_business_alerts(item.business)

            messages.success(request, "Stock updated successfully!")

            return redirect("view_inventory")

        except ValueError:
            messages.error(request, "Invalid quantity.")

    context = {
        "item": item,
        "item_history": item_history,
    }

    return render(request, "inventory/damaged_inventory.html", context)


@login_required
def inventory_history(request):
    business = Business.objects.get(
        owner=request.user
    )

    tab = request.GET.get(
        "tab",
        "all"
    )

    queryset = InventoryStockHistory.objects.filter(
        business=business
    ).select_related(
        "inventory",
        "performed_by"
    ).order_by("-created_at")

    # =====================================
    # FILTER BY TAB
    # =====================================

    if tab != "all":
        queryset = queryset.filter(
            action_type=tab
        )

    # =====================================
    # SEARCH
    # =====================================

    search = request.GET.get(
        "search",
        ""
    ).strip()

    if search:
        queryset = queryset.filter(

            Q(inventory__product_name__icontains=search) |
            Q(reference_number__icontains=search) |
            Q(performed_by__username__icontains=search) |
            Q(action_type__icontains=search)

        )

    # PAGINATION
    paginator = Paginator(
        queryset,
        10  # 10 products per page
    )

    page_number = request.GET.get(
        'page'
    )

    inventory_items = paginator.get_page(
        page_number
    )

    context = {
        "queryset": queryset,
        "tab": tab,
        "search": search,
        "inventory_items": inventory_items,
    }

    return render(
        request,
        "inventory/inventory_history.html",
        context
    )


@login_required
def supplier_list(request):
    business = get_object_or_404(
        Business,
        owner=request.user
    )

    search = request.GET.get("search", "").strip()

    suppliers = Supplier.objects.filter(business=business)

    if search:
        suppliers = suppliers.filter(
            name__icontains=search
        )

    context = {
        "suppliers": suppliers,
        "business": business,
        "search": search,
        "title": "Suppliers"
    }

    return render(request, "suppliers/supplier_list.html", context)


@login_required
@transaction.atomic
def create_supplier(request):
    user = request.user

    business = get_object_or_404(
        Business,
        owner=request.user
    )

    form = SupplierForm()

    if request.method == "POST":

        form = SupplierForm(request.POST)

        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.business = business
            supplier.save()

            messages.success(request, "Supplier created successfully.")
            return redirect("supplier_list")

    context = {
        "user": user,
        "form": form,
        "business": business,
        "title": "Create Supplier"
    }

    return render(request, "suppliers/create_supplier.html", context)


@login_required
@transaction.atomic
def update_supplier(request, pk):
    user = request.user

    business = get_object_or_404(
        Business,
        owner=request.user
    )

    supplier = get_object_or_404(
        Supplier,
        id=pk,
        business=business
    )

    form = SupplierForm(instance=supplier)

    if request.method == "POST":

        form = SupplierForm(request.POST, instance=supplier)

        if form.is_valid():
            form.save()

            messages.success(request, "Supplier updated successfully.")
            return redirect("supplier_list")

    context = {
        "user": user,
        "form": form,
        "business": business,
        "supplier": supplier,
        "title": "Update Supplier"
    }

    return render(request, "suppliers/create_supplier.html", context)


@login_required
@transaction.atomic
def delete_supplier(request, pk):
    business = get_object_or_404(
        Business,
        owner=request.user
    )

    supplier = get_object_or_404(
        Supplier,
        id=pk,
        business=business
    )

    if request.method == "POST":
        supplier.delete()

        messages.success(request, "Supplier deleted successfully.")
        return redirect("supplier_list")


# purchases
@login_required
@transaction.atomic
def create_purchase(request):

    business = get_object_or_404(
        Business,
        owner=request.user
    )

    suppliers = Supplier.objects.filter(
        business=business
    )

    products = Inventory.objects.filter(
        business=business
    )

    if request.method == "POST":

        supplier = get_object_or_404(
            Supplier,
            id=request.POST.get("supplier"),
            business=business
        )

        purchase = Purchase.objects.create(
            business=business,
            supplier=supplier,
            reference_number=f"PUR-{timezone.now().strftime('%Y%m%d%H%M%S')}",
            created_by=request.user,
            status="pending",
            total_cost=Decimal("0.00")
        )

        items = json.loads(
            request.POST.get(
                "items_json",
                "[]"
            )
        )

        purchase_discount = Decimal(
            request.POST.get(
                "purchase_discount",
                "0"
            )
        )

        purchase_tax = Decimal(
            request.POST.get(
                "purchase_tax",
                "0"
            )
        )

        purchase_total = Decimal("0.00")

        for item in items:

            qty = int(item["qty"])

            cost = Decimal(
                str(item["cost"])
            )

            discount = Decimal(
                str(item.get("discount", 0))
            )

            tax_percent = Decimal(
                str(item.get("tax", 0))
            )

            purchase_item = PurchaseItem.objects.create(
                purchase=purchase,
                product_id=item["product_id"],
                quantity=qty,
                unit_cost=cost,
                discount=discount,
                tax_percent=tax_percent
            )

            # use model-calculated value
            purchase_total += (
                purchase_item.total_cost
                or Decimal("0.00")
            )

        purchase.calculate_totals(
            purchase_discount=purchase_discount,
            purchase_tax=purchase_tax
        )

        supplier.total_purchases += purchase.total_cost
        supplier.last_supply_date = timezone.now()

        supplier.save(
            update_fields=[
                "total_purchases",
                "last_supply_date"
            ]
        )

        messages.success(
            request,
            "Purchase created successfully."
        )

        return redirect(
            "view_purchase",
            purchase.id
        )

    context = {
        "business": business,
        "suppliers": suppliers,
        "products": products,
    }

    return render(
        request,
        "purchases/create_purchase.html",
        context
    )


@login_required
@transaction.atomic
def post_purchase(request, pk):
    business = get_object_or_404(Business, owner=request.user)

    purchase = get_object_or_404(
        Purchase,
        id=pk,
        business=business
    )

    if purchase.status == "received":
        messages.warning(request, "Purchase already posted.")
        return redirect("view_purchase", pk=purchase.id)

    purchase.post_purchase(user=request.user)

    messages.success(request, "Purchase posted successfully.")
    return redirect("view_purchase", pk=purchase.id)


@login_required
def view_purchase(request, pk):
    business = get_object_or_404(Business, owner=request.user)

    purchase = get_object_or_404(
        Purchase,
        id=pk,
        business=business
    )

    context = {
        "purchase": purchase,
        "items": purchase.items.all(),
        "business": business,
    }

    return render(request, "purchases/view_purchase.html", context)


@login_required
def supplier_detail(request, pk):
    business = get_object_or_404(
        Business,
        owner=request.user
    )

    supplier = get_object_or_404(
        Supplier,
        id=pk,
        business=business
    )

    purchases = Purchase.objects.filter(
        supplier=supplier,
        business=business
    ).order_by("-created_at")

    # Total purchase amount
    total_purchase_amount = (
            purchases.aggregate(
                total=Sum("total_cost")
            )["total"] or 0
    )

    # Total paid
    total_paid = (
            purchases.aggregate(
                total=Sum("paid_amount")
            )["total"] or 0
    )

    # Outstanding amount for THIS supplier only
    outstanding_amount = (
            total_purchase_amount - total_paid
    )

    total_orders = purchases.count()

    context = {
        "business": business,
        "supplier": supplier,
        "purchases": purchases,
        "total_purchase_amount": total_purchase_amount,
        "total_orders": total_orders,
        "outstanding_amount": outstanding_amount,
        "total_paid": total_paid,
    }

    return render(
        request,
        "suppliers/supplier_detail.html",
        context
    )


@login_required
@transaction.atomic
def supplier_payment(request, purchase_id):

    business = get_object_or_404(
        Business,
        owner=request.user
    )
    purchase = get_object_or_404(
        Purchase,
        id=purchase_id
    )

    if request.method == "POST":

        try:

            amount = Decimal(
                request.POST.get(
                    "amount_paid",
                    "0"
                )
            )

        except:

            amount = Decimal("0.00")

        payment_method = request.POST.get(
            "payment_method"
        )

        external_reference = request.POST.get(
            "external_reference",
            ""
        )

        note = request.POST.get(
            "note",
            ""
        )

        if amount <= 0:

            messages.error(
                request,
                "Invalid payment amount"
            )

            return redirect(
                "view_purchase",
                purchase.id
            )

        if amount > purchase.balance:

            messages.error(
                request,
                "Payment exceeds remaining balance"
            )

            return redirect(
                "view_purchase",
                purchase.id
            )

        SupplierPayment.objects.create(

            supplier=purchase.supplier,

            purchase=purchase,

            amount_paid=amount,

            payment_method=payment_method,

            external_reference=external_reference,

            note=note,

            created_by=request.user
        )

        messages.success(
            request,
            "Supplier payment recorded successfully."
        )

        return redirect(
            "view_purchase",
            purchase.id
        )

    context = {

        "purchase":purchase,
        "business": business,
    }

    return render(
        request,
        "suppliers/supplier_payment.html",
        context
    )


@login_required
def supplier_payment_history(request):

    business = get_object_or_404(
        Business,
        owner=request.user
    )

    # =========================
    # GET FILTER VALUES
    # =========================
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()

    # =========================
    # BASE QUERY (OPTIMIZED)
    # =========================
    payments = SupplierPayment.objects.select_related(
        "supplier",
        "purchase",
        "created_by"
    ).filter(
        purchase__business=business
    ).order_by(
        "-created_at"
    )

    # =========================
    # SEARCH FILTER
    # =========================
    if search:
        payments = payments.filter(
            Q(reference__icontains=search) |
            Q(external_reference__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(purchase__reference_number__icontains=search)
        )

    # =========================
    # STATUS FILTER (TAB SYSTEM)
    # =========================
    if status in ["pending", "partial", "paid"]:
        payments = payments.filter(
            purchase__payment_status=status
        )

    # =========================
    # PAGINATION
    # =========================
    paginator = Paginator(payments, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # =========================
    # CONTEXT
    # =========================
    context = {
        "business": business,
        "page_obj": page_obj,
        "search": search,
        "status": status,
    }

    return render(request, "suppliers/supplier_payment_history.html", context)