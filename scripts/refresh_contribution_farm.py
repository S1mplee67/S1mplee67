#!/usr/bin/env python3
"""Refresh the two retro farm SVGs from GitHub's public contribution calendar.

The grid is a 53-week rolling Sunday-to-Saturday calendar. Only actual
nonzero contribution dates receive cows; decorations and animated UFOs
are deliberately preserved.
"""
from __future__ import annotations

from datetime import date, timedelta, timezone, datetime
from html import unescape
from pathlib import Path
import calendar
import re
import time
import urllib.request
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
USER = "S1mplee67"
TODAY = datetime.now(timezone.utc).date()
URL = f"https://github.com/users/{USER}/contributions?to={TODAY.isoformat()}"

# GitHub displays public contribution activity, not a count inferred from
# commits. GitHub can change its rendered markup, so fail safely if it does.
def activity() -> dict[date, int]:
    raw = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                URL, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; GitHubProfileFarm/1.0)",
                    "Accept": "text/html",
                    "Accept-Language": "en-US,en;q=0.9",
                })
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read().decode("utf-8")
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    pattern = re.compile(
        r'<td\b(?P<attrs>[^>]*\bdata-date="(?P<date>\d{4}-\d{2}-\d{2})"[^>]*)>'
        r'\s*</td>\s*<tool-tip\b[^>]*>(?P<tip>.*?)</tool-tip>',
        re.I | re.S,
    )
    events = {}
    for match in pattern.finditer(raw):
        d = date.fromisoformat(match.group("date"))
        tip = unescape(re.sub(r"<[^>]*>", "", match.group("tip")))
        n = re.search(r"([\d,]+) contributions? on ", tip, flags=re.I)
        if not n:
            if "no contributions" in tip.lower():
                count = 0
            else:
                raise ValueError(f"Unexpected contribution tooltip for {d}: {tip!r}")
        else:
            count = int(n.group(1).replace(",", ""))
        events[d] = count

    # We must never replace the verified farm with empty/incomplete data.
    if len(events) < 350:
        raise ValueError(f"GitHub contribution calendar appears incomplete ({len(events)} days)")
    recent = {day: count for day, count in events.items()
              if TODAY - timedelta(days=364) <= day <= TODAY and count > 0}
    if not recent:
        raise ValueError("No positive public activity returned; keeping existing farm")
    print(f"GitHub public calendar: {sum(recent.values())} contributions, "
          f"{len(recent)} days; snapshot {TODAY}")
    for day, count in sorted(recent.items()):
        print(f"  {day}: {count}")
    return recent



