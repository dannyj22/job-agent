# Job Agent

Scrapes web-development jobs from several boards, filters them against your
keywords, removes duplicates, and pushes **only new matching jobs** to a Discord
webhook. Runs on a schedule with `cron`.

Built for roles around **React, Next.js, Node.js, JavaScript/TypeScript, REST
APIs, full stack, HTML/CSS and databases** — with adjacent tech (Python, PHP,
DevOps, mobile, data/AI, QA) also accepted and neatly categorised.

---

## How it works

```
sources/*  ->  filters.py  ->  storage.py (SQLite dedupe)  ->  notifier.py (Discord)
```

1. **Sources** fetch raw jobs (official APIs, RSS, public job pages).
2. **Filter** scores each job by weighted keywords and assigns a category
   (`frontend`, `backend`, `fullstack`, `api`, `database`, `devops`, `mobile`,
   `data_ai`, `qa`, `other`).
3. **Storage** keeps every accepted job in SQLite so the same job is never
   alerted twice.
4. **Notifier** sends rich Discord embeds grouped 10 per message.

---

## Quick start

```bash
cd ~/job-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your DISCORD_WEBHOOK_URL
```

Create the webhook in Discord: **Server Settings → Integrations → Webhooks →
New Webhook → Copy Webhook URL**.

Verify everything:

```bash
.venv/bin/python -m jobagent doctor
.venv/bin/python -m jobagent sources
.venv/bin/python -m jobagent test-notify
```

Run it:

```bash
# fetch + send new matches to Discord
.venv/bin/python -m jobagent run

# preview without sending anything
.venv/bin/python -m jobagent run --dry-run

# store only, no notification
.venv/bin/python -m jobagent run --no-notify

# database stats
.venv/bin/python -m jobagent stats
```

---

## Schedule it (cron)

```bash
chmod +x scripts/*.sh
./scripts/install-cron.sh
```

Installs:

```
0 */3 * * * cd ~/job-agent && .venv/bin/python -m jobagent run >> logs/cron.log 2>&1
```

Change the schedule by passing a cron expression:

```bash
./scripts/install-cron.sh "30 8 * * *"     # every day at 08:30
./scripts/install-cron.sh "0 * * * *"      # hourly
```

> Cron only runs while the computer is on. For always-on alerts, move the same
> command to a small VPS or a GitHub Actions scheduled workflow.

---

## Tuning the results

Everything lives in [`config.yaml`](config.yaml):

| Setting | What it does |
| --- | --- |
| `filters.min_score` | Higher = fewer, more relevant jobs. Start at 4. |
| `filters.include_keywords.core` | Strong matches (React, Node, SQL…). Weight 4. |
| `filters.include_keywords.adjacent` | Nice-to-have tech. Weight 2. |
| `filters.include_keywords.general` | Generic dev words. Weight 1. |
| `filters.exclude_keywords` | Any match drops the job (sales, internship…). |
| `filters.locations` | Keep only these locations; empty = accept all. Remote always passes. |
| `sources.*.enabled` | Turn individual boards on/off. |
| `notify.discord.max_jobs_per_run` | Cap alerts per run. |

Each board's search queries (LinkedIn, Indeed, Adzuna) are also in
`config.yaml`.

---

## Sources

| Source | Type | Notes |
| --- | --- | --- |
| RemoteOK | JSON API | Reliable. |
| Remotive | JSON API | Reliable. |
| Jobicy | JSON API | Reliable. |
| Arbeitnow | JSON API | Reliable, EU-heavy. |
| We Work Remotely | RSS | Reliable. |
| Hacker News "Who is hiring?" | Algolia API | Monthly thread, noisy but high quality. |
| LinkedIn | Public guest HTML | Works today; **fragile** and subject to LinkedIn's ToS. Low volume only. |
| Indeed | HTML/RSS | **Usually blocked by a captcha (403).** Auto-skips without breaking the run. |
| Adzuna | Official API | Disabled by default. Free key gives Indeed-like coverage. |

### About Indeed

Indeed removed its public RSS feed and serves captchas to most servers. The
adapter tries anyway and logs a warning when blocked. Options:

- set `INDEED_PROXY` in `.env` to a residential/rotating proxy, or
- enable **Adzuna** (free key at <https://developer.adzuna.com/>) for very
  similar aggregated coverage.

```yaml
sources:
  adzuna:
    enabled: true
    country: us        # gb, de, fr, au, ca, in, ...
```

---

## Adding a new job board

Create `jobagent/sources/myboard.py`:

```python
from ..models import Job
from .base import JobSource

class MyBoardSource(JobSource):
    name = "myboard"

    def fetch(self) -> list[Job]:
        payload = self.get_json("https://example.com/api/jobs")
        return [
            Job(
                title=item["title"],
                company=item["company"],
                url=item["url"],
                source=self.name,
                location=item.get("location", ""),
                description=item.get("description", ""),
            )
            for item in payload
        ]
```

Then register it in `jobagent/sources/__init__.py` and add it to `config.yaml`.

---

## Project layout

```
job-agent/
├── config.yaml            # keywords, sources, filters
├── .env.example           # Discord webhook + optional API keys
├── requirements.txt
├── jobagent/
│   ├── cli.py             # run / test-notify / stats / sources / doctor
│   ├── config.py          # YAML + env loading
│   ├── models.py          # Job dataclass + fingerprint
│   ├── filters.py         # scoring + categories
│   ├── storage.py         # SQLite + dedupe
│   ├── notifier.py        # Discord embeds
│   ├── pipeline.py        # fetch -> filter -> dedupe -> notify
│   └── sources/           # one file per job board
│       ├── base.py
│       ├── remoteok.py
│       ├── remotive.py
│       ├── jobicy.py
│       ├── arbeitnow.py
│       ├── weworkremotely.py
│       ├── hackernews.py
│       ├── linkedin.py
│       ├── indeed.py
│       └── adzuna.py
├── scripts/
│   ├── run.sh
│   └── install-cron.sh
└── tests/
```

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `DISCORD_WEBHOOK_URL is not set` | Copy `.env.example` to `.env` and paste the URL. |
| No jobs at all | Run `--dry-run -v` and check the source table. LinkedIn/Indeed may be rate-limiting. |
| Too many irrelevant jobs | Raise `min_score` to 6–8, or trim the `general` keywords. |
| Too few jobs | Lower `min_score`, add keywords, enable more sources. |
| Duplicate alerts | Shouldn't happen; dedupe is by title+company+URL. Use `stats` to inspect. |
| Cron not firing | `crontab -l` to confirm, and check `logs/cron.log`. |

Logs: `logs/jobagent.log` (rotated) and `logs/cron.log`.

---

## Legal / etiquette

- Respect each site's terms and rate limits; keep LinkedIn/Indeed volume low.
- RemoteOK and Jobicy ask that you credit them and link back to the original
  posting — the Discord embeds already do this via the source field and job URL.
- This tool is for personal job hunting, not for republishing listings.
