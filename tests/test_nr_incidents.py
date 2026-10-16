import gzip
import os
import sys
import unittest
from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import nr_incidents
import train_alerts

UK = ZoneInfo("Europe/London")

XML = b"""<?xml version="1.0" encoding="utf-8"?>
<Incidents xmlns="http://nationalrail.co.uk/xml/incident" xmlns:com="http://nationalrail.co.uk/xml/common">
 <PtIncident>
  <IncidentNumber>A1</IncidentNumber>
  <ValidityPeriod><com:StartTime>2026-10-16T13:13:00.000+01:00</com:StartTime></ValidityPeriod>
  <Planned>false</Planned>
  <Summary>Disruption to services from Barking to Grays via Rainham (Essex) expected until 15:00</Summary>
  <Description>&lt;p&gt;A fault with the signalling system at Dagenham Dock.&lt;/p&gt;</Description>
  <Affects><Operators><AffectedOperator><OperatorRef>CC</OperatorRef><OperatorName>c2c</OperatorName></AffectedOperator></Operators></Affects>
 </PtIncident>
 <PtIncident>
  <IncidentNumber>A2</IncidentNumber>
  <ValidityPeriod><com:StartTime>2026-10-16T09:09:00.000+01:00</com:StartTime><com:EndTime>2026-10-16T10:22:00.000+01:00</com:EndTime></ValidityPeriod>
  <Planned>false</Planned><ClearedIncident>true</ClearedIncident>
  <Summary>CLEARED: Disruption to c2c services</Summary>
  <Affects><Operators><AffectedOperator><OperatorRef>CC</OperatorRef></AffectedOperator></Operators></Affects>
 </PtIncident>
 <PtIncident>
  <IncidentNumber>P1</IncidentNumber>
  <ValidityPeriod><com:StartTime>2026-10-18T00:00:00.000+01:00</com:StartTime><com:EndTime>2026-10-18T23:59:00.000+01:00</com:EndTime></ValidityPeriod>
  <Planned>true</Planned>
  <Summary>Buses replace trains between Rainham / Upminster and Pitsea until 13:05 on Sunday 18 October</Summary>
  <Affects><Operators><AffectedOperator><OperatorRef>CC</OperatorRef></AffectedOperator></Operators></Affects>
 </PtIncident>
 <PtIncident>
  <IncidentNumber>P2</IncidentNumber>
  <ValidityPeriod><com:StartTime>2026-10-17T00:00:00.000+01:00</com:StartTime><com:EndTime>2026-11-01T23:59:00.000+00:00</com:EndTime></ValidityPeriod>
  <Planned>true</Planned>
  <Summary>No London-bound trains at Limehouse from 20:45 on Saturday 17 October to Sunday 1 November</Summary>
  <Affects><Operators><AffectedOperator><OperatorRef>CC</OperatorRef></AffectedOperator></Operators></Affects>
 </PtIncident>
 <PtIncident>
  <IncidentNumber>X1</IncidentNumber>
  <ValidityPeriod><com:StartTime>2026-10-17T00:00:00.000+01:00</com:StartTime></ValidityPeriod>
  <Planned>true</Planned>
  <Summary>Greater Anglia works</Summary>
  <Affects><Operators><AffectedOperator><OperatorRef>LE</OperatorRef></AffectedOperator></Operators></Affects>
 </PtIncident>
</Incidents>"""


def good(line_id, name):
    return {"name": name, "ok": True, "summary": "Good Service", "reasons": [], "since": None}


class IncidentFeedTests(unittest.TestCase):
    def setUp(self):
        self.incidents = nr_incidents.parse(gzip.compress(XML))
        self.c2c = nr_incidents.for_operator(self.incidents, "CC")

    def test_parse_gzip_and_fields(self):
        self.assertEqual(len(self.incidents), 5)
        self.assertEqual(len(self.c2c), 4)
        first = self.incidents[0]
        self.assertFalse(first["planned"])
        self.assertEqual(first["description"], "A fault with the signalling system at Dagenham Dock.")

    def test_active_unplanned_skips_cleared(self):
        active = nr_incidents.active_unplanned(self.c2c, datetime(2026, 10, 16, 14, 0, tzinfo=UK))
        self.assertEqual([i["number"] for i in active], ["A1"])

    def test_planned_on_day(self):
        sat = [i["number"] for i in nr_incidents.planned_on(self.c2c, date(2026, 10, 17), UK)]
        sun = [i["number"] for i in nr_incidents.planned_on(self.c2c, date(2026, 10, 18), UK)]
        self.assertEqual(sat, ["P2"])
        self.assertEqual(sun, ["P2", "P1"])
        self.assertEqual(nr_incidents.planned_on(self.c2c, date(2026, 11, 7), UK), [])


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.incidents = nr_incidents.parse(XML)
        patches = [mock.patch.dict(os.environ, {"NR_INCIDENTS_KEY": "k"}),
                   mock.patch.object(nr_incidents, "get", return_value=self.incidents)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_weekend_preview_uses_national_rail_for_c2c(self):
        statuses = {"c2c": good("c2c", "c2c"), "suffragette": good("suffragette", "Suffragette")}
        sun = train_alerts.add_nr_planned_works(date(2026, 10, 18), statuses)
        text = train_alerts.format_day(date(2026, 10, 18), sun)
        self.assertEqual(text, "Sun 18 Oct: c2c: Planned works. No London-bound trains at Limehouse from 20:45 "
                               "on Saturday 17 October to Sunday 1 November. Buses replace trains between "
                               "Rainham / Upminster and Pitsea until 13:05 on Sunday 18 October. "
                               "Suffragette: running normally, no planned works.")

    def test_no_planned_works_means_running_normally(self):
        statuses = {"c2c": {"name": "c2c", "ok": False, "summary": "Part Closure", "reasons": ["TfL says"]}}
        text = train_alerts.format_day(date(2026, 11, 7), train_alerts.add_nr_planned_works(date(2026, 11, 7), statuses))
        self.assertEqual(text, "Sat 7 Nov: c2c: running normally, no planned works.")

    def test_live_alert_uses_national_rail_explanation(self):
        current = {"c2c": {"name": "c2c", "ok": False, "summary": "Special Service",
                           "reasons": ["https://www.nationalrail.co.uk/service-disruptions/dagenham-dock-20261016/"],
                           "since": None}}
        train_alerts.add_nr_explanations(current, datetime(2026, 10, 16, 13, 20, tzinfo=UK))
        msgs = train_alerts.build_messages({}, current)
        self.assertEqual(msgs, ["c2c: Special Service. Disruption to services from Barking to Grays via "
                                "Rainham (Essex) expected until 15:00."])

    def test_explanation_does_not_count_as_a_change(self):
        tfl = {"name": "c2c", "ok": False, "summary": "Special Service", "reasons": ["link"], "since": None}
        before = dict(tfl, nr_reasons=["NR summary"])
        self.assertEqual(train_alerts.build_messages({"c2c": before}, {"c2c": dict(tfl)}), [])

    def test_feed_failure_falls_back_to_tfl(self):
        with mock.patch.object(nr_incidents, "get", side_effect=OSError("down")):
            current = {"c2c": {"name": "c2c", "ok": False, "summary": "Severe Delays", "reasons": ["TfL reason"]}}
            train_alerts.add_nr_explanations(current)
        self.assertEqual(train_alerts.format_problem(current["c2c"]), "c2c: Severe Delays. TfL reason.")


if __name__ == "__main__":
    unittest.main()
