# OpportunityEngine Architectural Decisions

## Purpose

This file records decisions that materially shape OpportunityEngine. It is a lightweight Architectural Decision Record (ADR) log: each entry captures context, the decision, consequences, and status.

Decision identifiers are permanent. Superseded decisions remain in this file and point to their replacement.

## Status values

- **Proposed:** under discussion.
- **Accepted:** governs implementation.
- **Superseded:** replaced by a later decision.
- **Rejected:** considered but not adopted.

---

## OE-ADR-001 — The constitution is authoritative

**Status:** Accepted  
**Date:** 2026-07-29

### Context

OpportunityEngine uses AI and automation around employment and consulting opportunities. The system needs rules that cannot be silently weakened by prompts, code, workflows, or provider behavior.

### Decision

`config/constitution.json` is the authoritative machine-readable policy. If another instruction conflicts with it, the constitution controls. A missing or invalid constitution causes restricted workflows to fail closed.

### Consequences

- Runtime services must load and validate the constitution.
- Tests must verify constitutional boundaries.
- Constitution versions must be included in audit-relevant decisions.
- Changes to the constitution require deliberate review.

---

## OE-ADR-002 — Human control over every external action

**Status:** Accepted  
**Date:** 2026-07-29

### Context

Discovery and preparation can be automated safely, but applications, communications, contracts, identity verification, and financial commitments act as Scott.

### Decision

Every external action requires Scott's explicit, scoped approval. AI scores, shortlisting, document generation, prior approvals, or general preferences do not constitute approval for a different action.

### Consequences

- Approval is modeled as a first-class record.
- Missing, ambiguous, expired, or mismatched approval fails closed.
- Each approval identifies actor, action, target, and scope.
- The initial MVP performs no external application or messaging action.

---

## OE-ADR-003 — The master résumé is immutable source material

**Status:** Accepted  
**Date:** 2026-07-29

### Context

Tailored application documents must remain truthful and must not corrupt the authoritative source résumé.

### Decision

The master résumé is stored as immutable, versioned source material. Each tailored résumé is a newly generated artifact tied to an opportunity and source version.

### Consequences

- Master résumé records cannot be updated or deleted through normal application workflows.
- A corrected master résumé is imported as a new version.
- Generated claims must be traceable to approved source material.
- Generated documents keep independent version history.

---

## OE-ADR-004 — Start with a modular monolith

**Status:** Accepted  
**Date:** 2026-07-29

### Context

OpportunityEngine is initially a local, single-user project. Microservices, distributed queues, and multiple deployable units would add operational burden before the domain is stable.

### Decision

Build a modular monolith with clear domain-service and repository boundaries. FastAPI provides the application boundary while collection, filtering, scoring, documents, approvals, notifications, and auditing remain separate modules inside one deployable application.

### Consequences

- Development and deployment stay simple.
- Transactions and local debugging remain straightforward.
- Module contracts must prevent route handlers and adapters from accumulating business logic.
- Modules may be extracted later if measured scale or isolation requirements justify it.

---

## OE-ADR-005 — SQLite first, PostgreSQL later if justified

**Status:** Accepted  
**Date:** 2026-07-29

### Context

The initial deployment is local, single-user, and modest in volume. SQLite minimizes administration while providing transactions, foreign keys, constraints, and reliable local persistence.

### Decision

Use SQLite for v0.1. Keep domain and repository boundaries compatible with a future PostgreSQL migration, but do not introduce PostgreSQL operational complexity prematurely.

### Consequences

- Foreign keys must be enabled on every connection.
- Write transactions should remain short.
- Concurrency assumptions must match SQLite.
- Migration tests and backups are required.
- PostgreSQL is adopted only after a documented need.

---

## OE-ADR-006 — Deterministic rules precede AI judgment

**Status:** Accepted  
**Date:** 2026-07-29

### Context

Remote-only, travel, relocation, clearance, and full-time-replacement constraints are hard rules. A probabilistic model should not override them.

### Decision

Normalize evidence, apply deterministic hard filters, and only then invoke AI scoring for eligible opportunities. AI may assist with evidence extraction, but deterministic code owns rule enforcement.

### Consequences

