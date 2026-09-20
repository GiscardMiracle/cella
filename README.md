# Cella 🎓

A Discord bot that keeps a friend group's scholarship hunt organized. Post an opportunity, react to join, get quietly reminded until the deadline — no spreadsheet, no forgotten tabs.

![Python](https://img.shields.io/badge/python-3.12+-blue)
![discord.py](https://img.shields.io/badge/discord.py-2.4+-5865F2)
![License](https://img.shields.io/badge/license-MIT-green)

## Why

Scholarship opportunities move fast between friends: someone finds one, shares a link in a group chat, and three weeks later nobody remembers the deadline or who was even interested. Cella turns that chaos into structure — every opportunity gets its own tracked space, automatically.

## Features

- **`/opportunity-add`** — a proper form (name, description, link, deadline), no arguments to memorize
- **React to join** — reacting to an opportunity's post silently grants you a dedicated, private channel for that opportunity
- **`/opportunity-members`** — see who's in, at a glance
- **Smart reminders** — a DM every month, switching to every two weeks once the deadline is within reach, plus a final DM at 5 days and at 2 days before the deadline, so you never miss the window
- **Auto-close at deadline** — opportunities are marked closed on their own, no manual cleanup; the channel stays open so members can keep sharing news
- **Urgency at a glance** — the opportunity's embed shifts 🟢 → 🟠 → 🔴 as the deadline approaches
- **Auto-discovery** — periodically checks a watched listing page (e.g. the ministry's scholarship announcements) and posts new ones in `#opportunities` as soon as they appear, keeping a baseline state so it never floods the channel with what was already there
- **Auto-extracted info** — when an opportunity is created, its link is read (the page, plus the PDFs and "eligibility"-style pages it points to) and the key info — documents to provide, eligibility, deadline, benefits, how to apply — is posted as the dedicated channel's first message. With a free Gemini API key it reads any layout and even scanned PDFs; without one (or if the API is unavailable) it falls back to a keyword-based extractor, and says so clearly when nothing can be extracted
- **`/opportunity-backfill`** — for server managers: posts the extracted info in the channels of open opportunities that don't have it yet (created before the feature, or whose extraction failed). Quota-friendly: at most 10 extractions per run, paced, stopping at the first quota error, so it can safely be run again until everything is covered

## Tech stack

- Python 3.12+ / [discord.py](https://discordpy.readthedocs.io/) (slash commands, modals, raw gateway events)
- SQLite for storage — no external database to run
- `beautifulsoup4` / `pypdf` for scraping opportunity links and watched pages
- Optional [Gemini API](https://ai.google.dev/) free tier for AI extraction — no billing account, nothing to pay
- `systemd` for process management in production

## Architecture

```
bot/
├── main.py            # entry point
├── config.py           # env-based configuration
├── database/           # models, schema, CRUD
├── cogs/                # slash commands, reaction listener, daily scheduler, listing watcher
├── ui/                  # the opportunity creation modal
├── services/            # orchestration: opportunity lifecycle, reminder logic, scraping, watching
└── utils/                # Discord permissions & embed builders
```

Each layer only talks to the one below it — `services/` never touches Discord directly, `cogs/` never touches the database directly. Keeps things testable and easy to reason about as it grows.

## Getting started

```bash
git clone https://github.com/GiscardMiracle/cella.git
cd cella
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your bot's credentials
python3 -m bot.main
```

You'll need a Discord application with a bot user, the **Server Members** privileged intent enabled, and the bot invited with `Manage Roles`, `Manage Channels`, `Send Messages`, `Read Message History`, `Add Reactions`, and `Embed Links`.

Optional env vars:

- `WATCH_URL` — a listing page to poll for new announcements (omit to disable the watcher), and `WATCH_INTERVAL_HOURS` (default `6`).
- `GEMINI_API_KEY` — a free key from [Google AI Studio](https://aistudio.google.com/apikey) (no billing account needed) to enable AI extraction of opportunity info. Omit it and Cella uses its keyword extractor. The free tier allows a limited number of requests per model per day, so Cella tries several models in turn when one runs out; `GEMINI_MODEL` overrides that list (comma-separated, tried in order).

## Tests

```bash
python -m unittest discover -s tests
```

## Author

Built by Giscard Adjanon.
