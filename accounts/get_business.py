from .models import *
from business.models import *
from django.shortcuts import render, get_object_or_404

def get_business(request):
    staff = get_object_or_404(
        StaffProfile.objects.select_related("business"),
        staff=request.user
    )
    return staff.business