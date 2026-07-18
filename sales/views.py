# sales/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth.models import User
from django.utils import timezone
from business.models import Business
from .models import *
from .forms import *
from django.core.paginator import Paginator
from django.db.models import Q
from decimal import Decimal
from django.utils.crypto import get_random_string
from inventory.models import *
from django.http import JsonResponse
from django.db.models import F
from datetime import date
from sales.utils import update_business_metrics
from django.contrib.contenttypes.models import ContentType
from accounts.models import AuditLog, StaffProfile

from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from django.template.loader import get_template
import json


@login_required
def barcode_lookup(request):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    barcode = request.GET.get("barcode", "").strip()

    if not barcode:
        return JsonResponse({"error": "No barcode provided"}, status=400)

    try:
        product = Inventory.objects.get(
            business=business,
            barcode=barcode
        )

        data = {
            "id": product.id,
            "name": product.product_name,
            "price": float(product.selling_price),
            "stock": product.stock_quantity,
            "barcode": product.barcode,
        }

        return JsonResponse({"success": True, "product": data})

    except Inventory.DoesNotExist:

        return JsonResponse({
            "success": False,
            "message": "Product not found"
        })


@login_required
def tax_list(request):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    search = request.GET.get("search", "").strip()

    tax = Tax.objects.filter(business=business)

    if search:
        tax = tax.filter(
            name__icontains=search
        )

    context = {
        "tax": tax,
        "business": business,
        "search": search,
        "title": "Taxes"
    }

    return render(request, "sales/tax_list.html", context)


@login_required
@transaction.atomic
def tax(request):
    user = request.user

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business
    form = TaxForm()

    if request.method == 'POST':
        form = TaxForm(request.POST)

        if form.is_valid():
            instance = form.save(commit=False)
            instance.business = business
            instance.save()

            AuditLog.objects.create(
                user_id=user.id,
                action="Add Tax",
                description=(
                    f"Added tax '{instance.name}' "
                    f"({instance.tax_percentage}%)."
                ),
                content_type=ContentType.objects.get_for_model(Business),
                object_id=business.id,
                ip_address=request.META.get("REMOTE_ADDR")
            )

            messages.success(request, 'Tax successfully saved.')
            return redirect('tax_list')

    context = {
        "user": user,
        'business': business,
        'form': form,
        'title': 'Add Tax'

    }
    return render(request, 'sales/tax.html', context)


@login_required
@transaction.atomic
def update_tax(request, pk):
    user = request.user
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    queryset = get_object_or_404(
        Tax,
        id=pk,
        business=business
    )
    form = TaxForm(instance=queryset)

    if request.method == 'POST':

        form = TaxForm(
            request.POST,
            instance=queryset
        )

        if form.is_valid():
            instance = form.save()

            AuditLog.objects.create(
                user_id=user.id,
                action="Update Tax",
                description=(
                    f"Updated tax '{instance.name}' "
                    f"to {instance.tax_percentage}%."
                ),
                content_type=ContentType.objects.get_for_model(Business),
                object_id=business.id,
                ip_address=request.META.get("REMOTE_ADDR")
            )

            messages.success(
                request,
                'Tax successfully updated.'
            )

            return redirect('tax_list')

    context = {
        "user": user,
        'business': business,
        'form': form,
        'title': 'Update Tax ' + str(queryset.name)

    }
    return render(request, 'sales/tax.html', context)


@login_required
@transaction.atomic
def delete_tax(request, pk):
    user = request.user

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    queryset = get_object_or_404(
        Tax,
        id=pk,
        business=business
    )

    # =========================
    # AUDIT LOG (PROFILE UPDATE)
    # =========================

    AuditLog.objects.create(

        user_id=user.id,

        action="Delete Tax",

        description=(
            f"{queryset.name} "
            f"Delete tax '{queryset.name}'." f"{queryset.tax_percentage} "
        ),

        content_type=ContentType.objects.get_for_model(Business),

        object_id=business.id,

        ip_address=request.META.get("REMOTE_ADDR")
    )

    queryset.delete()

    messages.success(request, ' Tax successfully deleted')
    return redirect('tax_list')


@login_required
def discount_list(request):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    search = request.GET.get("search", "").strip()

    discounts = Discount.objects.filter(
        business=business
    )

    if search:
        discounts = discounts.filter(
            name__icontains=search
        )

    context = {
        "discounts": discounts,
        "business": business,
        "search": search,
        "title": "Discounts",
    }

    return render(
        request,
        "sales/discount_list.html",
        context
    )


