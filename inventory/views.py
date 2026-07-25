from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.models import User

from business.models import Business
from inventory.models import *
from inventory.forms import *
from sales.models import *
from collections import OrderedDict
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

from django.db.models import Count
from django.db.models.functions import Coalesce
from datetime import timedelta
from django.db.models import F

import csv
from django.http import HttpResponse
import io
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from datetime import datetime, timedelta


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
                    quantity=-damaged_qty,
                    new_stock=new_stock,
                    action_type="damaged",
                    received_by=request.user,
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


def get_inventory_history_queryset(request, business):

    tab = request.GET.get("tab", "all").strip()

    if tab not in VALID_HISTORY_TABS:
        tab = "all"

    search = request.GET.get("search", "").strip()
    supplier = request.GET.get("supplier", "").strip()
    product = request.GET.get("product", "").strip()
    staff = request.GET.get("staff", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    queryset = (
        InventoryStockHistory.objects
        .filter(business=business)
        .select_related(
            "inventory",
            "supplier",
            "received_by",
        )
        .order_by("-created_at")
    )

    if tab != "all":
        queryset = queryset.filter(action_type=tab)

    if search:

        queryset = queryset.filter(

            Q(inventory__product_name__icontains=search)

            |

            Q(reference_number__icontains=search)

            |

            Q(invoice_number__icontains=search)

            |

            Q(reference__icontains=search)

            |

            Q(received_by__username__icontains=search)

            |

            Q(received_by__first_name__icontains=search)

            |

            Q(received_by__last_name__icontains=search)

        )

    if supplier:
        queryset = queryset.filter(supplier_id=supplier)

    if product:
        queryset = queryset.filter(inventory_id=product)

    if staff:
        queryset = queryset.filter(received_by_id=staff)

    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)

    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    return queryset


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

    # ============================================
    # FILTERS
    # ============================================

    tab = request.GET.get("tab", "all").strip()

    if tab not in VALID_HISTORY_TABS:
        tab = "all"

    search = request.GET.get("search", "").strip()

    supplier = request.GET.get("supplier", "").strip()

    product = request.GET.get("product", "").strip()

    staff = request.GET.get("staff", "").strip()

    date_from = request.GET.get("date_from", "").strip()

    date_to = request.GET.get("date_to", "").strip()

    queryset = get_inventory_history_queryset(
        request,
        business,
    )

    # ============================================
    # MOVEMENT TYPE
    # ============================================

    if tab != "all":
        queryset = queryset.filter(action_type=tab)

    # ============================================
    # SEARCH
    # ============================================

    if search:

        queryset = queryset.filter(

            Q(inventory__product_name__icontains=search) |

            Q(reference_number__icontains=search) |

            Q(invoice_number__icontains=search) |

            Q(reference__icontains=search) |

            Q(received_by__username__icontains=search) |

            Q(received_by__first_name__icontains=search) |

            Q(received_by__last_name__icontains=search)

        )

    # ============================================
    # PRODUCT
    # ============================================

    if product:

        queryset = queryset.filter(
            inventory_id=product
        )

    # ============================================
    # SUPPLIER
    # ============================================

    if supplier:

        queryset = queryset.filter(
            supplier_id=supplier
        )

    # ============================================
    # STAFF
    # ============================================

    if staff:

        queryset = queryset.filter(
            received_by_id=staff
        )

    # ============================================
    # DATE RANGE
    # ============================================

    if date_from:

        queryset = queryset.filter(
            created_at__date__gte=date_from
        )

    if date_to:

        queryset = queryset.filter(
            created_at__date__lte=date_to
        )

    # ============================================
    # KPI CALCULATIONS
    # ============================================

    today = timezone.now().date()

    history = InventoryStockHistory.objects.filter(
        business=business
    )

    total_movements = history.count()

    today_movements = history.filter(
        created_at__date=today
    ).count()

    total_stock_in = history.filter(

        action_type__in=[
            "restock",
            "returned",
        ]

    ).aggregate(

        total=Coalesce(
            Sum("quantity"),
            0
        )

    )["total"]

    total_stock_out = history.filter(

        action_type__in=[
            "sale",
            "damaged",
            "transfer",
        ]

    ).aggregate(

        total=Coalesce(
            Sum("quantity"),
            0
        )

    )["total"]

    adjustment_count = history.filter(
        action_type="adjustment"
    ).count()

    damaged_count = history.filter(
        action_type="damaged"
    ).count()

    transfer_count = history.filter(
        action_type="transfer"
    ).count()

    return_count = history.filter(
        action_type="returned"
    ).count()

    # ============================================
    # PAGINATION
    # ============================================

    paginator = Paginator(queryset, 20)

    page_number = request.GET.get("page")

    queryset = paginator.get_page(page_number)

    context = {

        "queryset": queryset,

        "tab": tab,

        "search": search,

        "supplier": supplier,

        "product": product,

        "staff": staff,

        "date_from": date_from,

        "date_to": date_to,

        "tabs": HISTORY_TABS,

        "business": business,

        "title": "Inventory History",

        # KPI

        "total_movements": total_movements,

        "today_movements": today_movements,

        "total_stock_in": total_stock_in,

        "total_stock_out": total_stock_out,

        "adjustment_count": adjustment_count,

        "damaged_count": damaged_count,

        "transfer_count": transfer_count,

        "return_count": return_count,

        # FILTER DROPDOWNS

        "products": Inventory.objects.filter(
            business=business
        ).order_by("product_name"),

        "suppliers": Supplier.objects.filter(
            business=business,
            is_active=True,
        ).order_by("name"),

        "staffs": User.objects.filter(
            staffprofile__business=business
        ).distinct(),

    }

    return render(

        request,

        "inventory/inventory_history.html",

        context,

    )


