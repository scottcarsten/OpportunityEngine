"""SQLAlchemy ORM models mirroring `database/schema.sql`.

Column types, constraints, and defaults are transcribed from the physical
schema. Boolean-shaped SQLite columns (0/1 flags) are typed as ``Integer``
rather than ``Boolean`` so Python ``bool`` values continue to bind exactly as
they did against the raw ``sqlite3`` layer, and so the physical type matches
schema.sql's own ``INTEGER ... CHECK (x IN (0, 1))`` columns precisely.
"""

from sqlalchemy import (
    REAL,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


_UTC_NOW = text("strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")


class Base(DeclarativeBase):
    """Declarative base shared by every OpportunityEngine ORM model."""


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    configuration_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (CheckConstraint("enabled IN (0, 1)", name="ck_sources_enabled"),)


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    started_at: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[str | None] = mapped_column(Text)
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_created: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    records_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partially_succeeded', "
            "'failed', 'cancelled')",
            name="ck_collection_runs_status",
        ),
        CheckConstraint("records_seen >= 0", name="ck_collection_runs_records_seen"),
        CheckConstraint("records_created >= 0", name="ck_collection_runs_records_created"),
        CheckConstraint("records_updated >= 0", name="ck_collection_runs_records_updated"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NOT NULL",
            name="ck_collection_runs_completed_requires_started",
        ),
        Index("idx_collection_runs_source_status", "source_id", "status", "created_at"),
    )


class SourceRecord(Base):
    __tablename__ = "source_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    collection_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL")
    )
    external_id: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload_json: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    last_seen_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_records_source_external"),
        UniqueConstraint("source_id", "payload_hash", name="uq_source_records_source_payload"),
        Index("idx_source_records_canonical_url", "canonical_url"),
        Index("idx_source_records_last_seen", "last_seen_at"),
    )


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    organization_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    remote_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'unknown'")
    )
    engagement_type: Mapped[str | None] = mapped_column(Text)
    tax_type: Mapped[str | None] = mapped_column(Text)
    schedule_text: Mapped[str | None] = mapped_column(Text)
    compensation_min: Mapped[float | None] = mapped_column(REAL)
    compensation_max: Mapped[float | None] = mapped_column(REAL)
    compensation_currency: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'USD'")
    )
    compensation_period: Mapped[str | None] = mapped_column(Text)
    requires_travel: Mapped[int | None] = mapped_column(Integer)
    requires_relocation: Mapped[int | None] = mapped_column(Integer)
    requires_clearance: Mapped[int | None] = mapped_column(Integer)
    replaces_full_time_work: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[str | None] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'new'")
    )
    first_seen_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    last_seen_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (
        CheckConstraint(
            "remote_status IN ('remote', 'hybrid', 'onsite', 'unknown')",
            name="ck_opportunities_remote_status",
        ),
        CheckConstraint(
            "engagement_type IS NULL OR engagement_type IN ("
            "'contract', 'consulting', 'project', 'part_time', 'full_time', "
            "'temporary', 'internship', 'unknown')",
            name="ck_opportunities_engagement_type",
        ),
        CheckConstraint(
            "tax_type IS NULL OR tax_type IN ('1099', 'w2', 'corp_to_corp', 'unknown')",
            name="ck_opportunities_tax_type",
        ),
        CheckConstraint(
            "compensation_period IS NULL OR compensation_period IN ("
            "'hour', 'day', 'week', 'month', 'year', 'fixed', 'unknown')",
            name="ck_opportunities_compensation_period",
        ),
        CheckConstraint(
            "requires_travel IN (0, 1) OR requires_travel IS NULL",
            name="ck_opportunities_requires_travel",
        ),
        CheckConstraint(
            "requires_relocation IN (0, 1) OR requires_relocation IS NULL",
            name="ck_opportunities_requires_relocation",
        ),
        CheckConstraint(
            "requires_clearance IN (0, 1) OR requires_clearance IS NULL",
            name="ck_opportunities_requires_clearance",
        ),
        CheckConstraint(
            "replaces_full_time_work IN (0, 1) OR replaces_full_time_work IS NULL",
            name="ck_opportunities_replaces_full_time_work",
        ),
        CheckConstraint(
            "lifecycle_status IN ('new', 'eligible', 'ineligible', 'shortlisted', "
            "'deferred', 'rejected', 'preparing', 'ready_for_review', 'closed', 'expired')",
            name="ck_opportunities_lifecycle_status",
        ),
        CheckConstraint(
            "compensation_min IS NULL OR compensation_max IS NULL "
            "OR compensation_min <= compensation_max",
            name="ck_opportunities_compensation_range",
        ),
        Index(
            "idx_opportunities_status_score_input",
            "lifecycle_status",
            "remote_status",
            "engagement_type",
        ),
        Index("idx_opportunities_last_seen", "last_seen_at"),
    )


class OpportunitySource(Base):
    __tablename__ = "opportunity_sources"

    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    source_record_id: Mapped[int] = mapped_column(
        ForeignKey("source_records.id", ondelete="RESTRICT"), primary_key=True
    )
    is_primary: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    linked_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (
        CheckConstraint("is_primary IN (0, 1)", name="ck_opportunity_sources_is_primary"),
        Index("idx_opportunity_sources_primary", "opportunity_id", "is_primary"),
    )


