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

    def test_next_two_trains_after_the_problem(self):
        found = live_trains.find_problems([(BKG, [at(10, 0), at(38, None), at(49, 0), at(55, 3), at(63, 0)])], NOW)
        self.assertEqual(found["text"], "BKG to WCF: 08:38 cancelled. Next trains: 08:49 on time, 08:55 3 minutes delayed.")

    def test_one_late_train_is_not_enough(self):
        found = live_trains.find_problems([(WCF, [at(5, 12), at(20, 0)])], NOW)
        self.assertFalse(found["alert"])

    def test_two_late_trains_alert(self):
        found = live_trains.find_problems([(WCF, [at(5, 12)]), (BKG, [at(30, 5), at(40, 4)])], NOW)
        self.assertTrue(found["alert"])
        self.assertEqual(found["late"], 2)
        self.assertEqual(found["text"], "WCF to BKG: 08:05 12 minutes delayed. "
                                        "BKG to WCF: 08:30 5 minutes delayed. Next trains: 08:40 4 minutes delayed.")

    def test_trains_after_the_hour_are_ignored(self):
        found = live_trains.find_problems([(WCF, [at(70, None), at(80, 20), at(90, 20)])], NOW)
        self.assertFalse(found["alert"])


class CancelledInAdvanceTests(unittest.TestCase):
    def test_cancelled_when_first_seen_is_left_out(self):
        seen = {}
        boards = [(WCF, [at(5, 0), at(20, None)])]
        planned = live_trains.note_cancellations(boards, seen, NOW)
        self.assertFalse(live_trains.find_problems(boards, NOW, planned)["alert"])
        # Still left out on later checks.
        planned = live_trains.note_cancellations(boards, seen, NOW + timedelta(minutes=1))
        self.assertFalse(live_trains.find_problems(boards, NOW, planned)["alert"])

    def test_seen_running_then_cancelled_alerts(self):
        seen = {}
        live_trains.note_cancellations([(WCF, [at(20, 0)])], seen, NOW)
        boards = [(WCF, [at(20, None)])]
        planned = live_trains.note_cancellations(boards, seen, NOW)
        found = live_trains.find_problems(boards, NOW, planned)
        self.assertTrue(found["alert"])
        self.assertEqual(found["cancelled"], ["WCF 08:20"])

    def test_cancelled_an_hour_ahead_is_planned(self):
        seen = {}
        live_trains.note_cancellations([(BKG, [at(60, 0)])], seen, NOW)
        boards = [(BKG, [at(60, None)])]
        later = NOW
        planned = live_trains.note_cancellations(boards, seen, later)
        self.assertFalse(live_trains.find_problems(boards, later, planned)["alert"])

    def test_old_trains_are_forgotten(self):
        seen = {}
        live_trains.note_cancellations([(WCF, [at(20, 0)])], seen, NOW)
        live_trains.note_cancellations([], seen, NOW + timedelta(hours=4))
        self.assertEqual(seen, {})

    def test_late_trains_still_count(self):
        boards = [(WCF, [at(5, 12), at(20, 9)])]
        planned = live_trains.note_cancellations(boards, {}, NOW)
        self.assertTrue(live_trains.find_problems(boards, NOW, planned)["alert"])


class RouteTests(unittest.TestCase):
    def test_via_rainham_is_shown(self):
        stops = lambda *crs: [{"crs": c, "isPass": False} for c in crs]
        board = {"trainServices": [
            {"std": "2026-10-21T18:38:00", "isCancelled": True,
             "subsequentLocations": stops("UPM", "RNM", "PFL", "GRY", "PSE", "LES", "WCF")},
            {"std": "2026-10-21T18:49:00", "etd": "2026-10-21T18:49:00",
             "subsequentLocations": stops("UPM", "BSO", "PSE", "LES", "WCF")},
        ]}
        now = datetime(2026, 10, 21, 17, 30, tzinfo=timezone.utc)
        trains = live_trains.next_national_rail_trains(board, now)
        self.assertEqual(live_trains.describe_board("BKG", "WCF", trains),
                         "BKG to WCF: 18:38 (via Rainham) cancelled, 18:49 on time.")


class WatchBoardsTests(unittest.TestCase):
    def watch(self, state, current, found, now=NOW):
        with mock.patch.object(live_trains, "board_problems", return_value=(found, {"WCF x": "running"})), \
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
        self.assertEqual(state["c2c"], {"trains": {}})  # what the boards showed is kept

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
        self.assertNotIn("alert", state["c2c"])


if __name__ == "__main__":
    unittest.main()
