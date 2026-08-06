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

---

## OE-ADR-018 — Review decisions drive lifecycle_status; notifications are ingest-time only

**Status:** Accepted
**Date:** 2026-08-06

### Context

Milestone 5 (review inbox, Issue #8) needed a real decision workflow on top
of what Milestones 3–4 already exposed (filters, likely-duplicate/override
history, fit scores). Two tables from the original schema design had sat
unused since Milestone 0, in the same position `AuditService` was in before
Milestone 3: `review_decisions` and `notifications`.

### Decision

- `OpportunityService.record_review_decision(opportunity_id, decision,
  rationale=None, actor="scott")` maps each decision directly onto the
  schema's own dedicated `lifecycle_status` states, since a review decision
  *is* Scott's own judgment call (unlike the Milestone 3 override, which
  deliberately stayed scoped to `eligible`/`ineligible` because it was
  correcting a hard-filter judgment, not replacing it):

  | Decision | New `lifecycle_status` |
  |---|---|
  | `shortlist` | `shortlisted` |
  | `reject` | `rejected` |
  | `defer` | `deferred` |
  | `request_preparation` | `preparing` |
  | `reopen` | `eligible` |

  Every decision writes one `ReviewDecision` row and one `AuditEvent`
  (`event_type="review_decision"`) — the same audited-decision pattern
  `OE-ADR-016`'s override established. Rationale is optional here (the
  override's is required) — a quick shortlist/reject click shouldn't
  demand a written reason. No transition is blocked: Scott can move any
  opportunity between any of these states at any time, including
  re-deciding something already rejected.
- `_ingest()` creates one `Notification` row (`notification_type=
  "opportunity_needs_review"`, `channel="dashboard"`) whenever the result is
  `eligible` or `new` — **once, at ingest, not on every later status
  change.** A `reopen`/`reject`/etc. is already visible in that
  opportunity's own review-decision history; a second notification would
  just be noise. `record_review_decision` does not create notifications.
- The dashboard shows a count of `status="queued"` notifications; viewing
  an opportunity's detail page marks its notifications `sent` — a
  mark-as-read-on-view, implemented in the route layer so
  `get_opportunity()` itself stays a pure read.
- `get_opportunity()` now also joins `opportunity_sources` (primary) →
  `source_records` → `sources`, closing the one Milestone 5 item that
  wasn't already incidentally satisfied by Milestones 3–4.

### Consequences

- v0.1's stated MVP outcome is reached: Scott can open the dashboard,
  review normalized opportunities, understand why each passed or failed,
  and control every next step — filters, dedup, overrides, scores, source,
  and now decisions and notifications are all visible on one page.
- `templates/opportunity_detail.html` and `templates/dashboard.html` badge
  logic now distinguishes `shortlisted`/`deferred`/`rejected`/`preparing`
  instead of lumping every non-eligible/ineligible status into "Manual
  review".
