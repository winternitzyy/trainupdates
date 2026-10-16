import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import train_alerts

PURESMS = {"PURESMS_API_KEY": "k", "PURESMS_SENDER": "s", "ALERT_TO_NUMBER": "+447700900123"}


class SendingTests(unittest.TestCase):
    def run_send(self, env, ntfy_error=None):
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(train_alerts, "send_ntfy", side_effect=ntfy_error) as ntfy, \
             mock.patch.object(train_alerts, "send_sms") as sms:
            train_alerts.send_all(["c2c: back to Good Service."], dry_run=False)
        return ntfy, sms

    def test_ntfy_used_when_topic_set(self):
        ntfy, sms = self.run_send({"NTFY_TOPIC": "trainalerts-abc", **PURESMS})
        ntfy.assert_called_once_with("Train Alerts: c2c: back to Good Service.", "trainalerts-abc", None, None)
        sms.assert_not_called()

    def test_puresms_used_without_topic(self):
        ntfy, sms = self.run_send(PURESMS)
        ntfy.assert_not_called()
        sms.assert_called_once_with("Train Alerts: c2c: back to Good Service.", "k", "s", "+447700900123")

    def test_falls_back_to_puresms_when_ntfy_fails(self):
        ntfy, sms = self.run_send({"NTFY_TOPIC": "trainalerts-abc", **PURESMS},
                                  ntfy_error=urllib.error.URLError("down"))
        sms.assert_called_once()

    def test_ntfy_failure_without_puresms_raises(self):
        with self.assertRaises(urllib.error.URLError):
            self.run_send({"NTFY_TOPIC": "trainalerts-abc"}, ntfy_error=urllib.error.URLError("down"))


if __name__ == "__main__":
    unittest.main()
