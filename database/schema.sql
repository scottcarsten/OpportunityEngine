-- OpportunityEngine initial SQLite schema
-- Version: 0.1.0
-- Governing policy: config/constitution.json
--
-- Connection requirement:
--   PRAGMA foreign_keys = ON;
--
-- Timestamps are stored as UTC ISO-8601 text. Application code must keep
-- transactions short and treat historical evaluation/audit rows as immutable.
--
-- Retained as human-readable documentation of the physical design. The
-- applied source of truth is now the Alembic migrations in
-- `database/migrations/` (see `backend/db/models.py` for the corresponding
-- SQLAlchemy ORM models); this file is no longer executed at runtime.

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE schema_versions (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO schema_versions (version, description)
VALUES (1, 'Initial OpportunityEngine persistence model');

CREATE TABLE sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    base_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    configuration_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE collection_runs (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'succeeded', 'partially_succeeded', 'failed', 'cancelled')
    ),
    correlation_id TEXT NOT NULL UNIQUE,
    started_at TEXT,
    completed_at TEXT,
    records_seen INTEGER NOT NULL DEFAULT 0 CHECK (records_seen >= 0),
    records_created INTEGER NOT NULL DEFAULT 0 CHECK (records_created >= 0),
    records_updated INTEGER NOT NULL DEFAULT 0 CHECK (records_updated >= 0),
    error_summary TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (completed_at IS NULL OR started_at IS NOT NULL)
);

CREATE TABLE source_records (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    collection_run_id INTEGER REFERENCES collection_runs(id) ON DELETE SET NULL,
    external_id TEXT,
    canonical_url TEXT,
    payload_hash TEXT NOT NULL,
    raw_payload_json TEXT,
    retrieved_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (source_id, external_id),
    UNIQUE (source_id, payload_hash)
);

CREATE TABLE opportunities (
    id INTEGER PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    organization_name TEXT,
    description TEXT,
    canonical_url TEXT,
    location_text TEXT,
    remote_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        remote_status IN ('remote', 'hybrid', 'onsite', 'unknown')
    ),
    engagement_type TEXT CHECK (
        engagement_type IS NULL OR engagement_type IN (
            'contract', 'consulting', 'project', 'part_time', 'full_time', 'temporary', 'internship', 'unknown'
        )
    ),
    tax_type TEXT CHECK (
        tax_type IS NULL OR tax_type IN ('1099', 'w2', 'corp_to_corp', 'unknown')
    ),
    schedule_text TEXT,
    compensation_min REAL,
    compensation_max REAL,
    compensation_currency TEXT NOT NULL DEFAULT 'USD',
    compensation_period TEXT CHECK (
        compensation_period IS NULL OR compensation_period IN (
            'hour', 'day', 'week', 'month', 'year', 'fixed', 'unknown'
        )
    ),
    requires_travel INTEGER CHECK (requires_travel IN (0, 1) OR requires_travel IS NULL),
    requires_relocation INTEGER CHECK (requires_relocation IN (0, 1) OR requires_relocation IS NULL),
    requires_clearance INTEGER CHECK (requires_clearance IN (0, 1) OR requires_clearance IS NULL),
    replaces_full_time_work INTEGER CHECK (
        replaces_full_time_work IN (0, 1) OR replaces_full_time_work IS NULL
    ),
    published_at TEXT,
    expires_at TEXT,
    lifecycle_status TEXT NOT NULL DEFAULT 'new' CHECK (
        lifecycle_status IN (
            'new', 'eligible', 'ineligible', 'shortlisted', 'deferred',
            'rejected', 'preparing', 'ready_for_review', 'closed', 'expired'
        )
    ),
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (
        compensation_min IS NULL OR compensation_max IS NULL OR compensation_min <= compensation_max
    )
);

CREATE TABLE opportunity_sources (
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    source_record_id INTEGER NOT NULL REFERENCES source_records(id) ON DELETE RESTRICT,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    linked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (opportunity_id, source_record_id)
);

