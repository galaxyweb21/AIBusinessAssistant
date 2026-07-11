from django.shortcuts import render, redirect
from .models import Business
from .forms import BusinessForm

# Create your views here.


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
