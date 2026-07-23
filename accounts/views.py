from django.shortcuts import render, redirect
from django.contrib import messages

from accounts.forms import *
from business.forms import *
from inventory.models import *
from sales.models import *
import csv
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import *
from business.models import *
from django.db import transaction
from django.utils import timezone

from decimal import Decimal
from django.db.models import Sum
from django.db.models.functions import Coalesce

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch
from django.contrib.contenttypes.models import ContentType
from .utils import get_client_ip

from datetime import timedelta
from .get_business import get_business
# Create your views here.


@login_required
def index(request):
    user = request.user
    business = get_business(request)

    today = timezone.now().date()

    context = {
        "today": today,
        "business": business,

    }

    return render(request, 'index.html', context)


@transaction.atomic
def register_business(request):

    form = CreateUserForm()
    pform = ProfileForm()
    businessform = BusinessForm()

    if request.method == 'POST':

        form = CreateUserForm(request.POST)
        pform = ProfileForm(request.POST, request.FILES)
        businessform = BusinessForm(request.POST, request.FILES)

        if form.is_valid() and pform.is_valid() and businessform.is_valid():

            # =========================
            # CREATE USER
            # =========================
            user = form.save()

            # =========================
            # CREATE BUSINESS
            # =========================
            business = businessform.save(commit=False)
            business.owner = user
            business.save()

            # =========================
            # CREATE PROFILE
            # =========================
            profile = pform.save(commit=False)
            profile.staff = user
            profile.business_id = business.id
            profile.role_type = 'Admin'
            profile.save()

            # =========================
            # AUDIT LOG (BUSINESS CREATED)
            # =========================

            AuditLog.objects.create(

                user=user,

                action="Business Registration",

                description=(
                    f"New business '{business.name}' was created by "
                    f"{user.first_name or user.username}. "
                    f"Assigned role: Admin."
                ),

                content_type=ContentType.objects.get_for_model(Business),

                object_id=business.id,

                ip_address=request.META.get("REMOTE_ADDR")
            )

            messages.success(
                request,
                'Business account created successfully.'
            )

            return redirect('/')

        else:
            messages.error(
                request,
                'Please correct the errors below.'
            )

    context = {
        "form": form,
        "pform": pform,
        "businessform": businessform,
        "title": "Business Registration",
    }

    return render(
        request,
        'accounts/register_business.html',
        context
    )


@login_required
@transaction.atomic
def staff_profile(request):

    user = request.user
    staff = StaffProfile.objects.get(staff_id=user.id)
    business = get_business(request)

    total_staff = StaffProfile.objects.filter(business=get_business(request)).count()

    total_products = Inventory.objects.filter(business=get_business(request)).count()

    sales = Sale.objects.filter(business=get_business(request), status='Completed')

    total_revenue = sales.aggregate(total=Coalesce(Sum('total'), Decimal('0.00')))['total']
    #
    # total_profit = SaleItem.objects.filter(sale__business=business, sale__status='Completed').aggregate(
    #     total=Coalesce(Sum('profit'), Decimal('0.00')))['total']

    if request.method == 'POST':

        form = UpdateUserForm(
            request.POST,
            instance=user
        )

        pform = ProfileForm(
            request.POST,
            request.FILES,
            instance=staff
        )

        if form.is_valid() and pform.is_valid():

            # =========================
            # USER
            # =========================
            user_instance = form.save(commit=False)
            user_instance.save()

            # =========================
            # PROFILE
            # =========================
            profile_instance = pform.save(commit=False)
            profile_instance.staff = user_instance
            profile_instance.save()

            # =========================
            # AUDIT LOG (PROFILE UPDATE)
            # =========================

            AuditLog.objects.create(

                user=user_instance,

                action="Staff Profile Update",

                description=(
                    f"{user_instance.first_name or user_instance.username} "
                    f"updated profile for '{user_instance.first_name}'." f"{user_instance.last_name} "
                ),

                content_type=ContentType.objects.get_for_model(Business),

                object_id=business.id,

                ip_address=request.META.get("REMOTE_ADDR")
            )

            messages.success(
                request,
                'Profile updated successfully.'
            )

            return redirect('staff_profile')

        else:

            messages.error(
                request,
                'Please correct the errors below.'
            )

    else:

        form = UpdateUserForm(instance=user)

        pform = ProfileForm(instance=staff)

    context = {
        "user": user,
        "form": form,
        "pform": pform,

        "business": business,
        "staff": staff,

        # OPTIONAL STATS
        "total_staff": total_staff,
        "total_products": total_products,
        "total_revenue": total_revenue,

        "title": "Staff Profile",
    }

    return render(
        request,
        'accounts/staff_profile.html',
        context
    )


