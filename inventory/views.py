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
from django.db.models import Q, Sum, Avg
from django.contrib.contenttypes.models import ContentType
from accounts.models import *
import json
from accounts.get_business import get_business
from django.views.decorators.http import require_POST

import uuid
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation


@login_required
def generate_sku(request):

    sku = f"SKU-{uuid.uuid4().hex[:8].upper()}"

    return JsonResponse({
        "value": sku
    })


@login_required
def generate_barcode(request):

    barcode = str(uuid.uuid4().int)[:12]

    return JsonResponse({
        "value": barcode
    })


@login_required
def generate_qr(request):

    qr = f"QR-{uuid.uuid4().hex[:8].upper()}"

    return JsonResponse({
        "value": qr
    })

# ==========================================================
# views.py
# ==========================================================


TRACKED_FIELDS = [
    "product_name", "category", "brand", "unit", "description",
    "sku", "barcode", "qr_code",
    "cost_price", "selling_price",
    "stock_quantity", "minimum_stock", "maximum_stock",
    "reorder_level", "reorder_quantity",
    "featured", "track_stock", "status",
]


def _snapshot_inventory(instance):
    """Capture a flat, comparable string snapshot of tracked fields."""
    snapshot = {}
    for field_name in TRACKED_FIELDS:
        value = getattr(instance, field_name)
        snapshot[field_name] = str(value) if value is not None else ""
    return snapshot


def _diff_inventory(old_snapshot, instance):
    """Compare a prior snapshot against the current instance state."""
    changes = []
    for field_name in TRACKED_FIELDS:
        old_value = old_snapshot.get(field_name, "")
        new_value = getattr(instance, field_name)
        new_value = str(new_value) if new_value is not None else ""
        if old_value != new_value:
            changes.append(f"{field_name}: '{old_value}' → '{new_value}'")
    return changes


