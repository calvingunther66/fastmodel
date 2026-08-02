"""One-time migration: recompute Triage shift times on already-stored schedules.

Fixes data baked in *before* the weekly-hours-aware triage rule existed (see
`schedule_extractor.definitions.apply_triage_weekly_adjustment`): a Triage shift
that would push the person's Sunday-Saturday week over 40 worked hours now runs
07:30-16:00 (8h) instead of the standard 07:30-18:00 (10h). Re-parsing a fresh
upload already gets this for free; this script patches the schedule/archive JSON
that's already on disk so live `.ics` feeds pick it up without a re-upload.

Idempotent — safe to run more than once. Run inside the container after
`git pull && docker compose up -d --build`:

    docker compose exec schedule python tools/fix_triage_hours.py          # dry run
    docker compose exec schedule python tools/fix_triage_hours.py --apply  # write changes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schedule_extractor.definitions import apply_triage_weekly_adjustment  # noqa: E402


def _fix_file(path: Path, apply: bool) -> int:
    """Recompute triage windows in one schedule-shaped JSON file. Returns the
    number of triage shifts whose start/end changed."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  skip {path.name}: {exc}")
        return 0

    changed = 0
    for person in data.get("people", []):
        shifts = person.get("shifts", [])
        before = {
            id(s): (s.get("start"), s.get("end"), s.get("crosses_midnight"))
            for s in shifts if (s.get("code") or "").strip().upper() == "T"
        }
        apply_triage_weekly_adjustment(shifts)
        for s in shifts:
            key = id(s)
            if key not in before:
                continue
            after = (s.get("start"), s.get("end"), s.get("crosses_midnight"))
            if after != before[key]:
                changed += 1
                print(f"  {person.get('name')} {s.get('date')}: "
                      f"{before[key][0]}-{before[key][1]} -> {after[0]}-{after[1]}")

    if changed and apply:
        path.write_text(json.dumps(data, indent=2))
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None,
                        help="defaults to DATA_DIR / ./data, matching the running server")
    parser.add_argument("--apply", action="store_true",
                        help="write changes; without this it's a dry run")
    args = parser.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        from server.config import DATA_DIR
        data_dir = DATA_DIR

    targets = []
    schedule_path = data_dir / "schedule.json"
    if schedule_path.exists():
        targets.append(schedule_path)
    archive_dir = data_dir / "archive"
    if archive_dir.exists():
        targets.extend(sorted(archive_dir.glob("*.json")))

    if not targets:
        print(f"no schedule.json or archive found under {data_dir}")
        return

    total = 0
    for path in targets:
        print(f"{path.relative_to(data_dir)}:")
        n = _fix_file(path, args.apply)
        if n == 0:
            print("  no changes")
        total += n

    mode = "applied" if args.apply else "dry run — pass --apply to write"
    print(f"\n{total} triage shift(s) changed across {len(targets)} file(s) ({mode})")


if __name__ == "__main__":
    main()
