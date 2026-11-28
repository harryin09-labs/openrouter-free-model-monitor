"""Best-effort Telegram alert for a failed scheduled GitHub Actions job.

Uses existing GitHub Actions secrets. Never logs the bot token or chat ID.
"""
import json
import os
import sys
from urllib.request import Request, urlopen

token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
repo = os.getenv("GITHUB_REPOSITORY", "")
run_id = os.getenv("GITHUB_RUN_ID", "")
if not token or not chat_id:
    print("Failure alert unavailable: missing Telegram Actions secret(s).")
    raise SystemExit(0)
if not repo or not run_id:
    print("Failure alert unavailable: missing GitHub run metadata.")
    raise SystemExit(0)

link = f"https://github.com/{repo}/actions/runs/{run_id}"
text = ("⚠️ FREE MODEL MONITOR FAILURE\n"
        f"Repository: {repo}\n"
        "The scheduled monitor did not finish successfully.\n"
        f"Check logs: {link}")
try:
    req = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text,
                         "disable_web_page_preview": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=20) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError("Telegram API did not confirm delivery")
    print("Failure alert delivered to Telegram.")
except Exception:
    print("Unable to deliver failure alert; inspect Telegram configuration.")
    sys.exit(1)