CREATE TABLE deduplication_decisions (
    id INTEGER PRIMARY KEY,
    retained_opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    duplicate_opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    method TEXT NOT NULL CHECK (
        method IN ('external_id', 'canonical_url', 'fingerprint', 'similarity', 'manual')
    ),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    explanation TEXT NOT NULL,
    decided_by TEXT NOT NULL CHECK (decided_by IN ('system', 'ai', 'scott')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (retained_opportunity_id <> duplicate_opportunity_id),
    UNIQUE (retained_opportunity_id, duplicate_opportunity_id)
);

CREATE TABLE filter_evaluations (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    constitution_version TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('pass', 'fail', 'unknown', 'manual_review')),
    evidence TEXT,
    explanation TEXT NOT NULL,
    evaluator_version TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    evaluated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE scoring_runs (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'invalid')),
    scoring_version TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_version TEXT,
    input_hash TEXT NOT NULL,
    overall_score REAL CHECK (overall_score IS NULL OR (overall_score >= 0.0 AND overall_score <= 100.0)),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    fit_summary TEXT,
    concerns TEXT,
    structured_output_json TEXT,
    error_summary TEXT,
    correlation_id TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    completed_at TEXT
);

CREATE TABLE score_components (
    id INTEGER PRIMARY KEY,
    scoring_run_id INTEGER NOT NULL REFERENCES scoring_runs(id) ON DELETE CASCADE,
    component_code TEXT NOT NULL,
    score REAL NOT NULL CHECK (score >= 0.0 AND score <= 100.0),
    weight REAL NOT NULL CHECK (weight >= 0.0),
    explanation TEXT NOT NULL,
    UNIQUE (scoring_run_id, component_code)
);

CREATE TABLE resume_sources (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL UNIQUE CHECK (version > 0),
    file_name TEXT NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL,
    is_master INTEGER NOT NULL DEFAULT 1 CHECK (is_master IN (0, 1)),
    imported_by TEXT NOT NULL DEFAULT 'scott',
    imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    supersedes_id INTEGER REFERENCES resume_sources(id) ON DELETE RESTRICT,
    notes TEXT
);

CREATE TABLE generated_documents (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    resume_source_id INTEGER REFERENCES resume_sources(id) ON DELETE RESTRICT,
    document_type TEXT NOT NULL CHECK (
        document_type IN ('tailored_resume', 'cover_letter', 'fit_report', 'proposal')
    ),
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'validation_failed', 'ready_for_review', 'approved', 'rejected', 'superseded')
    ),
    storage_path TEXT,
    content_hash TEXT,
    provider TEXT,
    model TEXT,
    prompt_version TEXT,
    unsupported_claims_json TEXT,
    generated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    reviewed_at TEXT,
    UNIQUE (opportunity_id, document_type, version)
);

CREATE TABLE review_decisions (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK (
        decision IN ('shortlist', 'reject', 'defer', 'request_preparation', 'reopen')
    ),
    actor TEXT NOT NULL DEFAULT 'scott',
    rationale TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE approval_requests (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE CASCADE,
    generated_document_id INTEGER REFERENCES generated_documents(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL CHECK (
        action_type IN (
            'application', 'email', 'external_message', 'contract',
            'identity_verification', 'financial_commitment'
        )
    ),
    target TEXT NOT NULL,
    scope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired', 'consumed')
    ),
    requested_by TEXT NOT NULL,
    requested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resolved_by TEXT,
    resolved_at TEXT,
    expires_at TEXT,
    resolution_note TEXT,
    approval_token_hash TEXT UNIQUE,
    CHECK (
        (status = 'pending' AND resolved_at IS NULL)
        OR (status <> 'pending')
    ),
    CHECK (
        resolved_at IS NULL OR resolved_by IS NOT NULL
    )
);

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'local' CHECK (
        channel IN ('local', 'dashboard', 'email', 'sms', 'other')
    ),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (
        status IN ('queued', 'sent', 'failed', 'cancelled')
    ),
    subject TEXT NOT NULL,
    body TEXT,
    is_external INTEGER NOT NULL DEFAULT 0 CHECK (is_external IN (0, 1)),
    approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE RESTRICT,
    queued_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sent_at TEXT,
    error_summary TEXT,
    CHECK (is_external = 0 OR approval_request_id IS NOT NULL)
);

CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('scott', 'system', 'ai', 'external')),
    actor_identifier TEXT,
    entity_type TEXT,
    entity_id INTEGER,
    constitution_version TEXT,
    summary TEXT NOT NULL,
    details_json TEXT,
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_collection_runs_source_status
    ON collection_runs (source_id, status, created_at);

CREATE INDEX idx_source_records_canonical_url
    ON source_records (canonical_url);

CREATE INDEX idx_source_records_last_seen
    ON source_records (last_seen_at);

CREATE INDEX idx_opportunities_status_score_input
    ON opportunities (lifecycle_status, remote_status, engagement_type);

CREATE INDEX idx_opportunities_last_seen
    ON opportunities (last_seen_at);

CREATE INDEX idx_opportunity_sources_primary
    ON opportunity_sources (opportunity_id, is_primary);

CREATE INDEX idx_filter_evaluations_opportunity_time
    ON filter_evaluations (opportunity_id, evaluated_at);

CREATE INDEX idx_filter_evaluations_rule_outcome
    ON filter_evaluations (rule_code, outcome);

CREATE INDEX idx_scoring_runs_opportunity_time
    ON scoring_runs (opportunity_id, started_at);

CREATE INDEX idx_generated_documents_opportunity_status
    ON generated_documents (opportunity_id, status);

CREATE INDEX idx_review_decisions_opportunity_time
    ON review_decisions (opportunity_id, created_at);

CREATE INDEX idx_approval_requests_status_time
    ON approval_requests (status, requested_at);

CREATE INDEX idx_notifications_status_time
    ON notifications (status, queued_at);

CREATE INDEX idx_audit_events_correlation
    ON audit_events (correlation_id, occurred_at);

CREATE INDEX idx_audit_events_entity
    ON audit_events (entity_type, entity_id, occurred_at);

CREATE TRIGGER protect_master_resume_update
BEFORE UPDATE ON resume_sources
WHEN OLD.is_master = 1
BEGIN
    SELECT RAISE(ABORT, 'Master resume versions are immutable; import a new version instead.');
END;

CREATE TRIGGER protect_master_resume_delete
BEFORE DELETE ON resume_sources
WHEN OLD.is_master = 1
BEGIN
    SELECT RAISE(ABORT, 'Master resume versions cannot be deleted.');
END;

CREATE TRIGGER protect_filter_evaluation_update
BEFORE UPDATE ON filter_evaluations
BEGIN
    SELECT RAISE(ABORT, 'Filter evaluations are append-only.');
END;

CREATE TRIGGER protect_filter_evaluation_delete
BEFORE DELETE ON filter_evaluations
BEGIN
    SELECT RAISE(ABORT, 'Filter evaluations are append-only.');
END;

CREATE TRIGGER protect_scoring_run_update
BEFORE UPDATE ON scoring_runs
WHEN OLD.status IN ('succeeded', 'failed', 'invalid')
BEGIN
    SELECT RAISE(ABORT, 'Completed scoring runs are immutable.');
END;

CREATE TRIGGER protect_scoring_run_delete
BEFORE DELETE ON scoring_runs
BEGIN
    SELECT RAISE(ABORT, 'Scoring runs are append-only.');
END;

CREATE TRIGGER protect_audit_event_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events are append-only.');
END;

CREATE TRIGGER protect_audit_event_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events are append-only.');
END;

CREATE TRIGGER require_approval_for_external_notification_insert
BEFORE INSERT ON notifications
WHEN NEW.is_external = 1
BEGIN
    SELECT CASE
        WHEN NEW.approval_request_id IS NULL
        THEN RAISE(ABORT, 'External notifications require an approval request.')
        WHEN NOT EXISTS (
            SELECT 1
            FROM approval_requests
            WHERE id = NEW.approval_request_id
              AND status = 'approved'
              AND action_type IN ('email', 'external_message')
              AND (expires_at IS NULL OR expires_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        THEN RAISE(ABORT, 'External notification approval is missing, invalid, or expired.')
    END;
END;

COMMIT;
