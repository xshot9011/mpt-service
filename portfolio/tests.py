from django.test import TestCase
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from nav_manager.models import Asset as NavAsset, DailyPrice
from .models import Portfolio, AssetType, Symbol, Position, Transaction, LedgerEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_portfolio(name="Test Portfolio"):
    return Portfolio.objects.create(name=name)


def make_symbol(portfolio, asset_type_name="Cash", symbol_name="SCB Cash",
                nav_source=Symbol.NavSource.FIXED, nav_fixed=Decimal('1')):
    asset_type, _ = AssetType.objects.get_or_create(portfolio=portfolio, name=asset_type_name)
    return Symbol.objects.create(
        asset_type=asset_type,
        name=symbol_name,
        nav_source=nav_source,
        nav_fixed=nav_fixed,
    )


def make_position(portfolio, symbol):
    return Position.objects.create(portfolio=portfolio, symbol=symbol)


# ---------------------------------------------------------------------------
# Symbol NAV Tests
# ---------------------------------------------------------------------------

class SymbolNavTests(TestCase):
    def setUp(self):
        self.portfolio = make_portfolio()

    def test_nav_fixed_returns_fixed_value(self):
        symbol = make_symbol(self.portfolio, nav_fixed=Decimal('10.50'))
        self.assertEqual(symbol.get_nav(), Decimal('10.50'))

    def test_nav_script_returns_none(self):
        symbol = Symbol.objects.create(
            asset_type=AssetType.objects.create(portfolio=self.portfolio, name="Equity"),
            name="Some Fund",
            nav_source=Symbol.NavSource.SCRIPT,
            script_url="=IMPORTXML(...)",
        )
        self.assertIsNone(symbol.get_nav())

    def test_nav_manager_resolves_daily_price(self):
        nav_asset = NavAsset.objects.create(name="KTB Cash Fund", symbol="KTBCASH")
        today = timezone.now().date()
        DailyPrice.objects.create(asset=nav_asset, date=today, price=Decimal('12.3456'))

        symbol = Symbol.objects.create(
            asset_type=AssetType.objects.create(portfolio=self.portfolio, name="Money Market"),
            name="KTB Cash",
            nav_source=Symbol.NavSource.NAV_MANAGER,
            nav_asset=nav_asset,
        )
        self.assertEqual(symbol.get_nav(today), Decimal('12.3456'))

    def test_nav_manager_picks_latest_price_before_date(self):
        nav_asset = NavAsset.objects.create(name="SCB Money Plus", symbol="SCBMPLUS")
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        DailyPrice.objects.create(asset=nav_asset, date=yesterday, price=Decimal('9.00'))

        symbol = Symbol.objects.create(
            asset_type=AssetType.objects.create(portfolio=self.portfolio, name="Fixed Income"),
            name="SCB Money Plus",
            nav_source=Symbol.NavSource.NAV_MANAGER,
            nav_asset=nav_asset,
        )
        # No price for today — should fall back to yesterday
        self.assertEqual(symbol.get_nav(today), Decimal('9.00'))

    def test_nav_manager_no_asset_returns_none(self):
        symbol = Symbol.objects.create(
            asset_type=AssetType.objects.create(portfolio=self.portfolio, name="Other"),
            name="Unknown",
            nav_source=Symbol.NavSource.NAV_MANAGER,
            nav_asset=None,
        )
        self.assertIsNone(symbol.get_nav())


# ---------------------------------------------------------------------------
# Ledger / Transaction Tests
# ---------------------------------------------------------------------------

