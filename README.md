# OpenRouter Free Model Monitor

Daily GitHub Actions monitor for OpenRouter's public model catalog: https://openrouter.ai/models?q=free

## Features
- Checks public `https://openrouter.ai/api/v1/models` at **09:00 IST** daily.
- Tracks models with explicitly zero prompt and completion prices (and no nonzero additional pricing).
- Distinguishes `:free` model variants from other zero-price models.
- Detects added, removed, renamed and changed free models.
- Sends Telegram on changes, plus optional Sunday weekly summary; manual forced reports available.
- Commits snapshots and up to 370 days of history automatically.
- Prevents empty listings and suspicious mass removals from overwriting the last good snapshot.
- **No OpenRouter API key or browser required.**

## Setup

In repository **Settings → Secrets and variables → Actions → Repository secrets**, add:
- `TELEGRAM_BOT_TOKEN` — from Telegram @BotFather
- `TELEGRAM_CHAT_ID` — your chat or group ID

Do not put tokens in committed files. In **Settings → Actions → General → Workflow permissions**, enable **Read and write permissions** to allow snapshot commits.

Then choose **Actions → OpenRouter Free Models Monitor → Run workflow**, optionally enabling `force_notify`. First run creates a baseline instead of treating all current models as newly added.

Schedule: `30 3 * * *` = 09:00 IST daily (GitHub schedules may run late).

Run locally: `python scripts/monitor.py --dry-run`. Tests: `python -m unittest discover -s tests -v`.

A zero-price entry is a catalog observation, not a guarantee of unrestricted access, uptime, rate limits or account eligibility.
