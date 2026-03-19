from django.db import models
from decimal import Decimal
from django.utils import timezone
from django.core.validators import MinValueValidator
from nav_manager.models import Asset as NavAsset, DailyPrice


class Portfolio(models.Model):
    """A collection of symbols organised by asset types."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    currency = models.CharField(
        max_length=3,
        default='THB',
        help_text="Base currency for the portfolio (ISO 4217, e.g., THB, USD). This currency will be used to calculate the moving average cost."
    )

    def __str__(self):
        return self.name

    def value_at(self, target_date):
        """Calculate the total point-in-time value of the portfolio at target_date."""
        total_value = Decimal('0')

        for symbol in self.symbols.all():
            transactions_up_to_date = symbol.transactions.filter(timestamp__date__lte=target_date)

            qty = Decimal('0')
            for tx in transactions_up_to_date:
                qty += tx.quantity

            if qty > 0:
                nav = symbol.get_nav(target_date)
                if nav is not None:
                    total_value += qty * nav

        return total_value.quantize(Decimal('0.00000001'))


class AssetType(models.Model):
    """A category of assets within a portfolio (e.g. 'Cash', 'Thai Equity', 'Crypto')."""
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='asset_types')
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ('portfolio', 'name')

    def __str__(self):
        return f"{self.portfolio.name} / {self.name}"


class Symbol(models.Model):
    """A holding within a portfolio, combining NAV configuration and position data.

    Each symbol represents a user-named asset with its pricing source and
    quantity/cost tracking.  NAV can be provided via three sources:
      FIXED       — a static decimal stored on this record.
      SCRIPT      — a URL / formula string (e.g. IMPORTXML) for the frontend
                    to fetch via the proxy-scrape endpoint.
      NAV_MANAGER — linked to a nav_manager.Asset; NAV is resolved from its
                    DailyPrice records.
    """
    class NavSource(models.TextChoices):
        FIXED = 'FIXED', 'Fixed Value'
        SCRIPT = 'SCRIPT', 'User Script (IMPORTXML)'
        NAV_MANAGER = 'NAV_MANAGER', 'NAV Manager'

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='symbols')
    asset_type = models.ForeignKey(AssetType, on_delete=models.PROTECT, related_name='symbols')
    name = models.CharField(max_length=100)
    currency = models.CharField(
        max_length=3,
        default='THB',
        help_text="Currency this symbol is denominated in (ISO 4217, e.g. USD, THB).",
    )

    # --- NAV configuration ---

    nav_source = models.CharField(
        max_length=20,
        choices=NavSource.choices,
        default=NavSource.FIXED,
    )

    # Used when nav_source == FIXED
    nav_fixed = models.DecimalField(
        max_digits=30, decimal_places=8,
        null=True, blank=True,
    )

    # Used when nav_source == SCRIPT
    script_url = models.TextField(
        blank=True,
        help_text="URL to scrape the NAV from (used like IMPORTXML).",
    )
    script_xpath = models.TextField(
        blank=True,
        help_text="XPath query to extract the NAV from the URL (used like IMPORTXML).",
    )

    # Used when nav_source == NAV_MANAGER
    nav_asset = models.ForeignKey(
        NavAsset,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='symbols',
        help_text="Link to a nav_manager Asset whose DailyPrice records supply the NAV.",
    )

    # --- Position data ---

    quantity = models.DecimalField(
        max_digits=30, decimal_places=8, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    average_cost = models.DecimalField(
        max_digits=30, decimal_places=8, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )

    class Meta:
        unique_together = ('portfolio', 'asset_type', 'name')
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gte=0),
                name='symbol_quantity_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(average_cost__gte=0),
                name='symbol_average_cost_non_negative'
            ),
        ]

    def __str__(self):
        return f"{self.asset_type} / {self.name}"

    def get_nav(self, target_date=None):
        """Return the NAV decimal for the given date (or today if omitted).

        Returns None if the NAV cannot be determined.
        """
        if target_date is None:
            target_date = timezone.now().date()

        if self.nav_source == self.NavSource.FIXED:
            return self.nav_fixed

        if self.nav_source == self.NavSource.SCRIPT:
            # The script URL is for external/frontend use only.
            # Return None here; callers should handle this gracefully.
            return None

        if self.nav_source == self.NavSource.NAV_MANAGER:
            if self.nav_asset is None:
                return None
            latest_price = DailyPrice.objects.filter(
                asset=self.nav_asset,
                date__lte=target_date,
            ).order_by('-date').first()
            return latest_price.price if latest_price else None

        return None

    def recalculate_average_cost(self):
        """Re-calculate the moving-average cost based on all related BUY transactions.

        Only BUY transactions affect the average cost; SELLs reduce quantity.
        FX conversion is handled implicitly by modelling foreign currencies
        as their own symbols (e.g. a USD symbol with avg cost in THB).
        """
        buys = self.transactions.filter(transaction_type=Transaction.Type.BUY)
        total_qty = Decimal('0')
        total_cost = Decimal('0')
        for tx in buys:
            total_qty += tx.quantity
            total_cost += tx.quantity * tx.price
        if total_qty > 0:
            self.average_cost = (total_cost / total_qty).quantize(Decimal('0.00000001'))
        else:
            self.average_cost = Decimal('0')
        self.save(update_fields=['average_cost'])

    def cost_calculation_breakdown(self):
        """Return step-by-step breakdown of moving average cost calculation.

        Each entry shows a BUY transaction's contribution and the running
        average up to that point.  Useful for auditing / debugging.
        """
        buys = self.transactions.filter(
            transaction_type=Transaction.Type.BUY,
        ).order_by('timestamp')
        steps = []
        running_qty = Decimal('0')
        running_cost = Decimal('0')
        for tx in buys:
            line_cost = tx.quantity * tx.price
            running_qty += tx.quantity
            running_cost += line_cost
            steps.append({
                'transaction_id': tx.id,
                'timestamp': tx.timestamp,
                'quantity': tx.quantity,
                'price': tx.price,
                'line_cost': line_cost,
                'running_qty': running_qty,
                'running_cost': running_cost,
                'running_avg': (running_cost / running_qty).quantize(Decimal('0.00000001')),
            })
        return steps

    def unrealized_pnl(self, market_price: Decimal) -> Decimal:
        """Calculate unrealized P&L based on provided market price."""
        return (market_price - self.average_cost) * self.quantity


class Transaction(models.Model):
    """A trade that changes a symbol's holdings and creates ledger entries."""
    class Type(models.TextChoices):
        BUY = 'BUY', 'Buy'
        SELL = 'SELL', 'Sell'

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=4, choices=Type.choices)
    quantity = models.DecimalField(max_digits=30, decimal_places=8)
    price = models.DecimalField(max_digits=30, decimal_places=8)  # price per unit

    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.transaction_type} {self.quantity} {self.symbol.name} @ {self.price}"

    def save(self, *args, **kwargs):
        """Override save to update symbol holdings and create ledger entries."""
        super().save(*args, **kwargs)
        # Update symbol quantity (quantity can be positive or negative)
        self.symbol.quantity += self.quantity
        self.symbol.save(update_fields=['quantity'])
        # Recalculate average cost after a BUY (positive quantity)
        if self.quantity > 0:
            self.symbol.recalculate_average_cost()
        # Create double-entry ledger entries
        LedgerEntry.create_from_transaction(self)

    def realized_pnl(self) -> Decimal:
        """Realized P&L for this transaction (only meaningful for SELL / negative qty)."""
        if self.quantity < 0:
            abs_qty = abs(self.quantity)
            cost_basis = self.symbol.average_cost * abs_qty
            proceeds = self.price * abs_qty
            return (proceeds - cost_basis).quantize(Decimal('0.00000001'))
        return Decimal('0')


