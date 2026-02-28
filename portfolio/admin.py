from django.contrib import admin
from .models import Broker, Position, Transaction, LedgerEntry, Portfolio

admin.site.register(Broker)
admin.site.register(Position)
admin.site.register(Transaction)
admin.site.register(LedgerEntry)
admin.site.register(Portfolio)
