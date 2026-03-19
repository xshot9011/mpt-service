from django.urls import path
from .views import ProxyScrapeView

app_name = 'portfolio'

urlpatterns = [
    path('proxy-scrape/', ProxyScrapeView.as_view(), name='proxy_scrape'),
]
