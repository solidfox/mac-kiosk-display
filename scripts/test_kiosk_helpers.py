#!/usr/bin/env python3
"""Stdlib tests for kiosk helpers (no PyObjC)."""
import importlib.util
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kiosk_lib", ROOT / "scripts" / "kiosk_lib.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class ParseUntilTests(unittest.TestCase):
    def test_tonight_is_today_2359(self):
        ts = mod.parse_until("tonight")
        self.assertIsNotNone(ts)
        local = time.localtime(ts)
        self.assertEqual((local.tm_hour, local.tm_min), (23, 59))

    def test_hhmm(self):
        ts = mod.parse_until("23:59")
        local = time.localtime(ts)
        self.assertEqual((local.tm_hour, local.tm_min), (23, 59))

    def test_duration_seconds(self):
        start = time.time()
        ts = mod.parse_until("30")
        self.assertGreaterEqual(ts, start + 29)
        self.assertLessEqual(ts, start + 32)

    def test_empty(self):
        self.assertIsNone(mod.parse_until(None))
        self.assertIsNone(mod.parse_until(""))


class ToUrlTests(unittest.TestCase):
    def test_https_passthrough(self):
        url, local = mod.to_url("https://example.com/a")
        self.assertEqual(url, "https://example.com/a")
        self.assertIsNone(local)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            mod.to_url("/no/such/kiosk-file.html")


if __name__ == "__main__":
    unittest.main()
