from accounts.models import StaffProfile
from django.shortcuts import get_object_or_404


def get_staff_profile(request):
    """
    Resolve the logged-in user's StaffProfile -- business and role_type
    both live here. get_business() below is a thin wrapper around this,
    kept so any existing caller that only needs the Business object
    doesn't need to change.

    NOTE: this assumes exactly one StaffProfile per User (get_object_or_404
    raises if zero OR more than one match). If a person can legitimately
    hold staff profiles at more than one business, this needs a business
    selector (e.g. a session key for "active business") rather than a
    bare lookup by user -- flagging this as a pre-existing assumption,
    not something introduced here.
    """
    return get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user,
    )


def get_business(request):
    return get_staff_profile(request).business