@login_required
@transaction.atomic
def inventory(request):
    """Create a new inventory item (unchanged from your existing view)."""
    user = request.user
    business = get_business(request)

    form = InventoryForm(business=business)

    if request.method == 'POST':
        form = InventoryForm(request.POST, request.FILES, business=business)

        if form.is_valid():
            new_inventory = form.save(commit=False)
            new_inventory.business = business

            if Inventory.objects.filter(
                    product_name=new_inventory.product_name,
                    business=business
            ).exists():
                messages.error(
                    request,
                    f'Sorry product "{new_inventory.product_name}" already exists.'
                )
                return redirect('inventory')

            new_inventory.save()

            AuditLog.objects.create(
                user=request.user,
                action="Inventory Created",
                description=(
                    f"{request.user.username} added new product "
                    f"'{new_inventory.product_name}' "
                    f"(Qty: {new_inventory.stock_quantity}) "
                    f"to inventory."
                ),
                content_type=ContentType.objects.get_for_model(Inventory),
                object_id=new_inventory.id,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            messages.success(request, 'Inventory created successfully.')
            return redirect('view_inventory')

    context = {
        "form": form,
        "user": user,
        "business": business,
        "title": "Add Inventory",
    }
    return render(request, 'inventory/inventory.html', context)


@login_required
@transaction.atomic
def update_inventory(request, pk):
    """Update an existing inventory item, scoped to the current business."""
    user = request.user
    business = get_business(request)

    inventory_obj = get_object_or_404(
        Inventory.objects.select_related("category", "business"),
        pk=pk,
        business=business,
    )

    if request.method == 'POST':
        # Snapshot MUST be taken before the form binds — ModelForm.is_valid()
        # mutates self.instance in place during full_clean(), so capturing
        # "before" state after is_valid() would already show "after" values.
        old_snapshot = _snapshot_inventory(inventory_obj)
        had_image_before = bool(inventory_obj.product_image)

        form = InventoryForm(
            request.POST,
            request.FILES,
            instance=inventory_obj,
            business=business,
        )

        if form.is_valid():
            product_name = form.cleaned_data["product_name"]

            duplicate_exists = (
                Inventory.objects.filter(
                    product_name=product_name,
                    business=business,
                )
                .exclude(pk=inventory_obj.pk)
                .exists()
            )

            if duplicate_exists:
                form.add_error(
                    "product_name",
                    f'Product "{product_name}" already exists in your inventory.'
                )
            else:
                updated_inventory = form.save(commit=False)
                updated_inventory.business = business
                updated_inventory.save()

                changes = _diff_inventory(old_snapshot, updated_inventory)

                if "product_image" in form.changed_data:
                    now_has_image = bool(updated_inventory.product_image)
                    if now_has_image and not had_image_before:
                        changes.append("image added")
                    elif now_has_image and had_image_before:
                        changes.append("image replaced")
                    elif not now_has_image and had_image_before:
                        changes.append("image removed")

                change_summary = "; ".join(changes) if changes else "no field changes"

                AuditLog.objects.create(
                    user=request.user,
                    action="Inventory Updated",
                    description=(
                        f"{request.user.username} updated product "
                        f"'{updated_inventory.product_name}' "
                        f"(ID: {updated_inventory.id}). Changes: {change_summary}."
                    ),
                    content_type=ContentType.objects.get_for_model(Inventory),
                    object_id=updated_inventory.id,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )

                messages.success(request, 'Inventory updated successfully.')
                return redirect('view_inventory')
    else:
        form = InventoryForm(instance=inventory_obj, business=business)

    context = {
        "form": form,
        "user": user,
        "business": business,
        "title": "Update Inventory",
        "inventory": inventory_obj,
    }
    return render(request, 'inventory/inventory.html', context)


@login_required
@require_POST
@transaction.atomic
def delete_inventory(request, pk):
    """Delete an inventory item, scoped to the current business."""
    business = get_business(request)

    inventory_obj = get_object_or_404(
        Inventory,
        pk=pk,
        business=business,
    )

    product_name = inventory_obj.product_name
    inventory_id = inventory_obj.id

    inventory_obj.delete()

    AuditLog.objects.create(
        user=request.user,
        action="Inventory Deleted",
        description=(
            f"{request.user.username} deleted product "
            f"'{product_name}' (ID: {inventory_id}) from inventory."
        ),
        content_type=ContentType.objects.get_for_model(Inventory),
        object_id=inventory_id,
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    messages.success(request, f'"{product_name}" was deleted successfully.')
    return redirect('view_inventory')


@login_required
@transaction.atomic
def view_inventory(request):
    user = request.user

    business = get_business(request)

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
@transaction.atomic
def restock_inventory(request, pk):
    business = get_business(request)
    product = get_object_or_404(
        Inventory.objects.select_related("category"),
        pk=pk,
        business=business,
    )

    history = (
        InventoryStockHistory.objects
        .filter(inventory=product)
        .select_related("supplier", "received_by")
        .order_by("-created_at")
    )

    now = timezone.now()

    monthly_restocked = (
        history.filter(
            action_type="restock",
            created_at__month=now.month,
            created_at__year=now.year,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    total_restocked = (
        history.filter(action_type="restock")
        .aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    recent_suppliers = list(
        history.exclude(supplier=None)
        .values_list("supplier__name", flat=True)
        .distinct()[:5]
    )

    average_purchase_cost = (
        history.filter(action_type="restock")
        .exclude(purchase_cost=0)
        .aggregate(avg=Avg("purchase_cost"))["avg"]
        or product.cost_price
    )

    last_restock = history.filter(action_type="restock").first()

    if request.method == "POST":
        form = RestockForm(request.POST, business=business)

        if form.is_valid():
            add_qty = form.cleaned_data["quantity"]
            note = form.cleaned_data["note"]
            supplier = form.cleaned_data.get("supplier")
            invoice_number = form.cleaned_data.get("invoice_number") or ""
            purchase_cost = form.cleaned_data.get("purchase_cost") or product.cost_price

            # Lock the row for the duration of this transaction so two
            # concurrent restocks can't both read the same "before" stock
            # and silently overwrite each other.
            locked_item = Inventory.objects.select_for_update().get(pk=product.pk)

            previous_stock = locked_item.stock_quantity
            new_stock = previous_stock + add_qty

            locked_item.stock_quantity = new_stock
            locked_item.save(update_fields=["stock_quantity", "updated_at"])

            reference_number = (
                f"RST-{locked_item.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            )

            AuditLog.objects.create(
                user=request.user,
                action="Inventory Restock",
                description=(
                    f"{request.user.username} restocked "
                    f"'{locked_item.product_name}' by {add_qty} units. "
                    f"New stock: {new_stock}"
                ),
                content_type=ContentType.objects.get_for_model(Inventory),
                object_id=locked_item.id,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            InventoryStockHistory.objects.create(
                business=business,
                inventory=locked_item,
                previous_stock=previous_stock,
                quantity=add_qty,
                new_stock=new_stock,
                action_type="restock",
                received_by=request.user,
                supplier=supplier,
                invoice_number=invoice_number,
                purchase_cost=purchase_cost,
                received_date=timezone.now().date(),
                note=note or f"Restocked {add_qty} units",
                reference_number=reference_number,
            )

            generate_business_alerts(business)

            messages.success(
                request,
                f'"{locked_item.product_name}" restocked successfully. '
                f'New stock: {new_stock}.'
            )
            return redirect("view_inventory")
    else:
        form = RestockForm(business=business)

    current_stock = product.stock_quantity
    minimum_stock = product.minimum_stock
    maximum_stock = product.maximum_stock
    reorder_level = product.reorder_level

    inventory_value = Decimal(product.stock_quantity) * product.cost_price

    if maximum_stock and maximum_stock > current_stock:
        suggested_quantity = maximum_stock - current_stock
    else:
        suggested_quantity = product.reorder_quantity or 0

    if current_stock <= minimum_stock:
        stock_status = "Critical"
    elif current_stock <= reorder_level:
        stock_status = "Low"
    elif maximum_stock and current_stock >= maximum_stock:
        stock_status = "Overstock"
    else:
        stock_status = "Healthy"

    # Health meter position (0-100), relative to the max-stock band.
    if maximum_stock and maximum_stock > 0:
        health_percent = max(0, min(100, round((current_stock / maximum_stock) * 100)))
    else:
        health_percent = 100 if current_stock > minimum_stock else 0

    context = {
        "form": form,
        "product": product,
        "item_history": history[:10],
        "current_stock": current_stock,
        "minimum_stock": minimum_stock,
        "maximum_stock": maximum_stock,
        "reorder_level": reorder_level,
        "inventory_value": inventory_value,
        "average_purchase_cost": average_purchase_cost,
        "total_restocked": total_restocked,
        "monthly_restocked": monthly_restocked,
        "suggested_quantity": suggested_quantity,
        "stock_status": stock_status,
        "health_percent": health_percent,
        "recent_suppliers": recent_suppliers,
        "last_restock": last_restock,
        "title": f"Restock — {product.product_name}",
    }
    return render(request, "inventory/restock_inventory.html", context)


@login_required
@transaction.atomic
def damaged_inventory(request, pk):
    business = get_business(request)
    item = get_object_or_404(
        Inventory.objects.select_related("category"),
        pk=pk,
        business=business,
    )

    if request.method == "POST":
        form = DamageForm(request.POST, item=item)

        if form.is_valid():
            damaged_qty = form.cleaned_data["quantity"]
            note = form.cleaned_data["note"]

            # Lock the row, then re-validate against the locked value —
            # the form's clean_quantity() already checked stock, but that
            # check ran before the lock, so a concurrent request could have
            # changed stock in between. Re-check post-lock before writing.
            locked_item = Inventory.objects.select_for_update().get(pk=item.pk)

            if damaged_qty > locked_item.stock_quantity:
                form.add_error(
                    "quantity",
                    f"Only {locked_item.stock_quantity} unit(s) currently in "
                    f"stock — cannot mark {damaged_qty} as damaged."
                )
            else:
                previous_stock = locked_item.stock_quantity
                new_stock = previous_stock - damaged_qty

                locked_item.stock_quantity = new_stock
                locked_item.save(update_fields=["stock_quantity", "updated_at"])

                reference_number = (
                    f"DMG-{locked_item.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                )

                AuditLog.objects.create(
                    user=request.user,
                    action="Inventory Damage",
                    description=(
                        f"{request.user.username} marked "
                        f"{damaged_qty} units of '{locked_item.product_name}' as damaged. "
                        f"Remaining stock: {new_stock}"
                    ),
                    content_type=ContentType.objects.get_for_model(Inventory),
                    object_id=locked_item.id,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )

                InventoryStockHistory.objects.create(
                    business=business,
                    inventory=locked_item,
                    previous_stock=previous_stock,
                    quantity_changed=-damaged_qty,
                    new_stock=new_stock,
                    action_type="damaged",
                    performed_by=request.user,
                    note=note or f"Damaged {damaged_qty} units",
                    reference_number=reference_number,
                )

                generate_business_alerts(business)

                messages.success(
                    request,
                    f'{damaged_qty} unit(s) of "{locked_item.product_name}" marked as damaged. '
                    f'Remaining stock: {new_stock}.'
                )
                return redirect("view_inventory")
    else:
        form = DamageForm(item=item)

    item_history = item.history.all()[:10]

    context = {
        "item": item,
        "item_history": item_history,
        "form": form,
        "title": f"Mark Damaged — {item.product_name}",
    }
    return render(request, "inventory/damaged_inventory.html", context)


HISTORY_TABS = [
    ("all", "All Activity"),
    ("restock", "Restock"),
    ("sale", "Sale Deduction"),
    ("adjustment", "Manual Adjustment"),
    ("damaged", "Damaged"),
    ("returned", "Returned"),
    ("transfer", "Transfer"),
]

VALID_HISTORY_TABS = {key for key, _ in HISTORY_TABS}


@login_required
def inventory_history(request):
    business = get_business(request)

    tab = request.GET.get("tab", "all").strip()
    if tab not in VALID_HISTORY_TABS:
        tab = "all"

    search = request.GET.get("search", "").strip()

    queryset = InventoryStockHistory.objects.filter(
        business=business
    ).select_related("inventory", "performed_by").order_by("-created_at")

    if tab != "all":
        queryset = queryset.filter(action_type=tab)

    if search:
        queryset = queryset.filter(
            Q(inventory__product_name__icontains=search) |
            Q(reference_number__icontains=search) |
            Q(performed_by__username__icontains=search) |
            Q(action_type__icontains=search)
        )

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    queryset = paginator.get_page(page_number)

    context = {
        "queryset": queryset,
        "tab": tab,
        "search": search,
        "tabs": HISTORY_TABS,
        "business": business,
        "title": "Inventory History",
    }

    return render(request, "inventory/inventory_history.html", context)


@login_required
def supplier_list(request):
    business = get_business(request)

    search = request.GET.get("search", "").strip()

    suppliers = Supplier.objects.filter(business=business)

    if search:
        suppliers = suppliers.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(email__icontains=search)
        )

    suppliers = suppliers.order_by("-created_at")

    paginator = Paginator(suppliers, 10)
    page_number = request.GET.get("page")
    suppliers = paginator.get_page(page_number)

    context = {
        "suppliers": suppliers,
        "business": business,
        "search": search,
        "title": "Suppliers",
    }

    return render(request, "suppliers/supplier_list.html", context)

@login_required
@transaction.atomic
def create_supplier(request):
    user = request.user
    business = get_business(request)

    form = SupplierForm(business=business)

    if request.method == "POST":
        form = SupplierForm(request.POST, business=business)

        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.business = business
            supplier.save()

            messages.success(request, f'Supplier "{supplier.name}" created successfully.')
            return redirect("supplier_list")

    context = {
        "user": user,
        "form": form,
        "business": business,
        "title": "Create Supplier",
    }
    return render(request, "suppliers/create_supplier.html", context)


@login_required
@transaction.atomic
def update_supplier(request, pk):
    user = request.user
    business = get_business(request)

    supplier = get_object_or_404(Supplier, id=pk, business=business)

    form = SupplierForm(instance=supplier, business=business)

    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier, business=business)

        if form.is_valid():
            form.save()
            messages.success(request, f'Supplier "{supplier.name}" updated successfully.')
            return redirect("supplier_list")

    context = {
        "user": user,
        "form": form,
        "business": business,
        "supplier": supplier,
        "title": "Update Supplier",
    }
    return render(request, "suppliers/create_supplier.html", context)


@login_required
@require_POST
@transaction.atomic
def delete_supplier(request, pk):
    business = get_business(request)

    supplier = get_object_or_404(Supplier, id=pk, business=business)
    supplier_name = supplier.name

    supplier.delete()

    messages.success(request, f'"{supplier_name}" was deleted successfully.')
    return redirect("supplier_list")


# purchases

def _generate_purchase_reference():
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"PUR-{timestamp}-{suffix}"


@login_required
@transaction.atomic
def create_purchase(request):
    business = get_business(request)

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by("name")
    products = Inventory.objects.filter(business=business).order_by("product_name")

    if request.method == "POST":

        supplier_id = request.POST.get("supplier")
        supplier = None

        if supplier_id:
            supplier = Supplier.objects.filter(
                id=supplier_id, business=business
            ).first()

        if not supplier:
            messages.error(request, "Please select a valid supplier.")
            return render(request, "purchases/create_purchase.html", {
                "business": business, "suppliers": suppliers, "products": products,
            })

        try:
            items = json.loads(request.POST.get("items_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            messages.error(request, "Could not read the purchase items — please try again.")
            return render(request, "purchases/create_purchase.html", {
                "business": business, "suppliers": suppliers, "products": products,
            })

        if not items:
            messages.error(request, "Add at least one item to the purchase.")
            return render(request, "purchases/create_purchase.html", {
                "business": business, "suppliers": suppliers, "products": products,
            })

        try:
            purchase_discount = Decimal(str(request.POST.get("purchase_discount", "0") or "0"))
            purchase_tax = Decimal(str(request.POST.get("purchase_tax", "0") or "0"))
        except InvalidOperation:
            messages.error(request, "Discount and tax must be valid numbers.")
            return render(request, "purchases/create_purchase.html", {
                "business": business, "suppliers": suppliers, "products": products,
            })

        # Validate every line item BEFORE creating anything, so a bad item
        # never leaves a half-built purchase behind.
        validated_items = []

        for index, item in enumerate(items, start=1):
            try:
                product_id = item["product_id"]
                qty = int(item["qty"])
                cost = Decimal(str(item["cost"]))
                discount = Decimal(str(item.get("discount", 0) or 0))
                tax_percent = Decimal(str(item.get("tax", 0) or 0))
            except (KeyError, ValueError, TypeError, InvalidOperation):
                messages.error(request, f"Item {index} has invalid or missing data.")
                return render(request, "purchases/create_purchase.html", {
                    "business": business, "suppliers": suppliers, "products": products,
                })

            if qty <= 0:
                messages.error(request, f"Item {index}: quantity must be greater than zero.")
                return render(request, "purchases/create_purchase.html", {
                    "business": business, "suppliers": suppliers, "products": products,
                })

            if cost < 0 or discount < 0 or tax_percent < 0:
                messages.error(request, f"Item {index}: cost, discount, and tax cannot be negative.")
                return render(request, "purchases/create_purchase.html", {
                    "business": business, "suppliers": suppliers, "products": products,
                })

            # Ownership check: the product MUST belong to this business —
            # prevents attaching another business's inventory via a tampered request.
            product = Inventory.objects.filter(pk=product_id, business=business).first()
            if not product:
                messages.error(request, f"Item {index}: product not found in your inventory.")
                return render(request, "purchases/create_purchase.html", {
                    "business": business, "suppliers": suppliers, "products": products,
                })

            validated_items.append({
                "product": product,
                "qty": qty,
                "cost": cost,
                "discount": discount,
                "tax_percent": tax_percent,
            })

        # Everything validated — now safe to create records.
        purchase = Purchase.objects.create(
            business=business,
            supplier=supplier,
            reference_number=_generate_purchase_reference(),
            created_by=request.user,
            status="pending",
            total_cost=Decimal("0.00"),
        )

        for validated in validated_items:
            PurchaseItem.objects.create(
                purchase=purchase,
                product=validated["product"],
                quantity=validated["qty"],
                unit_cost=validated["cost"],
                discount=validated["discount"],
                tax_percent=validated["tax_percent"],
            )

        purchase.calculate_totals(
            purchase_discount=purchase_discount,
            purchase_tax=purchase_tax,
        )

        supplier.total_purchases += purchase.total_cost
        supplier.last_supply_date = timezone.now()
        supplier.save(update_fields=["total_purchases", "last_supply_date"])

        messages.success(
            request,
            f'Purchase "{purchase.reference_number}" created successfully.'
        )
        return redirect("view_purchase", purchase.id)

    context = {
        "business": business,
        "suppliers": suppliers,
        "products": products,
    }
    return render(request, "purchases/create_purchase.html", context)


@login_required
@require_POST
@transaction.atomic
def post_purchase(request, pk):
    business = get_business(request)

    purchase = get_object_or_404(
        Purchase.objects.select_for_update(),
        id=pk,
        business=business,
    )

    if purchase.status == "received":
        messages.warning(request, "Purchase already posted.")
        return redirect("view_purchase", pk=purchase.id)

    if purchase.status == "cancelled":
        messages.error(request, "Cannot post a cancelled purchase.")
        return redirect("view_purchase", pk=purchase.id)

    if not purchase.items.exists():
        messages.error(request, "Cannot post a purchase with no items.")
        return redirect("view_purchase", pk=purchase.id)

    purchase.post_purchase(user=request.user)

    messages.success(request, "Purchase posted successfully.")
    return redirect("view_purchase", pk=purchase.id)


@login_required
def view_purchase(request, pk):
    business = get_business(request)

    purchase = get_object_or_404(
        Purchase.objects.select_related("supplier", "created_by"),
        id=pk,
        business=business,
    )

    items = purchase.items.select_related("product")

    context = {
        "purchase": purchase,
        "items": items,
        "business": business,
    }

    return render(request, "purchases/view_purchase.html", context)


@login_required
def supplier_detail(request, pk):
    business = get_business(request)

    supplier = get_object_or_404(Supplier, id=pk, business=business)

    purchases_qs = Purchase.objects.filter(
        supplier=supplier,
        business=business,
    ).select_related("created_by").order_by("-created_at")

    total_purchase_amount = purchases_qs.aggregate(total=Sum("total_cost"))["total"] or 0
    total_paid = purchases_qs.aggregate(total=Sum("paid_amount"))["total"] or 0
    outstanding_amount = total_purchase_amount - total_paid
    total_orders = purchases_qs.count()

    paginator = Paginator(purchases_qs, 10)
    page_number = request.GET.get("page")
    purchases = paginator.get_page(page_number)

    context = {
        "business": business,
        "supplier": supplier,
        "purchases": purchases,
        "total_purchase_amount": total_purchase_amount,
        "total_orders": total_orders,
        "outstanding_amount": outstanding_amount,
        "total_paid": total_paid,
    }

    return render(request, "suppliers/supplier_detail.html", context)


@login_required
@transaction.atomic
def supplier_payment(request, purchase_id):
    business = get_business(request)

    # FIX: was missing business=business — any user could previously pay
    # against any business's purchase by ID alone.
    purchase = get_object_or_404(
        Purchase.objects.select_related("supplier"),
        id=purchase_id,
        business=business,
    )

    if request.method == "POST":
        # Lock the purchase row before validating against its balance, so
        # two concurrent payments can't both pass validation against the
        # same stale balance.
        locked_purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)

        form = SupplierPaymentForm(request.POST, purchase=locked_purchase)

        if form.is_valid():
            SupplierPayment.objects.create(
                supplier=locked_purchase.supplier,
                purchase=locked_purchase,
                amount_paid=form.cleaned_data["amount_paid"],
                payment_method=form.cleaned_data["payment_method"],
                external_reference=form.cleaned_data["external_reference"],
                note=form.cleaned_data["note"],
                created_by=request.user,
            )

            messages.success(request, "Supplier payment recorded successfully.")
            return redirect("view_purchase", purchase.id)
    else:
        form = SupplierPaymentForm(purchase=purchase)

    context = {
        "purchase": purchase,
        "business": business,
        "form": form,
    }

    return render(request, "suppliers/supplier_payment.html", context)


@login_required
def supplier_payment_history(request):
    business = get_business(request)

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
