#!/usr/bin/env python3
"""Fetch a TimeEdit calendar and render a deterministic course timeline PNG."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw, ImageFont


COURSE_TIMEZONE = ZoneInfo("Europe/Stockholm")
WIDTH = 2400
HEIGHT = 600
MARGIN_X = 145
LINE_Y = 320

COLORS = {
    "background": "#F7FAF8",
    "ink": "#18313D",
    "muted": "#617780",
    "faint": "#DCE7E6",
    "future": "#B8CDD0",
    "past": "#4EA5B5",
    "today": "#F26B3A",
    "lab": "#35A6A0",
    "exam": "#D65A45",
    "presentation": "#E49A32",
    "lecture": "#5D92B8",
    "study": "#8DBD69",
    "other": "#7A91A0",
}


@dataclass(frozen=True, order=True)
class Event:
    start: datetime
    end: datetime
    summary: str
    uid: str = ""

    @property
    def day(self) -> date:
        return self.start.astimezone(COURSE_TIMEZONE).date()


CATEGORY_RULES = (
    ("Examination", re.compile(r"\b(tentamen|examination|exam|quiz)\b", re.I)),
    ("Presentation", re.compile(r"\b(redovisning|presentation|demo)\b", re.I)),
    ("Seminar", re.compile(r"\b(seminarium|seminar)\b", re.I)),
    ("Laboratory", re.compile(r"\b(laboration|laboratory|lab)\b", re.I)),
    ("Workshop", re.compile(r"\b(workshop)\b", re.I)),
    ("Supervision", re.compile(r"\b(handledning|supervision)\b", re.I)),
    ("Lecture", re.compile(r"\b(föreläsning|lecture)\b", re.I)),
    ("Introduction", re.compile(r"\b(introduktion|introduction)\b", re.I)),
    ("Self-study", re.compile(r"\b(egna studier|self[- ]study)\b", re.I)),
    ("Project work", re.compile(r"\b(projektarbete|project work|grupparbete)\b", re.I)),
)


def unfold_ics(text: str) -> list[str]:
    """Unfold RFC 5545 content lines."""
    unfolded: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def unescape_ics(value: str) -> str:
    return (
        value.replace("\\N", "\n")
        .replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def parse_ics_datetime(raw: str, params: dict[str, str]) -> datetime:
    if params.get("VALUE", "").upper() == "DATE" or len(raw) == 8:
        parsed_date = datetime.strptime(raw[:8], "%Y%m%d").date()
        return datetime.combine(parsed_date, datetime.min.time(), COURSE_TIMEZONE)

    is_utc = raw.endswith("Z")
    value = raw[:-1] if is_utc else raw
    fmt = "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M"
    parsed = datetime.strptime(value, fmt)
    if is_utc:
        return parsed.replace(tzinfo=timezone.utc).astimezone(COURSE_TIMEZONE)

    tz_name = params.get("TZID", "Europe/Stockholm")
    try:
        source_timezone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        source_timezone = COURSE_TIMEZONE
    return parsed.replace(tzinfo=source_timezone).astimezone(COURSE_TIMEZONE)


def parse_events(text: str) -> list[Event]:
    events: list[Event] = []
    current: dict[str, tuple[str, dict[str, str]]] | None = None

    for line in unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and "DTSTART" in current:
                start_raw, start_params = current["DTSTART"]
                end_raw, end_params = current.get("DTEND", current["DTSTART"])
                start = parse_ics_datetime(start_raw, start_params)
                end = parse_ics_datetime(end_raw, end_params)
                summary = unescape_ics(current.get("SUMMARY", ("Course activity", {}))[0])
                uid = current.get("UID", ("", {}))[0]
                status = current.get("STATUS", ("", {}))[0].upper()
                if status != "CANCELLED":
                    events.append(Event(start=start, end=end, summary=summary, uid=uid))
            current = None
            continue
        if current is None or ":" not in line:
            continue

        head, raw_value = line.split(":", 1)
        parts = head.split(";")
        name = parts[0].upper()
        params: dict[str, str] = {}
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.upper()] = value.strip('"')
        if name in {"DTSTART", "DTEND", "SUMMARY", "UID", "STATUS"}:
            current[name] = (raw_value, params)

    unique = {(event.uid, event.start, event.summary): event for event in events}
    return sorted(unique.values())


def fetch_calendar(url: str, attempts: int = 3) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SIMS-timeline/1.0 (+https://github.com/rogols/SIMS-timeline)"},
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == attempts:
                raise RuntimeError(f"Could not fetch TimeEdit calendar after {attempts} attempts") from error
            time.sleep(attempt * 2)
    raise AssertionError("unreachable")


def category(summary: str) -> str:
    for label, pattern in CATEGORY_RULES:
        if pattern.search(summary):
            return label
    return "Course activity"


def category_color(label: str) -> str:
    if label == "Laboratory":
        return COLORS["lab"]
    if label == "Examination":
        return COLORS["exam"]
    if label in {"Presentation", "Seminar", "Workshop"}:
        return COLORS["presentation"]
    if label in {"Lecture", "Introduction"}:
        return COLORS["lecture"]
    if label in {"Self-study", "Project work"}:
        return COLORS["study"]
    return COLORS["other"]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    candidates = (
        filename,
        f"/usr/share/fonts/truetype/dejavu/{filename}",
        f"C:/Windows/Fonts/{'arialbd.ttf' if bold else 'arial.ttf'}",
        f"/Library/Fonts/{filename}",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def format_day(value: date) -> str:
    return f"{value.day} {value.strftime('%b').upper()}"


def x_for_day(value: date, start: date, end: date) -> float:
    duration = max((end - start).days, 1)
    ratio = (value - start).days / duration
    return MARGIN_X + max(0.0, min(1.0, ratio)) * (WIDTH - 2 * MARGIN_X)


def choose_milestones(events: list[Event], start: date, end: date) -> list[tuple[date, str]]:
    by_category: dict[str, list[date]] = defaultdict(list)
    for event in events:
        by_category[category(event.summary)].append(event.day)

    candidates: list[tuple[int, date, str]] = []
    priorities = {
        "Examination": 100,
        "Presentation": 90,
        "Seminar": 80,
        "Laboratory": 70,
        "Workshop": 60,
        "Introduction": 50,
    }
    for label, priority in priorities.items():
        days = sorted(set(by_category.get(label, [])))
        if days:
            candidates.append((priority, days[0], label))
            if label in {"Examination", "Presentation"} and len(days) > 1:
                candidates.append((priority - 1, days[-1], label))

    selected: list[tuple[date, str]] = [(start, "Course start")]
    for _, day_value, label in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if day_value in {start, end}:
            continue
        if any(abs((day_value - existing_day).days) < 5 for existing_day, _ in selected):
            continue
        selected.append((day_value, label))
        if len(selected) >= 5:
            break
    if end != start:
        selected.append((end, "Course finish"))
    return sorted(selected)


def render_timeline(events: list[Event], today: date, output: Path) -> None:
    if not events:
        raise ValueError("The calendar contains no course events")

    start = min(event.day for event in events)
    end = max(event.day for event in events)
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["background"])
    draw = ImageDraw.Draw(image)

    title_font = load_font(46, bold=True)
    subtitle_font = load_font(22)
    label_font = load_font(21, bold=True)
    small_font = load_font(17)
    tiny_font = load_font(15, bold=True)

    draw.text((MARGIN_X, 45), "SIMS · COURSE TIMELINE", fill=COLORS["ink"], font=title_font)
    subtitle = f"{format_day(start)} — {format_day(end)}  ·  {len(events)} scheduled activities"
    draw.text((MARGIN_X, 102), subtitle, fill=COLORS["muted"], font=subtitle_font)

    line_start = MARGIN_X
    line_end = WIDTH - MARGIN_X
    draw.line((line_start, LINE_Y, line_end, LINE_Y), fill=COLORS["future"], width=14)
    progress_x = x_for_day(today, start, end)
    if today >= start:
        past_end = line_end if today >= end else progress_x
        draw.line((line_start, LINE_Y, past_end, LINE_Y), fill=COLORS["past"], width=14)

    span_days = max((end - start).days, 1)
    tick_step = 7 if span_days <= 120 else 14
    tick = start
    while tick <= end:
        tick_x = x_for_day(tick, start, end)
        draw.line((tick_x, LINE_Y + 14, tick_x, LINE_Y + 25), fill=COLORS["faint"], width=3)
        if (tick - start).days % (tick_step * 2) == 0:
            tick_text = format_day(tick)
            draw.text(
                (tick_x - text_width(draw, tick_text, tiny_font) / 2, LINE_Y + 31),
                tick_text,
                fill=COLORS["muted"],
                font=tiny_font,
            )
        tick += timedelta(days=tick_step)

    events_by_day: dict[date, list[Event]] = defaultdict(list)
    for event in events:
        events_by_day[event.day].append(event)
    for event_day, day_events in sorted(events_by_day.items()):
        event_x = x_for_day(event_day, start, end)
        count = len(day_events)
        top = LINE_Y - min(68, 19 + count * 7)
        dominant = Counter(category(event.summary) for event in day_events).most_common(1)[0][0]
        color = COLORS["past"] if event_day < today else category_color(dominant)
        draw.line((event_x, LINE_Y - 7, event_x, top), fill=color, width=4)
        radius = min(11, 6 + count)
        draw.ellipse((event_x - radius, top - radius, event_x + radius, top + radius), fill=color)

    milestones = choose_milestones(events, start, end)
    for index, (milestone_day, milestone_label) in enumerate(milestones):
        milestone_x = x_for_day(milestone_day, start, end)
        label_y = 167 if index % 2 == 0 else 218
        draw.line((milestone_x, label_y + 31, milestone_x, LINE_Y - 82), fill=COLORS["faint"], width=3)
        date_text = format_day(milestone_day)
        label_width = max(text_width(draw, milestone_label, label_font), text_width(draw, date_text, small_font))
        left = max(10, min(WIDTH - label_width - 10, milestone_x - label_width / 2))
        draw.text((left, label_y), milestone_label, fill=COLORS["ink"], font=label_font)
        draw.text((left, label_y + 27), date_text, fill=COLORS["muted"], font=small_font)

    if today < start:
        status = f"STARTS {format_day(start)}"
        marker_x = line_start
    elif today > end:
        status = "COURSE COMPLETE"
        marker_x = line_end
    else:
        progress = round(((today - start).days / span_days) * 100)
        status = f"TODAY · {format_day(today)} · {progress}%"
        marker_x = progress_x

    draw.ellipse((marker_x - 22, LINE_Y - 22, marker_x + 22, LINE_Y + 22), fill=COLORS["background"], outline=COLORS["today"], width=9)
    status_width = text_width(draw, status, tiny_font) + 30
    status_left = max(MARGIN_X, min(WIDTH - MARGIN_X - status_width, marker_x - status_width / 2))
    draw.rounded_rectangle((status_left, LINE_Y + 70, status_left + status_width, LINE_Y + 106), radius=18, fill=COLORS["today"])
    draw.text((status_left + 15, LINE_Y + 79), status, fill="white", font=tiny_font)

    footer_top = 488
    draw.line((MARGIN_X, footer_top, WIDTH - MARGIN_X, footer_top), fill=COLORS["faint"], width=2)
    draw.text(
        (MARGIN_X, footer_top + 18),
        "Each stem is a scheduled day · taller stems contain more activities",
        fill=COLORS["muted"],
        font=small_font,
    )
    legend_items = [
        ("Lecture", COLORS["lecture"]),
        ("Laboratory", COLORS["lab"]),
        ("Seminar / presentation", COLORS["presentation"]),
        ("Self-study / project", COLORS["study"]),
        ("Other", COLORS["other"]),
    ]
    legend_x = MARGIN_X
    for legend_label, legend_color in legend_items:
        legend_y = footer_top + 54
        draw.ellipse((legend_x, legend_y, legend_x + 14, legend_y + 14), fill=legend_color)
        draw.text((legend_x + 23, legend_y - 3), legend_label, fill=COLORS["ink"], font=small_font)
        legend_x += 205 + text_width(draw, legend_label, small_font)
    source_text = "TimeEdit schedule · updated automatically every day at 06:00 Europe/Stockholm"
    source_width = text_width(draw, source_text, small_font)
    draw.text((WIDTH - MARGIN_X - source_width, HEIGHT - 28), source_text, fill=COLORS["muted"], font=small_font)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    image.save(temporary, format="PNG", optimize=False, compress_level=9)
    os.replace(temporary, output)


def parse_today(raw: str | None) -> date:
    if raw:
        return date.fromisoformat(raw)
    return datetime.now(COURSE_TIMEZONE).date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ics-url", default=os.environ.get("TIMEEDIT_ICS_URL"))
    parser.add_argument("--ics-file", type=Path, help="Read an ICS fixture instead of downloading it")
    parser.add_argument("--date", help="Override today's Stockholm date (YYYY-MM-DD)")
    parser.add_argument("--output", type=Path, default=Path("timeline.png"))
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.ics_file:
        calendar_text = args.ics_file.read_text(encoding="utf-8-sig")
    elif args.ics_url:
        calendar_text = fetch_calendar(args.ics_url)
    else:
        raise SystemExit("Set TIMEEDIT_ICS_URL, pass --ics-url, or pass --ics-file")

    events = parse_events(calendar_text)
    render_timeline(events, parse_today(args.date), args.output)
    print(f"Rendered {args.output} from {len(events)} events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
