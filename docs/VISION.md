# OpportunityEngine Vision

## Find opportunities, not jobs

OpportunityEngine is an AI-assisted research and preparation system built to help Scott discover, qualify, and prepare for remote contract, consulting, project-based, after-hours, and part-time IT opportunities.

Its financial objective is to help generate at least **$3,000 per month** in additional income from infrastructure, systems administration, security, cloud, and related consulting work without replacing Scott's primary full-time employment.

## Human-controlled automation

OpportunityEngine may collect, normalize, deduplicate, filter, score, summarize, and prepare opportunity materials. It is an assistant—not an autonomous applicant or a substitute for Scott's identity or judgment.

Scott remains the final decision-maker. The system must never:

- Automatically submit an application.
- Send an email or external message without explicit approval.
- Impersonate Scott.
- modify the master résumé.
- Enter into a contract or financial commitment.
- Complete identity verification on Scott's behalf.

For each approved opportunity, the system may generate a new, tailored résumé, cover letter, and fit report while preserving the master résumé as read-only source material.

## Opportunity constraints

The engine prioritizes work that is:

- Remote.
- Contract, consulting, or project-based.
- Compatible with after-hours or part-time availability.
- Relevant to Scott's IT infrastructure, systems administration, cloud, and security experience.

The engine rejects opportunities that require:

- Travel.
- Relocation.
- An existing security clearance.
- Replacing Scott's full-time employment.

## Intended workflow

1. Collect opportunities.
2. Normalize and deduplicate them.
3. Apply hard filters.
4. Score and explain fit using AI.
5. Prepare a tailored résumé, cover letter, and fit report.
6. Notify Scott.
7. Wait for explicit human approval before any external action.

## Planned platform

The planned platform uses Linux Mint, Python, FastAPI, SQLAlchemy, SQLite with a possible PostgreSQL migration, Docker, Bootstrap, Jinja2, OpenAI API, python-docx, Nginx, and cron or systemd scheduling.

The project's authoritative behavioral and safety rules are defined in `config/constitution.json`.