@login_required
@transaction.atomic
def discount(request):

    user = request.user

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    form = DiscountForm()

    if request.method == 'POST':

        form = DiscountForm(request.POST)

        if form.is_valid():

            instance = form.save(commit=False)

            instance.business = business

            instance.save()

            AuditLog.objects.create(
                user=user,
                action="Add Discount",
                description=(
                    f"Added discount "
                    f"{instance.name} "
                    f"({instance.percentage}%)"
                ),
                content_type=ContentType.objects.get_for_model(
                    Discount
                ),
                object_id=instance.id,
                ip_address=request.META.get(
                    "REMOTE_ADDR"
                )
            )

            messages.success(
                request,
                "Discount created successfully."
            )

            return redirect('discount_list')

    context = {
        "form": form,
        "business": business,
        "title": "Add Discount",
    }

    return render(
        request,
        "sales/discount.html",
        context
    )


@login_required
@transaction.atomic
def update_discount(request, pk):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    discount = get_object_or_404(
        Discount,
        pk=pk,
        business=business
    )

    form = DiscountForm(instance=discount)

    if request.method == 'POST':

        form = DiscountForm(
            request.POST,
            instance=discount
        )

        if form.is_valid():

            instance = form.save()

            AuditLog.objects.create(
                user=request.user,
                action="Update Discount",
                description=(
                    f"Updated discount "
                    f"{instance.name}"
                ),
                content_type=ContentType.objects.get_for_model(
                    Discount
                ),
                object_id=instance.id,
                ip_address=request.META.get(
                    "REMOTE_ADDR"
                )
            )

            messages.success(
                request,
                "Discount updated successfully."
            )

            return redirect('discount_list')

    context = {
        "form": form,
        "business": business,
        "title": f"Update {discount.name}",
    }

    return render(
        request,
        "sales/discount.html",
        context
    )


@login_required
@transaction.atomic
def delete_discount(request, pk):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    discount = get_object_or_404(
        Discount,
        pk=pk,
        business=business
    )

    AuditLog.objects.create(
        user=request.user,
        action="Delete Discount",
        description=(
            f"Deleted discount "
            f"{discount.name}"
        ),
        content_type=ContentType.objects.get_for_model(
            Discount
        ),
        object_id=discount.id,
        ip_address=request.META.get(
            "REMOTE_ADDR"
        )
    )

    discount.delete()

    messages.success(
        request,
        "Discount deleted successfully."
    )

    return redirect('discount_list')