@login_required
def export_inventory_history_csv(request):

    business = get_business(request)

    queryset = get_inventory_history_queryset(
        request,
        business,
    )

    response = HttpResponse(
        content_type="text/csv"
    )

    response[
        "Content-Disposition"
    ] = 'attachment; filename="inventory_history.csv"'

    writer = csv.writer(response)

    writer.writerow([
        "Product",
        "Movement",
        "Previous Stock",
        "Quantity",
        "Current Stock",
        "Supplier",
        "Invoice",
        "Warehouse",
        "Reference",
        "Performed By",
        "Remarks",
        "Date",
    ])

    for record in queryset:

        writer.writerow([

            record.inventory.product_name
            if record.inventory else "",

            record.get_action_type_display(),

            record.previous_stock,
            record.quantity,
            record.new_stock,
            record.supplier_name,
            record.invoice_number,
            record.warehouse,
            record.reference_number,
            record.received_by_name,
            record.remarks,
            record.created_at.strftime(
                "%d %b %Y %H:%M"
            ),

        ])

    return response


@login_required
def export_inventory_history_pdf(request):

    business = get_business(request)

    queryset = get_inventory_history_queryset(
        request,
        business,
    )

    tab = request.GET.get("tab", "all").strip()
    if tab not in VALID_HISTORY_TABS:
        tab = "all"

    tab_label = dict(HISTORY_TABS).get(tab, "All Activity")

    context = {
        "records": queryset,
        "business": business,
        "tab_label": tab_label,
        "generated_at": timezone.now(),
        "search": request.GET.get("search", "").strip(),
        "supplier": request.GET.get("supplier", "").strip(),
        "product": request.GET.get("product", "").strip(),
        "staff": request.GET.get("staff", "").strip(),
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
        "total_records": queryset.count(),
    }

    html = render_to_string(
        "inventory/inventory_history_pdf.html",
        context,
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        'attachment; filename="inventory_history.pdf"'
    )

    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        src=html,
        dest=result,
    )

    if pisa_status.err:
        return HttpResponse(
            "Error generating PDF",
            status=500,
        )

    response.write(result.getvalue())
    return response


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

            # NEW — optional per-line expiry date
            expiry_date = None
            raw_expiry = (item.get("expiry") or "").strip()

            if raw_expiry:
                try:
                    expiry_date = datetime.strptime(raw_expiry, "%Y-%m-%d").date()
                except ValueError:
                    messages.error(request, f"Item {index}: expiry date is not a valid date.")
                    return render(request, "purchases/create_purchase.html", {
                        "business": business, "suppliers": suppliers, "products": products,
                    })

                if expiry_date <= timezone.now().date():
                    messages.error(request, f"Item {index}: expiry date must be in the future.")
                    return render(request, "purchases/create_purchase.html", {
                        "business": business, "suppliers": suppliers, "products": products,
                    })

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
                "expiry_date": expiry_date,  # NEW
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
                expiry_date=validated["expiry_date"],
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

    # NEW — batches auto-created when this purchase was received
    batches = purchase.batches_created.select_related("product").order_by("expiry_date")

    context = {
        "purchase": purchase,
        "items": items,
        "batches": batches,   # NEW
        "business": business,
    }

    return render(request, "purchases/view_purchase.html", context)


