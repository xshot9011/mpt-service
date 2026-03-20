from django.test import TestCase
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from unittest.mock import patch, MagicMock
from requests.exceptions import Timeout, RequestException

from nav_manager.models import Asset as NavAsset, DailyPrice
from .models import Portfolio, AssetType, Symbol, Transaction, LedgerEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_portfolio(name="Test Portfolio"):
    return Portfolio.objects.create(name=name)


def make_symbol(portfolio, asset_type_name="Cash", symbol_name="SCB Cash",
                nav_source=Symbol.NavSource.FIXED, nav_fixed=Decimal('1')):
    asset_type, _ = AssetType.objects.get_or_create(portfolio=portfolio, name=asset_type_name)
    return Symbol.objects.create(
        portfolio=portfolio,
        asset_type=asset_type,
        name=symbol_name,
        nav_source=nav_source,
        nav_fixed=nav_fixed,
    )


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
        asset_type = AssetType.objects.create(portfolio=self.portfolio, name="Equity")
        symbol = Symbol.objects.create(
            portfolio=self.portfolio,
            asset_type=asset_type,
            name="Some Fund",
            nav_source=Symbol.NavSource.SCRIPT,
            script_url="=IMPORTXML(...)",
        )
        self.assertIsNone(symbol.get_nav())

    def test_nav_manager_resolves_daily_price(self):
        nav_asset = NavAsset.objects.create(name="KTB Cash Fund", symbol="KTBCASH")
        today = timezone.now().date()
        DailyPrice.objects.create(asset=nav_asset, date=today, price=Decimal('12.3456'))

        asset_type = AssetType.objects.create(portfolio=self.portfolio, name="Money Market")
        symbol = Symbol.objects.create(
            portfolio=self.portfolio,
            asset_type=asset_type,
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

        asset_type = AssetType.objects.create(portfolio=self.portfolio, name="Fixed Income")
        symbol = Symbol.objects.create(
            portfolio=self.portfolio,
            asset_type=asset_type,
            name="SCB Money Plus",
            nav_source=Symbol.NavSource.NAV_MANAGER,
            nav_asset=nav_asset,
        )
        # No price for today — should fall back to yesterday
        self.assertEqual(symbol.get_nav(today), Decimal('9.00'))

    def test_nav_manager_no_asset_returns_none(self):
        asset_type = AssetType.objects.create(portfolio=self.portfolio, name="Other")
        symbol = Symbol.objects.create(
            portfolio=self.portfolio,
            asset_type=asset_type,
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

    def test_buy_transaction_updates_symbol_and_average_cost(self):
        tx1 = Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('5.00'),
        )
        self.symbol.refresh_from_db()
        self.assertEqual(self.symbol.quantity, Decimal('10'))
        self.assertEqual(self.symbol.average_cost, Decimal('5.00000000'))

        tx2 = Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('5'),
            price=Decimal('7.00'),
        )
        self.symbol.refresh_from_db()
        self.assertEqual(self.symbol.quantity, Decimal('15'))
        # Moving average: (10*5 + 5*7) / 15 = 5.66666666
        self.assertEqual(self.symbol.average_cost, Decimal('5.66666666'))
        self.assertEqual(LedgerEntry.objects.filter(transaction=tx1).count(), 2)
        self.assertEqual(LedgerEntry.objects.filter(transaction=tx2).count(), 2)

    def test_sell_transaction_realized_pnl(self):
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('20'),
            price=Decimal('3.00'),
        )
        self.symbol.refresh_from_db()

        sell_tx = Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.SELL,
            quantity=Decimal('5'),
            price=Decimal('5.00'),
        )
        self.symbol.refresh_from_db()
        # Realized PnL = (5.00 - 3.00) * 5 = 10.00
        self.assertEqual(sell_tx.realized_pnl(), Decimal('10.00000000'))
        self.assertEqual(self.symbol.quantity, Decimal('15'))
        self.assertEqual(LedgerEntry.objects.filter(transaction=sell_tx).count(), 2)

    def test_unrealized_pnl_calculation(self):
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('2.50'),
        )
        self.symbol.refresh_from_db()
        pnl = self.symbol.unrealized_pnl(Decimal('3.00'))
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
            portfolio=self.portfolio,
            asset_type=asset_type,
            name="Test Fund",
            nav_source=Symbol.NavSource.NAV_MANAGER,
            nav_asset=self.nav_asset,
        )

    def test_portfolio_value_at_point_in_time(self):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        three_days_ago = today - timedelta(days=3)

        DailyPrice.objects.create(asset=self.nav_asset, date=three_days_ago, price=Decimal('100.00'))
        DailyPrice.objects.create(asset=self.nav_asset, date=yesterday, price=Decimal('110.00'))

        # Buy 5 units 3 days ago
        Transaction.objects.create(
            symbol=self.symbol,
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
            symbol=self.symbol,
            transaction_type=Transaction.Type.SELL,
            quantity=Decimal('2'),
            price=Decimal('115.00'),
            timestamp=timezone.now() - timedelta(days=1, hours=2),
        )

        # Yesterday: 3 * 110.00 = 330.00
        self.assertEqual(self.portfolio.value_at(yesterday), Decimal('330.00000000'))

        # Buy 10 more today
        Transaction.objects.create(
            symbol=self.symbol,
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
        today = timezone.now().date()

        Transaction.objects.create(
            symbol=symbol2,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('100'),
            price=Decimal('10.00'),
        )
        # 100 units * 10.00 fixed NAV = 1000.00
        self.assertEqual(portfolio2.value_at(today), Decimal('1000.00000000'))


# ---------------------------------------------------------------------------
# Average Cost Tests (no FX — currencies are modelled as symbols)
# ---------------------------------------------------------------------------

class AverageCostTests(TestCase):
    """Test that average cost is computed from price alone (FX is implicit)."""

    def setUp(self):
        self.portfolio = Portfolio.objects.create(name="Thai Portfolio", currency='THB')
        asset_type = AssetType.objects.create(portfolio=self.portfolio, name="Cash")
        self.symbol = Symbol.objects.create(
            portfolio=self.portfolio,
            asset_type=asset_type,
            name="SCB Cash",
            currency='THB',
            nav_source=Symbol.NavSource.FIXED,
            nav_fixed=Decimal('1'),
        )

    def test_single_buy_average_cost(self):
        """BUY 10 @ 5.00 → avg cost = 5.00."""
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('5.00'),
        )
        self.symbol.refresh_from_db()
        self.assertEqual(self.symbol.quantity, Decimal('10'))
        self.assertEqual(self.symbol.average_cost, Decimal('5.00000000'))

    def test_multiple_buys_weighted_average(self):
        """Two buys at different prices → weighted average."""
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('5.00'),  # cost = 50
        )
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('5'),
            price=Decimal('7.00'),  # cost = 35
        )
        self.symbol.refresh_from_db()
        self.assertEqual(self.symbol.quantity, Decimal('15'))
        # avg cost = (50 + 35) / 15 = 5.66666666
        self.assertEqual(self.symbol.average_cost, Decimal('5.66666666'))


