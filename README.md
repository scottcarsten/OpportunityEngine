# OpportunityEngine

> AI-assisted opportunity discovery, qualification, and application preparation platform.

---

## Vision

OpportunityEngine is designed to continuously discover **high-quality remote IT opportunities** while eliminating the noise of traditional job searching.

Its purpose is **not** to autonomously apply for jobs.

Its purpose is to act as an intelligent research assistant that:

- Discovers opportunities
- Scores them against a master résumé
- Generates tailored application documents
- Presents only high-confidence matches
- Keeps the human in complete control

---

## Primary Goal

Generate an additional **$3,000+/month** through:

- Remote contract work
- Part-time work
- After-hours consulting
- Fixed-price infrastructure projects
- MSP overflow work
- Microsoft 365 migrations
- Windows Server administration
- Active Directory consulting
- Azure / AWS infrastructure
- PowerShell automation

---

## Core Principles

- Human remains in control
- Never automatically apply
- Never impersonate the user
- Never send email without explicit approval
- Never modify the master résumé
- Generate a new résumé for every application
- Quality over quantity
- Eliminate opportunity noise

---

# Repository Structure

```
OpportunityEngine/

README.md
LICENSE
.gitignore
alembic.ini
pyproject.toml
requirements.txt

backend/        # FastAPI app: routes, services, adapters, AI providers
config/         # constitution.json (policy) + profile.json (your identity data, gitignored)
database/       # schema.sql (reference) + migrations/ (applied Alembic schema)
docs/           # VISION.md, ARCHITECTURE.md, DECISIONS.md (ADR log), ROADMAP.md
templates/      # server-rendered Jinja2 + Bootstrap pages
tests/
.github/        # GitHub Actions CI (backend-ci.yml)
```

`docker/`, a separate `frontend/`, and multi-user support remain
possible future directions (see `docs/ROADMAP.md`'s stretch goals) but
don't exist yet — this app is a single-user, server-rendered monolith
today.

---

# Technology Stack

- Linux Mint (development and target deployment platform)
- Python, FastAPI, Uvicorn
- SQLAlchemy + Alembic migrations, SQLite
- Claude API (Anthropic), model `claude-opus-5` — scoring and document generation
- `python-docx` + `reportlab` — DOCX/PDF export
- Jinja2 + Bootstrap (server-rendered, no separate frontend)
- Pytest + GitHub Actions CI

---

# Roadmap and Decisions

`docs/ROADMAP.md` is the authoritative, up-to-date milestone tracker —
this README's Status section below is a summary of it, not a
replacement. Every non-trivial design decision (and why it was made) is
recorded in `docs/DECISIONS.md`'s ADR log.

---

## Status

✅ **v0.1 MVP complete** · ✅ **v0.2 application preparation complete**

Working today:

- Localhost-only FastAPI application
- SQLAlchemy models and Alembic-managed database migrations, with SQLite
  constitutional safeguards enforced as triggers
- Manual opportunity entry
- Automated collection from four approved sources — We Work Remotely,
  Himalayas, Remotive, and Jobspresso — via `python -m backend.cli
  collect <source>`, each relevance-filtered to IT/infrastructure roles
  at collection time and sharing the same normalization and hard-filter
  path as manual entry
- Deterministic exact-fingerprint deduplication, plus similarity-based
  likely-duplicate detection
- An explicit, audited manual override of a hard-filter eligibility
  decision (never touches the original filter history)
- Explainable, advisory fit scoring via the Claude API (Opus 5) for
  opportunities that already passed hard filters — never authorizes any
  action, and never changes an opportunity's eligibility
- A review inbox: shortlist/reject/defer/request-preparation decisions
  (always audited), internal notifications for anything needing review,
  and the opportunity's source shown alongside its filters, score, and
  full decision history
- Importing and versioning a master résumé as permanent, read-only source
  material (`/resume`) — a correction is always a new version; nothing
  can edit or delete one once imported
- Generating a tailored résumé, cover letter, and fit report per
  opportunity via Claude Opus 5 — grounded only in the current master
  résumé, with any unsupported claim flagged for review; all three are
  only available once you've made a "Request preparation" review
  decision on that opportunity (the fit report also needs a completed
  score first). The tailored résumé renders into a real, ATS-conscious
  template (`/config/profile.json` holds your static identity/education/
  certifications — the AI never touches it) with the AI judging which
  roles from your full work history earn full detail versus a compressed
  one-line entry, targeting a two-page result. The cover letter renders
  into a plain business-letter structure (sender block, date, recipient,
  salutation, closing all templated — the AI only drafts the body
  paragraphs), deliberately kept simple for ATS safety
- Approving or rejecting a generated document — permanent once decided;
  a flagged document can still be approved, since flagging is meant to
  surface a judgment call for you, not block one
- Exporting any generated document as DOCX or PDF, regardless of its
  approval status, with real formatting (headings, bold) instead of raw
  Markdown characters
- Automated test suite and GitHub Actions CI

Not implemented yet:

- Applications, email, or any external action

---

## Run locally

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
cp config/profile.json.example config/profile.json  # then fill in your real identity data
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in a browser.

Scoring an opportunity calls the Claude API and needs an API key from
[console.anthropic.com](https://console.anthropic.com) — separate from a
claude.ai Pro/Max subscription, billed pay-as-you-go. Set
`ANTHROPIC_API_KEY` in `.env`; everything else works without it.

Run the tests with:

```bash
pytest
```

The v0.1 configuration rejects non-loopback bind addresses. OpportunityEngine
must not be exposed to a LAN or the public internet until authentication and
deployment controls are explicitly designed and approved.
