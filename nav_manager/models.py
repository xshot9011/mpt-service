from django.db import models
from django.utils import timezone

class Asset(models.Model):
    """Financial instrument being traded (e.g., stock, bond)."""
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return f"{self.symbol} - {self.name}"

class DailyPrice(models.Model):
    """Manual or automated record of an asset's end-of-day price."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="daily_prices")
    date = models.DateField(default=timezone.now)
    price = models.DecimalField(max_digits=30, decimal_places=8)

    class Meta:
        unique_together = ("asset", "date")

    def __str__(self):
        return f"{self.asset.symbol} on {self.date}: {self.price}"
