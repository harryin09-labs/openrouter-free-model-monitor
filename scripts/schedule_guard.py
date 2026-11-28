"""GitHub-only daily schedule guard and timing diagnostics.

A receipt is written only after the scheduled monitor finishes successfully.
Manual workflow_dispatch runs are deliberately not deduplicated.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT / "data" / "schedule_receipts.json"
TZ = ZoneInfo("Asia/Kolkata")
START = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "free_model_schedule_start.json"


def load_receipts():
    if not RECEIPTS.exists():
        return {"days": {}}
    data = json.loads(RECEIPTS.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
        raise ValueError("Invalid receipts file; cannot safely decide whether to send")
    return data


def scheduled_time(now, cron):
    """Expected UTC time for latest occurrence of a fixed daily cron."""
    bits = cron.split()
    if len(bits) != 5 or bits[2:] != ["*", "*", "*"]:
        raise ValueError("Unsupported cron; refusing incorrect delay metrics")
    minute, hour = int(bits[0]), int(bits[1])
    if not (0 <= minute <= 59 and 0 <= hour <= 23):
        raise ValueError("Invalid schedule time")
    planned = now.astimezone(timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if planned > now:
        planned -= timedelta(days=1)
    return planned


def write_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")
    print(f"{name}={value}")


def summary(line):
    print(line)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as output:
            output.write(line + "\n")


def check():
    event = os.getenv("GITHUB_EVENT_NAME", "")
    if event != "schedule":
        write_output("run_monitor", "true")
        summary("Manual run: daily receipt guard bypassed.")
        return
    today = datetime.now(TZ).date().isoformat()
    receipt = load_receipts()["days"].get(today)
    if receipt is not None:
        write_output("run_monitor", "false")
        summary(f"Scheduled backup skipped: daily report already completed for {today} IST.")
    else:
        now = datetime.now(timezone.utc)
        cron = os.environ.get("SCHEDULED_CRON", "").strip()
        expected = scheduled_time(now, cron)
        START.write_text(json.dumps({"actual_started_at_utc": now.isoformat(),
                                     "expected_at_utc": expected.isoformat()}), encoding="utf-8")
        write_output("run_monitor", "true")
        delay = max(0, round((now - expected).total_seconds() / 60, 1))
        summary(f"Scheduled run started for {today} IST. Expected {expected.isoformat()}, "
                f"observed {now.isoformat()}, GitHub scheduling delay ~{delay} minutes.")


def mark():
    if os.getenv("GITHUB_EVENT_NAME") != "schedule":
        summary("Manual run: no automatic daily receipt written.")
        return
    now = datetime.now(timezone.utc)
    today = now.astimezone(TZ).date().isoformat()
    cron = os.environ.get("SCHEDULED_CRON", "").strip()
    expected = scheduled_time(now, cron)
    if START.exists():
        start_data = json.loads(START.read_text(encoding="utf-8"))
        started = datetime.fromisoformat(start_data["actual_started_at_utc"])
    else:
        started = now
    delay = max(0, round((started - expected).total_seconds() / 60, 1))
    completion_lag = max(0, round((now - expected).total_seconds() / 60, 1))
    state = load_receipts()
    days = state["days"]
    if today in days:
        raise RuntimeError("Daily receipt appeared during execution; refusing to overwrite")
    days[today] = {
        "date_ist": today,
        "expected_at_utc": expected.isoformat(),
        "started_at_utc": started.isoformat(),
        "completed_at_utc": now.isoformat(),
        "delay_minutes_to_start": delay,
        "delay_minutes_to_completion": completion_lag,
        "trigger_cron": cron,
        "github_run_id": os.getenv("GITHUB_RUN_ID", ""),
        "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
        "telegram_report": "monitor-step-succeeded"
    }
    state["days"] = dict(sorted(days.items())[-45:])
    RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
    temp = RECEIPTS.with_suffix(".json.tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temp.replace(RECEIPTS)
    summary(f"Daily completion recorded: {today} IST; expected {expected.isoformat()}, "
            f"started {started.isoformat()}, completed {now.isoformat()}, "
            f"start delay ~{delay} minutes, completion lag ~{completion_lag} minutes.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"check", "mark"}:
        raise SystemExit("Usage: python scripts/schedule_guard.py check|mark")
    {"check": check, "mark": mark}[sys.argv[1]]()