@login_required
@transaction.atomic
def sales(request):
    user = request.user

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    # =====================================
    # SEARCH
    # =====================================
    search = request.GET.get('search', '').strip()

    products_queryset = Inventory.objects.filter(
        business=business
    ).order_by('-id')

    if search:
        products_queryset = products_queryset.filter(
            Q(product_name__icontains=search)
        )

    # ALWAYS DISTINCT (prevents duplicates)
    products_queryset = products_queryset.distinct()

    # =====================================
    # PAGINATION (ALWAYS RUNS)
    # =====================================
    paginator = Paginator(products_queryset, 12)
    page_number = request.GET.get('page', 1)
    products_page = paginator.get_page(page_number)

    # =====================================
    # AJAX LOAD MORE SUPPORT
    # =====================================
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            "html": render_to_string(
                "sales/partials/product_grid.html",
                {"products": products_page},
                request=request
            ),
            "has_next": products_page.has_next(),
            "next_page": (
                products_page.next_page_number()
                if products_page.has_next()
                else None
            )
        })

    # =====================================
    # ACTIVE TAXES
    # =====================================
    taxes = Tax.objects.filter(business=business, active=True)

    # =====================================
    # ACTIVE DISCOUNTS
    # =====================================
    discounts = []
    for discount in Discount.objects.filter(business=business, active=True):
        if discount.is_valid():
            discounts.append(discount)

    valid_discount_ids = [d.id for d in discounts]

    # =====================================
    # FORM
    # =====================================
    form = SaleForm()
    form.fields['customer'].queryset = Customer.objects.filter(
        business=business
    ).order_by('full_name')
    form.fields['tax'].queryset = taxes
    form.fields['discount'].queryset = Discount.objects.filter(
        id__in=valid_discount_ids
    )

    # =====================================
    # CREATE SALE
    # =====================================
    if request.method == 'POST':

        form = SaleForm(request.POST)
        sale_type = request.POST.get("sale_type", "Completed")

        form.fields['customer'].queryset = Customer.objects.filter(
            business=business
        ).order_by('full_name')
        form.fields['tax'].queryset = taxes
        form.fields['discount'].queryset = Discount.objects.filter(
            id__in=valid_discount_ids
        )

        if form.is_valid():

            product_ids = request.POST.getlist('product_id')
            quantities = request.POST.getlist('quantity')
            raw_amount_paid = request.POST.get('amount_paid', '0')

            # EMPTY CART VALIDATION
            if not product_ids:
                messages.error(request, 'Please select at least one product.')
                return redirect('sales')

            # CREATE SALE
            sale = form.save(commit=False)
            sale.business = business

            sale.subtotal = Decimal('0.00')
            sale.tax_amount = Decimal('0.00')
            sale.discount_amount = Decimal('0.00')
            sale.total = Decimal('0.00')
            sale.amount_paid = Decimal('0.00')
            sale.change = Decimal('0.00')
            sale.staff = user
            sale.status = sale_type
            sale.save()

            subtotal = Decimal('0.00')
            total_profit = Decimal('0.00')
            sale_items_created = 0

            # PROCESS ITEMS
            for product_id, qty in zip(product_ids, quantities):

                try:
                    qty = int(qty)
                    product = Inventory.objects.select_for_update().get(
                        id=product_id,
                        business=business
                    )
                except (Inventory.DoesNotExist, ValueError, TypeError):
                    continue

                if qty <= 0:
                    continue

                if qty > product.stock_quantity:
                    messages.error(
                        request,
                        f"{product.product_name} only has {product.stock_quantity} left in stock."
                    )
                    raise ValidationError("Insufficient stock.")

                item_price = Decimal(str(product.selling_price))
                item_cost = Decimal(str(product.cost_price))

                item_total = item_price * qty
                item_profit = (item_price - item_cost) * qty

                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=qty,
                    price=item_price,
                    cost_price=item_cost,
                    total=item_total,
                    profit=item_profit
                )

                if sale.status == "Completed":
                    previous_stock = product.stock_quantity
                    product.stock_quantity -= qty
                    product.save()

                    InventoryStockHistory.objects.create(
                        business=business,
                        inventory=product,
                        previous_stock=previous_stock,
                        quantity_changed=-qty,
                        new_stock=product.stock_quantity,
                        action_type='sale',
                        reference_number=f"SALE-{sale.receipt_number}",
                        performed_by=request.user,
                        note=f"Stock deducted from sale #{sale.receipt_number}"
                    )

                subtotal += item_total
                total_profit += item_profit
                sale_items_created += 1

            if sale_items_created == 0:
                sale.delete()
                messages.error(request, 'No valid products selected.')
                return redirect('sales')

            # TAX
            tax_amount = Decimal('0.00')
            if sale.tax and sale.tax.active:
                tax_amount = (
                    subtotal * Decimal(str(sale.tax.tax_percentage))
                ) / Decimal('100')

            # DISCOUNT
            discount_amount = Decimal('0.00')
            if sale.discount and sale.discount.is_valid():
                discount_amount = (
                    subtotal * Decimal(str(sale.discount.percentage))
                ) / Decimal('100')

            # TOTAL
            grand_total = subtotal + tax_amount - discount_amount
            if grand_total < 0:
                grand_total = Decimal('0.00')

            # AMOUNT PAID & CHANGE HANDLING
            if sale.status == "Proforma":
                amount_paid = Decimal('0.00')
                customer_change = Decimal('0.00')
            else:
                try:
                    amount_paid = Decimal(str(raw_amount_paid))
                except:
                    amount_paid = Decimal('0.00')

                customer_change = Decimal('0.00')
                if amount_paid > grand_total:
                    customer_change = amount_paid - grand_total

            sale.subtotal = subtotal
            sale.tax_amount = tax_amount
            sale.discount_amount = discount_amount
            sale.total = grand_total
            sale.amount_paid = amount_paid
            sale.change = customer_change
            sale.save()

            if sale.status == "Completed":
                update_business_metrics(business, sale)

            AuditLog.objects.create(
                user=request.user,
                action="Sale Completed" if sale.status == "Completed" else "Pro-forma Generated",
                description=(
                    f"{request.user.username} {'completed sale' if sale.status == 'Completed' else 'generated pro-forma'} "
                    f"#{sale.receipt_number if sale.status == 'Completed' else sale.invoice_number} "
                    f"Total: {sale.total} "
                    f"Items: {sale_items_created}"
                ),
                content_type=ContentType.objects.get_for_model(Sale),
                object_id=sale.id,
                ip_address=request.META.get("REMOTE_ADDR")
            )

            if sale.status == "Completed":
                messages.success(
                    request,
                    f"Sale completed successfully. Receipt No: {sale.receipt_number}"
                )
                return redirect('pos_receipt', pk=sale.id)
            else:
                messages.success(
                    request,
                    f"Pro-forma invoice generated. Invoice No: {sale.invoice_number}"
                )
                return redirect('proforma_invoice', pk=sale.id)

        else:
            messages.error(request, 'Please correct the form errors.')

    # =====================================
    # CONTEXT
    # =====================================
    context = {
        "form": form,
        "user": user,
        "business": business,
        "products": products_page,
        "search": search,
        "taxes": taxes,
        "discounts": discounts,
        "title": "Enterprise POS",
    }

    return render(request, 'sales/sales.html', context)


