import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime

from train_alerts import build_messages, in_quiet_hours, parse_statuses


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
        self.assertEqual(msgs, ["c2c: Severe Delays. C2C: Signal failure at Upminster."])

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
        self.assertEqual(msgs, ["c2c: Suspended. C2C: No service."])

    def test_quiet_hours(self):
        at = lambda h, m: datetime(2026, 1, 1, h, m)
        self.assertTrue(in_quiet_hours("00:00-05:00", at(3, 0)))
        self.assertFalse(in_quiet_hours("00:00-05:00", at(5, 0)))
        self.assertTrue(in_quiet_hours("23:30-05:00", at(23, 45)))
        self.assertFalse(in_quiet_hours("23:30-05:00", at(12, 0)))
        self.assertFalse(in_quiet_hours("", at(3, 0)))


if __name__ == "__main__":
    unittest.main()
