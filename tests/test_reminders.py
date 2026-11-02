import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import train_alerts
from train_alerts import UK, hold_recoveries, morning_due

NOW = datetime(2026, 11, 2, 10, 4, tzinfo=UK)
BAD = {"name": "c2c", "ok": False, "summary": "Severe disruption", "reasons": ["Lines blocked."]}
GOOD = {"name": "c2c", "ok": True, "summary": "Good Service", "reasons": []}


class HoldRecoveriesTests(unittest.TestCase):
    def test_brief_good_service_is_held(self):
        current = hold_recoveries({"c2c": BAD}, {"c2c": dict(GOOD)}, NOW)
        self.assertFalse(current["c2c"]["ok"])
        self.assertEqual(train_alerts.build_messages({"c2c": BAD}, current), [])
        # Disrupted again two minutes later: nothing to send either.
        again = hold_recoveries(current, {"c2c": dict(BAD)}, NOW + timedelta(minutes=2))
        self.assertEqual(train_alerts.build_messages(current, again), [])

    def test_good_service_after_five_minutes_is_sent(self):
        previous = {"c2c": BAD}
        for minutes in range(6):
            current = hold_recoveries(previous, {"c2c": dict(GOOD)}, NOW + timedelta(minutes=minutes))
            messages = train_alerts.build_messages(previous, current)
            previous = current
        self.assertEqual(messages, ["c2c: back to Good Service."])


class MorningTests(unittest.TestCase):
    def test_due_once_in_the_hour_after(self):
        at = datetime(2026, 11, 2, 6, 30, tzinfo=UK)
        self.assertFalse(morning_due(at - timedelta(minutes=1), None, "06:30"))
        self.assertTrue(morning_due(at, None, "06:30"))
        self.assertFalse(morning_due(at, "2026-11-02", "06:30"))
        self.assertFalse(morning_due(at + timedelta(hours=3), None, "06:30"))  # e.g. a restart at lunch
        self.assertFalse(morning_due(at, None, ""))

    def test_text_only_for_disrupted_lines(self):
        state = {"c2c": BAD, "suffragette": dict(GOOD, name="Suffragette"), "_weekly": "x"}
        with mock.patch.object(train_alerts.live_trains, "check", return_value="WCF to BKG: 06:47 on time."), \
             mock.patch.object(train_alerts, "send_all") as send:
            train_alerts.send_morning(state, dry_run=True)
        text = send.call_args[0][0][0]
        self.assertTrue(text.startswith("Morning update: c2c: Severe disruption. Lines blocked. Still disrupted."))
        self.assertNotIn("Suffragette", text)
        self.assertNotIn("live", state["c2c"])

    def test_no_text_when_all_good(self):
        with mock.patch.object(train_alerts, "send_all") as send:
            train_alerts.send_morning({"c2c": GOOD}, dry_run=True)
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
