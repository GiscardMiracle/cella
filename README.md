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
- **Smart reminders** — a DM every month, switching to every two weeks once the deadline is within reach, so you never miss the window
- **Auto-lock at deadline** — opportunities close themselves, no manual cleanup
- **Urgency at a glance** — the opportunity's embed shifts 🟢 → 🟠 → 🔴 as the deadline approaches

## Tech stack

- Python 3.12+ / [discord.py](https://discordpy.readthedocs.io/) (slash commands, modals, raw gateway events)
- SQLite for storage — no external database to run
- `systemd` for process management in production

## Architecture

```
bot/
├── main.py            # entry point
├── config.py           # env-based configuration
├── database/           # models, schema, CRUD
├── cogs/                # slash commands, reaction listener, daily scheduler
├── ui/                  # the opportunity creation modal
├── services/            # orchestration: opportunity lifecycle, reminder logic
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

## Author

Built by Giscard Adjanon.
