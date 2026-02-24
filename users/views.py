from django.shortcuts import render
from django.http import HttpResponse

def landing_page(request):
    if request.user.is_authenticated:
        return HttpResponse(f"hello {request.user.email}")
    else:
        return HttpResponse('Welcome. Please <a href="/accounts/login/">login</a>.')
