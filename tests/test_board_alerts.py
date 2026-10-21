import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import live_trains
import train_alerts

NOW = datetime(2026, 10, 21, 7, 0, tzinfo=timezone.utc)  # 08:00 UK
WCF = {"from": "WCF", "to": "BKG"}
BKG = {"from": "BKG", "to": "WCF"}


def at(minutes, delay):
    return (NOW + timedelta(minutes=minutes), delay)


def good(name="c2c"):
    return {"name": name, "ok": True, "summary": "Good Service", "reasons": []}


class FindProblemsTests(unittest.TestCase):
    def test_one_cancellation_alerts(self):
        found = live_trains.find_problems([(WCF, [at(5, 0), at(20, None)]), (BKG, [at(10, 0)])], NOW)
        self.assertTrue(found["alert"])
        self.assertEqual(found["cancelled"], ["WCF 08:20"])
        self.assertEqual(found["text"], "WCF to BKG: 08:20 cancelled.")

    def test_one_late_train_is_not_enough(self):
        found = live_trains.find_problems([(WCF, [at(5, 12), at(20, 0)])], NOW)
        self.assertFalse(found["alert"])

    def test_two_late_trains_alert(self):
        found = live_trains.find_problems([(WCF, [at(5, 12)]), (BKG, [at(30, 5), at(40, 4)])], NOW)
        self.assertTrue(found["alert"])
        self.assertEqual(found["late"], 2)
        self.assertEqual(found["text"], "WCF to BKG: 08:05 12 minutes delayed. BKG to WCF: 08:30 5 minutes delayed.")

    def test_trains_after_the_hour_are_ignored(self):
        found = live_trains.find_problems([(WCF, [at(70, None), at(80, 20), at(90, 20)])], NOW)
        self.assertFalse(found["alert"])


class WatchBoardsTests(unittest.TestCase):
    def watch(self, state, current, found, now=NOW):
        with mock.patch.object(live_trains, "board_problems", return_value=found), \
             mock.patch.object(live_trains, "check", return_value="WCF to BKG: 08:30 on time."):
            return train_alerts.watch_boards(state, current, now)

    CANCELLED = {"alert": True, "cancelled": ["WCF 08:20"], "late": 0, "text": "WCF to BKG: 08:20 cancelled."}
    CLEAR = {"alert": False, "cancelled": [], "late": 0, "text": ""}

    def test_alert_when_nobody_has_reported_it(self):
        messages, state = self.watch({}, {"c2c": good()}, self.CANCELLED)
        self.assertEqual(messages, [
            "c2c: 1 train cancelled. This is most likely a temporary issue as c2c haven't reported the "
            "disruption. This is currently displayed on the departure boards: WCF to BKG: 08:20 cancelled."])
        self.assertTrue(state["c2c"]["alert"])

    def test_suffragette_names_tfl(self):
        messages, _ = self.watch({}, {"suffragette": good("Suffragette")}, self.CANCELLED)
        self.assertIn("as TfL haven't reported", messages[0])

    def test_no_board_alert_when_officially_disrupted(self):
        disrupted = {"name": "c2c", "ok": False, "summary": "Severe Delays", "reasons": []}
        messages, state = self.watch({"c2c": {"alert": True}}, {"c2c": disrupted}, self.CANCELLED)
        self.assertEqual(messages, [])
        self.assertNotIn("c2c", state)

    def test_no_repeat_until_a_new_cancellation(self):
        state = {"c2c": {"alert": True, "cancelled": ["WCF 08:20"], "clear_since": None}}
        messages, _ = self.watch(state, {"c2c": good()}, self.CANCELLED)
        self.assertEqual(messages, [])
        more = dict(self.CANCELLED, cancelled=["WCF 08:20", "WCF 08:35"])
        messages, _ = self.watch(state, {"c2c": good()}, more)
        self.assertTrue(messages[0].startswith("Update: c2c: 2 trains cancelled."))

    def test_running_normally_again_after_15_clear_minutes(self):
        state = {"c2c": {"alert": True, "cancelled": ["WCF 08:20"], "clear_since": None}}
        messages, state = self.watch(state, {"c2c": good()}, self.CLEAR)
        self.assertEqual(messages, [])
        messages, state = self.watch(state, {"c2c": good()}, self.CLEAR, NOW + timedelta(minutes=15))
        self.assertEqual(messages, ["c2c: trains running normally again on the departure boards. "
                                    "WCF to BKG: 08:30 on time."])
        self.assertNotIn("c2c", state)


if __name__ == "__main__":
    unittest.main()