class DeduplicationDecision(Base):
    __tablename__ = "deduplication_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    retained_opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    duplicate_opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    method: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (
        CheckConstraint(
            "method IN ('external_id', 'canonical_url', 'fingerprint', 'similarity', 'manual')",
            name="ck_deduplication_decisions_method",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_deduplication_decisions_confidence",
        ),
        CheckConstraint(
            "decided_by IN ('system', 'ai', 'scott')",
            name="ck_deduplication_decisions_decided_by",
        ),
        CheckConstraint(
            "retained_opportunity_id <> duplicate_opportunity_id",
            name="ck_deduplication_decisions_distinct",
        ),
        UniqueConstraint(
            "retained_opportunity_id",
            "duplicate_opportunity_id",
            name="uq_deduplication_decisions_pair",
        ),
    )


class FilterEvaluation(Base):
    __tablename__ = "filter_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    constitution_version: Mapped[str] = mapped_column(Text, nullable=False)
    rule_code: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evaluator_version: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('pass', 'fail', 'unknown', 'manual_review')",
            name="ck_filter_evaluations_outcome",
        ),
        Index("idx_filter_evaluations_opportunity_time", "opportunity_id", "evaluated_at"),
        Index("idx_filter_evaluations_rule_outcome", "rule_code", "outcome"),
    )


class ScoringRun(Base):
    __tablename__ = "scoring_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_version: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    overall_score: Mapped[float | None] = mapped_column(REAL)
    confidence: Mapped[float | None] = mapped_column(REAL)
    fit_summary: Mapped[str | None] = mapped_column(Text)
    concerns: Mapped[str | None] = mapped_column(Text)
    structured_output_json: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    completed_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'invalid')",
            name="ck_scoring_runs_status",
        ),
        CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0.0 AND overall_score <= 100.0)",
            name="ck_scoring_runs_overall_score",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_scoring_runs_confidence",
        ),
        Index("idx_scoring_runs_opportunity_time", "opportunity_id", "started_at"),
    )


class ScoreComponent(Base):
    __tablename__ = "score_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scoring_run_id: Mapped[int] = mapped_column(
        ForeignKey("scoring_runs.id", ondelete="CASCADE"), nullable=False
    )
    component_code: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(REAL, nullable=False)
    weight: Mapped[float] = mapped_column(REAL, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("score >= 0.0 AND score <= 100.0", name="ck_score_components_score"),
        CheckConstraint("weight >= 0.0", name="ck_score_components_weight"),
        UniqueConstraint(
            "scoring_run_id", "component_code", name="uq_score_components_run_component"
        ),
    )


class ResumeSource(Base):
    __tablename__ = "resume_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_master: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    imported_by: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'scott'")
    )
    imported_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_sources.id", ondelete="RESTRICT")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("version > 0", name="ck_resume_sources_version"),
        CheckConstraint("is_master IN (0, 1)", name="ck_resume_sources_is_master"),
    )


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    resume_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_sources.id", ondelete="RESTRICT")
    )
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'draft'")
    )
    storage_path: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    unsupported_claims_json: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    reviewed_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "document_type IN ('tailored_resume', 'cover_letter', 'fit_report', 'proposal')",
            name="ck_generated_documents_document_type",
        ),
        CheckConstraint("version > 0", name="ck_generated_documents_version"),
        CheckConstraint(
            "status IN ('draft', 'validation_failed', 'ready_for_review', 'approved', "
            "'rejected', 'superseded')",
            name="ck_generated_documents_status",
        ),
        UniqueConstraint(
            "opportunity_id", "document_type", "version", name="uq_generated_documents_version"
        ),
        Index("idx_generated_documents_opportunity_status", "opportunity_id", "status"),
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'scott'"))
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('shortlist', 'reject', 'defer', 'request_preparation', 'reopen')",
            name="ck_review_decisions_decision",
        ),
        Index("idx_review_decisions_opportunity_time", "opportunity_id", "created_at"),
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    generated_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_documents.id", ondelete="SET NULL")
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    resolved_by: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[str | None] = mapped_column(Text)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    approval_token_hash: Mapped[str | None] = mapped_column(Text, unique=True)

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('application', 'email', 'external_message', 'contract', "
            "'identity_verification', 'financial_commitment')",
            name="ck_approval_requests_action_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired', 'consumed')",
            name="ck_approval_requests_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR (status <> 'pending')",
            name="ck_approval_requests_pending_unresolved",
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_by IS NOT NULL",
            name="ck_approval_requests_resolution_actor",
        ),
        Index("idx_approval_requests_status_time", "status", "requested_at"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    notification_type: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'local'")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'queued'")
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    is_external: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    approval_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="RESTRICT")
    )
    queued_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)
    sent_at: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "channel IN ('local', 'dashboard', 'email', 'sms', 'ntfy', 'other')",
            name="ck_notifications_channel",
        ),
        CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'cancelled')",
            name="ck_notifications_status",
        ),
        CheckConstraint("is_external IN (0, 1)", name="ck_notifications_is_external"),
        CheckConstraint(
            "is_external = 0 OR approval_request_id IS NOT NULL",
            name="ck_notifications_external_requires_approval",
        ),
        Index("idx_notifications_status_time", "status", "queued_at"),
    )


class AuditEventRecord(Base):
    """ORM row for `audit_events`.

    Named `AuditEventRecord` (not `AuditEvent`) to avoid colliding with the
    plain dataclass DTO of the same concept in
    `backend.services.audit_service`.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_identifier: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    constitution_version: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=_UTC_NOW)

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('scott', 'system', 'ai', 'external')",
            name="ck_audit_events_actor_type",
        ),
        Index("idx_audit_events_correlation", "correlation_id", "occurred_at"),
        Index("idx_audit_events_entity", "entity_type", "entity_id", "occurred_at"),
    )