- v0.2 (application preparation, Issue #7) is next.

---

## OE-ADR-019 — Master résumé versions are derived, not flagged current

**Status:** Accepted
**Date:** 2026-08-06

### Context

v0.2 (Issue #7) begins with "import and version a master résumé as
read-only" — everything else in v0.2 (tailored résumé generation, cover
letters, fit reports, claim-grounding, export) depends on a master résumé
existing, so it's the first slice. `resume_sources` and its two protective
triggers (`protect_master_resume_update`, `protect_master_resume_delete` —
both `WHEN OLD.is_master = 1`) were already designed in Milestone 0 and,
like several tables before it, sat unused.

The triggers mean a row with `is_master = 1` cannot be updated or deleted
under any circumstances, including flipping its own `is_master` flag to 0.
There is no way to "unmark the old version as current."

### Decision

- `backend/services/resume_service.py`'s `ResumeService` never attempts an
  `UPDATE` or `DELETE` on `resume_sources`. "Current" is derived —
  `MAX(version) WHERE is_master = 1` — not stored as a pointer. A
  correction is always a new row with `supersedes_id` pointing at the
  previous highest-version row (`OE-ADR-003`).
- Re-importing byte-identical content (same `sha256` hash) is a no-op that
  returns the existing version, mirroring the fingerprint short-circuit
  already established in `OpportunityService._ingest`.
- The stored file path is `{content_hash}{extension}`, where the extension
  comes from a small validated MIME-type allowlist (PDF, DOCX, plain text)
  — **never** the user-supplied filename. This, not filename validation, is
  what actually prevents path traversal (ARCHITECTURE.md §10): the
  filename is stored only as display metadata and never touches the
  filesystem path.
- A 10 MB size cap and the MIME-type allowlist are enforced before any
  file write or database operation.
- Every import is audited (`event_type="resume_imported"`) — a
  constitutionally significant action per `principles.master_resume_read_only`
  in `config/constitution.json`.

### Consequences

- No code path anywhere can mutate or delete a master résumé version —
  matching `principles.master_resume_read_only` structurally, not just by
  convention.
- Future document-generation work (the next v0.2 slice) reads
  `ResumeService.get_current_master()` for the résumé to ground claims
  against, and can freely reference `resume_sources.id` by version without
  worrying that version's content will ever change underneath it.

---

## OE-ADR-020 — Tailored résumé generation requires "preparing," and grounds and flags claims in one call

**Status:** Accepted
**Date:** 2026-08-06

### Context

v0.2's second slice covers three of the six remaining roadmap items at
once: generate a tailored résumé per opportunity, compare its claims
against approved source material, and flag unsupported ones. All three
are really one AI call — the model best positioned to say which parts of
a draft it invented is the same model that drafted it. `generated_documents`
was already fully designed in Milestone 0 (`document_type`, `version`,
a `status` check constraint of `draft/validation_failed/ready_for_review/
approved/rejected/superseded`, `unsupported_claims_json`) and, like
`resume_sources` before it, sat unused. Unlike `resume_sources` and
`scoring_runs`, it has no immutability trigger yet — document *approval
states* are a later slice, not this one.

### Decision

- `DocumentService.generate_tailored_resume` requires
  `lifecycle_status == "preparing"` — Scott's own `request_preparation`
  review decision (`OE-ADR-018`) — not merely "eligible" or "scored."
  `config/constitution.json`'s pipeline is "notify Scott, then wait for
  explicit approval"; scoring already happens before any human decision,
  so gating generation on eligibility alone would let it fire before
  Scott asked for it. `generate_tailored_resume` is one of
  `permitted_internal_actions` — internal-only, never authorization to
  send anything.
- `AnthropicDocumentProvider` (`backend/documents/anthropic_provider.py`)
  drafts the résumé and lists any unsupported claims in the same
  structured-output call, extending `OE-ADR-011`'s "external content is
  data, never instruction" to a second untrusted source: both the
  opportunity text and the master résumé's own content sit in clearly
  delimited user-turn blocks, never the system prompt.
- A provider exception records an `AuditEvent`
  (`event_type="document_generation_failed"`) but writes no
  `generated_documents` row — the schema's `status` check constraint has
  no failure state, and ARCHITECTURE.md §15 only requires that partial
  generation produce no approved artifact, not that every attempt leave a
  row.
- On success, `status` is set structurally, not by human judgment yet:
  `"validation_failed"` if `unsupported_claims` is non-empty, else
  `"ready_for_review"`. Regenerating always inserts the next `version`,
  never updates a previous one.
- Master résumé content reaches Claude differently by format: `.pdf` is
  sent as a native Anthropic `document` content block (Claude reads PDFs
  directly, so no extraction dependency is needed); `.txt` is decoded
  directly; `.docx` text is pulled with the new `python-docx` dependency,
  since the Messages API has no native `.docx` support.

### Consequences

- Scoring an opportunity never triggers document generation as a side
  effect — the two are gated on different lifecycle states, so a
  scored-but-not-yet-decided opportunity cannot silently accumulate
  generated drafts nobody asked for.
- A `"validation_failed"` document is not hidden or auto-discarded; it is
  stored and shown with its unsupported claims listed prominently, so an
  invented claim is something Scott sees, not something that quietly
  disappears.
- Document *approval states* (turning `"ready_for_review"` into
  `"approved"`/`"rejected"`, and the immutability trigger that should
  follow) and DOCX/PDF export remain open v0.2 items — this slice
  produces a plain-text draft only.

---

## OE-ADR-021 — Deterministic signal extraction fills in hard-filter unknowns

**Status:** Accepted
**Date:** 2026-08-06

### Context

Live-collecting from We Work Remotely (`OE-ADR-015`) during the tailored-
résumé smoke test showed every one of 50 real listings landing in
`lifecycle_status = "new"`: `WeWorkRemotelyAdapter.normalize()`
unconditionally mapped `requires_travel`, `requires_relocation`,
`requires_clearance`, and `replaces_full_time_work` to `None`, even when a
listing's own description plainly answered them. The feed genuinely has
no structured fields for the first three, but its `<type>` field
(Full-Time/Contract/Part-Time/Temporary) is structured and was already
being parsed into `engagement_type` — just never used for the
full-time-replacement filter. The net effect: the tool that's supposed to
do the reading was making Scott manually judge every single listing
himself, which is the opposite of the point.

### Decision

- `backend/adapters/signal_extraction.py` adds three source-agnostic,
  deterministic functions — `extract_travel_signal`,
  `extract_relocation_signal`, `extract_clearance_signal` — each scanning
  free text against a small curated phrase list for "definitely required"
  and "definitely not required," returning `None` otherwise. Per
  `OE-ADR-006`, hard filters run deterministically before any AI
  judgment; this stays pattern-matching, not a model call, so that
  guarantee is unchanged.
- **Precision over recall is the explicit bias.** Many descriptions won't
  match anything and stay `None` — same manual-review outcome as before.
  That's fine. Guessing a boolean wrong is not: it could let a
  travel-required or clearance-required listing silently pass a hard
  filter Scott is relying on. The phrase lists are intentionally narrow.
- `replaces_full_time_work` now derives directly from `engagement_type`
  (`True` for `full_time`, `False` for `contract`/`part_time`/
  `temporary`, `None` for `unknown`) — no text scanning needed, since
  the RSS `<type>` field is already structured data, not free text.
- **Confirmed with Scott before implementing:** this means a listing
  explicitly tagged "Full-Time" now auto-fails the full-time-replacement
  filter and lands `ineligible` instead of sitting in `"new"`. He
  confirmed this matches his actual goal — stacking side-hustle, 1099,
  hourly, and evening/weekend work around his existing job, not finding a
  replacement for it — and the existing audited override
  (`OpportunityService.override_lifecycle_status`, `OE-ADR-016`) still
  lets him reverse any single case by hand.

### Consequences

- Fewer real, collected listings land in `"new"` needing a manual
  eligibility call before Scott can even see a score — the tool reads the
  listing text so he doesn't have to.
- A definitive `True`/`False` from these functions carries the same
  weight as a hand-entered answer in the manual-entry form: it can now
  fail a listing outright. The narrow phrase lists exist specifically to
  keep that trustworthy.
- Any future source adapter facing the same "free text has the answer,
  structured fields don't" gap reuses
  `backend/adapters/signal_extraction.py` rather than re-solving it.

---

## OE-ADR-022 — Three more sources, each relevance-filtered at fetch time

**Status:** Accepted
**Date:** 2026-08-06

### Context

Scott asked to add 16 named job boards. A live research pass (checking
each site directly, not from memory) found most weren't viable: `jobs.
github.com`, CloudPeeps, and Toggl Hire are defunct or being
discontinued; Virtual Vocations and Jobgether explicitly prohibit
scraping/data-mining in their ToS; Outsourcely, Contra, and RemoFirst
aren't job-listings boards at all (an employer-side freelancer directory,
a freelancer marketplace, and an Employer-of-Record/payroll company,
respectively — confirmed, not guessed); "hesxjobs" doesn't exist (Scott
confirmed it was a typo for Hexjobs, whose robots.txt disallows crawling
its own job pages regardless). Three — **Himalayas**, **Remotive**,
**Jobspresso** — have a real public feed/API and no scraping involved,
the same bar `WeWorkRemotelyAdapter` (`OE-ADR-015`) already clears.

Live-probing each (not guessing) surfaced a shared problem: unlike We
Work Remotely's dedicated DevOps/Sysadmin category feed, all three of
these are general "every remote job, every industry" feeds — an HVAC
role, a Sales role, and a stock-trader role were each site's first live
item. Ingesting them unfiltered would flood Scott's review queue and
spend his Opus 5 scoring budget on irrelevant listings — the exact noise
problem this tool exists to eliminate. Each site's *best available*
filtering mechanism turned out to differ, so each adapter filters
differently, in order of preference (structured query, then structured
per-item field, then keyword scan as the fallback):

### Decision

- **`backend/adapters/himalayas.py`**: filters via the site's own free,
  unauthenticated JSON search API (`/jobs/api/search`), which supports a
  boolean-`OR` query — verified live to return 52 highly relevant results
  for a query built from the constitution's focus areas. This is
  filtering at the source, the strongest option, and a bonus: it's the
  first source with real structured compensation
  (`minSalary`/`maxSalary`/`salaryPeriod`) and a clean `employmentType`
  enum, so both flow into `OpportunityInput` directly instead of staying
  `None`/`unknown`.
- **`backend/adapters/remotive.py`**: its RSS items carry a structured
  `<category>` tag (verified live: `Devops`, `Information Technology`,
  `Software Development`, `Sales`, ...); `fetch()` keeps only `Devops`
  and `Information Technology`. `Software Development` is deliberately
  excluded — too broad, mostly generic app-dev roles outside scope, same
  precision-over-recall bias as `OE-ADR-021`. The feed's `?category=`
  query parameter is silently ignored (verified live), so this filters
  client-side over already-fetched items, not via a smarter request.
- **`backend/adapters/jobspresso.py`**: exposes no category or
  engagement-type field at all, and its category-specific feed URLs
  return zero items live. Falls back to the same deterministic,
  precision-biased keyword scan `OE-ADR-021` established for hard-filter
  signals, applied here to relevance instead — missing a borderline
  listing is fine, flooding the queue with false positives is not.
- All three reuse `backend/adapters/signal_extraction.py` for
  travel/relocation/clearance and the same `engagement_type`-derived
  `replaces_full_time_work` mapping as `OE-ADR-021`. Jobspresso exposes no
  engagement type at all, so that field stays `unknown`/`None` there, same
  as any We Work Remotely listing with an unrecognized `<type>`.
- `_HTMLTextExtractor`/`_strip_html` moved out of `we_work_remotely.py`
  into `backend/adapters/html_text.py` — three more adapters need HTML
  stripping now, not one.

### Consequences

- Adding a source is no longer "does it have RSS shaped exactly like We
  Work Remotely's" — it's "what's the best relevance signal this
  particular site actually offers," decided per source rather than forcing
  a single filtering strategy on all of them.
- Himalayas is the richest source collected so far: real compensation
  data lets scoring's `compensation_potential` dimension (`OE-ADR-017`)
  work with real numbers instead of "not specified" for the first time.
- Of the 16 originally-requested sites, 13 were dropped for concrete,
  verified reasons (defunct, ToS-prohibited, not actually a job board, or
  nonexistent) rather than left unresolved — see the research this ADR is
  based on for the full per-site breakdown if a dropped source is ever
  revisited.

---

## OE-ADR-023 — Cover letters and fit reports; a fit report synthesizes, it doesn't re-score

**Status:** Accepted
**Date:** 2026-08-06

### Context

v0.2's third slice covers the roadmap's "Generate cover-letter and
fit-report drafts" bullet. `generated_documents.document_type` already
allowed `cover_letter` and `fit_report` (Milestone 0); both reuse the
`DocumentService`/`DocumentGenerationProvider` machinery the tailored
résumé slice built (`OE-ADR-020`). A cover letter is the same shape of
task as the résumé — draft new content grounded in the master résumé,
flag anything unsupported. A fit report is not: it's meant to explain a
scoring run (`OE-ADR-017`) that already happened, not produce a fresh
judgment. Treating it like the other two — "draft something new about
how well this fits" — would let the model re-score the opportunity in
prose, potentially disagreeing with the actual `ScoringRun` sitting in
the database, which would be confusing at best and a second, uncontrolled
judgment path at worst.

### Decision

- `DocumentGenerationProvider` (`backend/documents/base.py`) gained
  `generate_cover_letter` (same signature as `generate_tailored_resume`)
  and `generate_fit_report`, which additionally takes a `scoring` dict —
  `overall_score`, `confidence`, `fit_summary`, `concerns`, and
  `components` — the same shape `OpportunityService.get_opportunity`
  already assembles for `scoring_runs`.
- `DocumentService.generate_fit_report` requires the opportunity's latest
  `ScoringRun` to have `status == "succeeded"`; otherwise it raises
  `ValueError` ("score this opportunity before generating a fit report")
  before ever calling the provider. Same `lifecycle_status == "preparing"`
  gate as the other two document types on top of that.
- `AnthropicDocumentProvider`'s fit-report system prompt explicitly frames
  the scores as *given facts, not to be re-judged* — the model's job is
  explaining and contextualizing them in prose, grounded in the résumé
  for any claim about Scott's own background. It still reports
  `unsupported_claims` for anything not grounded in either the résumé or
  the given scoring data.
- Two refactors, both justified by now having three call sites instead of
  one: `_master_resume_blocks` (PDF/docx/txt encoding) is shared across
  all three provider methods instead of being tailored-résumé-only, and
  `DocumentService._persist` (content-hash, file write, versioning,
  `GeneratedDocument` insert, audit event) is shared across all three
  service methods instead of being duplicated.
- `OpportunityService.get_opportunity`'s `generated_documents` changed
  from a flat list to a dict keyed by `document_type`, each newest-first
  — the template needs to address three independent histories, not
  filter one flat list three times.

### Consequences

- There is exactly one place an opportunity's fit gets judged
  (`ScoringService`) — the fit report can only elaborate on that
  judgment, never produce a second, contradictory one.
- `templates/opportunity_detail.html` gained a Jinja macro
  (`document_section`), following the same "reused several times with
  real per-call differences" bar `templates/dashboard.html`'s
  `filter_link` macro was held to — not introduced for the résumé
  section alone.
- Document *approval states* and DOCX/PDF export remain the only open
  v0.2 items.

---

## OE-ADR-024 — Document approval is permanent; `generated_documents` is now append-only

**Status:** Accepted
**Date:** 2026-08-06

### Context

`generated_documents.status` has allowed `approved`/`rejected` since
Milestone 0, but nothing ever wrote them and no trigger protected them —
`OE-ADR-020`/`OE-ADR-023` both flagged this as the follow-on. It was the
one append-only-relevant table in the schema still missing its
protective trigger; every other one (`resume_sources`, `filter_evaluations`,
`scoring_runs`, `audit_events`) already has one.

### Decision

- `database/migrations/versions/0002_protect_generated_documents.py`
  (mirrored in `database/schema.sql`) adds
  `protect_generated_document_update`/`_delete`, copying
  `scoring_runs`' exact shape: `WHEN OLD.status IN ('approved',
  'rejected')` blocks further updates, delete is blocked unconditionally.
  `draft`/`validation_failed`/`ready_for_review` rows stay mutable until
  decided.
- `DocumentService.record_approval_decision` (`backend/services/
  document_service.py`) is the only writer of `approved`/`rejected`. It
  pre-checks the row is still in a decidable status before writing —
  the same "friendly service-level check backstopped by a DB trigger"
  pattern `ResumeService` and `OpportunityService` already use — and
  records an `AuditEvent` (`document_approved`/`document_rejected`) with
  the rationale in `details_json` rather than a new column, mirroring how
  hard-filter override rationale is stored (`OE-ADR-016`).
- **`validation_failed` documents remain approvable.** The constitution's
  own stance is "flag uncertain claims," not "block them" — a flagged
  claim might be a defensible paraphrase (confirmed directly: the first
  real cover letter generated under `OE-ADR-023` flagged mostly
  reasonable interpretive framing, not fabrication). Routing it to Scott
  for a judgment call, rather than making `validation_failed` a dead end,
  is the point.
- **No unapprove/unreject, ever.** Consistent with every other
  append-only table here: a correction is always a new version — already
  true today, since regenerating already creates the next version
  regardless of the previous one's status.
- **Distinct from `approval_requests`.** That table (`action_type IN
  ('application', 'email', 'external_message', 'contract',
  'identity_verification', 'financial_commitment')`) is reserved for
  actual restricted external actions and remains completely unbuilt.
  Approving a résumé draft here only ever writes
  `generated_documents.status` — it is not, and must never become,
  authorization to send anything anywhere.

### Consequences

- `generated_documents` now has the same immutability guarantee every
  other significant-decision table in this schema has.
- The opportunity detail page's document sections show a permanent
  decision (badge + rationale + timestamp) once approved/rejected instead
  of leaving drafts in an ambiguous, endlessly-re-editable state.
- DOCX/PDF export — the one remaining v0.2 item — now has a natural
  trigger point: exporting an *approved* document, not an undecided
  draft.

---

## OE-ADR-025 — DOCX/PDF export renders a bounded Markdown subset, on demand

**Status:** Accepted
**Date:** 2026-08-06

### Context

v0.2's last item. Every generated document is stored and shown as plain
text. Checking real content generated this session showed formatting is
model-discretionary, not something any prompt currently requests or
forbids: the real cover letter for the Platform.sh opportunity was plain
prose (and contains Scott's actual name, address, and phone number,
confirming this content is genuinely sensitive and stays local), while
the real fit report for the same opportunity used `#`/`##` Markdown
headers and `**bold**`. Dumping raw `#`/`**` characters into an exported
DOCX/PDF would look broken.

### Decision

- `backend/documents/markdown_subset.py` parses only what's actually been
  observed: `#`/`##`/`###` headings, `**bold**` spans, and
  blank-line-separated paragraphs. No lists, links, or tables — an
  explicit scope boundary, not an oversight; an unrecognized construct
  falls through as plain paragraph text rather than being mangled.
  Heading detection only requires the block's *first line* to match,
  so a heading immediately followed by body text on the next line (no
  blank line) still splits correctly, not just the blank-line convention
  the real content happens to use today.
- `backend/documents/export.py` has two pure functions,
  `render_docx`/`render_pdf`, both consuming the same parsed block list —
  one parser, two renderers. `render_docx` reuses `python-docx` (already
  a dependency for *reading* imported résumés, now also used to write).
  `render_pdf` uses `reportlab` (new dependency) — a pure-Python PDF
  library with no system binary requirement, ruling out e.g.
  LibreOffice-headless conversion.
- **Every run of user-supplied text through ReportLab's `Paragraph` is
  XML-escaped (`xml.sax.saxutils.escape`) before any `<b>` markup is
  added.** `Paragraph` interprets its input as a small XML dialect;
  unescaped `&`/`<`/`>` in real content (an org name like "AT&T", a
  description containing `<script>`-looking text) would otherwise raise
  or silently corrupt output. Caught during implementation by testing
  against a deliberately adversarial sample, not left to surface in
  production.
- **Rendering is on-demand, not persisted.** Unlike the `.txt` original
  (content-hash-addressed, stored once), DOCX/PDF bytes are generated
  fresh per request and returned directly — no AI call involved, cheap
  and deterministic, so there's nothing to gain from storing three
  format copies per version.
- **Export is available regardless of document status** (confirmed with
  Scott before implementing) — `ready_for_review`, `validation_failed`,
  `approved`, and `rejected` are all exportable. It's a local format
  conversion of text that already exists, not a new approval boundary;
  restricting it to `approved` only would block previewing a draft's
  actual formatting before deciding on it.

### Consequences

- v0.2 is complete: import → generate (résumé/cover letter/fit report) →
  approve/reject → export, all working end to end against real data.
- Any future document type (a `proposal`, per the schema's existing
  `document_type` check constraint) gets export for free — `export.py`
  only depends on parsed blocks, not on which kind of document produced
  them.
- If the model ever produces a construct outside this subset (a list, a
  link), it will render as an unstructured paragraph rather than broken
  markup — a known, acceptable degradation documented here rather than a
  silent gap.

---

## OE-ADR-026 — Tailored résumé: structured generation, static identity data, ATS-conscious template

**Status:** Accepted
**Date:** 2026-08-06

### Context

Scott shared the actual résumé template he'd built in an earlier
Claude.ai session (navy/green header, bold section rules, a Core
Competencies grid, bold company/location + bold-italic title/italic
dates per role) and his full master résumé — ten roles back to 1996,
Education, Certifications. His goal, stated directly: get past the
automated résumé screeners (ATS) real companies use, not just produce
readable prose. Free-form prose/Markdown (`OE-ADR-025`) can't reproduce
that template — a résumé is structured data (a summary, a competency
list, role entries each with their own bullets), not a paragraph. This
decision covers the tailored résumé only; cover letter and fit report
are unaffected.

Every design choice below was worked out through direct dialogue with
Scott, not decided unilaterally:

### Decision

- **The identity header, Education, and Certifications are static data
  Claude never sees or generates.** `config/profile.json` (gitignored,
  mirroring the `.env`/`.env.example` precedent — real file local-only,
  `.example` committed) holds `full_name`, `title_line`, `location`,
  `phone`, `email`, `education`, and `certifications` (names only — no
  license/credential IDs, per Scott: "available upon request"). This
  isn't a prompt-engineering choice; it's structural — there is no code
  path by which the AI can alter this data, the same guarantee
  `master_resume_read_only` gets from DB triggers, achieved here by the
  data simply never entering the AI's input or output.
- **`generate_tailored_resume` now returns structured JSON** —
  `professional_summary`, `core_competencies` (9-15 phrases), and
  `experience` (each role: `company`/`location`/`title`/`dates`/
  `bullets`) — instead of one prose string. `DocumentGenerationResult.content`
  stays `str` (no interface change elsewhere); the provider
  `json.dumps()`s the structured dict into it.
- **Role selection is a relevance judgment, not a hard year cutoff.**
  The prompt asks the model to order and select roles by genuine
  relevance to *this* opportunity — recency is the default signal, but a
  real match (a healthcare-IT posting and an older healthcare-IT role)
  can override it. A role that doesn't earn full detail still appears
  (`bullets: []` renders as a single compressed company/title/dates
  line) — the work history is never truncated, only de-emphasized.
  Same grounding discipline as `OE-ADR-020`: never invent an employer,
  title, date, or bullet not in the master résumé, extended from
  "never invent" to also cover "never omit a role from history entirely."
  Target: roughly 3-5 roles with full bullets, rendering to about two
  pages — the accepted norm for 25 years of senior-level experience.
- **Core Competencies renders as a plain bullet list, not the original
  template's table.** The one deliberate visual deviation from Scott's
  template — bordered/shaded tables are a known, real ATS-parsing risk;
  every other element (bold, bullets, standard section headings) is
  already ATS-safe. Enforced by an automated test
  (`tests/test_resume_render.py`'s `len(document.tables) == 0`), not
  just a visual claim.
- **`backend/documents/resume_render.py`** renders the actual template
  (navy `#1F3864`/green `#1F6357`, chosen as reasonable representative
  values — Scott can request exact tweaks once he sees real rendered
  output) via `python-docx`/`reportlab`, separate from the generic
  Markdown-subset path (`OE-ADR-025`) cover letters and fit reports
  still use.
- **Legacy fallback.** The two tailored-résumé versions generated before
  this change are plain prose, not JSON. `parse_resume_content` returns
  `None` for non-JSON content; both the in-app preview and export fall
  back to the pre-existing generic renderer instead of crashing — a
  one-time compatibility note, not an ongoing design.
- **Test fixtures never depend on the real, gitignored `config/profile.json`.**
  `tests/fixtures/profile_sample.json` is a committed placeholder;
  `client_and_app`'s `Settings` explicitly points `profile_path` at it —
  caught during implementation (the export tests initially fell through
  to the real local file and would have broken in CI, where it doesn't
  exist).

### Consequences

- The exported tailored résumé now genuinely resembles the template
  Scott showed, not generic formatted prose.
- Every future opportunity's tailored résumé is grounded in the same
  full work history, letting the AI make a fresh relevance judgment per
  posting rather than Scott re-curating roles by hand each time.
- The cover letter's own template work (deliberately simple/linear for
  ATS safety, per Scott's direction) is a separate, not-yet-started
  follow-on — this ADR covers the résumé only.

### Addendum — hitting the 2-page target (2026-08-06)

The first live render came in at ~4 pages against real content (15
competencies, 4 full-bullet roles). Fixed with two independent changes,
both requested directly by Scott:

- **Layout**: 0.25" margins on all four sides (his real-world default for
  printed documents), smaller body/bullet font (9-9.5pt vs. the initial
  10-11pt), and tighter paragraph/heading spacing throughout both
  renderers — verified this alone brought the *same* v2 content from 4
  pages to 3.
- **Density**: tightened the generation prompt's guidance — competencies
  9-12 (was 9-15), roles with full bullets 3-4 (was 3-5), bullets per
  role 3-5 concise one-liners (was 4-7) — reasoning that an ATS reads
  smaller fonts fine, so cutting font size costs nothing, while cutting
  real content should be minimized and only pushed as far as actually
  needed.

Combined, a fresh live generation rendered to exactly 2 pages with all 9
roles still present in the work history (compressed roles still appear
as a single line — nothing dropped, per the original decision above).
