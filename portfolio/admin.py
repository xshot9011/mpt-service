from django.contrib import admin
# Imforms Django admin to use these models in the admin interface
from .models import Portfolio, AssetType, Symbol, Position, Transaction, LedgerEntry


# Allows editing Symbol objects directly within the AssetType edit page in the admin interface.
# TabularInline displays them in a compact, table-like format.
class SymbolInline(admin.TabularInline):
    # Specifies which model this inline represents
    model = Symbol
    # Number of empty form rows to display by default for adding new Symbols
    extra = 1


# Allows editing AssetType objects directly within the Portfolio edit page in the admin interface.
class AssetTypeInline(admin.TabularInline):
    # Specifies which model this inline represents
    model = AssetType
    # Number of empty form rows to display by default for adding new AssetTypes
    extra = 1


# Registers the Portfolio model with the admin site and customizes its display
@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    # Fields to display as columns in the Portfolio list view
    list_display = ('name',)
    # Includes the AssetTypeInline so you can add/edit AssetTypes when viewing a Portfolio
    inlines = [AssetTypeInline]


# Registers the AssetType model and customizes its admin interface
@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    # Displays the AssetType name and the Portfolio it belongs to in the list view
    list_display = ('name', 'portfolio')
    # Adds a sidebar filter to let users filter AssetTypes by Portfolio
    list_filter = ('portfolio',)
    # Includes the SymbolInline so you can add/edit Symbols when viewing an AssetType
    inlines = [SymbolInline]


# Registers the Symbol model and customizes its admin interface
@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    # Columns to show in the list view, providing a quick overview of NAV settings
    list_display = ('name', 'asset_type', 'nav_source', 'nav_fixed', 'nav_asset')
    # Adds sidebar filters to filter Symbols by their NAV source or the Portfolio they belong to
    list_filter = ('nav_source', 'asset_type__portfolio')


# Default registration for these models without any custom admin class (uses default basic views)
admin.site.register(Position)
admin.site.register(Transaction)
admin.site.register(LedgerEntry)
