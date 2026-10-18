import os
import sys
import unittest
from unittest import mock
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import live_trains
from train_alerts import build_messages, format_problem, format_still_disrupted

NOW = datetime(2026, 10, 18, 12, 35, tzinfo=timezone.utc)


def dep(dest, scheduled, estimated, status):
    return {"destinationName": dest, "scheduledTimeOfDeparture": scheduled,
            "estimatedTimeOfDeparture": estimated, "departureStatus": status}


# Shape copied from TfL's ArrivalDepartures for South Tottenham.
BOARD = [
    dep("Barking Rail Station", "2026-10-18T12:20:00Z", "2026-10-18T12:20:00Z", "OnTime"),  # gone
    dep("Barking Rail Station", "2026-10-18T12:37:00Z", "2026-10-18T12:38:15Z", "Delayed"),
    dep("Gospel Oak Rail Station", "2026-10-18T12:43:00Z", "2026-10-18T12:43:00Z", "OnTime"),
    dep("Barking Rail Station", "2026-10-18T12:52:00Z", "2026-10-18T12:52:00Z", "Cancelled"),
    dep("Barking Rail Station", "2026-10-18T13:07:00Z", "2026-10-18T13:14:00Z", "Delayed"),
    dep("Barking Rail Station", "2026-10-18T13:22:00Z", "2026-10-18T13:22:00Z", "OnTime"),
]


class LiveTrainTests(unittest.TestCase):
    def test_next_three_trains_our_way(self):
        trains = live_trains.next_trains(BOARD, "Barking", NOW)
        self.assertEqual([(t.strftime("%H:%M"), d) for t, d in trains],
                         [("12:37", 1), ("12:52", None), ("13:07", 7)])

    def test_describe_board(self):
        trains = live_trains.next_trains(BOARD, "Barking", NOW)
        # 12:37 UTC is 13:37 in the UK in October.
        self.assertEqual(live_trains.describe_board("STO", "BKG", trains),
                         "STO to BKG: 13:37 1 minute delayed, 13:52 cancelled, "
                         "14:07 7 minutes delayed.")

    def test_on_time(self):
        trains = live_trains.next_trains(BOARD, "Gospel Oak", NOW)
        self.assertEqual(live_trains.describe_board("BKG", "STO", trains),
                         "BKG to STO: 13:43 on time.")

    def test_delayed_without_estimate(self):
        board = [dep("Barking Rail Station", "2026-10-18T12:52:00Z", None, "Delayed")]
        trains = live_trains.next_trains(board, "Barking", NOW)
        self.assertEqual(live_trains.describe_board("STO", "BKG", trains),
                         "STO to BKG: 13:52 delayed.")

    def test_live_text_added_when_back_to_good_service(self):
        before = {"suffragette": {"name": "Suffragette", "ok": False, "summary": "Severe Delays", "reasons": []}}
        now = {"suffragette": {"name": "Suffragette", "ok": True, "summary": "Good Service", "reasons": [],
                               "live": "BKG to STO: 13:43 on time."}}
        self.assertEqual(build_messages(before, now),
                         ["Suffragette: back to Good Service. BKG to STO: 13:43 on time."])

    def test_national_rail_board(self):
        # Shape copied from National Rail's staff board for Westcliff, filtered to Barking.
        board = {"trainServices": [
            {"std": "2026-10-18T13:30:00", "atd": "2026-10-18T13:31:00", "etd": None},  # gone
            {"std": "2026-10-18T13:40:00", "etd": "2026-10-18T13:40:10", "isCancelled": False},
            {"std": "2026-10-18T14:03:00", "etd": None, "isCancelled": True},
            {"std": "2026-10-18T14:33:00", "etd": "2026-10-18T14:39:00", "isCancelled": False},
            {"std": "2026-10-18T15:02:00", "etd": "2026-10-18T15:02:00", "isCancelled": False},
        ]}
        trains = live_trains.next_national_rail_trains(board, NOW)
        self.assertEqual(live_trains.describe_board("WCF", "BKG", trains),
                         "WCF to BKG: 13:40 on time, 14:03 cancelled, 14:33 6 minutes delayed.")

    def test_falls_back_to_tfl_when_national_rail_fails(self):
        with mock.patch.dict(os.environ, {"NR_LDB_KEY": "k"}), \
             mock.patch.object(live_trains, "fetch_national_rail", side_effect=OSError("down")), \
             mock.patch.object(live_trains, "fetch_board", return_value=BOARD):
            self.assertEqual(live_trains.check("suffragette", NOW),
                             "STO to BKG: 13:37 1 minute delayed, 13:52 cancelled, 14:07 7 minutes delayed.")

    def test_no_boards_for_line(self):
        self.assertEqual(live_trains.check("unknown-line", NOW), "")

    def test_live_text_added_to_alerts(self):
        status = {"name": "Suffragette", "ok": False, "summary": "Severe Delays",
                  "reasons": ["Signal failure."], "live": "BKG to STO: 13:43 cancelled."}
        self.assertEqual(format_problem(status),
                         "Suffragette: Severe Delays. Signal failure. BKG to STO: 13:43 cancelled.")
        self.assertEqual(format_still_disrupted(status),
                         "Suffragette: Severe Delays. Signal failure. Still disrupted. "
                         "BKG to STO: 13:43 cancelled.")


if __name__ == "__main__":
    unittest.main()