@login_required
@transaction.atomic
def update_sales(request, pk):
    user = User.objects.get(id=request.user.id)

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    queryset = get_object_or_404(
        Sale,
        id=pk,
        business=business
    )

    form = SaleForm(instance=queryset)

    if request.method == 'POST':

        form = SaleForm(
            request.POST,
            instance=queryset
        )

        if form.is_valid():
            sale = form.save(commit=False)

            sale.business = business

            sale.save()

            AuditLog.objects.create(

                user=request.user,

                action="Sale Updated",

                description=(
                    f"{request.user.username} updated sale "
                    f"#{sale.receipt_number}. "
                    f"New total: {sale.total}"
                ),

                content_type=ContentType.objects.get_for_model(Sale),

                object_id=sale.id,

                ip_address=request.META.get("REMOTE_ADDR")
            )

            messages.success(
                request,
                'Sale updated successfully.'
            )

            return redirect('view_sales')

    context = {
        "form": form,
        "user": user,
        "queryset": queryset,
        "business": business,
        "title": "Update Sale",
    }

    return render(
        request,
        'sales/sales.html',
        context
    )


@login_required
@transaction.atomic
def refund_sale(request, pk):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    sale = get_object_or_404(
        Sale,
        id=pk,
        business=business
    )

    if not sale.can_refund:
        messages.error(
            request,
            "Refund not allowed."
        )
        return redirect('view_sales')

    if request.method != "POST":
        return redirect('view_sales')

    sale_item_ids = request.POST.getlist("items")

    if not sale_item_ids:
        messages.error(
            request,
            "No items selected."
        )
        return redirect('view_sales')

    # Create refund record
    refund = Refund.objects.create(
        sale=sale,
        business=business,
        processed_by=request.user
    )

    # =====================================
    # PROCESS REFUND ITEMS
    # =====================================

    for sale_item_id in sale_item_ids:

        sale_item = get_object_or_404(
            SaleItem,
            id=sale_item_id,
            sale=sale
        )

        qty = int(
            request.POST.get(
                f"qty_{sale_item_id}",
                1
            )
        )

        remaining_qty = (
                sale_item.quantity -
                sale_item.refunded_quantity
        )

        # Safety validation
        if qty <= 0 or qty > remaining_qty:
            messages.error(
                request,
                f"Invalid quantity for {sale_item.product.product_name}"
            )

            return redirect("view_sales")

        product = sale_item.product

        old_stock = product.stock_quantity

        # Restore stock
        product.stock_quantity += qty
        product.save()

        # Update refunded quantity
        sale_item.refunded_quantity += qty
        sale_item.save()

        # Save refund item
        RefundItem.objects.create(
            refund=refund,
            sale_item=sale_item,
            quantity=qty,
            unit_price=sale_item.price
        )

        # Inventory history
        InventoryStockHistory.objects.create(
            business=business,
            inventory=product,
            previous_stock=old_stock,
            quantity_changed=qty,
            new_stock=product.stock_quantity,
            action_type='returned',
            reference_number=f"REFUND-{sale.receipt_number}",
            performed_by=request.user
        )

    # =====================================
    # RECALCULATE SALE VALUES
    # =====================================

    remaining_total = 0

    for item in sale.items.all():

        remaining_qty = item.quantity - item.refunded_quantity

        # skip fully refunded items
        if remaining_qty <= 0:
            continue

        # recalculate remaining sale amount
        remaining_total += (
                remaining_qty * item.price
        )

    # update only real database field
    sale.total = remaining_total

    # =====================================
    # UPDATE STATUS
    # =====================================

    total_items = sum(
        i.quantity
        for i in sale.items.all()
    )

    total_refunded = sum(
        i.refunded_quantity
        for i in sale.items.all()
    )

    if total_refunded == 0:

        sale.status = "Completed"

    elif total_refunded < total_items:

        sale.status = "Partially Refunded"

    else:

        sale.status = "Refunded"

    sale.refund_date = timezone.now()

    sale.save()

    AuditLog.objects.create(

        user=request.user,

        action="Sale Refunded",

        description=(
            f"{request.user.username} processed refund "
            f"for sale #{sale.receipt_number}. "
            f"Status: {sale.status} | Remaining total: {sale.total}"
        ),

        content_type=ContentType.objects.get_for_model(Sale),

        object_id=sale.id,

        ip_address=request.META.get("REMOTE_ADDR")
    )

    messages.success(
        request,
        "Refund processed successfully"
    )

    return redirect('view_sales')