- Every filter evaluation stores a rule code, evidence, outcome, and explanation.
- Failed opportunities are not scored unless Scott explicitly requests a diagnostic evaluation.
- Model changes cannot silently change constitutional eligibility.
- Filter behavior is straightforward to unit test.

---

## OE-ADR-007 — AI results are versioned, explainable evidence

**Status:** Accepted  
**Date:** 2026-07-29

### Context

AI outputs can vary between models, prompts, and repeated runs. Opportunity decisions must remain understandable and reproducible enough for review.

### Decision

Store each AI-assisted run as an immutable result with provider, model, prompt version, input reference, structured output, component scores, confidence, and explanation. Re-running creates a new record.

### Consequences

- Historical outputs are preserved.
- The UI can compare scores and explanations.
- Costs and model behavior can be evaluated.
- AI output remains advisory and untrusted until validated.

---

## OE-ADR-008 — Preserve source evidence and ingestion history

**Status:** Accepted  
**Date:** 2026-07-29

### Context

Listings change, disappear, or conflict across sources. Normalized data alone is insufficient for troubleshooting and audit.

### Decision

Preserve source identity, external identifiers, canonical URLs, retrieval metadata, and a safe representation of raw source data. Link each normalized opportunity to all supporting source records.

### Consequences

- Normalization and deduplication can be audited.
- Storage grows over time and requires retention decisions.
- Sensitive or prohibited source content must not be retained unnecessarily.
- Raw content is treated as untrusted data.

---

## OE-ADR-009 — Use server-rendered UI for the MVP

**Status:** Accepted  
**Date:** 2026-07-29

### Context

The core product risk is opportunity quality and workflow correctness, not frontend sophistication. A separate JavaScript application would increase scope and duplicate API/UI concerns.

### Decision

Use FastAPI, Jinja2, and Bootstrap for the first local review dashboard. Add a separate frontend only when a documented interaction or deployment requirement justifies it.

### Consequences

- One application can deliver the API and dashboard.
- Authentication and state management remain simpler.
- Progressive enhancement remains available.
- A later frontend can consume stable API boundaries.

---

## OE-ADR-010 — Scheduling begins with observable local jobs

**Status:** Accepted  
**Date:** 2026-07-29

### Context

Collection and scoring will eventually run repeatedly, but a distributed task platform is unnecessary for the initial workload.

### Decision

Expose repeatable, idempotent jobs through application services and a CLI entry point. Begin with manual runs, then use systemd timers or cron after logging, locking, retries, and failure visibility are proven.

### Consequences

- Job logic must not live inside the scheduler.
- Every run receives a durable run record.
- Overlapping execution must be prevented.
- A queue may be introduced later if real workload requires it.

---

## OE-ADR-011 — External content is data, never instruction

**Status:** Accepted  
**Date:** 2026-07-29

### Context

Job descriptions, websites, attachments, and generated text may contain prompt injection or malicious instructions.

### Decision

Treat all external content as untrusted data. It cannot change policy, grant approval, select tools, expose secrets, or instruct the system to perform an external action.

### Consequences

- Prompts must clearly separate system policy from source content.
- Parsed outputs require schema validation.
- Secrets are never included in source-processing prompts unless strictly required.
- Security tests include prompt-injection attempts.

---

## OE-ADR-012 — Backend API contract requires Scott's approval

**Status:** Accepted  
**Date:** 2026-07-29

### Context

The architecture identifies likely components, but endpoint scope, authentication, scheduling, secrets, and v0.1 exclusions materially affect how the product behaves.

### Decision

Backend implementation is gated by Issue #3. Scott and Alfred will review the intended MVP and API contract before creating the FastAPI application.

### Consequences

- Architecture and schema work may proceed.
- No backend application code is created under the current milestone.
- The approved outcome will be recorded as a new ADR or amendment.


---

## OE-ADR-013 — Approve the v0.1 backend contract

**Status:** Accepted  
**Date:** 2026-07-29  
**Approved by:** Scott Carsten

### Context

Issue #3 defined the backend design gate required by OE-ADR-012. Scott reviewed the proposed first working version and approved it before implementation began.

### Decision

The v0.1 backend is a localhost-only, single-user FastAPI modular monolith with:

