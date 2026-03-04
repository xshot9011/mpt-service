from django.contrib import admin
from .models import Asset, DailyPrice

admin.site.register(Asset)
admin.site.register(DailyPrice)