def align_ufos(src: str, counts: dict[date, int], start_sunday: date) -> str:
    """Anchor three ships and their beams to real cow positions each refresh.

    The cow in the first calendar row has no safe space *above* it because
    month labels occupy y=91. For that target, the UFO hovers to its right and
    aims a diagonal beam back at the cow. All other targets use vertical beams.
    """
    rows = []
    for day, count in sorted(counts.items()):
        week = (day - start_sunday).days // 7
        weekday = (day.weekday() + 1) % 7
        rows.append({
            "day": day, "count": count,
            "x": 92.5 + 17.5 * week,
            "y": 110 + 19 * weekday
        })
    if not rows:
        raise ValueError("Cannot position UFOs without contribution cows")

    peak = max(rows, key=lambda item: (item["count"], item["day"]))
    newest = rows[-1]
    # A slightly lower early cow keeps the first and featured craft separated.
    earliest_pool = [
        item for item in rows
        if item["day"] not in (peak["day"], newest["day"])
    ]
    early = next(
        (item for item in earliest_pool if item["y"] >= 185),
        earliest_pool[0] if earliest_pool else rows[0]
    )
    desired = [early, peak, newest]
    selected = []
    for item in desired:
        if item["day"] in [existing["day"] for existing in selected]:
            item = next(
                (candidate for candidate in rows
                 if candidate["day"] not in [x["day"] for x in selected]),
                item
            )
        selected.append(item)

    start_marker = "<!-- Three small independent scout ships"
    start = src.find(start_marker)
    end = src.find('<path d="M17 271H1182"', start)
    if start < 0 or end < 0:
        raise ValueError("Existing UFO scene delimiters not found")
    scene = src[start:end]
    updated = [
        "<!-- Three UFOs dynamically aligned to cow dates; "
        "beams terminate on their targeted contribution tiles -->"
    ]
    for idx, (kind, target) in enumerate(zip("abc", selected)):
        pattern = (
            r'<g transform="translate\([\d.]+ [\d.]+\)">\s*'
            rf'<g class="ufo-{kind}">.*?</g>\s*</g>\s*</g>'
        )
        matches = list(re.finditer(pattern, scene, flags=re.S))
        if len(matches) != 1:
            raise ValueError(f"Cannot locate original UFO {kind} artwork")
        ship = matches[0].group(0)
        cow_x = target["x"] + 7.0
        cow_y = target["y"] + 8.0
        if target["y"] <= 135:
            # First-row cows need a side approach to avoid the month header.
            ufo_x = cow_x + 49
            ufo_y = target["y"] + 18
        else:
            ufo_x = cow_x
            ufo_y = target["y"] - 33
        dx, dy = cow_x - ufo_x, cow_y - ufo_y
        if dx < -20:
            # Beam runs diagonally back to the upper-right-grid cow.
            beam = (
                f"M-6 13L{dx - 6:.1f} {dy - 7:.1f}"
                f"L{dx + 6:.1f} {dy + 7:.1f}L6 13Z"
            )
        else:
            # Vertical beam lands on the cow, not beneath its grid tile.
            beam = f"M-7 13L-12 {dy + 4:.1f}H12L7 13Z"

        group_open = re.match(r'<g transform="translate\([\d.]+ [\d.]+\)">', ship)
        if not group_open:
            raise ValueError("Unexpected spacecraft group structure")
        metadata = (
            f'<g data-ufo-target="{target["day"]}" '
            f'data-cow-x="{cow_x:.1f}" data-cow-y="{cow_y:.1f}" '
            f'transform="translate({ufo_x:.1f} {ufo_y:.1f})">'
        )
        ship = metadata + ship[group_open.end():]
        ship, n = re.subn(
            r'(<path class="ray-[ab]" d=")[^"]+(" fill=)',
            lambda match: match.group(1) + beam + match.group(2),
            ship, count=1,
        )
        if n != 1:
            raise ValueError(f"UFO {kind} is missing its tractor beam")
        updated.append(ship)
    src = src[:start] + "\n".join(updated) + "\n" + src[end:]

    # Ships now hover directly over their target while their beam is active.
    # Previously they moved 80px sideways during the beam, losing alignment.
    flight_start = src.find("@keyframes scoutLeft")
    flight_end = src.find("@keyframes tractorRay", flight_start)
    if flight_start < 0 or flight_end < 0:
        raise ValueError("UFO flight animations are missing")
    new_flight = """@keyframes scoutLeft {
  0%,8%{opacity:0;transform:translate(-90px,-24px)}
  18%{opacity:1;transform:translate(-10px,-4px)}
  28%,62%{opacity:1;transform:translate(0,0)}
  77%{opacity:.8;transform:translate(50px,-15px)}
  95%,100%{opacity:0;transform:translate(94px,-32px)}
}
@keyframes scoutCenter {
  0%,18%{opacity:0;transform:translate(58px,-26px)}
  29%,74%{opacity:1;transform:translate(0,0)}
  88%,100%{opacity:0;transform:translate(-78px,-29px)}
}
@keyframes scoutRight {
  0%,29%{opacity:0;transform:translate(70px,-27px)}
  40%,76%{opacity:1;transform:translate(0,0)}
  88%,100%{opacity:0;transform:translate(-75px,-32px)}
}
"""
    src = src[:flight_start] + new_flight + src[flight_end:]
    return src


