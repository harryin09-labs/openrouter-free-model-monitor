#!/usr/bin/env python3
"""Track free OpenRouter models through the public model catalog API."""
import argparse
import html
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API = "https://openrouter.ai/api/v1/models"
CATALOG = "https://openrouter.ai/models?q=free"
ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "data/free_models.json"
HIST = ROOT / "data/history.json"

def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json", "User-Agent": "openrouter-free-model-monitor/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=data, headers=headers), timeout=40) as response:
                obj = json.load(response)
            if not isinstance(obj, dict):
                raise ValueError("Expected JSON object")
            return obj
        except (HTTPError, URLError, TimeoutError) as exc:
            status = getattr(exc, "code", None)
            if attempt == 2 or status not in (None, 429, 500, 502, 503, 504):
                raise RuntimeError("API request failed: " + type(exc).__name__) from exc
            time.sleep(2 ** attempt)
    raise RuntimeError("Request failed")

def is_zero(value):
    if value is None or isinstance(value, bool):
        return False
    try:
        return float(str(value).strip()) == 0.0
    except (ValueError, TypeError):
        return False

def parse_model(row):
    if not isinstance(row, dict):
        return None
    mid, price = row.get("id"), row.get("pricing")
    if not isinstance(mid, str) or not mid.strip() or not isinstance(price, dict):
        return None
    if not (is_zero(price.get("prompt")) and is_zero(price.get("completion"))):
        return None
    for k, v in price.items():
        if k not in ("prompt", "completion") and v is not None and not is_zero(v):
            return None
    mid = mid.strip()
    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        name = mid
    context = row.get("context_length")
    return {"id": mid, "name": name.strip(),
            "kind": "free_variant" if mid.endswith(":free") else "other_zero_price",
            "context_length": context if type(context) is int and context >= 0 else None,
            "url": "https://openrouter.ai/" + mid}

def parse_catalog(payload):
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Model API returned no rows")
    models = {}
    for row in rows:
        model = parse_model(row)
        if model:
            models[model["id"]] = model
    if not models:
        raise ValueError("No free models found: previous snapshot preserved")
    return [models[mid] for mid in sorted(models)]

def load(path, default):
    if not path.exists():
        return default
    obj = json.loads(path.read_text(encoding="utf8"))
    return obj

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    temp.replace(path)

def diff(before, after):
    old, new = {m["id"]: m for m in before}, {m["id"]: m for m in after}
    added = [new[x] for x in sorted(new.keys() - old.keys())]
    removed = [old[x] for x in sorted(old.keys() - new.keys())]
    changed = [new[x] for x in sorted(old.keys() & new.keys()) if
               any(old[x].get(k) != new[x].get(k) for k in ("name", "kind", "context_length"))]
    return added, removed, changed

def format_models(models, limit=18):
    items = ["• " + html.escape(m["name"]) + "\n  <code>" + html.escape(m["id"]) + "</code>" for m in models[:limit]]
    if len(models) > limit:
        items.append("…and " + str(len(models) - limit) + " more in repository")
    return "\n".join(items)

def footer():
    return '\n\n<a href="https://github.com/harryin09-labs/openrouter-free-model-monitor">GitHub monitor</a> | <a href="' + CATALOG + '">OpenRouter free models</a>'

def daily_message(now, models, added, removed, changed, baseline):
    variants = sum(m["kind"] == "free_variant" for m in models)
    lines = ["🤖 <b>OPENROUTER FREE MODEL MONITOR</b>", "📅 " + now.strftime("%d %B %Y"),
             "", "📦 Total zero-price models: <b>" + str(len(models)) + "</b>",
             "🆓 :free variants: <b>" + str(variants) + "</b>",
             "💠 Other zero-price: <b>" + str(len(models) - variants) + "</b>",
             "🟢 Added: <b>" + str(len(added)) + "</b> | 🔴 Removed: <b>" + str(len(removed)) +
             "</b> | 🔄 Changed: <b>" + str(len(changed)) + "</b>"]
    if baseline:
        lines.append("✅ Initial baseline created; existing models are not classified as new.")
    if added:
        lines.extend(["", "🟢 <b>NEW FREE MODELS</b>", format_models(added)])
    if removed:
        lines.extend(["", "🔴 <b>REMOVED OR NO LONGER FREE</b>", format_models(removed)])
    if changed:
        lines.extend(["", "🔄 <b>DETAILS CHANGED</b>", format_models(changed)])
    if not (added or removed or changed or baseline):
        lines.append("✅ No changes detected.")
    lines.append("ℹ️ Zero-price does not guarantee unrestricted account access.")
    return "\n".join(lines) + footer()

