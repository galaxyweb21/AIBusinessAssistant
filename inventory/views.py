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
from .forms import LabelTemplateForm


# =============================================
# HELPER FUNCTIONS
# =============================================

def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')



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


# inventory/views.py - Purchase Module

def _generate_purchase_reference():
    """Generate a unique purchase reference."""
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"PUR-{timestamp}-{suffix}"


def _generate_po_reference():
    """Generate a unique purchase order reference."""
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"PO-{timestamp}-{suffix}"


def _generate_grn_reference():
    """Generate a unique goods receipt reference."""
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"GRN-{timestamp}-{suffix}"


# =============================================
# PURCHASE VIEWS
# =============================================

@login_required
@transaction.atomic
def create_purchase(request):
    """Create a new purchase (vendor invoice)."""
    business = get_business(request)

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by("name")
    products = Inventory.objects.filter(business=business, status="active").order_by("product_name")

    if request.method == "POST":
        supplier_id = request.POST.get("supplier")
        supplier = get_object_or_404(Supplier, id=supplier_id, business=business)

        try:
            items_data = json.loads(request.POST.get("items_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            messages.error(request, "Invalid item data. Please try again.")
            return render(request, "purchases/create_purchase.html", {
                "business": business,
                "suppliers": suppliers,
                "products": products,
            })

        if not items_data:
            messages.error(request, "Add at least one item to the purchase.")
            return render(request, "purchases/create_purchase.html", {
                "business": business,
                "suppliers": suppliers,
                "products": products,
            })

        # Validate and build items
        validated_items = []
        for idx, item in enumerate(items_data, 1):
            try:
                product_id = int(item.get("product_id"))
                qty = int(item.get("qty", 0))
                cost = Decimal(str(item.get("cost", 0)))
                discount = Decimal(str(item.get("discount", 0)))
                tax_percent = Decimal(str(item.get("tax", 0)))
                expiry = item.get("expiry") or None
            except (ValueError, InvalidOperation) as e:
                messages.error(request, f"Item {idx}: Invalid data format.")
                return render(request, "purchases/create_purchase.html", {
                    "business": business, "suppliers": suppliers, "products": products
                })

            if qty <= 0:
                messages.error(request, f"Item {idx}: Quantity must be greater than zero.")
                return render(request, "purchases/create_purchase.html", {
                    "business": business, "suppliers": suppliers, "products": products
                })

            if cost < 0 or discount < 0 or tax_percent < 0:
                messages.error(request, f"Item {idx}: Negative values not allowed.")
                return render(request, "purchases/create_purchase.html", {
                    "business": business, "suppliers": suppliers, "products": products
                })

            product = get_object_or_404(Inventory, id=product_id, business=business)

            # Validate expiry date
            if expiry:
                try:
                    expiry_date = timezone.datetime.strptime(expiry, "%Y-%m-%d").date()
                    if expiry_date <= timezone.now().date():
                        messages.error(request, f"Item {idx}: Expiry date must be in the future.")
                        return render(request, "purchases/create_purchase.html", {
                            "business": business, "suppliers": suppliers, "products": products
                        })
                except ValueError:
                    messages.error(request, f"Item {idx}: Invalid expiry date format.")
                    return render(request, "purchases/create_purchase.html", {
                        "business": business, "suppliers": suppliers, "products": products
                    })
            else:
                expiry_date = None

            validated_items.append({
                "product": product,
                "qty": qty,
                "cost": cost,
                "discount": discount,
                "tax_percent": tax_percent,
                "expiry_date": expiry_date,
            })

        # Get purchase-level discounts
        purchase_discount = Decimal(str(request.POST.get("purchase_discount", "0") or "0"))
        purchase_tax = Decimal(str(request.POST.get("purchase_tax", "0") or "0"))

        # Create purchase
        purchase = Purchase.objects.create(
            business=business,
            supplier=supplier,
            reference_number=_generate_purchase_reference(),
            created_by=request.user,
            purchase_discount=purchase_discount,
            purchase_tax_percent=purchase_tax,
            status="pending",
        )

        # Create purchase items
        for item in validated_items:
            PurchaseItem.objects.create(
                purchase=purchase,
                product=item["product"],
                quantity=item["qty"],
                unit_cost=item["cost"],
                discount=item["discount"],
                tax_percent=item["tax_percent"],
                expiry_date=item["expiry_date"],
            )

        # Calculate totals
        purchase.calculate_totals()

        # Update supplier metrics
        supplier.total_purchases += purchase.total_cost
        supplier.last_supply_date = timezone.now()
        supplier.save(update_fields=["total_purchases", "last_supply_date"])

        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action="Purchase Created",
            description=f"{request.user.username} created purchase {purchase.reference_number} from {supplier.name}.",
            content_type=ContentType.objects.get_for_model(Purchase),
            object_id=purchase.id,
            ip_address=get_client_ip(request),
        )

        messages.success(request, f'Purchase "{purchase.reference_number}" created successfully.')
        return redirect("view_purchase", purchase.id)

    context = {
        "business": business,
        "suppliers": suppliers,
        "products": products,
        "title": "Create Purchase",
    }
    return render(request, "purchases/create_purchase.html", context)


@login_required
def purchase_list(request):
    """List all purchases with filtering."""
    business = get_business(request)

    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    purchases = Purchase.objects.filter(
        business=business
    ).select_related("supplier", "created_by").order_by("-created_at")

    if search:
        purchases = purchases.filter(
            Q(reference_number__icontains=search) |
            Q(supplier__name__icontains=search)
        )

    if status_filter in ["draft", "pending", "received", "cancelled"]:
        purchases = purchases.filter(status=status_filter)

    # KPIs
    total_purchases = purchases.count()
    total_value = purchases.aggregate(total=Sum("total_cost"))["total"] or Decimal("0.00")
    total_outstanding = purchases.aggregate(
        total=Sum(F("total_cost") - F("paid_amount"))
    )["total"] or Decimal("0.00")

    # Pagination
    paginator = Paginator(purchases, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "purchases": page_obj,
        "search": search,
        "status": status_filter,
        "total_purchases": total_purchases,
        "total_value": total_value,
        "total_outstanding": total_outstanding,
        "business": business,
        "title": "Purchases",
    }
    return render(request, "purchases/purchase_list.html", context)


@login_required
def view_purchase(request, pk):
    """View purchase details."""
    business = get_business(request)

    purchase = get_object_or_404(
        Purchase.objects.select_related("supplier", "created_by"),
        id=pk,
        business=business,
    )

    items = purchase.items.select_related("product")
    batches = purchase.batches_created.select_related("product").order_by("expiry_date")
    payments = purchase.payments.all().order_by("-created_at")

    context = {
        "purchase": purchase,
        "items": items,
        "batches": batches,
        "payments": payments,
        "business": business,
        "title": f"Purchase {purchase.reference_number}",
    }
    return render(request, "purchases/view_purchase.html", context)


@login_required
@require_POST
@transaction.atomic
def post_purchase(request, pk):
    """Post/receive a purchase - updates inventory."""
    business = get_business(request)

    purchase = get_object_or_404(
        Purchase.objects.select_for_update(),
        id=pk,
        business=business,
    )

    try:
        purchase.post_purchase(user=request.user)
        messages.success(request, "Purchase received successfully. Inventory updated.")
    except Exception as e:
        messages.error(request, str(e))

    return redirect("view_purchase", pk=purchase.id)


# =============================================
# PURCHASE ORDER VIEWS
# =============================================

@login_required
@transaction.atomic
def create_purchase_order(request):
    """Create a new purchase order."""
    business = get_business(request)

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by("name")
    products = Inventory.objects.filter(business=business, status="active").order_by("product_name")

    if request.method == "POST":
        supplier_id = request.POST.get("supplier")
        supplier = get_object_or_404(Supplier, id=supplier_id, business=business)

        try:
            items_data = json.loads(request.POST.get("items_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            messages.error(request, "Invalid item data.")
            return render(request, "purchases/create_purchase_order.html", {
                "business": business, "suppliers": suppliers, "products": products
            })

        if not items_data:
            messages.error(request, "Add at least one item.")
            return render(request, "purchases/create_purchase_order.html", {
                "business": business, "suppliers": suppliers, "products": products
            })

        # Create PO
        po = PurchaseOrder.objects.create(
            business=business,
            supplier=supplier,
            reference_number=_generate_po_reference(),
            created_by=request.user,
            expected_date=request.POST.get("expected_date") or None,
            notes=request.POST.get("notes", "").strip(),
            status="issued",
        )

        # Create PO items
        for item in items_data:
            product = get_object_or_404(Inventory, id=item.get("product_id"), business=business)
            expiry = item.get("expiry") or None

            PurchaseOrderItem.objects.create(
                po=po,
                product=product,
                quantity=int(item.get("qty", 0)),
                unit_cost=Decimal(str(item.get("cost", 0))),
                discount=Decimal(str(item.get("discount", 0))),
                tax_percent=Decimal(str(item.get("tax", 0))),
                expiry_date=expiry,
            )

        # Audit log
        AuditLog.objects.create(
            user=request.user,
            action="Purchase Order Created",
            description=f"{request.user.username} created PO {po.reference_number}.",
            content_type=ContentType.objects.get_for_model(PurchaseOrder),
            object_id=po.id,
            ip_address=get_client_ip(request),
        )

        messages.success(request, f'Purchase Order "{po.reference_number}" created successfully.')
        return redirect("view_purchase_order", po.id)

    context = {
        "business": business,
        "suppliers": suppliers,
        "products": products,
        "title": "Create Purchase Order",
    }
    return render(request, "purchases/create_purchase_order.html", context)


@login_required
def purchase_order_list(request):
    """List all purchase orders."""
    business = get_business(request)

    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    orders = PurchaseOrder.objects.filter(
        business=business
    ).select_related("supplier", "created_by").order_by("-created_at")

    if search:
        orders = orders.filter(
            Q(reference_number__icontains=search) |
            Q(supplier__name__icontains=search)
        )

    if status_filter:
        orders = orders.filter(status=status_filter)

    # KPIs
    total_orders = orders.count()
    pending_orders = orders.filter(status__in=["draft", "issued", "partially_received"]).count()
    received_orders = orders.filter(status="received").count()
    total_value = orders.aggregate(total=Sum("items__total_cost"))["total"] or Decimal("0.00")

    paginator = Paginator(orders, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "search": search,
        "status": status_filter,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "received_orders": received_orders,
        "total_value": total_value,
        "business": business,
        "title": "Purchase Orders",
    }
    return render(request, "purchases/purchase_order_list.html", context)


@login_required
def view_purchase_order(request, pk):
    """View purchase order details."""
    business = get_business(request)

    po = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier", "created_by"),
        id=pk,
        business=business,
    )

    items = po.items.select_related("product")

    context = {
        "po": po,
        "items": items,
        "business": business,
        "title": f"PO {po.reference_number}",
    }
    return render(request, "purchases/view_purchase_order.html", context)


# =============================================
# GOODS RECEIPT VIEWS
# =============================================

@login_required
@transaction.atomic
def create_goods_receipt(request, po_pk=None):
    """Create a goods receipt from a purchase order or standalone."""
    business = get_business(request)

    po = None
    if po_pk:
        po = get_object_or_404(PurchaseOrder, pk=po_pk, business=business)

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by("name")
    products = Inventory.objects.filter(business=business, status="active").order_by("product_name")

    if request.method == "POST":
        supplier_id = request.POST.get("supplier")
        if po:
            supplier = po.supplier
        else:
            supplier = get_object_or_404(Supplier, id=supplier_id, business=business)

        try:
            items_data = json.loads(request.POST.get("items_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            messages.error(request, "Invalid item data.")
            return render(request, "purchases/create_goods_receipt.html", {
                "business": business, "suppliers": suppliers, "products": products, "po": po
            })

        if not items_data:
            messages.error(request, "Add at least one item.")
            return render(request, "purchases/create_goods_receipt.html", {
                "business": business, "suppliers": suppliers, "products": products, "po": po
            })

        # Create Purchase (for inventory posting)
        purchase = Purchase.objects.create(
            business=business,
            supplier=supplier,
            reference_number=_generate_purchase_reference(),
            created_by=request.user,
            status="received",
        )

        # Create GRN
        grn = GoodsReceipt.objects.create(
            business=business,
            purchase_order=po,
            purchase=purchase,
            receipt_number=_generate_grn_reference(),
            received_by=request.user,
            received_at=timezone.now(),
            notes=request.POST.get("notes", "").strip(),
            status="received",
        )

        # Create items
        for item in items_data:
            product = get_object_or_404(Inventory, id=item.get("product_id"), business=business)
            qty = int(item.get("qty", 0))
            unit_cost = Decimal(str(item.get("cost", 0)))
            expiry = item.get("expiry") or None

            # Purchase item
            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                quantity=qty,
                unit_cost=unit_cost,
                discount=Decimal("0.00"),
                tax_percent=Decimal("0.00"),
                expiry_date=expiry,
            )

            # GRN item
            GoodsReceiptItem.objects.create(
                grn=grn,
                product=product,
                quantity=qty,
                unit_cost=unit_cost,
                expiry_date=expiry,
            )

        # Calculate totals and post
        purchase.calculate_totals()
        purchase.post_purchase(user=request.user)

        # Update PO status
        if po:
            po.status = "received"
            po.save(update_fields=["status"])

        # Audit log
        AuditLog.objects.create(
            user=request.user,
            action="Goods Receipt Created",
            description=f"{request.user.username} received goods via {grn.receipt_number}.",
            content_type=ContentType.objects.get_for_model(GoodsReceipt),
            object_id=grn.id,
            ip_address=get_client_ip(request),
        )

        messages.success(request, f'Goods receipt "{grn.receipt_number}" created successfully.')
        return redirect("view_goods_receipt", grn.id)

    context = {
        "business": business,
        "suppliers": suppliers,
        "products": products,
        "po": po,
        "title": "Create Goods Receipt",
    }
    return render(request, "purchases/create_goods_receipt.html", context)


@login_required
def goods_receipt_list(request):
    """List all goods receipts."""
    business = get_business(request)

    search = request.GET.get("search", "").strip()

    receipts = GoodsReceipt.objects.filter(
        business=business
    ).select_related("purchase_order", "purchase", "received_by").order_by("-created_at")

    if search:
        receipts = receipts.filter(
            Q(receipt_number__icontains=search) |
            Q(purchase__reference_number__icontains=search) |
            Q(purchase_order__reference_number__icontains=search)
        )

    # KPIs
    total_receipts = receipts.count()
    today_receipts = receipts.filter(received_at__date=timezone.now().date()).count()
    pending_receipts = receipts.filter(status="draft").count()
    total_value = receipts.aggregate(
        total=Sum("purchase__total_cost")
    )["total"] or Decimal("0.00")

    paginator = Paginator(receipts, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "search": search,
        "total_receipts": total_receipts,
        "today_receipts": today_receipts,
        "pending_receipts": pending_receipts,
        "total_value": total_value,
        "business": business,
        "title": "Goods Receipts",
    }
    return render(request, "purchases/goods_receipt_list.html", context)


@login_required
def view_goods_receipt(request, pk):
    """View goods receipt details."""
    business = get_business(request)

    grn = get_object_or_404(
        GoodsReceipt.objects.select_related("purchase_order", "purchase", "received_by"),
        id=pk,
        business=business,
    )

    items = grn.items.select_related("product")

    context = {
        "grn": grn,
        "items": items,
        "business": business,
        "title": f"GRN {grn.receipt_number}",
    }
    return render(request, "purchases/view_goods_receipt.html", context)


# =============================================
# SUPPLIER PAYMENT VIEWS
# =============================================



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
    """Record a supplier payment."""
    business = get_business(request)

    purchase = get_object_or_404(
        Purchase.objects.select_related("supplier"),
        id=purchase_id,
        business=business,
    )

    if request.method == "POST":
        form = SupplierPaymentForm(request.POST, purchase=purchase)

        if form.is_valid():
            # Create payment
            payment = SupplierPayment.objects.create(
                supplier=purchase.supplier,
                purchase=purchase,
                amount_paid=form.cleaned_data["amount_paid"],
                payment_method=form.cleaned_data["payment_method"],
                external_reference=form.cleaned_data["external_reference"],
                note=form.cleaned_data["note"],
                created_by=request.user,
            )

            # Audit log
            AuditLog.objects.create(
                user=request.user,
                action="Supplier Payment",
                description=f"{request.user.username} paid {payment.amount_paid} to {purchase.supplier.name}.",
                content_type=ContentType.objects.get_for_model(SupplierPayment),
                object_id=payment.id,
                ip_address=get_client_ip(request),
            )

            messages.success(request, f"Payment of GHS {payment.amount_paid} recorded successfully.")
            return redirect("view_purchase", purchase.id)
    else:
        form = SupplierPaymentForm(purchase=purchase)

    context = {
        "purchase": purchase,
        "business": business,
        "form": form,
        "title": "Supplier Payment",
    }
    return render(request, "suppliers/supplier_payment.html", context)


@login_required
def supplier_payment_history(request):
    """View supplier payment history."""
    business = get_business(request)

    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    payments = SupplierPayment.objects.select_related(
        "supplier", "purchase", "created_by"
    ).filter(
        purchase__business=business
    ).order_by("-created_at")

    if search:
        payments = payments.filter(
            Q(reference__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(purchase__reference_number__icontains=search)
        )

    if status_filter in ["pending", "partial", "paid"]:
        payments = payments.filter(purchase__payment_status=status_filter)

    paginator = Paginator(payments, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "business": business,
        "page_obj": page_obj,
        "search": search,
        "status": status_filter,
        "title": "Payment History",
    }
    return render(request, "suppliers/supplier_payment_history.html", context)


# =============================================
# API VIEWS
# =============================================

def pending_po_count_api(request):
    """API endpoint for pending PO count."""
    business = get_business(request)
    count = PurchaseOrder.objects.filter(
        business=business,
        status__in=["draft", "issued", "partially_received"]
    ).count()
    return JsonResponse({"count": count})


def low_stock_count_api(request):
    """API endpoint for low stock count."""
    business = get_business(request)
    count = Inventory.objects.filter(
        business=business,
        stock_quantity__lte=5,
        stock_quantity__gt=0
    ).count()
    return JsonResponse({"count": count})



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



@login_required
def label_select(request):
    """Step 1: pick which products to print labels for."""
    business = get_business(request)

    query = request.GET.get("q", "").strip()
    preselect_id = request.GET.get("product", "")

    products = Inventory.objects.filter(business=business, status="active")

    if query:
        products = products.filter(
            Q(product_name__icontains=query)
            | Q(sku__icontains=query)
            | Q(barcode__icontains=query)
        )

    products = products.order_by("product_name")

    templates = LabelTemplate.objects.filter(business=business)
    if not templates.exists():
        # Seed one sensible default so the page isn't empty on first use
        LabelTemplate.objects.create(
            business=business,
            name="Standard Shelf Tag (40x30mm)",
            is_default=True,
        )
        templates = LabelTemplate.objects.filter(business=business)

    context = {
        "products": products,
        "templates": templates,
        "query": query,
        "preselect_id": preselect_id,
    }
    return render(request, "inventory/labels/select.html", context)


@login_required
@require_POST
def label_print(request):
    """Step 2: receive the selected products + quantities, render the printable sheet."""
    business = get_business(request)

    product_ids = request.POST.getlist("product_id")
    template_id = request.POST.get("template_id")
    template = get_object_or_404(LabelTemplate, id=template_id, business=business)

    labels = []  # flattened list: one entry per physical label to print
    for pid in product_ids:
        qty_raw = request.POST.get(f"qty_{pid}", "0")
        try:
            qty = int(qty_raw)
        except ValueError:
            qty = 0
        if qty <= 0:
            continue

        product = get_object_or_404(Inventory, id=pid, business=business)
        labels.extend([product] * qty)

        LabelPrintLog.objects.create(
            business=business,
            product=product,
            template=template,
            quantity=qty,
            printed_by=request.user,
        )

    if not labels:
        messages.warning(request, "Select at least one product and a quantity greater than zero.")
        return redirect("select")

    context = {
        "business": business,
        "template": template,
        "labels": labels,
    }
    return render(request, "inventory/labels/print_sheet.html", context)


@login_required
def template_list(request):
    business = get_business(request)
    templates = LabelTemplate.objects.filter(business=business)
    return render(request, "inventory/labels/template_list.html", {"templates": templates})


@login_required
def template_create(request):
    business = get_business(request)
    if request.method == "POST":
        form = LabelTemplateForm(request.POST)
        if form.is_valid():
            tmpl = form.save(commit=False)
            tmpl.business = business
            tmpl.save()
            messages.success(request, "Label template saved.")
            return redirect("template_list")
    else:
        form = LabelTemplateForm()
    return render(request, "inventory/labels/template_form.html", {"form": form, "is_edit": False})


@login_required
def template_edit(request, pk):
    business = get_business(request)
    template = get_object_or_404(LabelTemplate, pk=pk, business=business)
    if request.method == "POST":
        form = LabelTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, "Label template updated.")
            return redirect("template_list")
    else:
        form = LabelTemplateForm(instance=template)
    return render(
        request, "inventory/labels/template_form.html",
        {"form": form, "is_edit": True, "template": template}
    )


@login_required
@require_POST
def template_delete(request, pk):
    business = get_business(request)
    template = get_object_or_404(LabelTemplate, pk=pk, business=business)
    template.delete()
    messages.success(request, "Label template deleted.")
    return redirect("template_list")


def get_or_create_default_warehouse(business):
    warehouse = Warehouse.objects.filter(business=business, is_default=True).first()
    if warehouse:
        return warehouse
    return Warehouse.objects.create(business=business, name="Main Warehouse", is_default=True)


def _seed_warehouse_stock(product):
    """
    The first time a product's warehouse breakdown is opened, make sure it
    has at least one WarehouseStock row so the per-warehouse total always
    equals Inventory.stock_quantity. Everything starts out sitting in the
    business's default warehouse.
    """
    if WarehouseStock.objects.filter(product=product).exists():
        return
    default_wh = get_or_create_default_warehouse(product.business)
    WarehouseStock.objects.create(
        business=product.business,
        warehouse=default_wh,
        product=product,
        quantity=product.stock_quantity,
    )


# ==========================================================
# WAREHOUSES
# ==========================================================

@login_required
def warehouse_list(request):
    business = get_business(request)
    warehouses = Warehouse.objects.filter(business=business).annotate(
        total_stock=Sum("stock_levels__quantity")
    )
    return render(request, "inventory/warehouses/list.html", {"warehouses": warehouses})


@login_required
def warehouse_create(request):
    business = get_business(request)
    if request.method == "POST":
        form = WarehouseForm(request.POST)
        if form.is_valid():
            wh = form.save(commit=False)
            wh.business = business
            wh.save()
            messages.success(request, "Warehouse created.")
            return redirect("warehouse_list")
    else:
        form = WarehouseForm()
    return render(request, "inventory/warehouses/form.html", {"form": form, "is_edit": False})


@login_required
def warehouse_edit(request, pk):
    business = get_business(request)
    warehouse = get_object_or_404(Warehouse, pk=pk, business=business)
    if request.method == "POST":
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            form.save()
            messages.success(request, "Warehouse updated.")
            return redirect("warehouse_list")
    else:
        form = WarehouseForm(instance=warehouse)
    return render(
        request, "inventory/warehouses/form.html",
        {"form": form, "is_edit": True, "warehouse": warehouse}
    )


@login_required
@require_POST
def warehouse_delete(request, pk):
    business = get_business(request)
    warehouse = get_object_or_404(Warehouse, pk=pk, business=business)

    if warehouse.stock_levels.filter(quantity__gt=0).exists():
        messages.error(request, "Can't delete a warehouse that still holds stock. Transfer it out first.")
        return redirect("warehouse_list")

    warehouse.delete()
    messages.success(request, "Warehouse deleted.")
    return redirect("warehouse_list")


# ==========================================================
# PER-PRODUCT WAREHOUSE STOCK
# ==========================================================

@login_required
def product_warehouse_stock(request, product_id):
    business = get_business(request)
    product = get_object_or_404(Inventory, id=product_id, business=business)

    _seed_warehouse_stock(product)

    warehouses = Warehouse.objects.filter(business=business, is_active=True)

    if request.method == "POST":
        new_quantities = {}
        total = 0
        for wh in warehouses:
            raw = request.POST.get(f"qty_{wh.id}", "0")
            try:
                qty = int(raw)
            except ValueError:
                qty = 0
            qty = max(qty, 0)
            new_quantities[wh.id] = qty
            total += qty

        if total != product.stock_quantity:
            messages.error(
                request,
                f"Warehouse quantities must add up to the product's total stock "
                f"({product.stock_quantity}). You entered {total}."
            )
        else:
            with transaction.atomic():
                for wh in warehouses:
                    stock, _ = WarehouseStock.objects.get_or_create(
                        business=business, warehouse=wh, product=product,
                        defaults={"quantity": 0},
                    )
                    stock.quantity = new_quantities[wh.id]
                    stock.save(update_fields=["quantity", "updated_at"])
            messages.success(request, "Warehouse stock updated.")
            return redirect("product_warehouse_stock", product_id=product.id)

    stock_levels = WarehouseStock.objects.filter(
        product=product, warehouse__in=warehouses
    ).select_related("warehouse")
    stock_by_wh = {s.warehouse_id: s.quantity for s in stock_levels}

    rows = [
        {"warehouse": wh, "quantity": stock_by_wh.get(wh.id, 0)}
        for wh in warehouses
    ]

    return render(request, "inventory/warehouses/product_detail.html", {
        "product": product,
        "rows": rows,
    })


# ==========================================================
# STOCK TRANSFERS
# ==========================================================

@login_required
def transfer_list(request):
    business = get_business(request)
    status = request.GET.get("status", "")

    transfers = StockTransfer.objects.filter(business=business).select_related(
        "source_warehouse", "destination_warehouse"
    )
    if status:
        transfers = transfers.filter(status=status)

    return render(request, "inventory/transfers/list.html", {
        "transfers": transfers,
        "status": status,
    })


@login_required
def transfer_create(request):
    business = get_business(request)
    warehouses = Warehouse.objects.filter(business=business, is_active=True)
    products = Inventory.objects.filter(business=business, status="active").order_by("product_name")

    if request.method == "POST":
        source_id = request.POST.get("source_warehouse")
        destination_id = request.POST.get("destination_warehouse")
        notes = request.POST.get("notes", "")
        product_ids = request.POST.getlist("product_id")

        if not source_id or not destination_id:
            messages.error(request, "Choose both a source and a destination warehouse.")
            return redirect("transfer_create")

        if source_id == destination_id:
            messages.error(request, "Source and destination warehouse must be different.")
            return redirect("transfer_create")

        source = get_object_or_404(Warehouse, id=source_id, business=business)
        destination = get_object_or_404(Warehouse, id=destination_id, business=business)

        items = []
        for pid in product_ids:
            raw = request.POST.get(f"qty_{pid}", "0")
            try:
                qty = int(raw)
            except ValueError:
                qty = 0
            if qty > 0:
                items.append((pid, qty))

        if not items:
            messages.error(request, "Add at least one product with a quantity greater than zero.")
            return redirect("transfer_create")

        with transaction.atomic():
            transfer = StockTransfer.objects.create(
                business=business,
                source_warehouse=source,
                destination_warehouse=destination,
                notes=notes,
                requested_by=request.user,
            )
            for pid, qty in items:
                product = get_object_or_404(Inventory, id=pid, business=business)
                StockTransferItem.objects.create(transfer=transfer, product=product, quantity=qty)

        messages.success(request, f"Transfer {transfer.reference_number} created as a draft.")
        return redirect("transfer_detail", pk=transfer.id)

    return render(request, "inventory/transfers/create.html", {
        "warehouses": warehouses,
        "products": products,
    })


@login_required
def transfer_detail(request, pk):
    business = get_business(request)
    transfer = get_object_or_404(
        StockTransfer.objects.select_related("source_warehouse", "destination_warehouse"),
        pk=pk, business=business,
    )
    items = transfer.items.select_related("product")
    return render(request, "inventory/transfers/detail.html", {
        "transfer": transfer,
        "items": items,
    })


@login_required
@require_POST
def transfer_dispatch(request, pk):
    business = get_business(request)
    transfer = get_object_or_404(StockTransfer, pk=pk, business=business)
    try:
        transfer.dispatch(user=request.user)
        messages.success(request, f"Transfer {transfer.reference_number} dispatched.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("transfer_detail", pk=pk)


@login_required
@require_POST
def transfer_receive(request, pk):
    business = get_business(request)
    transfer = get_object_or_404(StockTransfer, pk=pk, business=business)
    try:
        transfer.receive(user=request.user)
        messages.success(request, f"Transfer {transfer.reference_number} received.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("transfer_detail", pk=pk)


@login_required
@require_POST
def transfer_cancel(request, pk):
    business = get_business(request)
    transfer = get_object_or_404(StockTransfer, pk=pk, business=business)
    try:
        transfer.cancel(user=request.user)
        messages.success(request, f"Transfer {transfer.reference_number} cancelled.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("transfer_detail", pk=pk)