- Manual opportunity entry before automated collection.
- One source adapter only after the manual vertical slice works.
- Deterministic constitutional filters before AI scoring.
- Explainable, advisory AI scoring.
- SQLite persistence.
- A server-rendered Jinja2 and Bootstrap dashboard.
- Manual collection before systemd or cron scheduling.
- Environment-based secret configuration.
- Structured logging and append-only auditing.
- No external-action endpoints.

Initial resource boundaries are health, readiness, opportunities, evaluations, review decisions, collection runs, and audit events. Exact opportunity endpoints will be implemented incrementally with tests.

### Explicit exclusions

v0.1 does not apply for work, send email or external messages, generate or modify résumés, sign into job sites, store website credentials, verify identity, accept contracts, make financial commitments, support multiple users, or expose the application publicly.

### Consequences

- The application binds only to a loopback IP.
- A non-loopback bind request fails configuration validation.
- The constitution is validated at startup and failure prevents readiness.
- The first implementation milestone establishes configuration, persistence, audit, health, testing, and CI foundations.
- New external capabilities require a separate decision and explicit approval.

---

## OE-ADR-014 — Adopt SQLAlchemy and Alembic for persistence

**Status:** Accepted
**Date:** 2026-08-05

### Context

Milestone 1 of `docs/ROADMAP.md` called for SQLAlchemy models and migrations
based on `database/schema.sql`, but the initial implementation used a raw
`sqlite3` connection with `database/schema.sql` applied once via
`executescript()`. This left the codebase inconsistent with
`docs/ARCHITECTURE.md` §6, which already documented SQLAlchemy as the
persistence layer, and left schema evolution without a real migration tool.

### Decision

Replace the raw-`sqlite3` layer with SQLAlchemy ORM models
(`backend/db/models.py`) covering all sixteen tables in
`database/schema.sql`, and adopt Alembic for migrations
(`database/migrations/`). The initial migration (`0001_initial_schema`)
transcribes the approved physical schema exactly, including the six
constitutional-safeguard triggers (append-only audit and filter history,
immutable master résumé, immutable completed scoring runs, approval-gated
external notifications). SQLAlchemy has no DDL support for triggers, so
these remain hand-written raw SQL inside the migration via `op.execute()`.
`database/schema.sql` is retained as human-readable documentation of the
physical design; it is no longer executed at runtime.

### Consequences

- Schema changes going forward are made as new Alembic migrations, not by
  editing `database/schema.sql` in place.
- `backend/database.py` runs `alembic upgrade head` at startup instead of
  a one-time `executescript()`, which is naturally idempotent.
- Service code (`OpportunityService`, `AuditService`) queries through
  SQLAlchemy sessions rather than hand-written SQL strings.
- Autogenerate (`alembic revision --autogenerate`) can assist with future
  ordinary column/table changes, but triggers still require manual
  `op.execute()` edits.
- `Settings.schema_path` and `Database`'s `schema_path` parameter were
  removed as dead configuration once migrations took over schema creation.

---

## OE-ADR-015 — First source adapter: We Work Remotely RSS

**Status:** Accepted
**Date:** 2026-08-05
**Approved by:** Scott Carsten (source selection)

### Context

Milestone 2 (`docs/ROADMAP.md`, Issue #4) called for a source-adapter
interface and one approved opportunity source, per `OE-ADR-013`'s "one
source adapter only after the manual vertical slice works." Scott chose We
Work Remotely's DevOps and Sysadmin RSS feed: publicly syndicated for this
purpose, no API key, and its category matches the infrastructure/sysadmin
focus in `config/constitution.json`.

### Decision

- `backend/adapters/base.py` defines the adapter contract: a
  `RawOpportunityRecord` (external id, canonical URL, retrieval time, raw
  payload) plus a `SourceAdapter` protocol with `fetch()` and `normalize()`
  as two explicit stages, matching `docs/ARCHITECTURE.md` §5's pipeline —
  adapters preserve raw evidence without interpreting it; normalization
  maps that evidence into the canonical `OpportunityInput` model.
- `backend/adapters/we_work_remotely.py` implements it using stdlib
  `xml.etree.ElementTree` (verified against the live feed; no new XML
  dependency needed) and strips HTML from descriptions via stdlib
  `html.parser` rather than rendering untrusted external markup, per
  `OE-ADR-011` and the architecture's "escape rendered content" rule.
  Fields the feed doesn't publish (compensation, tax type,
  travel/relocation/clearance/full-time-replacement) are left `unknown`/
  `None`, which the existing hard-filter logic already routes to
  `manual_review` rather than auto-approving.
