from rest_framework import serializers
from .models import Portfolio, AssetType, Symbol, Position, Transaction, LedgerEntry, ExchangeRate


class SymbolSerializer(serializers.ModelSerializer):
    """Basic serializer for Symbol."""
    nav = serializers.SerializerMethodField()

    class Meta:
        model = Symbol
        fields = ['id', 'asset_type', 'name', 'currency', 'nav_source', 'nav_fixed', 'script_url', 'nav_asset', 'nav']

    def get_nav(self, obj):
        # We can expose the calculated NAV right here!
        return obj.get_nav()


class AssetTypeSerializer(serializers.ModelSerializer):
    """Basic serializer for AssetType."""
    symbols = SymbolSerializer(many=True, read_only=True)

    class Meta:
        model = AssetType
        fields = ['id', 'portfolio', 'name', 'symbols']


class PositionSerializer(serializers.ModelSerializer):
    """Basic serializer for Position."""
    symbol_display = serializers.CharField(source='symbol.name', read_only=True)

    class Meta:
        model = Position
        fields = ['id', 'portfolio', 'symbol', 'symbol_display', 'quantity', 'average_cost']


class PortfolioSerializer(serializers.ModelSerializer):
    """Detailed serializer for Portfolio, optionally nesting its children."""
    asset_types = AssetTypeSerializer(many=True, read_only=True)
    positions = PositionSerializer(many=True, read_only=True)
    current_value = serializers.SerializerMethodField()

    class Meta:
        model = Portfolio
        fields = ['id', 'name', 'description', 'currency', 'current_value', 'asset_types', 'positions']

    def get_current_value(self, obj):
        from django.utils import timezone
        return obj.value_at(timezone.now().date())


class TransactionSerializer(serializers.ModelSerializer):
    """Basic serializer for Transaction."""
    class Meta:
        model = Transaction
        fields = '__all__'


class LedgerEntrySerializer(serializers.ModelSerializer):
    """Basic serializer for LedgerEntry."""
    class Meta:
        model = LedgerEntry
        fields = '__all__'


class ExchangeRateSerializer(serializers.ModelSerializer):
    """Basic serializer for ExchangeRate."""
    class Meta:
        model = ExchangeRate
        fields = ['id', 'from_currency', 'to_currency', 'date', 'rate']
