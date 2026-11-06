from datetime import datetime, timezone
import json
import tempfile
import os
import unittest

from ncodex.feeds import watch_records
from ncodex.ledger import PaperLedger
from ncodex.memory import PatternMemory
from ncodex.pipeline import PaperDesk
from tests.test_schema_risk import NOW, valid_candidate


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.ledger = PaperLedger()
        self.memory = PatternMemory()
        self.desk = PaperDesk(self.ledger)

    def tearDown(self):
        self.memory.close()
        self.ledger.close()

    def test_normalized_feed_dedupe_and_does_not_trade(self):
        payload = valid_candidate()
        payload["event_id"] = "event-1"
        raw = json.dumps(payload) + "\n"
        out = list(watch_records([raw, raw], self.desk, self.memory, "10", now=NOW))
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0]["first_seen"])
        self.assertFalse(out[1]["first_seen"])
        self.assertTrue(out[0]["allowed_for_paper"])
        self.assertFalse(out[0]["live_trading_allowed"])
        self.assertEqual(self.ledger.summary()["positions"], {})

    def test_collision_rejected_and_security_missing(self):
        a = valid_candidate()
        a["event_id"] = "same"
        b = dict(a)
        b["security"] = dict(a["security"])
        b["security"]["honeypot"] = True
        out = list(watch_records(
            [json.dumps(a), json.dumps(b), '{"chain":"solana"}', 'bad-json'],
            self.desk, self.memory, "10", now=NOW))
        self.assertIn("error", out[1])
        self.assertIn("error", out[2])
        self.assertIn("error", out[3])
        self.assertEqual(self.memory.report()["gmgn"]["observations"], 1)

    def test_persist_memory_without_live_trades(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            memory = PatternMemory(path)
            rows = list(watch_records([json.dumps(valid_candidate())], self.desk,
                                      memory, "10", now=NOW))
            memory.close()
            memory2 = PatternMemory(path)
            self.assertEqual(memory2.report()["gmgn"]["observations"], 1)
            memory2.close()
            self.assertFalse(rows[0]["live_trading_allowed"])
        finally:
            os.unlink(path)

    def test_oversized_record_fails_closed(self):
        out = list(watch_records(["a" * 300000], self.desk, self.memory, "10", now=NOW))
        self.assertEqual(out[0]["error"], "record_too_large")