@login_required
def view_sales(request):
    user = request.user
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    # =====================================
    # INITIALIZE VARIABLES (Prevents NameError)
    # =====================================
    total_revenue = Decimal('0.00')
    total_profit = Decimal('0.00')

    # =====================================
    # FILTER TYPE
    # =====================================
    tab = request.GET.get('tab', 'all')

    # BASE QUERY
    sales_queryset = Sale.objects.filter(
        business=business
    ).select_related('customer').prefetch_related('items', 'items__product').order_by('-id')

    # SEARCH
    search = request.GET.get('search', '').strip()
    if search:
        sales_queryset = sales_queryset.filter(
            Q(receipt_number__icontains=search) |
            Q(invoice_number__icontains=search) |
            Q(customer__full_name__icontains=search)
        )

    # STATUS FILTERING
    if tab == 'completed':
        sales_queryset = sales_queryset.filter(status='Completed')
    elif tab == 'refunded':
        sales_queryset = sales_queryset.filter(status='Refunded')
    elif tab == 'proforma':
        sales_queryset = sales_queryset.filter(status='Proforma')
    else:
        # Default 'all' hides Proforma
        sales_queryset = sales_queryset.exclude(status='Proforma')

    # =====================================
    # CALCULATIONS
    # =====================================
    # We calculate based on the filtered queryset
    for sale in sales_queryset:
        # Calculate Remaining Items and Live Profit
        remaining_items = 0
        live_profit = 0

        for item in sale.items.all():
            remaining_qty = item.quantity - item.refunded_quantity
            if remaining_qty > 0:
                remaining_items += remaining_qty
                live_profit += (item.price - item.cost_price) * remaining_qty

        sale.remaining_items = remaining_items
        sale.live_profit = live_profit

        # KPI Totals (Only for Completed sales)
        if sale.status == 'Completed':
            total_revenue += sale.total
            total_profit += sale.live_profit

    # Counts for Tabs
    total_sales = sales_queryset.count()
    completed_sales_count = Sale.objects.filter(business=business, status='Completed').count()
    refunded_sales_count = Sale.objects.filter(business=business, status='Refunded').count()
    proforma_sales_count = Sale.objects.filter(business=business, status='Proforma').count()

    # PAGINATION
    paginator = Paginator(sales_queryset, 15)
    page_number = request.GET.get('page')
    sales = paginator.get_page(page_number)

    context = {
        "sales": sales,
        "search": search,
        "tab": tab,
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "completed_sales_count": completed_sales_count,
        "refunded_sales_count": refunded_sales_count,
        "proforma_sales_count": proforma_sales_count,
        "business": business,
        "user": user,
        "title": "Sales History",
    }

    return render(request, 'sales/view_sales.html', context)


@login_required
def customers(request):
    user = request.user

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    # =====================================
    # BASE QUERY
    # =====================================
    customer_queryset = Customer.objects.filter(
        business=business
    ).order_by('full_name')

    # =====================================
    # SEARCH
    # =====================================
    search = request.GET.get(
        'search',
        ''
    ).strip()

    if search:
        customer_queryset = customer_queryset.filter(

            Q(full_name__icontains=search) |

            Q(phone__icontains=search) |

            Q(email__icontains=search)

        )

    # =====================================
    # PAGINATION
    # =====================================
    paginator = Paginator(
        customer_queryset,
        15
    )

    page_number = request.GET.get('page')

    cust = paginator.get_page(
        page_number
    )
    # =====================================
    # CUSTOMER STATS
    # =====================================
    total_customers = customer_queryset.count()

    customers_with_email = customer_queryset.exclude(
        email__isnull=True
    ).exclude(email='').count()

    customers_with_phone = customer_queryset.exclude(
        phone__isnull=True
    ).exclude(phone='').count()

    context = {

        "cust": cust,

        "customer_queryset": customer_queryset,

        "search": search,

        "business": business,

        "user": user,

        "total_customers": total_customers,

        "customers_with_email": customers_with_email,

        "customers_with_phone": customers_with_phone,

        "title": f"{business.name} Customers",
    }

    return render(request, 'sales/customers.html', context)


