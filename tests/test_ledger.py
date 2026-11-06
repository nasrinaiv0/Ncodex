from decimal import Decimal
import os
import tempfile
import unittest

from ncodex.ledger import PaperLedger


MINT = "So11111111111111111111111111111111111111112"


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = PaperLedger()
        self.ledger.fund("fund-1", "1000.00")

    def tearDown(self):
        self.ledger.close()

    def test_fund_idempotent_and_balanced(self):
        self.assertFalse(self.ledger.fund("fund-1", "1000.00"))
        self.assertEqual(self.ledger.cash_usd(), Decimal("1000.00"))
        self.assertTrue(self.ledger.journal_balanced())

    def test_buy_sell_fifo_partial_and_fees(self):
        self.ledger.buy("b1", MINT, "2", "100", "1")
        self.ledger.buy("b2", MINT, "3", "120", "3")
        self.assertEqual(self.ledger.cash_usd(), Decimal("436"))
        profit = self.ledger.sell("s1", MINT, "3", "150", "2")
        # 2 @ 100.5 cost each; one @ 121 cost => 322 basis; 448 net => 126 pnl
        self.assertEqual(profit, Decimal("126"))
        self.assertEqual(self.ledger.position(MINT), (Decimal("2"), Decimal("242")))
        self.assertEqual(self.ledger.cash_usd(), Decimal("884"))
        self.assertEqual(self.ledger.realized_pnl_usd(), Decimal("126"))
        self.assertTrue(self.ledger.journal_balanced())

    def test_negative_pnl(self):
        self.ledger.buy("b", MINT, "2", "100", "1")
        self.assertEqual(self.ledger.sell("s", MINT, "2", "50", "2"), Decimal("-103"))
        self.assertEqual(self.ledger.cash_usd(), Decimal("897"))
        self.assertTrue(self.ledger.journal_balanced())

    def test_no_insufficient_cash_or_inventory(self):
        with self.assertRaisesRegex(ValueError, "insufficient paper cash"):
            self.ledger.buy("buy", MINT, "100", "100")
        with self.assertRaisesRegex(ValueError, "insufficient paper token inventory"):
            self.ledger.sell("sell", MINT, "1", "100")
        self.assertTrue(self.ledger.journal_balanced())

    def test_trade_idempotency_prevents_double_charge(self):
        self.assertTrue(self.ledger.buy("b", MINT, "2", "1", "0.1"))
        self.assertFalse(self.ledger.buy("b", MINT, "2", "1", "0.1"))
        with self.assertRaisesRegex(ValueError, "idempotency"):
            self.ledger.buy("b", MINT, "3", "1", "0.1")
        self.assertEqual(self.ledger.position(MINT)[0], Decimal("2"))
        self.assertTrue(self.ledger.journal_balanced())

    def test_subcent_precision_and_exact_sale(self):
        self.ledger.buy("b", MINT, "0.333333333", "0.00000001", "0.000000001")
        self.ledger.sell("s", MINT, "0.333333333", "0.00000004", "0.000000001")
        self.assertEqual(self.ledger.position(MINT), (Decimal("0"), Decimal("0")))
        self.assertTrue(self.ledger.journal_balanced())

    def test_sell_fee_greater_than_gross_rejected(self):
        self.ledger.buy("b", MINT, "1", "1")
        with self.assertRaises(ValueError):
            self.ledger.sell("s", MINT, "1", "1", "2")

    def test_sqlite_persistence(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db = PaperLedger(path)
            db.fund("fund", "12")
            db.buy("b", MINT, "2", "1")
            db.close()
            db = PaperLedger(path)
            self.assertEqual(db.cash_usd(), Decimal("10"))
            self.assertTrue(db.journal_balanced())
            db.close()
        finally:
            os.unlink(path)
