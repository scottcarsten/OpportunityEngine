# OpportunityEngine Roadmap

## Purpose

This roadmap turns OpportunityEngine into a series of small, complete, reviewable milestones. Each milestone must add something tangible, preserve Scott's control, and comply with `config/constitution.json`.

The roadmap is directional rather than a promise of autonomous execution. Any external action—applications, email, messages, contracts, identity verification, or financial commitments—always requires Scott's explicit approval.

## Current status

**Project phase:** v0.2 in progress  
**Completed:** all of v0.1 (design baseline through the review inbox), plus v0.2's master résumé import/versioning, tailored-résumé-generation, and cover-letter/fit-report-generation slices  
**In progress:** v0.2 (application preparation) — document versioning and approval states, and DOCX/PDF export remain  
**Next milestone:** add document versioning and approval states, or export DOCX/PDF artifacts (Issue #7)

## Definition of done

A milestone is complete when:

- Its acceptance criteria are satisfied.
- Relevant automated tests pass.
- Documentation reflects actual behavior.
- Decisions and tradeoffs are recorded.
- Audit-relevant behavior is observable.
- No constitutional rule is weakened.
- The repository contains a usable increment, not empty scaffolding.

## v0.1 — Local foundation and opportunity inbox

**Goal:** Run a local, single-user application on Linux Mint that can store, review, filter, and score opportunities without taking external action.

### Milestone 0 — Design baseline

- [x] Define the vision.
- [x] Establish the project constitution.
- [x] Create a GitHub issue backlog.
- [x] Define the initial architecture.
- [x] Record foundational architectural decisions.
- [x] Design the SQLite schema.
- [x] Review and approve the MVP backend scope and API contract (Issue #3).

### Milestone 1 — Backend foundation

- [x] Create the FastAPI application skeleton.
- [x] Add typed configuration and secret handling.
- [x] Add SQLAlchemy models and migrations based on `database/schema.sql`.
- [x] Add health and readiness endpoints.
- [x] Add structured logging and audit-event services.
- [x] Add unit and integration test infrastructure.

**Gate:** Scott approved Issue #3 before implementation began.

### Milestone 1A — Manual opportunity vertical slice

- [x] Add a server-rendered manual opportunity-entry form.
- [x] Normalize supplied listing data.
- [x] Detect exact duplicate entries with deterministic fingerprints.
- [x] Apply the constitutional hard filters.
- [x] Store the listing, source evidence, and filter evaluations in SQLite.
- [x] Display the review inbox and detailed filter explanations.
- [x] Test eligible, ineligible, unknown, and duplicate workflows.

Completed in Issue #10.

### Milestone 2 — Collection and normalization

- [x] Define the source-adapter interface.
- [x] Implement the first approved opportunity source.
- [x] Preserve source attribution and ingestion history.
- [x] Normalize incoming records into the canonical model.
- [x] Make repeated collection idempotent.

Completed: first source is We Work Remotely's DevOps and Sysadmin RSS feed
(`backend/adapters/we_work_remotely.py`), run via
`python -m backend.cli collect we_work_remotely`
(`OE-ADR-015`). Tracked by Issue #4.

A live collection run surfaced that normalization was leaving
travel/relocation/clearance/full-time-replacement unknown even when the
listing text answered them, forcing a manual review of every collected
listing. `backend/adapters/signal_extraction.py` now extracts those
signals deterministically — free-text pattern matching for the first
three, and a direct mapping from the RSS's already-structured `<type>`
field for full-time-replacement — while still defaulting to unknown
(manual review) whenever a listing doesn't clearly say. See `OE-ADR-021`.

Three more sources are live: Himalayas (`backend/adapters/himalayas.py`,
run via `python -m backend.cli collect himalayas`), Remotive
(`backend/adapters/remotive.py`, `collect remotive`), and Jobspresso
(`backend/adapters/jobspresso.py`, `collect jobspresso`). Unlike We Work
Remotely, each of these publishes every remote job across every
industry, not just DevOps/Sysadmin, so each adapter filters for relevance
at `fetch()` time using whatever signal that source actually offers
(Himalayas' own search query, Remotive's structured category tag, or a
keyword scan for Jobspresso). Himalayas is also the first source with
real structured compensation data. See `OE-ADR-022` for the full
per-source research and design rationale, including which of the 16
originally-requested sources were dropped and why.

### Milestone 3 — Deduplication and hard filters

- [x] Generate deterministic opportunity fingerprints.
- [x] Detect exact duplicates via deterministic fingerprints.
- [x] Detect likely duplicates via similarity review.
- [x] Enforce remote-only, no-travel, no-relocation, no-clearance, and no-full-time-replacement rules.
- [x] Store every filter decision and explanation.
- [x] Provide a manual override path that is explicit and audited.

Fingerprinting, exact-duplicate short-circuiting, hard-filter enforcement,
and filter-decision storage were delivered in Milestones 1A/2
(`OpportunityService._fingerprint`/`_evaluate_filters`, shared by manual
entry and collection). Likely-duplicate detection
(`OpportunityService._detect_likely_duplicates`, recorded as
`deduplication_decisions` rows) and the audited manual-override path
(`OpportunityService.override_lifecycle_status`, recorded as `audit_events`
rows) closed out the milestone (`OE-ADR-016`). Tracked by Issue #5.

### Milestone 4 — Explainable scoring

- [x] Define scoring dimensions and weights.
- [x] Score skills, work type, schedule, compensation, risk, and confidence.
- [x] Store model, prompt, and scoring-version metadata.
- [x] Produce plain-language fit and concern explanations.
- [x] Ensure a score never implies permission to act.

Scoring is powered by Claude Opus 5 (`backend/scoring/anthropic_provider.py`)
behind a `ScoringProvider` interface (`backend/scoring/base.py`), so no
domain code depends on a specific model. `ScoringService`
(`backend/services/scoring_service.py`) enforces "only score opportunities
that already passed hard filters" and never writes
`opportunities.lifecycle_status` — the score is structurally advisory only.
See `OE-ADR-017`. Tracked by Issue #6.

### Milestone 5 — Review inbox

- [x] List newly qualified opportunities.
- [x] Show source, filters, score components, fit, concerns, and history.
- [x] Allow Scott to shortlist, reject, defer, or request preparation.
- [x] Record every decision in the audit log.
- [x] Add internal notifications for items needing review.

Review decisions (`OpportunityService.record_review_decision`) move
`lifecycle_status` into the schema's own dedicated states
(`shortlisted`/`deferred`/`rejected`/`preparing`) and are always audited.
Internal notifications (`notifications` table) are created once, at ingest,
for anything landing in `eligible` or `new`; the dashboard shows a pending
count, and viewing an opportunity marks its notification sent. The detail
page now also shows its source (`sources`/`source_records`). See
`OE-ADR-018`. Tracked by Issue #8.

**v0.1 MVP outcome reached:** Scott can open a local dashboard, review normalized opportunities, understand why each passed or failed, and control every next step.

## v0.2 — Application preparation

**Goal:** Prepare high-quality, opportunity-specific materials while treating the master résumé as immutable source data.

- [x] Import and version a master résumé as read-only.
- [x] Generate a new tailored résumé per selected opportunity.
- [x] Generate cover-letter and fit-report drafts.
- [x] Compare generated claims against approved source material.
- [x] Flag unsupported or uncertain claims.
- [ ] Add document versioning and approval states.
- [ ] Export DOCX and PDF artifacts.

Master résumé import/versioning (`backend/services/resume_service.py`,
`/resume`) was v0.2's first slice. Content-hash-addressed storage means a
row's `storage_path` never depends on the untrusted uploaded filename;
"current" version is derived (`MAX(version) WHERE is_master=1`), not a
mutable flag, since the DB triggers make a row permanently immutable once
inserted. See `OE-ADR-019`.

Tailored résumé generation (`backend/services/document_service.py`,
`backend/documents/anthropic_provider.py`) is the second slice: Claude
Opus 5 drafts a résumé grounded only in the current master résumé and, in
the same call, flags any statement in its own draft that isn't directly
supported by it. Generation requires Scott's `request_preparation`
review decision first (`lifecycle_status == "preparing"`), not just an
eligible or scored opportunity. See `OE-ADR-020`.

Cover-letter and fit-report generation is the third slice, reusing that
same service and provider. A cover letter follows the same
draft-and-flag-unsupported-claims pattern as the résumé; a fit report is
different in kind — it synthesizes an opportunity's existing scoring run
(`OE-ADR-017`) into readable prose rather than producing a new judgment,
and requires a successful score to exist first. See `OE-ADR-023`.
Document versioning and approval states, and DOCX/PDF export, are the
remaining follow-on milestones. Tracked by Issue #7.

**v0.2 outcome:** Scott can approve or reject complete application packages, but the system still cannot submit them.

## v0.3 — Controlled workflow and notifications

**Goal:** Improve the review experience while keeping all external execution human-controlled.

- [ ] Add configurable internal notification channels.
- [ ] Add review queues and follow-up reminders.
- [ ] Add opportunity aging and stale-listing detection.
- [ ] Add reporting for pipeline volume, quality, and estimated value.
- [ ] Add explicit approval receipts for restricted actions.
- [ ] Design—but do not silently enable—external integrations.

## v0.4 — Quality, resilience, and deployment

- [ ] Containerize application services.
- [ ] Add backup, restore, and disaster-recovery procedures.
- [ ] Add PostgreSQL migration support if scale requires it.
- [ ] Add security hardening, dependency scanning, and secret scanning.
- [ ] Add performance and reliability tests.
- [ ] Produce Linux Mint and Docker deployment guides.

## Stretch goals

These are intentionally outside the MVP:

- Plugin-based source adapters.
- Local or hosted language-model options.
- Multiple résumé profiles.
- Client and consulting lead tracking.
- Revenue forecasting.
- Multi-user support with role-based access.
- Mobile-friendly review.
- Provider integrations approved individually by Scott.

## Explicit non-goals

OpportunityEngine will not:

- Automatically apply for work.
- Send email or external messages without approval.
- Impersonate Scott.
- Modify the master résumé.
- Complete identity verification.
- Accept contracts or make financial commitments.
- Replace Scott's full-time employment.
- Optimize for application volume over opportunity quality.

## Backlog map

- Issue #1 — Documentation baseline
- Issue #2 — SQLite persistence model
- Issue #3 — MVP backend scope and API contract
- Issue #4 — Collection and normalization
- Issue #5 — Deduplication and hard filters
- Issue #6 — Explainable scoring
- Issue #7 — Document preparation and approvals
- Issue #8 — Review dashboard and notifications
- Issue #9 — Backend foundation
- Issue #10 — Manual opportunity-entry vertical slice
