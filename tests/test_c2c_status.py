import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import c2c_status
import train_alerts

UK = ZoneInfo("Europe/London")

CONTENT = ("<p>Due to a track circuit failure at Dagenham Dock fewer trains are able to run.</p><p>Impact:</p>"
           "<p>Train services running across the whole c2c network may be cancelled or delayed by up to 15 "
           "minutes. Disruption is expected until 15:00 16/10.</p><p>Customer Advice:</p><p>What's Happened?</p>"
           "<p>We are aware of an incident with the track in the Dagenham Dock area. </p>")
ALERT = {"alert_id": "1341016132", "title": "Cancellations to services on all routes", "content": CONTENT,
         "severity": "severe"}
SEVERE = {"c2c_stat": "severe", "alerts": [ALERT], "emergency_announcements": [],
          "information_announcements": [],
          "service_alts": [{"title": "All Lines | Fenchurch Street - Barking (23:30)", "severity": "minor"}],
          "route_groups": {r: {"badge": "severe"} for r in ("basildon", "rainham", "ockendon")}}
GOOD = {"c2c_stat": "good", "alerts": [], "emergency_announcements": [],
        "service_alts": [{"title": "Planned works tonight", "severity": "minor"}],
        "route_groups": {r: {"badge": "good"} for r in ("basildon", "rainham", "ockendon")}}
TEXT = ("c2c: Severe disruption. Cancellations to services on all routes: Due to a track circuit failure at "
        "Dagenham Dock fewer trains are able to run. Train services running across the whole c2c network may "
        "be cancelled or delayed by up to 15 minutes. Disruption is expected until 15:00 16/10.")


def tfl_c2c():
    return {"c2c": {"name": "c2c", "ok": False, "summary": "Special Service", "reasons": ["link"], "since": None}}


class C2cStatusTests(unittest.TestCase):
    def test_severe_alert_text(self):
        status = c2c_status.to_status(SEVERE)
        self.assertFalse(status["ok"])
        self.assertEqual(train_alerts.format_problem(status), TEXT)

    def test_planned_works_alone_is_good_service(self):
        self.assertTrue(c2c_status.to_status(GOOD)["ok"])

    def test_some_routes_named(self):
        data = dict(SEVERE, route_groups={"basildon": {"badge": "good"}, "rainham": {"badge": "severe"},
                                          "ockendon": {"badge": "good"}})
        self.assertEqual(c2c_status.to_status(data)["reasons"][-1], "Affected: via Rainham.")


class ApplyTests(unittest.TestCase):
    now = datetime(2026, 10, 16, 13, 55, tzinfo=UK)

    def apply(self, previous, data=None, error=None, now=None):
        with mock.patch.object(c2c_status, "fetch", return_value=data, side_effect=error):
            return train_alerts.apply_c2c_website(tfl_c2c(), previous, now or self.now)

    def test_switch_from_tfl_alerts_once(self):
        previous = tfl_c2c()
        current = self.apply(previous, SEVERE)
        self.assertEqual(train_alerts.build_messages(previous, current), [TEXT])
        again = self.apply(current, SEVERE, now=self.now + timedelta(minutes=1))
        self.assertEqual(train_alerts.build_messages(current, again), [])
        self.assertEqual(again["c2c"]["since"], self.now.isoformat())  # first seen time kept

    def test_recovery(self):
        current = self.apply(tfl_c2c(), SEVERE)
        later = self.apply(current, GOOD, now=self.now + timedelta(minutes=30))
        self.assertEqual(train_alerts.build_messages(current, later), ["c2c: back to Good Service."])

    def test_website_blip_keeps_last_reading(self):
        current = self.apply(tfl_c2c(), SEVERE)
        blip = self.apply(current, error=OSError("down"), now=self.now + timedelta(minutes=2))
        self.assertEqual(train_alerts.build_messages(current, blip), [])

    def test_long_outage_falls_back_to_tfl(self):
        current = self.apply(tfl_c2c(), SEVERE)
        later = self.apply(current, error=OSError("down"), now=self.now + timedelta(minutes=20))
        self.assertEqual(later["c2c"]["summary"], "Special Service")


if __name__ == "__main__":
    unittest.main()
