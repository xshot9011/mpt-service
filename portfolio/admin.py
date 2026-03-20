from django.contrib import admin
from .models import Portfolio, AssetType, Symbol, Transaction, LedgerEntry


# Allows editing Symbol objects directly within the AssetType edit page in the admin interface.
class SymbolInline(admin.TabularInline):
    model = Symbol
    extra = 1
    fields = ('name', 'currency', 'nav_source', 'nav_fixed', 'nav_asset', 'quantity', 'average_cost')
    readonly_fields = ('quantity', 'average_cost')


# Allows editing AssetType objects directly within the Portfolio edit page in the admin interface.
class AssetTypeInline(admin.TabularInline):
    model = AssetType
    extra = 1


# Registers the Portfolio model with the admin site and customizes its display
@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('name', 'currency')
    inlines = [AssetTypeInline]


# Registers the AssetType model and customizes its admin interface
@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'portfolio')
    list_filter = ('portfolio',)
    inlines = [SymbolInline]


# Registers the Symbol model and customizes its admin interface
@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ('name', 'portfolio', 'asset_type', 'currency', 'nav_source', 'quantity', 'average_cost')
    list_filter = ('nav_source', 'currency', 'portfolio')


# Default registration for remaining models
admin.site.register(Transaction)
admin.site.register(LedgerEntry)
