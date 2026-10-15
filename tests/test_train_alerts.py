import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime

from train_alerts import (build_messages, format_weekly, in_quiet_hours, next_sunday,
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

    def test_next_sunday(self):
        self.assertEqual(str(next_sunday(datetime(2026, 10, 15, 18, 0))), "2026-10-18")  # Thursday
        self.assertEqual(str(next_sunday(datetime(2026, 10, 18, 9, 0))), "2026-10-25")  # Sunday

    def test_weekly_due_only_thursday_evening_once(self):
        thu = datetime(2026, 10, 15, 18, 0)
        self.assertTrue(weekly_due(thu, None))
        self.assertFalse(weekly_due(thu, thu.strftime("%G-W%V")))
        self.assertFalse(weekly_due(datetime(2026, 10, 15, 17, 59), None))
        self.assertFalse(weekly_due(datetime(2026, 10, 16, 18, 0), None))

    def test_format_weekly(self):
        planned = [{"id": "c2c", "name": "c2c", "lineStatuses": [
                       {"statusSeverity": 10, "statusSeverityDescription": "Good Service"},
                       {"statusSeverity": 4, "statusSeverityDescription": "Planned Closure",
                        "reason": "No trains Barking to Upminster."}]},
                   tfl_line("suffragette", "Suffragette", 10, "Good Service")]
        text = format_weekly(datetime(2026, 10, 18).date(), parse_statuses(planned))
        self.assertEqual(text, "Train status for the coming Sunday 18 Oct: c2c: Planned Closure. "
                               "No trains Barking to Upminster. "
                               "Suffragette: running normally, no planned works.")

    def test_weekly_drops_repeated_date(self):
        data = [tfl_line("suffragette", "Suffragette", 4, "Part Closure",
                         "SUFFRAGETTE LINE: Sunday 18 October, no service between Barking and "
                         "Barking Riverside, please use local London Buses services.")]
        text = format_weekly(datetime(2026, 10, 18).date(), parse_statuses(data))
        self.assertEqual(text, "Train status for the coming Sunday 18 Oct: Suffragette: Part Closure. "
                               "No service between Barking and Barking Riverside, "
                               "please use local London Buses services.")

    def test_line_name_prefix_removed(self):
        data = [tfl_line("suffragette", "Suffragette", 4, "Part Closure",
                         "SUFFRAGETTE LINE: Sunday 18 October, no service between Barking and Barking Riverside.")]
        self.assertEqual(parse_statuses(data)["suffragette"]["reasons"],
                         ["Sunday 18 October, no service between Barking and Barking Riverside."])


if __name__ == "__main__":
    unittest.main()
