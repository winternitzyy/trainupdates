import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime

from train_alerts import (build_messages, coming_weekend, format_still_disrupted, format_weekly,
                          in_quiet_hours,
                          parse_statuses, weekly_due)


def tfl_line(line_id, name, severity, description, reason=None):
    status = {"statusSeverity": severity, "statusSeverityDescription": description}
    if reason:
        status["reason"] = reason
    return {"id": line_id, "name": name, "lineStatuses": [status]}


GOOD = [tfl_line("c2c", "c2c", 10, "Good Service"),
        tfl_line("suffragette", "Suffragette", 10, "Good Service")]
DELAYED = [tfl_line("c2c", "c2c", 6, "Severe Delays", "C2C: Signal failure at Upminster."),
           tfl_line("suffragette", "Suffragette", 10, "Good Service")]


class TrainAlertTests(unittest.TestCase):
    def test_parse_good_service(self):
        parsed = parse_statuses(GOOD)
        self.assertTrue(parsed["c2c"]["ok"])
        self.assertEqual(parsed["suffragette"]["summary"], "Good Service")

    def test_first_run_good_service_sends_nothing(self):
        self.assertEqual(build_messages({}, parse_statuses(GOOD)), [])

    def test_first_run_with_disruption_alerts(self):
        msgs = build_messages({}, parse_statuses(DELAYED))
        self.assertEqual(msgs, ["c2c: Severe Delays. Signal failure at Upminster."])

    def test_disruption_starts(self):
        msgs = build_messages(parse_statuses(GOOD), parse_statuses(DELAYED))
        self.assertEqual(len(msgs), 1)
        self.assertIn("Severe Delays", msgs[0])

    def test_unchanged_disruption_is_not_repeated(self):
        state = parse_statuses(DELAYED)
        self.assertEqual(build_messages(state, parse_statuses(DELAYED)), [])

    def test_recovery_alert(self):
        msgs = build_messages(parse_statuses(DELAYED), parse_statuses(GOOD))
        self.assertEqual(msgs, ["c2c: back to Good Service."])

    def test_severity_change_alerts_again(self):
        worse = [tfl_line("c2c", "c2c", 1, "Suspended", "C2C: No service."),
                 tfl_line("suffragette", "Suffragette", 10, "Good Service")]
        msgs = build_messages(parse_statuses(DELAYED), parse_statuses(worse))
        self.assertEqual(msgs, ["c2c: Suspended. No service."])

    def test_quiet_hours(self):
        at = lambda h, m: datetime(2026, 1, 1, h, m)
        self.assertTrue(in_quiet_hours("00:00-05:00", at(3, 0)))
        self.assertFalse(in_quiet_hours("00:00-05:00", at(5, 0)))
        self.assertTrue(in_quiet_hours("23:30-05:00", at(23, 45)))
        self.assertFalse(in_quiet_hours("23:30-05:00", at(12, 0)))
        self.assertFalse(in_quiet_hours("", at(3, 0)))

    def test_coming_weekend(self):
        self.assertEqual([str(d) for d in coming_weekend(datetime(2026, 10, 15, 18, 0))],
                         ["2026-10-17", "2026-10-18"])  # Thursday
        self.assertEqual([str(d) for d in coming_weekend(datetime(2026, 10, 17, 9, 0))],
                         ["2026-10-24", "2026-10-25"])  # Saturday

    def test_weekly_due_only_thursday_evening_once(self):
        thu = datetime(2026, 10, 15, 18, 0)
        self.assertTrue(weekly_due(thu, None))
        self.assertFalse(weekly_due(thu, thu.strftime("%G-W%V")))
        self.assertFalse(weekly_due(datetime(2026, 10, 15, 17, 59), None))
        self.assertFalse(weekly_due(datetime(2026, 10, 16, 18, 0), None))

    def test_format_weekly(self):
        sat = [tfl_line("c2c", "c2c", 10, "Good Service"),
               tfl_line("suffragette", "Suffragette", 10, "Good Service")]
        sun = [tfl_line("c2c", "c2c", 10, "Good Service"),
               tfl_line("suffragette", "Suffragette", 4, "Part Closure",
                        "SUFFRAGETTE LINE: Sunday 18 October, no service between Barking and "
                        "Barking Riverside, please use local London Buses services.")]
        text = format_weekly([(datetime(2026, 10, 17).date(), parse_statuses(sat)),
                              (datetime(2026, 10, 18).date(), parse_statuses(sun))])
        self.assertEqual(text,
            "Train status for the coming weekend (Sat 17 & Sun 18 Oct).\n"
            "c2c: running normally, no planned works.\n"
            "Suffragette: Sat: running normally, no planned works. Sun: Part Closure. "
            "No service between Barking and Barking Riverside, please use local London Buses services.")

    def test_line_name_prefix_removed(self):
        data = [tfl_line("suffragette", "Suffragette", 4, "Part Closure",
                         "SUFFRAGETTE LINE: Sunday 18 October, no service between Barking and Barking Riverside.")]
        self.assertEqual(parse_statuses(data)["suffragette"]["reasons"],
                         ["Sunday 18 October, no service between Barking and Barking Riverside."])


    def test_still_disrupted_shows_start_time(self):
        data = [{"id": "c2c", "name": "c2c", "lineStatuses": [{
            "statusSeverity": 6, "statusSeverityDescription": "Severe Delays",
            "reason": "C2C: Signal failure at Upminster.",
            "validityPeriods": [{"fromDate": "2026-10-17T13:32:00Z", "toDate": "2026-10-17T23:00:00Z"}]}]}]
        text = format_still_disrupted(parse_statuses(data)["c2c"])
        self.assertEqual(text, "c2c: Severe Delays since Sat 14:32. Signal failure at Upminster. "
                               "Still disrupted.")

    def test_still_disrupted_without_start_time(self):
        text = format_still_disrupted(parse_statuses(DELAYED)["c2c"])
        self.assertEqual(text, "c2c: Severe Delays. Signal failure at Upminster. Still disrupted.")


if __name__ == "__main__":
    unittest.main()
