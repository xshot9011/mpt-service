from django.test import TestCase
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from symbol.models import Asset, DailyPrice
from .models import Broker, Position, Transaction, LedgerEntry, Portfolio

class LedgerModelTests(TestCase):
    def setUp(self):
        self.portfolio = Portfolio.objects.create(name="Test Portfolio")
        self.asset = Asset.objects.create(name="Test Asset", symbol="TA")
        self.broker = Broker.objects.create(name="Test Broker")
        self.position = Position.objects.create(            portfolio=self.portfolio,
            asset=self.asset, 
            broker=self.broker
        )

    def test_buy_transaction_updates_position_and_average_cost(self):
        # First BUY of 10 units at price 5.00
        tx1 = Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('5.00')
        )
        self.position.refresh_from_db()
        self.assertEqual(self.position.quantity, Decimal('10'))
        self.assertEqual(self.position.average_cost, Decimal('5.00000000'))
        # ... remainder of existing tests ...
        # Second BUY of 5 units at price 7.00
        tx2 = Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('5'),
            price=Decimal('7.00')
        )
        self.position.refresh_from_db()
        self.assertEqual(self.position.quantity, Decimal('15'))
        # Moving average: (10*5 + 5*7) / 15 = 5.66666666
        self.assertEqual(self.position.average_cost, Decimal('5.66666666'))
        # Ledger entries count should be 4 (2 per transaction)
        self.assertEqual(LedgerEntry.objects.filter(transaction=tx1).count(), 2)
        self.assertEqual(LedgerEntry.objects.filter(transaction=tx2).count(), 2)

    def test_sell_transaction_realized_pnl(self):
        # Setup initial BUY to have average cost
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('20'),
            price=Decimal('3.00')
        )
        self.position.refresh_from_db()
        # SELL 5 units at price 5.00
        sell_tx = Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.SELL,
            quantity=Decimal('5'),
            price=Decimal('5.00')
        )
        self.position.refresh_from_db()
        # Realized PnL = (5.00 - 3.00) * 5 = 10.00
        self.assertEqual(sell_tx.realized_pnl(), Decimal('10.00000000'))
        # Quantity should be reduced
        self.assertEqual(self.position.quantity, Decimal('15'))
        # Ledger entries for sell transaction
        self.assertEqual(LedgerEntry.objects.filter(transaction=sell_tx).count(), 2)

    def test_unrealized_pnl_calculation(self):
        # BUY 10 units at price 2.50
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('2.50')
        )
        self.position.refresh_from_db()
        # Assume market price 3.00
        pnl = self.position.unrealized_pnl(Decimal('3.00'))
        # (3.00 - 2.50) * 10 = 5.00
        self.assertEqual(pnl, Decimal('5.00000000'))

    def test_portfolio_value_at_point_in_time(self):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        three_days_ago = today - timedelta(days=3)

        # Record daily prices
        DailyPrice.objects.create(asset=self.asset, date=three_days_ago, price=Decimal('100.00'))
        DailyPrice.objects.create(asset=self.asset, date=yesterday, price=Decimal('110.00'))
        # Note: No price explicitly for 'two_days_ago' or 'today'

        # Transaction 1: Buy 5 units 3 days ago @ 95.00
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('5'),
            price=Decimal('95.00'),
            timestamp=timezone.now() - timedelta(days=3)
        )

        # Portfolio value 3 days ago: 5 units * 100.00 = 500.00
        val_3_days_ago = self.portfolio.value_at(three_days_ago)
        self.assertEqual(val_3_days_ago, Decimal('500.00000000'))

        # Portfolio value 2 days ago: 
        # still 5 units, last known price is from three_days_ago (100.00) -> 500.00
        val_2_days_ago = self.portfolio.value_at(two_days_ago)
        self.assertEqual(val_2_days_ago, Decimal('500.00000000'))

        # Transaction 2: Sell 2 units yesterday @ 115.00
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.SELL,
            quantity=Decimal('2'),
            price=Decimal('115.00'),
            timestamp=timezone.now() - timedelta(days=1, hours=2) # earlier yesterday
        )

        # Portfolio value yesterday: 
        # qty = 5 - 2 = 3 units
        # last known price = yesterday's price = 110.00
        # 3 * 110.00 = 330.00
        val_yesterday = self.portfolio.value_at(yesterday)
        self.assertEqual(val_yesterday, Decimal('330.00000000'))

        # Transaction 3: Buy 10 units today @ 105.00 (but after our 'target_date' check)
        # If we check value_at(yesterday), this transaction should be ignored.
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('105.00'),
            timestamp=timezone.now()
        )
        
        # Verify yesterday's value hasn't changed despite today's transaction
        self.assertEqual(self.portfolio.value_at(yesterday), Decimal('330.00000000'))
        
        # Portfolio value today:
        # qty = 3 + 10 = 13 units
        # last known price = yesterday's price = 110.00 (since no price today)
        # 13 * 110.00 = 1430.00
        val_today = self.portfolio.value_at(today)
        self.assertEqual(val_today, Decimal('1430.00000000'))
