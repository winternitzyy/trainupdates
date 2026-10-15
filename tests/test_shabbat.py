import os
import sys
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shabbat import in_shabbat, shabbat_times

UK = ZoneInfo("Europe/London")


def uk(*args):
    return datetime(*args, tzinfo=UK)


class ShabbatTests(unittest.TestCase):
    def test_times_are_friday_evening_and_saturday_night(self):
        start, end = shabbat_times(date(2026, 10, 16))
        self.assertEqual(start.astimezone(UK).date(), date(2026, 10, 16))
        self.assertEqual(end.astimezone(UK).date(), date(2026, 10, 17))
        self.assertLess(start, end)

    def test_window(self):
        start, end = (t.astimezone(UK) for t in shabbat_times(date(2026, 10, 16)))
        self.assertFalse(in_shabbat(uk(2026, 10, 16, start.hour, start.minute - 1), margin_minutes=0))
        self.assertTrue(in_shabbat(uk(2026, 10, 16, start.hour, start.minute + 1), margin_minutes=0))
        self.assertTrue(in_shabbat(uk(2026, 10, 17, 12, 0)))
        self.assertTrue(in_shabbat(uk(2026, 10, 17, end.hour, end.minute - 1), margin_minutes=0))
        self.assertFalse(in_shabbat(uk(2026, 10, 17, end.hour, end.minute + 1), margin_minutes=0))

    def test_margin_covers_hebcal_times(self):
        # Hebcal for Westcliff-on-Sea, 16-17 Oct 2026: candles 17:43, Shabbat ends 18:50.
        self.assertTrue(in_shabbat(uk(2026, 10, 16, 17, 43)))
        self.assertTrue(in_shabbat(uk(2026, 10, 17, 18, 50)))
        self.assertFalse(in_shabbat(uk(2026, 10, 16, 17, 30)))
        self.assertFalse(in_shabbat(uk(2026, 10, 17, 19, 0)))

    def test_weekdays_never_shabbat(self):
        for day in (12, 13, 14, 15, 18):
            self.assertFalse(in_shabbat(uk(2026, 10, day, 20, 0)))

    def test_summer_and_winter(self):
        self.assertTrue(in_shabbat(uk(2026, 6, 20, 22, 0)))   # long summer Shabbat
        self.assertFalse(in_shabbat(uk(2026, 12, 19, 18, 0)))  # short winter Shabbat over


if __name__ == "__main__":
    unittest.main()