def one_farm(name: str, counts: dict[date, int]) -> None:
    path = ASSETS / name
    src = path.read_text(encoding="utf-8")
    light = "-light." in name
    total = sum(counts.values())
    count_days = len(counts)

    # GitHub graph columns are weeks beginning Sunday. Roll the window as
    # time passes, rather than letting new contributions fall outside the SVG.
    current_sunday = TODAY - timedelta(days=(TODAY.weekday() + 1) % 7)
    start_sunday = current_sunday - timedelta(weeks=52)

    # Redraw the 53-week tile matrix without changing the surrounding artwork.
    dark_inactive = ("#263A34", "#304238", "#375044")
    light_inactive = ("#B9CBB2", "#AAC1A7", "#C4D4C0")
    inactive = light_inactive if light else dark_inactive
    on = "#609B73" if light else "#5A9476"
    stroke = "#739181" if light else "#526A5A"
    cells = []
    activity_in_grid = {}
    for week in range(53):
        for weekday in range(7):
            d = start_sunday + timedelta(days=7*week + weekday)
            if d > TODAY:
                continue
            x = 92.0 + 17.5 * week
            y = 109 + 19 * weekday
            n = counts.get(d, 0)
            fill = on if n else inactive[(week + weekday) % len(inactive)]
            if n:
                activity_in_grid[d] = n
            xtext = f"{x:g}"
            cells.append(
                f'<rect x="{xtext}" y="{y}" width="13.5" height="15" rx="2" '
                f'fill="{fill}" stroke="{stroke}" stroke-opacity=".35" '
                f'stroke-width=".5"/>'
            )
    if len(activity_in_grid) != len(counts):
        raise ValueError("Some contribution days fall outside the rolling calendar")

    # Month labels must roll with the grid too.
    label_color = "#536C60" if light else "#97AAA0"
    months = []
    for week in range(53):
        first = start_sunday + timedelta(days=7 * week)
        if week > 0:
            last_month = (first - timedelta(days=7)).month
            if first.month == last_month:
                continue
        months.append(
            f'<text x="{92 + 17.5 * week:g}" y="91" font-family="Consolas,monospace" '
            f'font-size="10" fill="{label_color}">{calendar.month_abbr[first.month]}</text>'
        )
    # Note first Sunday in a month might be preceded by days of previous
    # month; using the first week that contains the first day is closer to
    # GitHub's month labels.
    weekdays_marker = '<g font-family="Consolas,monospace" font-size="10"'
    months_start = re.search(r'<text x="92" y="91"[^>]*>.*?</text>', src)
    if not months_start:
        raise ValueError("Could not find month labels")
    weekdays_idx = src.find(weekdays_marker, months_start.start())
    if weekdays_idx < 0:
        raise ValueError("Weekday labels not found")
    src = src[:months_start.start()] + "".join(months) + "\n" + src[weekdays_idx:]

    grid_begin = src.find('<rect x="92" y="109" width="13.5"')
    if grid_begin < 0:
        raise ValueError("Grid start not found")
    cow_begin = src.find('<g transform="translate(', grid_begin)
    fence_begin = src.find('<!-- Fence sections inside the contribution calendar', cow_begin)
    if cow_begin < 0 or fence_begin < 0:
        raise ValueError("Cow region delimiters not found")

    cow_region = src[cow_begin:fence_begin]
    cow_re = re.compile(
        r'<g transform="translate\([\d.]+,[\d.]+\)"><title>'
        r'\d{4}-\d{2}-\d{2}: \d+ contributions?</title>'
        r'<g class="cow-(?:idle|lift)">.*?</g></g>', re.S
    )
    old_cows = cow_re.findall(cow_region)
    if len(old_cows) < 4:
        raise ValueError("Missing original cow illustrations")

    source_idle = next((v for v in old_cows if 'class="cow-idle"' in v), None)
    source_lift = next((v for v in old_cows if 'class="cow-lift"' in v), None)
    if not source_idle or not source_lift:
        raise ValueError("Cannot recover both grazing and abducted cow templates")
    lift_day = max(activity_in_grid, key=lambda day: (activity_in_grid[day], day))

    cows = []
    for day, count in sorted(activity_in_grid.items()):
        week = (day - start_sunday).days // 7
        weekday = (day.weekday() + 1) % 7
        cx, cy = 92.5 + 17.5 * week, 110 + 19 * weekday
        base = source_lift if day == lift_day else source_idle
        base = re.sub(r'^<g transform="translate\([\d.]+,[\d.]+\)">',
                      f'<g transform="translate({cx:.1f},{cy:.1f})">', base)
        base = re.sub(r'<title>\d{4}-\d{2}-\d{2}: \d+ contributions?</title>',
                      f'<title>{day.isoformat()}: {count} '
                      f'{"contribution" if count == 1 else "contributions"}</title>', base)
        cows.append(base)
    # Draw edible grass at the mouth of each grazing cow, using exactly
    # the same tile coordinates that positioned the cow itself. Keep an
    # external transform container so CSS swaying never overrides translate.
    # The abducted cow does not graze.
    grass_color = "#547C51" if light else "#86AC72"
    grass = []
    for day, count in sorted(activity_in_grid.items()):
        if day == lift_day:
            continue
        week = (day - start_sunday).days // 7
        weekday = (day.weekday() + 1) % 7
        cx, cy = 92.5 + 17.5 * week, 110 + 19 * weekday
        grass.append(
            f'<g data-cow-day="{day.isoformat()}" '
            f'transform="translate({cx:.1f} {cy:.1f})">'
            f'<g class="grass-sway" fill="none" stroke="{grass_color}" '
            f'stroke-width="1.45" stroke-linecap="round" opacity=".95">'
            '<path d="M14 11l-2-6m2 6 3-8M16 11l4-5"/>'
            '</g></g>'
        )
    src = (src[:grid_begin] + "".join(cells) + "\n"
           + "\n".join(cows) + "\n"
           + "<!-- Grazing grass tied to exact contribution cow locations -->\n"
           + "\n".join(grass) + "\n" + src[fence_begin:])

    # Old snapshots hardcoded grass at fixed right-side positions. Remove
    # that obsolete layer; otherwise it drifts away from the moving cow grid.
    src, old_grass_removed = re.subn(
        r'<g class="grass-sway" fill="none" stroke="[^"]+" '
        r'stroke-width="1\.1" opacity="\.85">.*?</g>\s*'
        r'(?=<!-- Two chickens)',
        "", src, count=1, flags=re.S,
    )

    src = align_ufos(src, activity_in_grid, start_sunday)

    # Use exact live counts across header, legend and accessible description.
    src, n1 = re.subn(r'\d+ CONTRIBUTIONS / \d+ DAYS',
                      f'{total} CONTRIBUTIONS / {count_days} DAYS', src, count=1)
    src, n2 = re.subn(r'SNAPSHOT : \d{4}-\d{2}-\d{2}',
                      f'SNAPSHOT : {TODAY}', src, count=1)
    legend = " / ".join(str(n) for n in list(dict(sorted(counts.items())).values())[:13])
    if count_days > 13:
        legend += f" / +{count_days - 13} OTHER DAYS"
    src, n3 = re.subn(r'COWS = ACTIVE DAYS \| [^<]*? CONTRIBUTIONS',
                      f'COWS = ACTIVE DAYS | {legend} CONTRIBUTIONS', src, count=1)
    src, n4 = re.subn(r'<desc id="farmdesc">.*?</desc>',
        f'<desc id="farmdesc">Retro animated farm representing {total} public GitHub '
        f'contributions across {count_days} active days as of {TODAY}. '
        f'Each cow marks one actual active calendar day. The three animated UFOs, '
        f'chickens, sheep, rabbit, farmhouse, trees and fences are decorative. '
        f'This is a dated snapshot, not a live calendar.</desc>', src, count=1, flags=re.S)
    if min(n1,n2,n3,n4) != 1:
        raise ValueError(f"Missing header, legend, snapshot or description in {name}")

    ElementTree.fromstring(src)
    actual = re.findall(r'<title>\d{4}-\d{2}-\d{2}: (\d+) contributions?</title>', src)
    if len(actual) != count_days or sum(map(int, actual)) != total:
        raise ValueError("Cow date/count validation failed")
    for marker in ['class="ufo-a"', 'class="ufo-b"', 'class="ufo-c"',
                   'class="chicken-peck"', 'class="sheep-walk"',
                   'class="rabbit-hop"', 'prefers-reduced-motion']:
        if marker not in src:
            raise ValueError(f"Existing farm feature was lost: {marker}")
    if src != path.read_text(encoding="utf-8"):
        path.write_text(src, encoding="utf-8")
        print(f"Updated {name}")


