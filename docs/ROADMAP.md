# OpportunityEngine Roadmap

## Purpose

This roadmap turns OpportunityEngine into a series of small, complete, reviewable milestones. Each milestone must add something tangible, preserve Scott's control, and comply with `config/constitution.json`.

The roadmap is directional rather than a promise of autonomous execution. Any external action—applications, email, messages, contracts, identity verification, or financial commitments—always requires Scott's explicit approval.

## Current status

**Project phase:** v0.1 design baseline  
**Completed:** design baseline, backend foundation, and manual opportunity vertical slice  
**In progress:** v0.1 opportunity collection, filtering, scoring, and review workflow  
**Next milestone:** first approved source adapter and repeatable collection in Issue #4

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
- [ ] Review and approve the MVP backend scope and API contract (Issue #3).

### Milestone 1 — Backend foundation

- [x] Create the FastAPI application skeleton.
- [x] Add typed configuration and secret handling.
- [ ] Add SQLAlchemy models and migrations based on `database/schema.sql`.
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

- [ ] Define the source-adapter interface.
- [ ] Implement the first approved opportunity source.
- [ ] Preserve source attribution and ingestion history.
- [ ] Normalize incoming records into the canonical model.
- [ ] Make repeated collection idempotent.

Tracked by Issue #4.

### Milestone 3 — Deduplication and hard filters

- [ ] Generate deterministic opportunity fingerprints.
- [ ] Detect exact and likely duplicates.
- [ ] Enforce remote-only, no-travel, no-relocation, no-clearance, and no-full-time-replacement rules.
- [ ] Store every filter decision and explanation.
- [ ] Provide a manual override path that is explicit and audited.

Tracked by Issue #5.

### Milestone 4 — Explainable scoring

- [ ] Define scoring dimensions and weights.
- [ ] Score skills, work type, schedule, compensation, risk, and confidence.
- [ ] Store model, prompt, and scoring-version metadata.
- [ ] Produce plain-language fit and concern explanations.
- [ ] Ensure a score never implies permission to act.

Tracked by Issue #6.

### Milestone 5 — Review inbox

- [ ] List newly qualified opportunities.
- [ ] Show source, filters, score components, fit, concerns, and history.
- [ ] Allow Scott to shortlist, reject, defer, or request preparation.
- [ ] Record every decision in the audit log.
- [ ] Add internal notifications for items needing review.

Tracked by Issue #8.

**v0.1 MVP outcome:** Scott can open a local dashboard, review normalized opportunities, understand why each passed or failed, and control every next step.

## v0.2 — Application preparation

**Goal:** Prepare high-quality, opportunity-specific materials while treating the master résumé as immutable source data.

- [ ] Import and version a master résumé as read-only.
- [ ] Generate a new tailored résumé per selected opportunity.
- [ ] Generate cover-letter and fit-report drafts.
- [ ] Compare generated claims against approved source material.
- [ ] Flag unsupported or uncertain claims.
- [ ] Add document versioning and approval states.
- [ ] Export DOCX and PDF artifacts.

Tracked by Issue #7.

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