# ---------------------------------------------------------------------------
# Cost Calculation Breakdown Tests
# ---------------------------------------------------------------------------

class CostBreakdownTests(TestCase):
    """Test the cost_calculation_breakdown() audit trail."""

    def setUp(self):
        self.portfolio = make_portfolio()
        self.symbol = make_symbol(self.portfolio, nav_fixed=Decimal('10.00'))

    def test_empty_symbol_returns_empty_list(self):
        self.assertEqual(self.symbol.cost_calculation_breakdown(), [])

    def test_single_buy_breakdown(self):
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('5.00'),
        )
        steps = self.symbol.cost_calculation_breakdown()
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]['quantity'], Decimal('10'))
        self.assertEqual(steps[0]['price'], Decimal('5.00'))
        self.assertEqual(steps[0]['line_cost'], Decimal('50.00'))
        self.assertEqual(steps[0]['running_avg'], Decimal('5.00000000'))

    def test_multiple_buys_breakdown(self):
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('10'),
            price=Decimal('5.00'),
        )
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('5'),
            price=Decimal('8.00'),
        )
        steps = self.symbol.cost_calculation_breakdown()
        self.assertEqual(len(steps), 2)
        # After first buy: avg = 50 / 10 = 5.00
        self.assertEqual(steps[0]['running_avg'], Decimal('5.00000000'))
        # After second buy: avg = (50 + 40) / 15 = 6.00
        self.assertEqual(steps[1]['running_avg'], Decimal('6.00000000'))
        self.assertEqual(steps[1]['running_qty'], Decimal('15'))
        self.assertEqual(steps[1]['running_cost'], Decimal('90.00'))

    def test_sells_excluded_from_breakdown(self):
        """SELL transactions should not appear in the breakdown."""
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.BUY,
            quantity=Decimal('20'),
            price=Decimal('3.00'),
        )
        Transaction.objects.create(
            symbol=self.symbol,
            transaction_type=Transaction.Type.SELL,
            quantity=Decimal('5'),
            price=Decimal('4.00'),
        )
        steps = self.symbol.cost_calculation_breakdown()
        self.assertEqual(len(steps), 1)  # only the BUY


