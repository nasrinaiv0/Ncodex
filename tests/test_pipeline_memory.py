from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from ncodex.ledger import PaperLedger
from ncodex.memory import PatternMemory
from ncodex.pipeline import PaperDesk
from ncodex.schema import Candidate
from tests.test_schema_risk import NOW, MINT, valid_candidate


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.ledger = PaperLedger()
        self.ledger.fund("fund", "100")
        self.memory = PatternMemory()
        self.desk = PaperDesk(self.ledger, self.memory)
        self.candidate = Candidate.from_mapping(valid_candidate())

    def tearDown(self):
        self.ledger.close()

    def test_human_approval_required(self):
        with self.assertRaises(PermissionError):
            self.desk.buy("trade", self.candidate, "20", approved=False, now=NOW)

    def test_paper_buy_works_and_not_double_counted(self):
        self.desk.buy("trade", self.candidate, "20", approved=True, now=NOW, fee_usd="0.10")
        self.assertEqual(self.ledger.cash_usd(), Decimal("80.00"))
        self.assertEqual(self.ledger.daily_buy_notional_usd(
            datetime.now(timezone.utc).date().isoformat()), Decimal("20.00"))
        self.assertTrue(self.ledger.journal_balanced())
        self.assertEqual(self.memory.report()["gmgn"]["observations"], 1)

    def test_reject_exceeded_daily_budget(self):
        self.ledger.buy("one", MINT, "50", "1")
        self.ledger.buy("two", MINT, "50", "1")
        self.assertIn("daily_buy_budget_exceeded",
                      self.desk.review(self.candidate, "1", NOW).reasons)

    def test_pattern_memory_outcome_is_audit_not_prediction(self):
        self.memory.observe("x", "gmgn", MINT, True, ())
        self.memory.record_outcome("x", "1.5000")
        self.memory.record_outcome("x", "1.5000")
        with self.assertRaises(ValueError):
            self.memory.record_outcome("x", "-9")
        self.assertEqual(self.memory.report()["gmgn"]["wins"], 1)
        self.assertEqual(self.memory.report()["gmgn"]["net_realized_usd"], "1.5000")
