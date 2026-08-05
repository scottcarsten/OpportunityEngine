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
- OpenAI API
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

🚧 **v0.1 development**

Working today:

- Localhost-only FastAPI application
- SQLAlchemy models and Alembic-managed database migrations, with SQLite
  constitutional safeguards enforced as triggers
- Manual opportunity entry
- Deterministic deduplication and hard-filter evaluation
- Review inbox and detailed filter explanations
- Automated test suite and GitHub Actions CI

Not implemented yet:

- Automated opportunity collection
- AI scoring
- Résumé or cover-letter generation
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

Run the tests with:

```bash
pytest
```

The v0.1 configuration rejects non-loopback bind addresses. OpportunityEngine
must not be exposed to a LAN or the public internet until authentication and
deployment controls are explicitly designed and approved.