class LedgerEntry(models.Model):
    """Double-entry record for each transaction.

    For every transaction two entries are created: a debit and a credit.
    """
    class EntryType(models.TextChoices):
        DEBIT = 'DEBIT', 'Debit'
        CREDIT = 'CREDIT', 'Credit'

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='ledger_entries')
    entry_type = models.CharField(max_length=6, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=30, decimal_places=8)
    account = models.CharField(max_length=100)  # e.g. "Cash", "Asset"
    description = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    @classmethod
    def create_from_transaction(cls, transaction):
        """Create paired debit/credit entries for a transaction."""
        amount = (transaction.quantity * transaction.price).quantize(Decimal('0.00000001'))
        symbol_name = transaction.symbol.name
        if transaction.transaction_type == Transaction.Type.BUY:
            cls.objects.create(
                transaction=transaction,
                entry_type=cls.EntryType.DEBIT,
                amount=amount,
                account='Cash',
                description=f"Buy {transaction.quantity} {symbol_name}",
            )
            cls.objects.create(
                transaction=transaction,
                entry_type=cls.EntryType.CREDIT,
                amount=amount,
                account='Asset',
                description=f"Buy {transaction.quantity} {symbol_name}",
            )
        else:
            cls.objects.create(
                transaction=transaction,
                entry_type=cls.EntryType.DEBIT,
                amount=amount,
                account='Asset',
                description=f"Sell {transaction.quantity} {symbol_name}",
            )
            cls.objects.create(
                transaction=transaction,
                entry_type=cls.EntryType.CREDIT,
                amount=amount,
                account='Cash',
                description=f"Sell {transaction.quantity} {symbol_name}",
            )

    def __str__(self):
        return f"{self.entry_type} {self.amount} to {self.account}"
