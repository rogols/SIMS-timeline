import hashlib
import unittest
from datetime import date
from pathlib import Path

from generate_timeline import category, parse_events, render_timeline


FIXTURE = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260902T111500Z
DTEND:20260902T150000Z
UID:start@example.test
SUMMARY:SIMS\\, Introduktion
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/Stockholm:20260909T101500
DTEND;TZID=Europe/Stockholm:20260909T120000
UID:lab@example.test
SUMMARY:SIMS\\, Labor
 ation 1
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260920
DTEND;VALUE=DATE:20260921
UID:finish@example.test
SUMMARY:SIMS\\, Redovisning
END:VEVENT
END:VCALENDAR
"""


class TimelineTests(unittest.TestCase):
    def test_parses_folded_and_timed_events(self):
        events = parse_events(FIXTURE)
        self.assertEqual(3, len(events))
        self.assertEqual("SIMS, Laboration 1", events[1].summary)
        self.assertEqual("Laboratory", category(events[1].summary))
        self.assertEqual(13, events[0].start.hour)  # 11:15 UTC is 13:15 in Stockholm.

    def test_render_is_deterministic_for_fixed_inputs(self):
        events = parse_events(FIXTURE)
        first = Path("test-output-first.png")
        second = Path("test-output-second.png")
        try:
            render_timeline(events, date(2026, 9, 9), first)
            render_timeline(events, date(2026, 9, 9), second)
            self.assertEqual(
                hashlib.sha256(first.read_bytes()).digest(),
                hashlib.sha256(second.read_bytes()).digest(),
            )
        finally:
            first.unlink(missing_ok=True)
            second.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