@login_required
@transaction.atomic
def business_profile(request):

    user = request.user
    business = get_business(request)

    total_staff = StaffProfile.objects.filter( business = get_business(request)).count()

    total_products = Inventory.objects.filter( business = get_business(request)).count()

    sales = Sale.objects.filter( business = get_business(request), status='Completed')

    total_revenue = sales.aggregate(total=Coalesce(Sum('total'), Decimal('0.00')))['total']
    #
    # total_profit = SaleItem.objects.filter(sale__business=business, sale__status='Completed').aggregate(
    #     total=Coalesce(Sum('profit'), Decimal('0.00')))['total']

    if request.method == 'POST':

        form = UpdateUserForm(
            request.POST,
            instance=user
        )

        pform = ProfileForm(
            request.POST,
            request.FILES,
            instance=staff
        )

        bform = BusinessForm(request.POST, request.FILES, instance=business)

        if form.is_valid() and pform.is_valid() and bform.is_valid():

            # =========================
            # USER
            # =========================
            user_instance = form.save(commit=False)
            user_instance.save()

            # =========================
            # PROFILE
            # =========================
            profile_instance = pform.save(commit=False)
            profile_instance.staff = user_instance
            profile_instance.save()

            # =========================
            # BUSINESS
            # =========================
            # if staff.role_type == "Admin":
            business_instance = bform.save(commit=False)
            business_instance.save()

            # =========================
            # AUDIT LOG (PROFILE UPDATE)
            # =========================

            AuditLog.objects.create(

                user=user_instance,

                action="Staff Profile Update",

                description=(
                    f"{user_instance.first_name or user_instance.username} "
                    f"updated profile for '{user_instance.first_name}'." f"{user_instance.last_name} "
                ),

                content_type=ContentType.objects.get_for_model(Business),

                object_id=business.id,

                ip_address=request.META.get("REMOTE_ADDR")
            )

            messages.success(
                request,
                'Profile updated successfully.'
            )

            return redirect('business_profile')

        else:

            messages.error(
                request,
                'Please correct the errors below.'
            )

    else:

        form = UpdateUserForm(instance=user)

        pform = ProfileForm(instance=staff)
        bform = BusinessForm(instance=business)

    context = {
        "user": user,
        "form": form,
        "pform": pform,
        "bform": bform,

        "business": business,
        "staff": staff,

        # OPTIONAL STATS
        "total_staff": total_staff,
        "total_products": total_products,
        "total_revenue": total_revenue,

        "title": "Staff Profile",
    }

    return render(
        request,
        'accounts/business_profile.html',
        context
    )


@login_required
@transaction.atomic
def register_staff(request):

    user = User.objects.get(id=request.user.id)

    business = get_business(request)

    form = CreateUserForm()
    pform = StaffProfileForm()

    if request.method == 'POST':

        form = CreateUserForm(request.POST)
        pform = StaffProfileForm(
            request.POST,
            request.FILES
        )

        if form.is_valid() and pform.is_valid():

            # =========================
            # CREATE USER
            # =========================

            new_user = form.save()

            profile = pform.save(
                commit=False
            )

            profile.staff = new_user
            profile.business = business
            profile.save()

            # =========================
            # CREATE AUDIT LOG
            # =========================

            AuditLog.objects.create(

                user=request.user,

                action="Staff Registration",

                description=(
                    f"{request.user.username} "
                    f"created staff account "
                    f"'{new_user.username}' "
                    f"with role "
                    f"'{profile.role_type}'"
                ),

                content_type=ContentType.objects.get_for_model(
                    profile
                ),

                object_id=profile.id,

                ip_address=get_client_ip(
                    request
                )

            )

            messages.success(
                request,
                "User account created successfully."
            )

            return redirect(
                'register_staff'
            )

        else:

            messages.error(
                request,
                "Please correct the errors below."
            )

    # =========================
    # ANALYTICS
    # =========================

    staff_qs = StaffProfile.objects.filter(
        business=business
    )

    total_staff = staff_qs.count()

    admin_count = staff_qs.filter(
        role_type="Admin"
    ).count()

    cashier_count = staff_qs.filter(
        role_type="Cashier"
    ).count()

    today_staff = staff_qs.filter(
        staff__date_joined__date=timezone.now().date()
    ).count()

    context = {

        "user": user,
        "business": business,
        "form": form,
        "pform": pform,

        "total_staff": total_staff,
        "admin_count": admin_count,
        "cashier_count": cashier_count,
        "today_staff": today_staff,

        "title": "Business Registration",
    }

    return render(
        request,
        'accounts/register_staff.html',
        context
    )


