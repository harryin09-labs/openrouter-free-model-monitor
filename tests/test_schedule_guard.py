import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import schedule_guard as guard


class ScheduleGuardTests(unittest.TestCase):
    def test_daily_cron_conversion(self):
        now = datetime(2026, 11, 29, 4, 55, tzinfo=timezone.utc)
        result = guard.scheduled_time(now, "17 3 * * *")
        self.assertEqual(result.isoformat(), "2026-11-29T03:17:00+00:00")

    def test_refuses_invalid_cron(self):
        with self.assertRaises(ValueError):
            guard.scheduled_time(datetime.now(timezone.utc), "0 0 * * MON")

    def test_receipt_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / "receipts.json"
            today = datetime.now(guard.TZ).date().isoformat()
            file.write_text('{"days":{"' + today + '":{"telegram_report":"monitor-step-succeeded"}}}')
            out = Path(d) / "output.txt"
            with patch.object(guard, "RECEIPTS", file), patch.dict(
                os.environ, {"GITHUB_EVENT_NAME": "schedule", "GITHUB_OUTPUT": str(out)}, clear=False
            ):
                guard.check()
            self.assertIn("run_monitor=false", out.read_text())

    def test_manual_run_bypasses_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "output.txt"
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch",
                                          "GITHUB_OUTPUT": str(out)}, clear=False):
                guard.check()
            self.assertIn("run_monitor=true", out.read_text())

    def test_record_scheduled_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / "receipts.json"
            with patch.object(guard, "RECEIPTS", file), patch.dict(os.environ, {
                "GITHUB_EVENT_NAME": "schedule", "SCHEDULED_CRON": "17 3 * * *",
                "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"
            }, clear=False):
                guard.mark()
                receipt = guard.load_receipts()["days"]
            self.assertEqual(len(receipt), 1)
            self.assertEqual(next(iter(receipt.values()))["github_run_id"], "123")


if __name__ == "__main__":
    unittest.main()
