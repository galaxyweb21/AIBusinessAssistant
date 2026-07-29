from django.shortcuts import render, redirect
from .models import Business
from .forms import BusinessForm

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from .context_processors import sidebar_counts as _sidebar_counts_context

# Create your views here.

from .context_processors import sidebar_counts as _sidebar_counts_context


@login_required
def sidebar_counts_api(request):
    return JsonResponse(_sidebar_counts_context(request))


def business(request):

    form = BusinessForm()
    if request.method == 'POST':
        form = BusinessForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)

            if Business.objects.filter(name=instance.name).exists():
                messages.error(request, 'Sorry Business Name ' + str(instance.name) + ' already exists')
            else:
                instance.save()

                messages.success(request, 'successfully saved')
                return redirect('/accounts/index/')

    context = {
        "form": form,
        "title": "Register Business",

        }

    return render(request, "business/business.html", context)

