"""
Sidebar context — badge counts (low_stock_count, pending_sales,
customer_count) AND the logged-in user's staff profile (staff).

WHY A CONTEXT PROCESSOR:
admin_sidebar.html is rendered on essentially every page (it lives in
base/base.html), so whatever supplies these values has to run on every
request, not just some. Three options exist for that:

  1. Add the same queries to every view's context dict.
     -> what you're trying to avoid; also guaranteed to be forgotten on
        the next new view someone adds.
  2. A template tag that queries the DB inline.
     -> works, but re-runs on every {% include %} of the sidebar with no
        single place to cache/invalidate it.
  3. A context processor.
     -> runs once per request, automatically available in every
        template's context, one file to maintain. This is what's below.

`staff` was added here after the sidebar's own
`{% with staff=request.user.staffprofile %}` turned out to silently
resolve to nothing on every request -- StaffProfile.staff is a plain
ForeignKey, so Django's actual reverse accessor is `staffprofile_set`,
not `.staffprofile`. Templates swallow that AttributeError silently, so
`staff` was undefined everywhere the sidebar renders, not just in one
section of it.

PERFORMANCE:
Without caching, that's 3 extra queries on every single page load just
for sidebar badges nobody is looking at most of the time. Instead, the
counts are cached per-business for a short window (60s) using Django's
cache framework, and proactively invalidated the moment a relevant model
changes (see signals.py) — so the badge is never more than one save/
delete-cycle stale, without paying the query cost on every request.

`staff` is deliberately NOT part of that cached entry. The count cache
is keyed by business_id and shared across every staff member of that
business -- correct for counts (same numbers for everyone), but wrong
for `staff`, which is per-user. Caching it there would risk one staff
member's role_type being served to a different staff member of the same
business. It costs no extra query to resolve fresh each request:
get_staff_profile() was already being queried every request via
get_business() before this change, just discarding the object and
keeping only .business.

IMPORTANT — the get_staff_profile import below is intentionally INSIDE
the function, not at the top of this file. accounts.models imports
(directly or via a chain) something that eventually reaches back into
this file at Django's app-loading time, and a top-level `from
accounts.get_business import get_staff_profile` here turns that into a
circular import:

    accounts.models (loading)
      -> ... -> business.context_processors (this file)
           -> accounts.get_business
                -> accounts.models  <-- still loading, not finished yet
                   -> ImportError: cannot import name 'StaffProfile'
                      from partially initialized module 'accounts.models'

Deferring the import into the function body means it isn't evaluated
until a request actually comes in and sidebar_counts() runs — by which
point every app has finished loading and the cycle never triggers.
"""

from django.core.cache import cache

CACHE_TTL_SECONDS = 60
LOW_STOCK_THRESHOLD = 5  # matches the <=5 threshold already used in view_inventory.html
BADGE_DISPLAY_CAP = 99   # sidebar badges are a fixed-width pill; show "99+" past this


def cache_key_for(business_id):
    return f"sidebar_counts:{business_id}"


def _for_badge(n):
    """
    Cap a count for display in the small sidebar pill. Returns the real
    int when it's small (so {% if %} in the template still correctly
    treats 0 as falsy and hides the badge), or a "99+" style string once
    it's too wide to fit — the pill has a fixed min-width, so an
    uncapped 3-4 digit count would overflow/break the sidebar layout.
    The real, uncapped number is still what every other page (e.g. an
    actual low-stock or sales list) shows — only this cached dict, which
    only ever feeds the sidebar badge, is capped.
    """
    return n if n <= BADGE_DISPLAY_CAP else f"{BADGE_DISPLAY_CAP}+"


def sidebar_counts(request):
    """
    Registered in settings.py under TEMPLATES -> OPTIONS -> context_processors.
    Returns {} (i.e. contributes nothing) for logged-out users, or when
    get_staff_profile() can't resolve one, so the sidebar's |default:"0"
    filters and `{% if staff %}` checks still apply safely in those cases.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    from accounts.get_business import get_staff_profile  # see note at top of file

    try:
        staff = get_staff_profile(request)
    except Exception:
        # get_staff_profile() uses get_object_or_404, which raises Http404
        # when the logged-in user has no StaffProfile (e.g. a superuser
        # made via createsuperuser, or a user mid-onboarding). A context
        # processor runs on every page — including the Django admin,
        # since this project only defines one template backend — so it
        # must never raise; just contribute nothing in that case.
        return {}

    business = staff.business
    if business is None:
        return {"staff": staff}

    key = cache_key_for(business.id)
    counts = cache.get(key)

    if counts is None:
        # Imported here (rather than at module level) to avoid any import-
        # order issues between apps at Django startup.
        from inventory.models import Inventory
        from sales.models import Sale, Customer

        counts = {
            "low_stock_count": _for_badge(
                Inventory.objects.filter(
                    business=business,
                    status="active",
                    stock_quantity__lte=LOW_STOCK_THRESHOLD,
                ).count()
            ),
            "pending_sales": _for_badge(
                Sale.objects.filter(
                    business=business,
                    status="Proforma",
                ).count()
            ),
            "customer_count": _for_badge(
                Customer.objects.filter(
                    business=business,
                ).count()
            ),
        }
        cache.set(key, counts, CACHE_TTL_SECONDS)

    return {"staff": staff, **counts}