@login_required
def purchase_list(request):
    business = get_business(request)

    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()

    purchases = Purchase.objects.filter(
        business=business
    ).select_related("supplier", "created_by").order_by("-created_at")

    if search:
        purchases = purchases.filter(
            Q(reference_number__icontains=search) |
            Q(supplier__name__icontains=search)
        )

    if status in ["draft", "pending", "received", "cancelled"]:
        purchases = purchases.filter(status=status)

    total_purchases = purchases.count()

    total_value = purchases.aggregate(
        total=Coalesce(Sum("total_cost"), Decimal("0.00"))
    )["total"]

    total_outstanding = purchases.aggregate(
        total=Coalesce(Sum(F("total_cost") - F("paid_amount")), Decimal("0.00"))
    )["total"]

    paginator = Paginator(purchases, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "purchases": page_obj,
        "search": search,
        "status": status,
        "total_purchases": total_purchases,
        "total_value": total_value,
        "total_outstanding": total_outstanding,
        "business": business,
        "title": "Purchases",
    }

    return render(request, "purchases/purchase_list.html", context)


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



# =====================================
# EXPIRY MANAGEMENT
# =====================================

def _get_expiry_queryset(request, business):
    """Shared filtering logic for the dashboard view and the CSV export,
    so the two can never silently drift apart."""

    tab = request.GET.get("tab", "all").strip()
    search = request.GET.get("search", "").strip()
    product_id = request.GET.get("product", "").strip()
    supplier_id = request.GET.get("supplier", "").strip()

    queryset = ProductBatch.objects.filter(
        business=business, status="active"
    ).select_related("product", "supplier").order_by("expiry_date")

    if search:
        queryset = queryset.filter(
            Q(product__product_name__icontains=search) |
            Q(batch_number__icontains=search)
        )

    if product_id:
        queryset = queryset.filter(product_id=product_id)

    if supplier_id:
        queryset = queryset.filter(supplier_id=supplier_id)

    today = timezone.now().date()
    warning_cutoff = today + timedelta(days=ProductBatch.NEAR_EXPIRY_WARNING_DAYS)
    critical_cutoff = today + timedelta(days=ProductBatch.NEAR_EXPIRY_CRITICAL_DAYS)

    if tab == "expired":
        queryset = queryset.filter(expiry_date__lt=today)
    elif tab == "critical":
        queryset = queryset.filter(expiry_date__gte=today, expiry_date__lte=critical_cutoff)
    elif tab == "warning":
        queryset = queryset.filter(expiry_date__gt=critical_cutoff, expiry_date__lte=warning_cutoff)
    elif tab == "healthy":
        queryset = queryset.filter(expiry_date__gt=warning_cutoff)

    return queryset


