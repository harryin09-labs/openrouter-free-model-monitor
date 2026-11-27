import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import monitor

class MonitorTests(unittest.TestCase):
    def test_free_variant(self):
        row = {"id": "provider/model:free", "name": "Model", "pricing": {"prompt": "0", "completion": "0"}}
        self.assertEqual(monitor.parse_model(row)["kind"], "free_variant")
    def test_zero_price_other(self):
        row = {"id": "provider/model", "pricing": {"prompt": 0, "completion": 0}}
        self.assertEqual(monitor.parse_model(row)["kind"], "other_zero_price")
    def test_nonfree_prompt(self):
        self.assertIsNone(monitor.parse_model({"id": "x:free", "pricing": {"prompt": "0.01", "completion": "0"}}))
    def test_nonfree_completion(self):
        self.assertIsNone(monitor.parse_model({"id": "x", "pricing": {"prompt": "0", "completion": "1"}}))
    def test_nonfree_request_fee(self):
        self.assertIsNone(monitor.parse_model({"id": "x", "pricing": {"prompt": "0", "completion": "0", "request": "0.1"}}))
    def test_missing_prices(self):
        self.assertIsNone(monitor.parse_model({"id": "x", "pricing": {"prompt": "0"}}))
    def test_refuses_empty(self):
        with self.assertRaises(ValueError):
            monitor.parse_catalog({"data": []})
    def test_diff(self):
        old = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        new = [{"id": "a", "name": "A2"}, {"id": "c", "name": "C"}]
        a, r, c = monitor.diff(old, new)
        self.assertEqual((len(a), len(r), len(c)), (1, 1, 1))

if __name__ == "__main__":
    unittest.main()