- `OpportunityService.create_manual` was refactored so manual entry and
  automated collection share one fingerprint/filter/persist path
  (`_ingest`), instead of two implementations that could drift apart.
- `backend/services/collection_service.py` orchestrates one adapter run and
  relies on the schema's existing `uq_source_records_source_external`
  constraint for idempotency: a listing already seen from a source (same
  external id) only bumps `last_seen_at`.
- `backend/cli.py` (`python -m backend.cli collect we_work_remotely`) is
  the manual, repeatable entry point required by `OE-ADR-010`; no
  cron/systemd scheduling yet.

### Explicit scope boundary

If a collected listing's fingerprint matches an already-known opportunity,
this milestone reuses the exact manual-entry short-circuit (return the
existing id, create no new `source_record`). Recording that repeat sighting
as a `deduplication_decisions` row is Milestone 3 (Issue #5) work, not this
one's.

### Consequences

- Auto-collected opportunities flow through the same
  `list_opportunities()`/`get_opportunity()` dict contract as manual
  entries, so no template changes were needed.
- A second adapter can be added by implementing `SourceAdapter` and
  registering it in `backend/cli.py`'s `ADAPTERS` map.
- Milestone 3's likely-duplicate detection and audited manual-override path
  remain open.

---

## OE-ADR-016 — Human-only, audited hard-filter override

**Status:** Accepted
**Date:** 2026-08-05

### Context

Milestone 3's two remaining items were likely-duplicate detection beyond
exact fingerprint matches, and a manual path to override a hard-filter
outcome. `docs/ARCHITECTURE.md` §5.4 states a hard filter's rule is
deterministic and that "AI may extract evidence used by a rule, but it may
not override the rule" — it does not say a human may not. Scott chose to
scope the override narrowly to the hard-filter decision itself
(`eligible`/`ineligible`), leaving the separate shortlist/reject/defer
review workflow (`review_decisions`) to Milestone 5.

### Decision

- Likely-duplicate detection (`OpportunityService._detect_likely_duplicates`)
  runs inside `_ingest`, after the exact-fingerprint check misses, comparing
  the new opportunity against existing ones with the same organization name
  using `difflib.SequenceMatcher` over the same identity string
  `_fingerprint` already hashes. Matches at or above 0.85 become a
  `deduplication_decisions` row (`method="similarity"`, `decided_by=
  "system"`). Both opportunities remain separate, undecided rows — nothing
  is auto-merged or suppressed, per ARCHITECTURE §5.3.
- `OpportunityService.override_lifecycle_status(opportunity_id, new_status,
  rationale)` lets Scott move an opportunity between `eligible` and
  `ineligible` directly. It requires a non-empty rationale, updates
  `opportunities.lifecycle_status`, and records the action via
  `AuditService` (`event_type="hard_filter_override"`, `actor_type=
  "scott"`) — the first real caller `AuditService` has had since it was
  built in Milestone 1.
- The override never touches `filter_evaluations` rows. Those stay exactly
  as the hard filters produced them (and are DB-trigger-protected from
  ever changing) — the override is a second, additional fact layered on
  top, not a correction of the first one.
- No `approval_requests` row is created: per the constitution, approval
  gating applies to *external* actions (applications, email, contracts).
  An internal eligibility call is one Scott is already permitted to make
  directly.

### Consequences

- AI/automation must never call `override_lifecycle_status` — nothing in
  the codebase does, and any future AI-scoring code must not gain this
  capability without a new, explicit decision.
- `templates/opportunity_detail.html` surfaces both: a "possible duplicate"
  link to the other opportunity, and an override form plus history, so the
  override path is observable, not just logged.
- Milestone 3 is complete. Milestone 4 (explainable scoring) is next.

---

## OE-ADR-017 — Claude Opus 5 is the AI scoring provider, not OpenAI

**Status:** Accepted
**Date:** 2026-08-05

### Context

`README.md`, `docs/VISION.md`, and `docs/ARCHITECTURE.md` named OpenAI as
the planned AI provider from the project's earliest design pass. Scott
chose Claude instead for Milestone 4 (explainable scoring, Issue #6) — the
first place AI actually enters the pipeline — partly because Claude has
already done much of the work correcting what the OpenAI-assisted v1
planning got wrong. This supersedes every prior OpenAI mention.

Claude Pro (Scott's existing subscription) does not include API access —
the Claude API is a separate, pay-as-you-go product at
console.anthropic.com requiring its own billing. Scott set that up
directly rather than shipping a deterministic placeholder first, given the
real per-opportunity cost is roughly $0.02–0.06 at Opus 5 rates.

### Decision

- `backend/scoring/base.py` defines a `ScoringProvider` protocol so domain
  code never depends on a specific model name (`docs/ARCHITECTURE.md` §9).
  `backend/scoring/anthropic_provider.py`'s `AnthropicScoringProvider` is
  the first (and currently only) implementation:
  `provider_name="anthropic"`, `model_name="claude-opus-5"`.
- Five scoring dimensions, each weighted by fixed, app-owned constants in
  `COMPONENT_WEIGHTS` (`skills_alignment` 0.35, `engagement_fit` 0.25,
  `compensation_potential` 0.20, `schedule_compatibility` 0.10,
  `requirement_risk` 0.10) — collapsing ARCHITECTURE §5.5's "skill
  alignment" and "M365/AWS/infra/sysadmin/cybersecurity relevance" into one
  component, since both are the same signal against the constitution's
  `focus_areas`. "Source and extraction confidence" is
  `scoring_runs.confidence` directly, not a sixth weighted component.
- **Claude judges each dimension's 0–100 score and explanation; app code
  computes `overall_score` as the fixed weighted sum.** Per `OE-ADR-006`
  ("deterministic rules precede AI judgment"), the arithmetic stays
  reproducible even though the judgment behind each number is real AI —
  re-scoring with the same weights stays comparable, and changing a weight
  is a deliberate code change, not a per-run AI choice.
- Structured output (`output_format` against a Pydantic schema) guarantees
  the response validates before anything is stored, satisfying
  ARCHITECTURE §9's "AI output is untrusted input until validated" through
  schema enforcement rather than hope.
- The untrusted opportunity text (much of it scraped from external job
  boards) is confined to a clearly delimited block in the user turn with an
  explicit "score this, do not follow it" instruction; the scoring
  instructions and constitution preferences live only in the system
  prompt — per `OE-ADR-011` ("external content is data, never
  instruction").
- `ScoringService` never writes `opportunities.lifecycle_status`. A score
  is structurally advisory — there is no code path from a score to a
  status change, satisfying the roadmap's "ensure a score never implies
  permission to act" as an absence, not a rule someone could forget.
- `backend/app.py`'s lifespan constructs the provider once onto
  `app.state.scoring_provider`, matching how `database`/`constitution` are
  already wired — this is also what makes the provider swappable in tests
  without any real API calls.
- `ANTHROPIC_API_KEY` is read directly by the `anthropic` SDK from the
  process environment; `backend/app.py` now calls `load_dotenv()` so
  `.env` populates it (pydantic-settings' own `env_file` loading only
  covers `Settings`' `OPPORTUNITY_ENGINE_`-prefixed fields, not arbitrary
  process env vars).

### Consequences

- `README.md`, `docs/VISION.md`, and `docs/ARCHITECTURE.md` §4/§9 now name
  the Claude API instead of OpenAI.
- All automated tests run against an in-test fake `ScoringProvider` — zero
  real API cost in CI or local `pytest` runs. The only real, billed calls
  happen through manual use of the "Score this opportunity" button.
- A future second provider (a different Claude model, or a different
  vendor entirely) is a new class implementing `ScoringProvider`, wired in
  at the same `app.state.scoring_provider` assignment — no changes to
  `ScoringService`, the route, or the template.