@login_required
def expiry_dashboard(request):

    business = get_business(request)

    queryset = _get_expiry_queryset(request, business)

    today = timezone.now().date()
    warning_cutoff = today + timedelta(days=ProductBatch.NEAR_EXPIRY_WARNING_DAYS)
    critical_cutoff = today + timedelta(days=ProductBatch.NEAR_EXPIRY_CRITICAL_DAYS)

    # KPI counts always reflect the FULL active set, not the tab-filtered
    # queryset — so the tab counters stay accurate no matter which tab
    # you're currently viewing.
    base_active = ProductBatch.objects.filter(business=business, status="active")

    expired_count = base_active.filter(expiry_date__lt=today).count()
    critical_count = base_active.filter(expiry_date__gte=today, expiry_date__lte=critical_cutoff).count()
    warning_count = base_active.filter(expiry_date__gt=critical_cutoff, expiry_date__lte=warning_cutoff).count()
    healthy_count = base_active.filter(expiry_date__gt=warning_cutoff).count()
    total_batches = base_active.count()

    value_at_risk = base_active.filter(
        expiry_date__lte=warning_cutoff
    ).aggregate(
        total=Coalesce(Sum(F("quantity") * F("cost_price")), Decimal("0.00"))
    )["total"]

    paginator = Paginator(queryset, 20)
    batches = paginator.get_page(request.GET.get("page"))

    context = {
        "batches": batches,
        "tab": request.GET.get("tab", "all").strip(),
        "search": request.GET.get("search", "").strip(),
        "product_id": request.GET.get("product", "").strip(),
        "supplier_id": request.GET.get("supplier", "").strip(),

        "total_batches": total_batches,
        "expired_count": expired_count,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "healthy_count": healthy_count,
        "value_at_risk": value_at_risk,

        "products": Inventory.objects.filter(business=business).order_by("product_name"),
        "suppliers": Supplier.objects.filter(business=business, is_active=True).order_by("name"),

        "dispose_form": DisposeBatchForm(),

        "business": business,
        "title": "Expiry Management",
    }

    return render(request, "inventory/expiry_dashboard.html", context)