def update_readme(counts: dict[date, int]) -> None:
    path = ROOT / "README.md"
    s = path.read_text(encoding="utf-8")
    total, days = sum(counts.values()), len(counts)
    full_date = f"{TODAY:%B} {TODAY.day}, {TODAY.year}"
    sentence = f"**{total} contributions across {days} days**, based on my public contribution calendar on **{full_date}**."
    s, n = re.subn(
        r'\*\*\d+ contributions across (?:\w+|\d+) days\*\*, based on my public contribution calendar on \*\*[A-Za-z]+ \d+, \d{4}\*\*\.',
        sentence, s, count=1,
    )
    if n != 1:
        raise ValueError("README farm statement changed unexpectedly")
    s, n = re.subn(
        r'(?<=Animated retro GitHub contribution farm: )'
        r'(?:\w+|\d+) cows mark actual contribution days',
        f'{days} cows mark actual contribution days',
        s, count=1,
    )
    if n != 1:
        raise ValueError("README farm image description changed unexpectedly")
    if s != path.read_text(encoding="utf-8"):
        path.write_text(s, encoding="utf-8")
        print("Updated README farm summary")


if __name__ == "__main__":
    counts = activity()
    for theme in ("contribution-farm.svg", "contribution-farm-light.svg"):
        one_farm(theme, counts)
    update_readme(counts)
