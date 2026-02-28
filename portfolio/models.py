from django.db import models
from decimal import Decimal
from django.utils import timezone
from symbol.models import Asset, DailyPrice


class Broker(models.Model):
    """Entity through which trades are executed."""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Portfolio(models.Model):
    """A collection of positions and transactions."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

    def value_at(self, target_date):
        """Calculate the total point-in-time value of the portfolio at target_date."""
        total_value = Decimal('0')
        # We need to compute the quantity of each asset held at target_date
        # Then multiply by the last known DailyPrice <= target_date
        
        # Get all positions in this portfolio
        for position in self.positions.all():
            # Sum quantity of buys - sells before or on target_date
            transactions_up_to_date = position.transactions.filter(timestamp__date__lte=target_date)
            
            qty = Decimal('0')
            for tx in transactions_up_to_date:
                if tx.transaction_type == Transaction.Type.BUY:
                    qty += tx.quantity
                else:
                    qty -= tx.quantity
            
            if qty > 0:
                # Find the latest price for this asset <= target_date
                latest_price = DailyPrice.objects.filter(
                    asset=position.asset, 
                    date__lte=target_date
                ).order_by('-date').first()
                
                if latest_price:
                    total_value += qty * latest_price.price
        
        return total_value.quantize(Decimal('0.00000001'))


class Position(models.Model):
    """Current holding of an asset across a broker.
    Quantity and average cost are stored with high precision.
    """
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="positions", null=True, blank=True)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="positions")
    broker = models.ForeignKey(Broker, on_delete=models.CASCADE, related_name="positions")
    quantity = models.DecimalField(max_digits=30, decimal_places=8, default=Decimal('0'))
    average_cost = models.DecimalField(max_digits=30, decimal_places=8, default=Decimal('0'))

    class Meta:
        unique_together = ("asset", "broker")

    def __str__(self):
        return f"{self.asset.symbol} @ {self.broker.name}: {self.quantity}"

    def recalculate_average_cost(self):
        """Re‑calculate the moving‑average cost based on all related BUY transactions.
        Only BUY transactions affect the average cost; SELLs reduce quantity.
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
        self.save(update_fields=["average_cost"])

    def unrealized_pnl(self, market_price: Decimal) -> Decimal:
        """Calculate unrealized P&L based on provided market price."""
        return (market_price - self.average_cost) * self.quantity


class Transaction(models.Model):
    """A trade that changes a position and creates ledger entries."""
    class Type(models.TextChoices):
        BUY = "BUY", "Buy"
        SELL = "SELL", "Sell"

    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=4, choices=Type.choices)
    quantity = models.DecimalField(max_digits=30, decimal_places=8)
    price = models.DecimalField(max_digits=30, decimal_places=8)  # price per unit
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.transaction_type} {self.quantity} {self.position.asset.symbol} @ {self.price}"

    def save(self, *args, **kwargs):
        """Override save to update position and create ledger entries."""
        creating = self._state.adding
        super().save(*args, **kwargs)
        # Update position quantity
        if self.transaction_type == self.Type.BUY:
            self.position.quantity += self.quantity
        else:
            self.position.quantity -= self.quantity
        self.position.save(update_fields=["quantity"])
        # Recalculate average cost after a BUY
        if self.transaction_type == self.Type.BUY:
            self.position.recalculate_average_cost()
        # Create double‑entry ledger entries
        LedgerEntry.create_from_transaction(self)

    def realized_pnl(self) -> Decimal:
        """Realized P&L for this transaction (only meaningful for SELL)."""
        if self.transaction_type == self.Type.SELL:
            cost_basis = self.position.average_cost * self.quantity
            proceeds = self.price * self.quantity
            return (proceeds - cost_basis).quantize(Decimal('0.00000001'))
        return Decimal('0')


class LedgerEntry(models.Model):
    """Double‑entry record for each transaction.
    For every transaction two entries are created: a debit and a credit.
    """
    class EntryType(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="ledger_entries")
    entry_type = models.CharField(max_length=6, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=30, decimal_places=8)
    account = models.CharField(max_length=100)  # e.g., "Cash", "Asset"
    description = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    @classmethod
    def create_from_transaction(cls, transaction):
        """Create paired debit/credit entries for a transaction.
        Simplified example: cash account vs asset account.
        """
        amount = (transaction.quantity * transaction.price).quantize(Decimal('0.00000001'))
        if transaction.transaction_type == Transaction.Type.BUY:
            # Debit cash, Credit asset
            cls.objects.create(
                transaction=transaction,
                entry_type=cls.EntryType.DEBIT,
                amount=amount,
                account="Cash",
                description=f"Buy {transaction.quantity} {transaction.position.asset.symbol}",
            )
            cls.objects.create(
                transaction=transaction,
                entry_type=cls.EntryType.CREDIT,
                amount=amount,
                account="Asset",
                description=f"Buy {transaction.quantity} {transaction.position.asset.symbol}",
            )
        else:
            # SELL: Debit asset, Credit cash
            cls.objects.create(
                transaction=transaction,
                entry_type=cls.EntryType.DEBIT,
                amount=amount,
                account="Asset",
                description=f"Sell {transaction.quantity} {transaction.position.asset.symbol}",
            )
            cls.objects.create(
                transaction=transaction,
                entry_type=cls.EntryType.CREDIT,
                amount=amount,
                account="Cash",
                description=f"Sell {transaction.quantity} {transaction.position.asset.symbol}",
            )

    def __str__(self):
        return f"{self.entry_type} {self.amount} to {self.account}"