@login_required
@transaction.atomic
def add_batch(request):

    business = get_business(request)

    initial = {}
    preselected_product = request.GET.get("product")
    if preselected_product:
        initial["product"] = preselected_product

    form = ProductBatchForm(business=business, initial=initial)

    if request.method == "POST":
        form = ProductBatchForm(request.POST, business=business)

        if form.is_valid():
            also_add_to_stock = form.cleaned_data.pop("also_add_to_stock", False)

            batch = form.save(commit=False)
            batch.business = business
            batch.save()

            if also_add_to_stock:
                locked_product = Inventory.objects.select_for_update().get(pk=batch.product_id)
                previous_stock = locked_product.stock_quantity
                new_stock = previous_stock + batch.quantity

                locked_product.stock_quantity = new_stock
                locked_product.save(update_fields=["stock_quantity", "updated_at"])

                InventoryStockHistory.objects.create(
                    business=business,
                    inventory=locked_product,
                    previous_stock=previous_stock,
                    quantity=batch.quantity,
                    new_stock=new_stock,
                    action_type="restock",
                    supplier=batch.supplier,
                    received_by=request.user,
                    received_date=batch.received_date,
                    reference_number=batch.batch_number,
                    remarks=f"Batch {batch.batch_number} received (expiry tracked)",
                )

            AuditLog.objects.create(
                user=request.user,
                action="Batch Added",
                description=(
                    f"{request.user.username} added batch '{batch.batch_number}' "
                    f"for '{batch.product.product_name}' — {batch.quantity} unit(s), "
                    f"expiring {batch.expiry_date}."
                ),
                content_type=ContentType.objects.get_for_model(ProductBatch),
                object_id=batch.id,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            messages.success(request, f'Batch "{batch.batch_number}" added successfully.')
            return redirect("expiry_dashboard")

    context = {
        "form": form,
        "business": business,
        "title": "Add Batch",
    }
    return render(request, "inventory/add_batch.html", context)


@login_required
@require_POST
@transaction.atomic
def dispose_batch(request, pk):

    business = get_business(request)

    batch = get_object_or_404(
        ProductBatch.objects.select_for_update(),
        pk=pk, business=business, status="active",
    )

    form = DisposeBatchForm(request.POST, batch=batch)

    if not form.is_valid():
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
        return redirect("expiry_dashboard")

    qty = form.cleaned_data["quantity"]
    reason = form.cleaned_data["reason"]

    locked_product = Inventory.objects.select_for_update().get(pk=batch.product_id)
    previous_stock = locked_product.stock_quantity

    # Defensive: never push stock negative even if this batch's tracked
    # quantity has drifted from the product's real stock over time.
    deduction = min(qty, previous_stock)
    new_stock = previous_stock - deduction

    locked_product.stock_quantity = new_stock
    locked_product.save(update_fields=["stock_quantity", "updated_at"])

    InventoryStockHistory.objects.create(
        business=business,
        inventory=locked_product,
        previous_stock=previous_stock,
        quantity=-deduction,
        new_stock=new_stock,
        action_type="expired",
        received_by=request.user,
        reference_number=batch.batch_number,
        remarks=reason or f"Batch {batch.batch_number} disposed (expired)",
    )

    batch.disposed_quantity += qty
    batch.quantity -= qty
    batch.disposal_reason = reason
    batch.disposed_by = request.user
    batch.disposed_at = timezone.now()

    if batch.quantity <= 0:
        batch.quantity = 0
        batch.status = "disposed"

    batch.save()

    AuditLog.objects.create(
        user=request.user,
        action="Batch Disposed",
        description=(
            f"{request.user.username} disposed {qty} unit(s) of batch "
            f"'{batch.batch_number}' ({locked_product.product_name}). "
            f"Reason: {reason or 'Expired'}"
        ),
        content_type=ContentType.objects.get_for_model(ProductBatch),
        object_id=batch.id,
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    generate_business_alerts(business)

    messages.success(
        request,
        f'{qty} unit(s) of batch "{batch.batch_number}" disposed and removed from stock.'
    )
    return redirect("expiry_dashboard")


@login_required
def export_expiry_csv(request):

    business = get_business(request)
    queryset = _get_expiry_queryset(request, business)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="expiry_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Product", "Batch Number", "Quantity", "Cost Price", "Batch Value",
        "Expiry Date", "Days To Expiry", "Status", "Supplier", "Received Date",
    ])

    for batch in queryset:
        writer.writerow([
            batch.product.product_name,
            batch.batch_number,
            batch.quantity,
            batch.cost_price,
            batch.batch_value,
            batch.expiry_date.strftime("%d %b %Y"),
            batch.days_to_expiry,
            batch.expiry_status.title(),
            batch.supplier_name,
            batch.received_date.strftime("%d %b %Y") if batch.received_date else "-",
        ])

    return response


def _sales_window_stats(sale_items_queryset):
    """Sum units/revenue/profit net of refunds, using the model's own
    remaining_* properties rather than raw quantity — a fully or
    partially refunded item should not count as sold."""

    units = 0
    revenue = Decimal("0.00")
    profit = Decimal("0.00")

    for item in sale_items_queryset:
        units += item.remaining_quantity
        revenue += item.remaining_total
        profit += item.remaining_profit

    return units, revenue, profit