def weekly_message(now, models, hist):
    start = (now.date() - timedelta(days=6)).isoformat()
    recent = [r for r in hist if start <= r.get("date", "") <= now.date().isoformat()]
    def unique(key):
        return len({mid for r in recent for mid in r.get(key, [])})
    return ("📅 <b>OPENROUTER WEEKLY SUMMARY</b>\n" + now.strftime("%d %B %Y") +
            "\n📦 Current zero-price models: <b>" + str(len(models)) + "</b>" +
            "\n🟢 Added: " + str(unique("added")) + "\n🔴 Removed: " +
            str(unique("removed")) + "\n🔄 Changed: " + str(unique("changed")) + footer())

def send(message, dry_run=False):
    if dry_run:
        print("TELEGRAM DRY RUN:\n" + message)
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID GitHub Actions secrets")
    if len(message) > 3900:
        # Keep valid HTML tags by dropping complete model entries from the end of the message.
        message = message[:2500].rsplit("\n", 1)[0]
        # Conservatively strip HTML tags from a truncated message.
        import re
        message = re.sub(r"<[^>]*>", "", html.unescape(message)) + "\n…truncated; see GitHub."
        message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    result = request_json("https://api.telegram.org/bot" + token + "/sendMessage",
                          {"chat_id": chat, "text": message, "parse_mode": "HTML",
                           "disable_web_page_preview": True})
    if not result.get("ok"):
        raise RuntimeError("Telegram returned ok=false")
    print("Telegram notification sent")

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--force-notify", action="store_true")
    p.add_argument("--weekly", choices=("auto", "yes", "no"), default="auto")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-removal-percent", type=float, default=60.0)
    args = p.parse_args(argv)
    now = datetime.now(ZoneInfo(os.getenv("REPORT_TIMEZONE", "Asia/Kolkata")))
    current = parse_catalog(request_json(API))
    old_doc = load(SNAP, {"models": []})
    hist_doc = load(HIST, {"runs": []})
    if not isinstance(old_doc, dict) or not isinstance(old_doc.get("models"), list):
        raise ValueError("Invalid stored snapshot")
    if not isinstance(hist_doc, dict) or not isinstance(hist_doc.get("runs"), list):
        raise ValueError("Invalid stored history")
    old, history = old_doc["models"], hist_doc["runs"]
    if any(not isinstance(x, dict) or not isinstance(x.get("id"), str) for x in old):
        raise ValueError("Invalid stored model entry")
    if len({x["id"] for x in old}) != len(old):
        raise ValueError("Duplicate prior model IDs")
    baseline = not old
    added, removed, changed = ([], [], []) if baseline else diff(old, current)
    if old and len(removed) * 100 / len(old) > args.max_removal_percent:
        raise RuntimeError("Suspicious mass removal: snapshot preserved")
    today = now.date().isoformat()
    entry = {"date": today, "count": len(current), "added": [m["id"] for m in added],
             "removed": [m["id"] for m in removed], "changed": [m["id"] for m in changed]}
    for previous in history:
        if previous.get("date") == today:
            for key in ("added", "removed", "changed"):
                entry[key] = sorted(set(entry[key]) | set(previous.get(key, [])))
    history = sorted([x for x in history if x.get("date") != today] + [entry],
                     key=lambda x: x["date"])[-370:]
    weekly = args.weekly == "yes" or (args.weekly == "auto" and now.weekday() == 6 and
                                      os.getenv("ENABLE_WEEKLY_SUMMARY", "true").lower() == "true")
    if baseline or args.force_notify or added or removed or changed:
        send(daily_message(now, current, added, removed, changed, baseline), args.dry_run)
    if weekly:
        send(weekly_message(now, current, history), args.dry_run)
    if not args.dry_run:
        save(SNAP, {"updated_at": now.isoformat(), "source": API, "models": current})
        save(HIST, {"runs": history})
    print(json.dumps({"count": len(current), "added": len(added),
                      "removed": len(removed), "changed": len(changed),
                      "baseline": baseline, "dry_run": args.dry_run}))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