@login_required
def check_or_create_customer(request):
    if request.method != "POST":
        return JsonResponse({

            "status": "error",
            "message": "Invalid request."

        })

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    full_name = request.POST.get("name", "").strip()
    phone = request.POST.get("phone", "").strip()
    email = request.POST.get("email", "").strip()

    # =========================
    # VALIDATION
    # =========================

    if not phone and not email:
        return JsonResponse({

            "status": "error",

            "message":
                "Phone or email is required."

        })

    # =========================
    # CHECK EXISTING CUSTOMER
    # =========================

    customer = None

    if phone:
        customer = Customer.objects.filter(business=business, phone=phone).first()

    if not customer and email:
        customer = Customer.objects.filter(business=business, email=email).first()

    # =========================
    # EXISTING CUSTOMER
    # =========================

    if customer:
        return JsonResponse({

            "status": "exists",

            "customer_id": customer.id,

            "customer_name":
                customer.full_name,

            "message":
                "Existing customer selected."

        })

    # =========================
    # CREATE NEW CUSTOMER
    # =========================

    customer = Customer.objects.create(

        business=business,

        full_name=(
            full_name
            if full_name
            else "Walk-in Customer"
        ),

        phone=phone,

        email=email

    )

    AuditLog.objects.create(

        user=request.user,

        action="Customer Created",

        description=(
            f"{request.user.username} created customer "
            f"'{customer.full_name}' "
            f"Phone: {customer.phone or 'N/A'}"
        ),

        content_type=ContentType.objects.get_for_model(Customer),

        object_id=customer.id,

        ip_address=request.META.get("REMOTE_ADDR")
    )

    # =========================
    # RESPONSE
    # =========================

    return JsonResponse({

        "status": "created",

        "customer_id": customer.id,

        "customer_name":
            customer.full_name,

        "message":
            "Customer created successfully."

    })


# =====================================
# UPDATE CUSTOMER
# =====================================

@login_required
@transaction.atomic
def update_customer(request, pk):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business
    customer = get_object_or_404(
        Customer,
        id=pk,
        business=business
    )

    if request.method == "POST":

        full_name = request.POST.get(
            "full_name",
            ""
        ).strip()

        phone = request.POST.get(
            "phone",
            ""
        ).strip()

        email = request.POST.get(
            "email",
            ""
        ).strip()

        address = request.POST.get(
            "address",
            ""
        ).strip()

        # =========================
        # VALIDATION
        # =========================
        if not full_name:
            messages.error(
                request,
                "Customer name is required."
            )

            return redirect("customers")

        # =========================
        # DUPLICATE PHONE
        # =========================
        if phone:

            phone_exists = Customer.objects.filter(
                business=business,
                phone=phone
            ).exclude(id=customer.id).exists()

            if phone_exists:
                messages.error(
                    request,
                    "Phone number already exists."
                )

                return redirect("customers")

        # =========================
        # DUPLICATE EMAIL
        # =========================
        if email:

            email_exists = Customer.objects.filter(
                business=business,
                email=email
            ).exclude(id=customer.id).exists()

            if email_exists:
                messages.error(
                    request,
                    "Email already exists."
                )

                return redirect("customers")

        customer.full_name = full_name
        customer.phone = phone
        customer.email = email
        customer.address = address

        customer.save()

        AuditLog.objects.create(

            user=request.user,

            action="Customer Updated",

            description=(
                f"{request.user.username} updated customer "
                f"'{customer.full_name}' "
                f"(ID: {customer.id})"
            ),

            content_type=ContentType.objects.get_for_model(Customer),

            object_id=customer.id,

            ip_address=request.META.get("REMOTE_ADDR")
        )

        messages.success(
            request,
            "Customer updated successfully."
        )

        return redirect("customers")

    return redirect("customers")


# =====================================
# DELETE CUSTOMER
# =====================================
@login_required
@transaction.atomic
def delete_customer(request, pk):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    customer = get_object_or_404(
        Customer,
        id=pk,
        business=business
    )

    # =========================
    # PREVENT DELETE IF USED
    # =========================
    sale_exists = Sale.objects.filter(
        customer=customer
    ).exists()

    if sale_exists:
        messages.error(
            request,
            "Cannot delete customer with sales history."
        )

        return redirect("customers")

    AuditLog.objects.create(

        user=request.user,

        action="Customer Deleted",

        description=(
            f"{request.user.username} deleted customer "
            f"'{customer.full_name}' "
            f"(Phone: {customer.phone or 'N/A'})"
        ),

        content_type=ContentType.objects.get_for_model(Customer),

        object_id=customer.id,

        ip_address=request.META.get("REMOTE_ADDR")
    )

    customer.delete()

    messages.success(
        request,
        "Customer deleted successfully."
    )

    return redirect("customers")


