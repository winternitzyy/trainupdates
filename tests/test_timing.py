import csv
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import timing

UK = ZoneInfo("Europe/London")
T0 = datetime(2026, 10, 16, 13, 20, tzinfo=UK)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


class TimingTests(unittest.TestCase):
    def run_checks(self, checks):
        episode, rows = None, []
        for minute, c2c, tfl, nr in checks:
            episode, row = timing.update(episode, at(minute), c2c, "Cancellations to services on all routes",
                                         tfl, nr)
            if row:
                rows.append(row)
        return episode, rows

    def test_records_who_was_first(self):
        nr = [{"created": T0 - timedelta(minutes=7), "summary": "Disruption between Barking and Grays"}]
        checks = [(0, False, True, nr),          # TfL and National Rail (created 13:13) already show it
                  (35, True, True, nr),          # c2c website at 13:55
                  (60, False, False, []),        # all clear at 14:20
                  (65, False, False, []),
                  (71, False, False, [])]        # still clear 10+ minutes later: episode ends
        episode, rows = self.run_checks(checks)
        self.assertIsNone(episode)
        self.assertEqual(rows, [{
            "date": "2026-10-16", "c2c_website": "13:55", "tfl": "13:20", "national_rail": "13:13",
            "first": "National Rail", "lead_minutes": "7",
            "c2c_title": "Cancellations to services on all routes",
            "national_rail_summary": "Disruption between Barking and Grays", "ended": "14:20"}])

    def test_episode_not_closed_until_clear_for_10_minutes(self):
        episode, rows = self.run_checks([(0, True, False, []), (5, False, False, []), (14, False, False, [])])
        self.assertIsNotNone(episode)
        self.assertEqual(rows, [])

    def test_short_clear_does_not_end_episode(self):
        episode, rows = self.run_checks([(0, True, False, []), (5, False, False, []), (8, True, False, [])])
        self.assertIsNotNone(episode)
        self.assertEqual(rows, [])

    def test_same_minute_is_a_tie(self):
        _, rows = self.run_checks([(0, True, True, []), (1, False, False, []), (12, False, False, [])])
        self.assertEqual((rows[0]["first"], rows[0]["lead_minutes"]), ("c2c website & TfL", "0"))

    def test_nothing_wrong_nothing_logged(self):
        self.assertEqual(self.run_checks([(0, False, False, []), (1, False, False, [])]), (None, []))

    def test_append_writes_header_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.csv")
            row = dict.fromkeys(timing.COLUMNS, "x")
            timing.append(row, path)
            timing.append(row, path)
            with open(path) as f:
                self.assertEqual(len(list(csv.DictReader(f))), 2)


if __name__ == "__main__":
    unittest.main()
