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

# Planned Repository Structure

```
OpportunityEngine/

README.md
LICENSE
.gitignore
alembic.ini

docs/
architecture/
backend/
frontend/
config/
tests/
docker/
database/       # schema.sql (reference) + migrations/ (applied schema)
templates/

requirements.txt
docker-compose.yml
pyproject.toml
```

---

# Planned Technology Stack

- Linux Mint
- Python
- FastAPI
- SQLite
- Docker
- SQLAlchemy
- Bootstrap
- Claude API (Anthropic)
- python-docx
- Jinja2
- Nginx

---

# Development Phases

## Phase 1

- Project Skeleton
- Documentation
- Constitution
- SQLite
- Search Engine

## Phase 2

- Opportunity Collection
- Deduplication
- Filtering
- AI Scoring

## Phase 3

- Résumé Generation
- Cover Letter Generation
- Proposal Generation

## Phase 4

- Dashboard
- Notifications
- Review Workflow

## Phase 5

- Portfolio-quality polishing
- Plugin architecture
- Multi-user support

---

## Status

✅ **v0.1 MVP complete** · 🚧 **v0.2 in progress**

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
- Generating a tailored résumé draft per opportunity via Claude Opus 5,
  grounded only in the current master résumé, with any unsupported claim
  in the draft flagged for review — only available once you've made a
  "Request preparation" review decision on that opportunity
- Automated test suite and GitHub Actions CI

Not implemented yet:

- Cover-letter/fit-report generation, document approval states, and
  DOCX/PDF export
- Applications, email, or any external action

---

## Run locally

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
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