@login_required
def product_intelligence(request, pk):

    business = get_business(request)

    product = get_object_or_404(
        Inventory.objects.select_related("category"),
        pk=pk,
        business=business,
    )

    today = timezone.now().date()

    # =====================================
    # STOCK MOVEMENT HISTORY
    # =====================================
    history = (
        InventoryStockHistory.objects
        .filter(business=business, inventory=product)
        .select_related("supplier", "received_by")
        .order_by("-created_at")
    )

    recent_movements = history[:15]

    restock_history = history.filter(action_type="restock")
    damage_history = history.filter(action_type="damaged")
    return_history = history.filter(action_type="returned")

    total_restocked = restock_history.aggregate(
        total=Coalesce(Sum("quantity"), 0)
    )["total"]

    monthly_restocked = restock_history.filter(
        created_at__month=today.month,
        created_at__year=today.year,
    ).aggregate(total=Coalesce(Sum("quantity"), 0))["total"]

    total_damaged = abs(
        damage_history.aggregate(total=Coalesce(Sum("quantity"), 0))["total"]
    )

    average_purchase_cost = (
        restock_history.exclude(purchase_cost=0)
        .aggregate(avg=Avg("purchase_cost"))["avg"]
        or product.cost_price
    )

    last_restock = restock_history.first()
    last_damage = damage_history.first()

    # =====================================
    # SUPPLIER BREAKDOWN
    # =====================================
    supplier_breakdown = (
        restock_history.filter(supplier__isnull=False)
        .values("supplier__id", "supplier__name")
        .annotate(total_qty=Sum("quantity"), orders=Count("id"))
        .order_by("-total_qty")[:5]
    )

    # =====================================
    # EXPIRY / BATCHES
    # =====================================
    active_batches = list(
        ProductBatch.objects
        .filter(business=business, product=product, status="active")
        .order_by("expiry_date")
    )

    expired_batches_count = sum(1 for b in active_batches if b.expiry_status == "expired")
    critical_batches_count = sum(1 for b in active_batches if b.expiry_status == "critical")
    warning_batches_count = sum(1 for b in active_batches if b.expiry_status == "warning")

    expiry_value_at_risk = sum(
        b.batch_value for b in active_batches
        if b.expiry_status in ("expired", "critical", "warning")
    ) or Decimal("0.00")

    nearest_expiry = active_batches[0] if active_batches else None

    # =====================================
    # SALES HISTORY + VELOCITY
    # =====================================
    sale_items = (
        SaleItem.objects
        .filter(product=product, sale__business=business,
                sale__status__in=["Completed", "Partially Refunded", "Refunded"])
        .select_related("sale", "sale__customer")
        .order_by("-sale__created_at")
    )

    last_30 = list(sale_items.filter(sale__created_at__date__gte=today - timedelta(days=30)))
    last_90 = list(sale_items.filter(sale__created_at__date__gte=today - timedelta(days=90)))

    units_sold_30d, revenue_30d, profit_30d = _sales_window_stats(last_30)
    units_sold_90d, revenue_90d, profit_90d = _sales_window_stats(last_90)
    all_time_units, all_time_revenue, all_time_profit = _sales_window_stats(sale_items)

    recent_sales = sale_items[:10]

    avg_daily_units_30d = (units_sold_30d / 30) if units_sold_30d else 0

    # =====================================
    # FORECAST
    # =====================================
    if avg_daily_units_30d > 0:
        days_of_stock_left = round(product.stock_quantity / avg_daily_units_30d, 1)
    else:
        days_of_stock_left = None

    if product.maximum_stock and product.maximum_stock > product.stock_quantity:
        suggested_reorder_qty = product.maximum_stock - product.stock_quantity
    else:
        suggested_reorder_qty = product.reorder_quantity or 0

    if days_of_stock_left is None:
        forecast_status = "insufficient_data"
    elif days_of_stock_left <= 7:
        forecast_status = "critical"
    elif days_of_stock_left <= 21:
        forecast_status = "watch"
    else:
        forecast_status = "healthy"

    # =====================================
    # CHART DATA
    # =====================================
    chart_movements = list(history.order_by("created_at")[:60])
    stock_chart_labels = [m.created_at.strftime("%d %b") for m in chart_movements]
    stock_chart_values = [m.new_stock for m in chart_movements]

    sales_by_day = OrderedDict()
    cursor = today - timedelta(days=29)
    while cursor <= today:
        sales_by_day[cursor] = 0
        cursor += timedelta(days=1)

    for item in last_30:
        day = item.sale.created_at.date()
        if day in sales_by_day:
            sales_by_day[day] += item.remaining_quantity

    sales_chart_labels = [d.strftime("%d %b") for d in sales_by_day.keys()]
    sales_chart_values = list(sales_by_day.values())

    # =====================================
    # ALERTS (product-specific, rule-based)
    # =====================================
    alerts = []

    if product.is_out_of_stock:
        alerts.append({"type": "danger", "icon": "fas fa-circle-xmark",
                        "message": "This product is completely out of stock."})
    elif product.is_low_stock:
        alerts.append({"type": "warning", "icon": "fas fa-triangle-exclamation",
                        "message": f"Stock is at or below the minimum threshold ({product.minimum_stock})."})

    if product.maximum_stock and product.stock_quantity >= product.maximum_stock:
        alerts.append({"type": "info", "icon": "fas fa-box-archive",
                        "message": "Stock is at or above the configured maximum — consider pausing restocks."})

    if expired_batches_count:
        alerts.append({"type": "danger", "icon": "fas fa-skull-crossbones",
                        "message": f"{expired_batches_count} batch(es) have already expired and should be disposed."})

    if critical_batches_count:
        alerts.append({"type": "warning", "icon": "fas fa-clock",
                        "message": f"{critical_batches_count} batch(es) expire within 7 days."})

    if forecast_status == "critical":
        alerts.append({"type": "danger", "icon": "fas fa-hourglass-end",
                        "message": f"At current sales velocity, stock runs out in about {days_of_stock_left} day(s)."})
    elif forecast_status == "watch":
        alerts.append({"type": "warning", "icon": "fas fa-hourglass-half",
                        "message": f"Stock is projected to last about {days_of_stock_left} day(s) — plan a reorder."})

    if not alerts:
        alerts.append({"type": "success", "icon": "fas fa-circle-check",
                        "message": "No active risks detected for this product right now."})

    context = {
        "product": product,
        "business": business,

        "recent_movements": recent_movements,
        "total_restocked": total_restocked,
        "monthly_restocked": monthly_restocked,
        "last_restock": last_restock,
        "average_purchase_cost": average_purchase_cost,

        "damage_history": damage_history[:10],
        "total_damaged": total_damaged,
        "damage_count": damage_history.count(),
        "last_damage": last_damage,

        "return_count": return_history.count(),

        "supplier_breakdown": supplier_breakdown,

        "active_batches": active_batches,
        "expired_batches_count": expired_batches_count,
        "critical_batches_count": critical_batches_count,
        "warning_batches_count": warning_batches_count,
        "expiry_value_at_risk": expiry_value_at_risk,
        "nearest_expiry": nearest_expiry,

        "recent_sales": recent_sales,
        "units_sold_30d": units_sold_30d,
        "revenue_30d": revenue_30d,
        "profit_30d": profit_30d,
        "units_sold_90d": units_sold_90d,
        "all_time_units": all_time_units,
        "all_time_revenue": all_time_revenue,

        "days_of_stock_left": days_of_stock_left,
        "suggested_reorder_qty": suggested_reorder_qty,
        "forecast_status": forecast_status,

        "stock_chart_labels": json.dumps(stock_chart_labels),
        "stock_chart_values": json.dumps(stock_chart_values),
        "sales_chart_labels": json.dumps(sales_chart_labels),
        "sales_chart_values": json.dumps(sales_chart_values),

        "alerts": alerts,

        "title": f"{product.product_name} — Intelligence",
    }

    return render(request, "inventory/product_intelligence.html", context)