@login_required
@transaction.atomic
def update_staff(request, staff_id):

    user = request.user

    business = get_business(request)

    form = UpdateUserForm(instance=user)
    pform = StaffProfileForm(instance=staff)

    if request.method == "POST":

        form = UpdateUserForm(request.POST, instance=user)
        pform = StaffProfileForm(
            request.POST,
            request.FILES,
            instance=staff
        )

        if form.is_valid() and pform.is_valid():

            instance = form.save()
            profile = pform.save(commit=False)
            profile.save()

            # =========================
            # CREATE AUDIT LOG
            # =========================

            AuditLog.objects.create(

                user=request.user,

                action="Staff Registration",

                description=(
                    f"{request.user.username} "
                    f"updated staff details "
                    f"'{instance.username}' "
                    f"with role "
                    f"'{profile.role_type}'"
                ),

                content_type=ContentType.objects.get_for_model(
                    profile
                ),

                object_id=profile.id,

                ip_address=get_client_ip(
                    request
                )

            )

            messages.success(request, "Staff updated successfully.")
            return redirect("staff_list")

        messages.error(request, "Please correct the errors below.")

    # =========================
    # 🔥 ANALYTICS FIX HERE
    # =========================

    staff_qs = StaffProfile.objects.filter(business = get_business(request))

    total_staff = staff_qs.count()

    admin_count = staff_qs.filter(role_type="Admin").count()

    cashier_count = staff_qs.filter(role_type="Cashier").count()

    today_staff = staff_qs.filter(
        staff__date_joined__date=timezone.now().date()
    ).count()

    context = {
        "form": form,
        "pform": pform,
        "staff": staff,
        "user": user,
        "business": business,

        # 🔥 FIXED ANALYTICS
        "total_staff": total_staff,
        "admin_count": admin_count,
        "cashier_count": cashier_count,
        "today_staff": today_staff,
        "title": "Update staff " + str(user.first_name) + " details"
    }

    return render(request, "accounts/update_staff.html", context)


@login_required
@transaction.atomic
def deactivate_staff(request, staff_id):

    user = User.objects.get(id=request.user.id)

    business = get_business(request)

    # Prevent repeated deactivation
    if not staff.is_active:

        messages.warning(
            request,
            "Staff is already inactive."
        )

        return redirect("staff_list")

    # ==========================
    # DEACTIVATE STAFF
    # ==========================

    staff.is_active = False
    staff.save()

    # ==========================
    # AUDIT LOG
    # ==========================

    AuditLog.objects.create(

        # user performing action
        user=request.user,

        action="Staff Deactivation",

        description=(
            f"{request.user.first_name or request.user.username} "
            f"deactivated staff "
            f"'{staff.staff.first_name} "
            f"{staff.staff.last_name}' "
            f"with role '{staff.role_type}'"
        ),

        content_type=ContentType.objects.get_for_model(
            StaffProfile
        ),

        object_id=staff.id,

        ip_address=get_client_ip(
            request
        )
    )

    messages.success(
        request,
        "Staff deactivated successfully."
    )

    return redirect("staff_list")


@login_required
@transaction.atomic
def reactivate_staff(request, staff_id):
    business = get_business(request)

    staff.is_active = True
    staff.save()

    AuditLog.objects.create(

        user=request.user,

        action="Staff Reactivation",

        description=(
            f"{request.user.first_name or request.user.username} "
            f"reactivated "
            f"'{staff.staff.first_name} "
            f"{staff.staff.last_name}' "
            f"with role '{staff.role_type}'"
        ),

        content_object=staff,

        ip_address=request.META.get(
            "REMOTE_ADDR"
        )
    )

    messages.success(
        request,
        "Staff reactivated successfully."
    )

    return redirect(
        "staff_list"
    )