class LedgerModelTests(TestCase):
    def setUp(self):
        self.portfolio = make_portfolio()
        self.symbol = make_symbol(self.portfolio, nav_fixed=Decimal('5.00'))
        self.position = make_position(self.portfolio, self.symbol)

    def test_buy_transaction_updates_position_and_average_cost(self):
        tx1 = Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('5.00'),
        )
        self.position.refresh_from_db()
        self.assertEqual(self.position.quantity, Decimal('10'))
        self.assertEqual(self.position.average_cost, Decimal('5.00000000'))

        tx2 = Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('5'),
            price=Decimal('7.00'),
        )
        self.position.refresh_from_db()
        self.assertEqual(self.position.quantity, Decimal('15'))
        # Moving average: (10*5 + 5*7) / 15 = 5.66666666
        self.assertEqual(self.position.average_cost, Decimal('5.66666666'))
        self.assertEqual(LedgerEntry.objects.filter(transaction=tx1).count(), 2)
        self.assertEqual(LedgerEntry.objects.filter(transaction=tx2).count(), 2)

    def test_sell_transaction_realized_pnl(self):
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('20'),
            price=Decimal('3.00'),
        )
        self.position.refresh_from_db()

        sell_tx = Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.SELL,
            quantity=Decimal('5'),
            price=Decimal('5.00'),
        )
        self.position.refresh_from_db()
        # Realized PnL = (5.00 - 3.00) * 5 = 10.00
        self.assertEqual(sell_tx.realized_pnl(), Decimal('10.00000000'))
        self.assertEqual(self.position.quantity, Decimal('15'))
        self.assertEqual(LedgerEntry.objects.filter(transaction=sell_tx).count(), 2)

    def test_unrealized_pnl_calculation(self):
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('2.50'),
        )
        self.position.refresh_from_db()
        pnl = self.position.unrealized_pnl(Decimal('3.00'))
        # (3.00 - 2.50) * 10 = 5.00
        self.assertEqual(pnl, Decimal('5.00000000'))


# ---------------------------------------------------------------------------
# Portfolio value_at Tests
# ---------------------------------------------------------------------------

class PortfolioValueAtTests(TestCase):
    def setUp(self):
        self.portfolio = make_portfolio()
        self.nav_asset = NavAsset.objects.create(name="Test Fund", symbol="TFUND")
        asset_type = AssetType.objects.create(portfolio=self.portfolio, name="Equity")
        self.symbol = Symbol.objects.create(
            asset_type=asset_type,
            name="Test Fund",
            nav_source=Symbol.NavSource.NAV_MANAGER,
            nav_asset=self.nav_asset,
        )
        self.position = make_position(self.portfolio, self.symbol)

    def test_portfolio_value_at_point_in_time(self):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        three_days_ago = today - timedelta(days=3)

        DailyPrice.objects.create(asset=self.nav_asset, date=three_days_ago, price=Decimal('100.00'))
        DailyPrice.objects.create(asset=self.nav_asset, date=yesterday, price=Decimal('110.00'))

        # Buy 5 units 3 days ago
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('5'),
            price=Decimal('95.00'),
            timestamp=timezone.now() - timedelta(days=3),
        )

        # 3 days ago: 5 * 100.00 = 500.00
        self.assertEqual(self.portfolio.value_at(three_days_ago), Decimal('500.00000000'))

        # 2 days ago: still 5 units, last known price = 100.00 → 500.00
        self.assertEqual(self.portfolio.value_at(two_days_ago), Decimal('500.00000000'))

        # Sell 2 units yesterday
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.SELL,
            quantity=Decimal('2'),
            price=Decimal('115.00'),
            timestamp=timezone.now() - timedelta(days=1, hours=2),
        )

        # Yesterday: 3 * 110.00 = 330.00
        self.assertEqual(self.portfolio.value_at(yesterday), Decimal('330.00000000'))

        # Buy 10 more today
        Transaction.objects.create(
            position=self.position,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('105.00'),
            timestamp=timezone.now(),
        )

        # Yesterday's value unchanged despite new transaction
        self.assertEqual(self.portfolio.value_at(yesterday), Decimal('330.00000000'))

        # Today: 13 * 110.00 (no price today → falls back to yesterday) = 1430.00
        self.assertEqual(self.portfolio.value_at(today), Decimal('1430.00000000'))

    def test_portfolio_value_fixed_nav_symbol(self):
        """Portfolio with a FIXED nav symbol should compute value correctly."""
        portfolio2 = make_portfolio("Fixed NAV Portfolio")
        symbol2 = make_symbol(portfolio2, symbol_name="KTB Cash", nav_fixed=Decimal('10.00'))
        pos2 = make_position(portfolio2, symbol2)
        today = timezone.now().date()

        Transaction.objects.create(
            position=pos2,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('100'),
            price=Decimal('10.00'),
        )
        # 100 units * 10.00 fixed NAV = 1000.00
        self.assertEqual(portfolio2.value_at(today), Decimal('1000.00000000'))