# ---------------------------------------------------------------------------
# ProxyScrapeView Tests
# ---------------------------------------------------------------------------

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

User = get_user_model()

class ProxyScrapeViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('portfolio:proxy_scrape')

    def test_missing_url_parameter(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_invalid_scheme(self):
        response = self.client.get(self.url, {'url': 'ftp://example.com/file'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Only HTTP and HTTPS', response.data['error'])

    def test_internal_ip_blocked(self):
        # 127.0.0.1 is loopback
        response = self.client.get(self.url, {'url': 'http://127.0.0.1/admin'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # localhost also resolves to loopback usually
        response = self.client.get(self.url, {'url': 'http://localhost'})
        # Should be caught as well
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

    @patch('portfolio.views.requests.get')
    def test_successful_fetch(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/html; charset=UTF-8'}
        mock_response.iter_content.return_value = [b"<html><body>test</body></html>"]
        mock_get.return_value.__enter__.return_value = mock_response

        response = self.client.get(self.url, {'url': 'https://example.com/nav'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['html'], "<html><body>test</body></html>")
        # Ensure it passed stream=True and a timeout
        mock_get.assert_called_once()
        kwargs = mock_get.call_args[1]
        self.assertTrue(kwargs.get('stream'))
        self.assertEqual(kwargs.get('timeout'), 5)

    @patch('portfolio.views.requests.get')
    def test_timeout_handled(self, mock_get):
        mock_get.side_effect = Timeout("Request timed out")

        response = self.client.get(self.url, {'url': 'https://example.com/slow'})
        
        self.assertEqual(response.status_code, status.HTTP_504_GATEWAY_TIMEOUT)

    @patch('portfolio.views.requests.get')
    def test_payload_too_large(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/html; charset=UTF-8'}
        # Send 2 chunks that combined exceed 1MB (1024 * 1024)
        mock_response.iter_content.return_value = [b"a" * (1024 * 512), b"b" * (1024 * 513)]
        mock_get.return_value.__enter__.return_value = mock_response

        response = self.client.get(self.url, {'url': 'https://example.com/large'})
        
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    @patch('portfolio.views.requests.get')
    def test_xpath_extraction_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/html; charset=UTF-8'}
        mock_response.iter_content.return_value = [
            b"<html><body><div class='nav'>145.20</div></body></html>"
        ]
        mock_get.return_value.__enter__.return_value = mock_response

        response = self.client.get(self.url, {
            'url': 'https://example.com/nav',
            'xpath': '//div[@class="nav"]/text()'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return JUST the result, not the full HTML
        self.assertEqual(response.data['result'], '145.20')
        self.assertNotIn('html', response.data)

    @patch('portfolio.views.requests.get')
    def test_xpath_no_match(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/html; charset=UTF-8'}
        mock_response.iter_content.return_value = [b"<html><body>test</body></html>"]
        mock_get.return_value.__enter__.return_value = mock_response

        response = self.client.get(self.url, {
            'url': 'https://example.com/nav',
            'xpath': '//div[@class="missing"]'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['result'])

    @patch('portfolio.views.requests.get')
    def test_xpath_invalid_syntax(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/html; charset=UTF-8'}
        mock_response.iter_content.return_value = [b"<html><body>test</body></html>"]
        mock_get.return_value.__enter__.return_value = mock_response

        response = self.client.get(self.url, {
            'url': 'https://example.com/nav',
            'xpath': '//div[@class="unclosed'  # Invalid XPath
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Failed to evaluate XPath', response.data['error'])