@login_required
def customers_purchase(request, pk):
    user = request.user

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business
    customer = get_object_or_404(
        Customer,
        id=pk,
        business=business
    )

    # =====================================
    # FILTER TYPE
    # =====================================
    tab = request.GET.get(
        'tab',
        'all'
    )

    # =====================================
    # BASE QUERY
    # =====================================
    sales_queryset = Sale.objects.filter(
        business=business, customer_id=pk
    ).select_related(
        'customer'
    ).prefetch_related(
        'items',
        'items__product'
    ).order_by('-id')

    # =====================================
    # SEARCH
    # =====================================
    search = request.GET.get(
        'search',
        ''
    ).strip()

    if search:
        sales_queryset = sales_queryset.filter(

            Q(receipt_number__icontains=search) |

            Q(invoice_number__icontains=search) |

            Q(customer__full_name__icontains=search)

        )

    # =====================================
    # FILTER BY STATUS
    # =====================================
    if tab == 'completed':

        sales_queryset = sales_queryset.filter(
            status='Completed'
        )

    elif tab == 'refunded':

        sales_queryset = sales_queryset.filter(
            status='Refunded'
        )
    # =====================================
    # LIVE KPI + TAB COUNTS
    # =====================================

    total_revenue = 0
    total_profit = 0
    total_sales = 0

    completed_sales_count = 0
    refunded_sales_count = 0

    for sale in sales_queryset:

        total_purchased = sum(
            i.quantity
            for i in sale.items.all()
        )

        total_refunded = sum(
            i.refunded_quantity
            for i in sale.items.all()
        )

        remaining_items = 0
        live_profit = 0

        for item in sale.items.all():

            remaining_qty = (
                    item.quantity -
                    item.refunded_quantity
            )

            if remaining_qty <= 0:
                continue

            remaining_items += remaining_qty

            item_profit = (
                                  item.price -
                                  item.product.cost_price
                          ) * remaining_qty

            live_profit += item_profit

        sale.remaining_items = remaining_items
        sale.live_profit = live_profit

        # Skip fully refunded sales
        if total_refunded >= total_purchased:
            refunded_sales_count += 1
            continue

        total_sales += 1
        completed_sales_count += 1

        total_revenue += sale.total
        total_profit += live_profit

        if total_refunded > 0:
            refunded_sales_count += 1
    # =====================================
    # PAGINATION
    # =====================================
    paginator = Paginator(
        sales_queryset,
        15
    )

    page_number = request.GET.get('page')

    sales = paginator.get_page(
        page_number
    )

    context = {
        "sales": sales,
        "customer": customer,
        "search": search,
        "tab": tab,
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "completed_sales_count": completed_sales_count,
        "refunded_sales_count": refunded_sales_count,
        "business": business,
        "user": user,
        "title": "Sales History",
    }

    return render(request, 'sales/customers_purchase.html', context)


@login_required
def pos_receipt(request, pk):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business
    sale = get_object_or_404(Sale, id=pk, business=business)

    sale_items = sale.items.all()
    # =========================
    # REFUND-AWARE STATUS LOGIC
    # =========================

    total_items = 0
    total_refunded = 0

    for item in sale_items:
        total_items += item.quantity
        total_refunded += getattr(item, "refunded_quantity", 0) or 0

    # fallback safety
    total_paid = sale.amount_paid or 0
    total_amount = sale.total or 0

    # =========================
    # FINAL STATUS ENGINE (NEW LOGIC)
    # =========================

    # ======================================
    # DOCUMENT STATUS ENGINE
    # ======================================

    if sale.status == "Proforma":

        computed_status = "Proforma"

    elif total_refunded == total_items and total_items > 0:

        computed_status = "Refunded"

    elif total_refunded > 0:

        computed_status = "Partially Refunded"

    elif total_paid >= total_amount:

        computed_status = "Completed"

    else:

        computed_status = "Pending"

    subtotal = sale.subtotal or 0

    tax_amount = Decimal('0.00')
    discount_amount = Decimal('0.00')

    if sale.tax:
        tax_amount = (
                             subtotal *
                             Decimal(str(sale.tax.tax_percentage))
                     ) / Decimal('100')

    if sale.discount and sale.discount.is_valid():
        discount_amount = (
                                  subtotal *
                                  Decimal(str(sale.discount.percentage))
                          ) / Decimal('100')

    context = {
        'sale': sale,
        'sale_items': sale_items,
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'discount_amount': discount_amount,
        'title': (
            'Pro-forma Invoice'
            if sale.status == "Proforma"
            else 'POS Receipt'
        ),

        # NEW: computed business-safe status
        'computed_status': computed_status,
    }
    return render(
        request,
        'sales/receipt.html',
        context
    )