@login_required
@transaction.atomic
def delete_staff(request, staff_id):
    business = get_business(request)

    user = staff_profile.staff

    if request.method == "POST":
        AuditLog.objects.create(

            user=request.user,

            action="Staff Deleted",

            description=(
                f"{request.user.username} permanently deleted staff "
                f"'{staff_profile.staff.first_name} "
                f"{staff_profile.staff.last_name}' "
                f"({staff_profile.staff.username}) "
                f"from the system."
            ),

            content_type=ContentType.objects.get_for_model(StaffProfile),

            object_id=staff_profile.id,

            ip_address=request.META.get("REMOTE_ADDR")
        )

        staff_profile.delete()
        user.delete()

        messages.success(
            request,
            "Staff deleted successfully."
        )

        return redirect("staff_list")


@login_required
def staff_list_view(request):

    user = User.objects.get(id=request.user.id)

    business = get_business(request)

    search = request.GET.get("search", "").strip()
    role = request.GET.get("role", "").strip()
    tab = request.GET.get("tab", "active")

    # =========================
    # BASE STAFF QUERY
    # =========================
    staff_qs = StaffProfile.objects.filter(
        business=get_business(request)
    )

    base_qs = StaffProfile.objects.filter(
        business=get_business(request)
    )

    # =========================
    # ACTIVE / INACTIVE
    # =========================
    if tab == "inactive":
        staff_qs = staff_qs.filter(is_active=False)
    else:
        staff_qs = staff_qs.filter(is_active=True)

    # =========================
    # SEARCH
    # =========================
    if search:
        staff_qs = staff_qs.filter(
            Q(staff__first_name__icontains=search) |
            Q(staff__last_name__icontains=search) |
            Q(staff__username__icontains=search) |
            Q(staff__email__icontains=search)
        )

    # =========================
    # ROLE
    # =========================
    if role:
        staff_qs = staff_qs.filter(role_type=role)

    # =========================
    # PAGINATION
    # =========================
    paginator = Paginator(
        staff_qs.order_by("-id"),
        10
    )

    page = request.GET.get("page")
    staff_list = paginator.get_page(page)

    # =========================
    # CONTENT TYPES
    # =========================
    staff_ct = ContentType.objects.get_for_model(
        StaffProfile
    )

    user_ct = ContentType.objects.get_for_model(
        User
    )

    now = timezone.now()

    # =========================
    # ATTACH ACTIVITY TO STAFF
    # =========================
    for staff in staff_list:

        # =================================
        # STAFF ACTIVITY + PERFORMED ACTIONS
        # =================================

        logs = AuditLog.objects.filter(

            # actions performed ON this staff
            Q(
                content_type=staff_ct,
                object_id=staff.id
            )

            |

            Q(
                content_type=user_ct,
                object_id=staff.staff.id
            )

            |

            # actions performed BY this user
            Q(
                user=staff.staff
            )

        ).distinct().order_by(
            "-created_at"
        )[:5]

        recent_logs = []

        for log in logs:

            diff = now - log.created_at

            if diff < timedelta(minutes=1):
                ago = "Just now"

            elif diff < timedelta(hours=1):
                mins = int(diff.total_seconds()/60)
                ago = f"{mins} minute{'s' if mins !=1 else ''} ago"

            elif diff < timedelta(days=1):
                hrs = int(diff.total_seconds()/3600)
                ago = f"{hrs} hour{'s' if hrs !=1 else ''} ago"

            elif diff < timedelta(days=7):
                days = diff.days
                ago = f"{days} day{'s' if days !=1 else ''} ago"

            else:
                ago = log.created_at.strftime(
                    "%d %b %Y"
                )

            actor = "System"

            if log.user:
                actor = (
                    f"{log.user.first_name} "
                    f"{log.user.last_name}"
                ).strip()

                if not actor:
                    actor = log.user.username

            recent_logs.append({

                "action": log.action,

                "description":
                    f"{actor}: {log.description}"
                    if log.description
                    else actor,

                "time": ago
            })

        staff.recent_logs = recent_logs

    context = {
        "staff_list": staff_list,
        "search": search,
        "role": role,
        "tab": tab,
        "business": business,
        "active_count":
            base_qs.filter(
                is_active=True
            ).count(),

        "inactive_count":
            base_qs.filter(
                is_active=False
            ).count(),
    }

    return render(
        request,
        "accounts/staff_list.html",
        context
    )




