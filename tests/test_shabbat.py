import os
import sys
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shabbat import in_rest_period, rest_period, sunset, yom_tov

UK = ZoneInfo("Europe/London")


def uk(*args):
    return datetime(*args, tzinfo=UK)


class ShabbatTests(unittest.TestCase):
    def test_shabbat_ends_72_minutes_after_sunset(self):
        start, end, label = rest_period(date(2026, 10, 17))
        self.assertEqual(label, "Shabbat")
        self.assertEqual(end, sunset(date(2026, 10, 17)) + timedelta(minutes=72))
        self.assertEqual(start, sunset(date(2026, 10, 16)) - timedelta(minutes=18))

    def test_window_edges(self):
        start, end, _ = (x.astimezone(UK) if isinstance(x, datetime) else x
                         for x in rest_period(date(2026, 10, 17)))
        before, after = start - timedelta(minutes=1), end + timedelta(minutes=1)
        self.assertIsNone(in_rest_period(before, margin_minutes=0))
        self.assertEqual(in_rest_period(start, margin_minutes=0), "Shabbat")
        self.assertEqual(in_rest_period(end - timedelta(minutes=1), margin_minutes=0), "Shabbat")
        self.assertIsNone(in_rest_period(after, margin_minutes=0))
        self.assertEqual(in_rest_period(after), "Shabbat")  # covered by the 5-minute margin

    def test_weekdays(self):
        for day in (12, 13, 14, 15):
            self.assertIsNone(in_rest_period(uk(2026, 10, day, 20, 0)))

    def test_yom_tov_dates(self):
        self.assertEqual(yom_tov(date(2026, 9, 12)), "Rosh Hashanah")
        self.assertEqual(yom_tov(date(2026, 9, 13)), "Rosh Hashanah")
        self.assertEqual(yom_tov(date(2026, 9, 21)), "Yom Kippur")
        self.assertEqual(yom_tov(date(2027, 4, 22)), "Pesach")
        self.assertEqual(yom_tov(date(2027, 4, 29)), "Pesach")
        self.assertEqual(yom_tov(date(2027, 6, 11)), "Shavuot")
        self.assertIsNone(yom_tov(date(2027, 4, 25)))  # Chol Hamoed

    def test_yom_tov_running_into_shabbat_is_one_period(self):
        start, end, label = rest_period(date(2027, 4, 22))
        self.assertEqual(label, "Shabbat and Pesach")
        self.assertEqual(start.astimezone(UK).date(), date(2027, 4, 21))
        self.assertEqual(end.astimezone(UK).date(), date(2027, 4, 24))
        self.assertEqual(in_rest_period(uk(2027, 4, 23, 12, 0)), "Shabbat and Pesach")

    def test_weekday_yom_tov(self):
        self.assertEqual(in_rest_period(uk(2027, 10, 11, 12, 0)), "Yom Kippur")
        self.assertIsNone(in_rest_period(uk(2027, 10, 12, 12, 0)))


if __name__ == "__main__":
    unittest.main()