@login_required
def proforma_invoice(request, pk):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    sale = get_object_or_404(
        Sale,
        id=pk,
        business=business,
        status='Proforma'
    )

    sale_items = sale.items.all()

    subtotal = sale.subtotal or Decimal('0.00')

    tax_amount = Decimal('0.00')
    discount_amount = Decimal('0.00')

    if sale.tax:
        tax_amount = (
                             subtotal *
                             Decimal(str(sale.tax.tax_percentage))
                     ) / Decimal('100')

    if sale.discount and sale.discount.is_valid():
        discount_amount = (
                                  subtotal *
                                  Decimal(str(sale.discount.percentage))
                          ) / Decimal('100')

    context = {
        "sale": sale,
        "sale_items": sale_items,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "discount_amount": discount_amount,
        "title": "Pro-forma Invoice",
    }

    return render(
        request,
        "sales/proforma_invoice.html",
        context
    )


@login_required
def sale_detail_api(request, pk):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    sale = get_object_or_404(
        Sale.objects.select_related('customer').prefetch_related('items__product'),
        id=pk,
        business=business
    )

    items = []

    for item in sale.items.all():
        remaining_qty = item.quantity - item.refunded_quantity

        items.append({
            "id": item.id,
            "name": item.product.product_name,

            # core quantities
            "qty": item.quantity,
            "refunded_qty": item.refunded_quantity,
            "remaining_qty": remaining_qty,

            # safety flags
            "can_refund": remaining_qty > 0,
            "is_fully_refunded": remaining_qty == 0,

            # pricing
            "price": float(item.price),
            "total": float(item.total),
        })

    data = {
        "id": sale.id,
        "receipt": sale.receipt_number,
        "invoice": sale.invoice_number,
        "customer": sale.customer.full_name if sale.customer else "Walk-in Customer",
        "subtotal": float(sale.subtotal),
        "total": float(sale.total),
        "paid": float(sale.amount_paid),
        "change": float(sale.change),
        "status": sale.status,
        "payment_method": sale.payment_method,
        "date": sale.created_at.strftime("%d %b %Y %H:%M"),
        "refund_date": sale.refund_date.strftime("%d %b %Y %H:%M") if sale.refund_date else None,
        "created_at": sale.created_at.strftime("%d %b %Y %H:%M"),

        # FIXED
        "can_refund": sale.can_refund,

        "items": items,
        "total_profit": float(sale.total_profit),
    }

    return JsonResponse(data)


@login_required
def sale_pdf_view(request, sale_id):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    sale = get_object_or_404(
        Sale.objects.select_related(
            'customer',
            'tax',
            'discount'
        ).prefetch_related(
            'items'
        ),
        id=sale_id,
        business=business
    )

    html = render_to_string(
        "sales/sale_pdf.html",
        {
            "sale": sale
        }
    )

    response = HttpResponse(
        content_type='application/pdf'
    )

    response['Content-Disposition'] = (
        f'attachment; filename="SALE-{sale.receipt_number}.pdf"'
    )

    pisa_status = pisa.CreatePDF(
        html,
        dest=response,
        encoding='UTF-8'
    )

    if pisa_status.err:
        return HttpResponse(
            "Error generating PDF",
            status=500
        )

    return response


@login_required
def sales_report_pdf(request):
    user = request.user

    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )

    business = staff.business

    tab = request.GET.get(
        'tab',
        'all'
    )

    sales = Sale.objects.filter(
        business=business
    ).select_related(
        'customer'
    ).prefetch_related(
        'items'
    ).order_by(
        '-created_at'
    )

    if tab == 'completed':
        sales = sales.filter(
            status='Completed'
        )

    elif tab == 'refunded':
        sales = sales.filter(
            status='Refunded'
        )

    total_revenue = sum(
        sale.total for sale in sales
    )

    total_profit = sum(
        sale.total_profit for sale in sales
    )

    template = get_template(
        'sales/sales_report_pdf.html'
    )

    html = template.render({
        'user': user,
        'business': business,
        'sales': sales,
        'tab': tab,
        'total_revenue': total_revenue,
        'total_profit': total_profit,
    })

    response = HttpResponse(
        content_type='application/pdf'
    )

    response['Content-Disposition'] = (
        'filename="sales-report.pdf"'
    )

    pisa_status = pisa.CreatePDF(
        html,
        dest=response
    )

    if pisa_status.err:
        return HttpResponse(
            'PDF generation error'
        )

    return response
