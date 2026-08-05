"""Initial OpportunityEngine persistence model.

Mirrors `database/schema.sql` exactly: table order, columns, constraints,
indexes, and the six constitutional-safeguard triggers (append-only audit
and filter history, immutable master résumé, immutable completed scoring
runs, approval-gated external notifications).

Revision ID: 0001
Revises:
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UTC_NOW = sa.text("strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")


def upgrade() -> None:
    op.create_table(
        "schema_versions",
        sa.Column("version", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("applied_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text()),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("configuration_json", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_sources_enabled"),
    )

    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False, unique=True),
        sa.Column("started_at", sa.Text()),
        sa.Column("completed_at", sa.Text()),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_summary", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partially_succeeded', "
            "'failed', 'cancelled')",
            name="ck_collection_runs_status",
        ),
        sa.CheckConstraint("records_seen >= 0", name="ck_collection_runs_records_seen"),
        sa.CheckConstraint("records_created >= 0", name="ck_collection_runs_records_created"),
        sa.CheckConstraint("records_updated >= 0", name="ck_collection_runs_records_updated"),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NOT NULL",
            name="ck_collection_runs_completed_requires_started",
        ),
    )
    op.create_index(
        "idx_collection_runs_source_status",
        "collection_runs",
        ["source_id", "status", "created_at"],
    )

    op.create_table(
        "source_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "collection_run_id",
            sa.Integer(),
            sa.ForeignKey("collection_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("external_id", sa.Text()),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("raw_payload_json", sa.Text()),
        sa.Column("retrieved_at", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("last_seen_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.UniqueConstraint(
            "source_id", "external_id", name="uq_source_records_source_external"
        ),
        sa.UniqueConstraint("source_id", "payload_hash", name="uq_source_records_source_payload"),
    )
    op.create_index("idx_source_records_canonical_url", "source_records", ["canonical_url"])
    op.create_index("idx_source_records_last_seen", "source_records", ["last_seen_at"])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("organization_name", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("location_text", sa.Text()),
        sa.Column(
            "remote_status", sa.Text(), nullable=False, server_default=sa.text("'unknown'")
        ),
        sa.Column("engagement_type", sa.Text()),
        sa.Column("tax_type", sa.Text()),
        sa.Column("schedule_text", sa.Text()),
        sa.Column("compensation_min", sa.REAL()),
        sa.Column("compensation_max", sa.REAL()),
        sa.Column(
            "compensation_currency", sa.Text(), nullable=False, server_default=sa.text("'USD'")
        ),
        sa.Column("compensation_period", sa.Text()),
        sa.Column("requires_travel", sa.Integer()),
        sa.Column("requires_relocation", sa.Integer()),
        sa.Column("requires_clearance", sa.Integer()),
        sa.Column("replaces_full_time_work", sa.Integer()),
        sa.Column("published_at", sa.Text()),
        sa.Column("expires_at", sa.Text()),
        sa.Column("lifecycle_status", sa.Text(), nullable=False, server_default=sa.text("'new'")),
        sa.Column("first_seen_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("last_seen_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.CheckConstraint(
            "remote_status IN ('remote', 'hybrid', 'onsite', 'unknown')",
            name="ck_opportunities_remote_status",
        ),
        sa.CheckConstraint(
            "engagement_type IS NULL OR engagement_type IN ("
            "'contract', 'consulting', 'project', 'part_time', 'full_time', "
            "'temporary', 'internship', 'unknown')",
            name="ck_opportunities_engagement_type",
        ),
        sa.CheckConstraint(
            "tax_type IS NULL OR tax_type IN ('1099', 'w2', 'corp_to_corp', 'unknown')",
            name="ck_opportunities_tax_type",
        ),
        sa.CheckConstraint(
            "compensation_period IS NULL OR compensation_period IN ("
            "'hour', 'day', 'week', 'month', 'year', 'fixed', 'unknown')",
            name="ck_opportunities_compensation_period",
        ),
        sa.CheckConstraint(
            "requires_travel IN (0, 1) OR requires_travel IS NULL",
            name="ck_opportunities_requires_travel",
        ),
        sa.CheckConstraint(
            "requires_relocation IN (0, 1) OR requires_relocation IS NULL",
            name="ck_opportunities_requires_relocation",
        ),
        sa.CheckConstraint(
            "requires_clearance IN (0, 1) OR requires_clearance IS NULL",
            name="ck_opportunities_requires_clearance",
        ),
        sa.CheckConstraint(
            "replaces_full_time_work IN (0, 1) OR replaces_full_time_work IS NULL",
            name="ck_opportunities_replaces_full_time_work",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('new', 'eligible', 'ineligible', 'shortlisted', "
            "'deferred', 'rejected', 'preparing', 'ready_for_review', 'closed', 'expired')",
            name="ck_opportunities_lifecycle_status",
        ),
        sa.CheckConstraint(
            "compensation_min IS NULL OR compensation_max IS NULL "
            "OR compensation_min <= compensation_max",
            name="ck_opportunities_compensation_range",
        ),
    )
    op.create_index(
        "idx_opportunities_status_score_input",
        "opportunities",
        ["lifecycle_status", "remote_status", "engagement_type"],
    )
    op.create_index("idx_opportunities_last_seen", "opportunities", ["last_seen_at"])

    op.create_table(
        "opportunity_sources",
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_record_id",
            sa.Integer(),
            sa.ForeignKey("source_records.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("is_primary", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("linked_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.CheckConstraint("is_primary IN (0, 1)", name="ck_opportunity_sources_is_primary"),
    )
    op.create_index(
        "idx_opportunity_sources_primary",
        "opportunity_sources",
        ["opportunity_id", "is_primary"],
    )

    op.create_table(
        "deduplication_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "retained_opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "duplicate_opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("confidence", sa.REAL()),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.CheckConstraint(
            "method IN ('external_id', 'canonical_url', 'fingerprint', 'similarity', 'manual')",
            name="ck_deduplication_decisions_method",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_deduplication_decisions_confidence",
        ),
        sa.CheckConstraint(
            "decided_by IN ('system', 'ai', 'scott')",
            name="ck_deduplication_decisions_decided_by",
        ),
        sa.CheckConstraint(
            "retained_opportunity_id <> duplicate_opportunity_id",
            name="ck_deduplication_decisions_distinct",
        ),
        sa.UniqueConstraint(
            "retained_opportunity_id",
            "duplicate_opportunity_id",
            name="uq_deduplication_decisions_pair",
        ),
    )

    op.create_table(
        "filter_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("constitution_version", sa.Text(), nullable=False),
        sa.Column("rule_code", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text()),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evaluator_version", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("evaluated_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.CheckConstraint(
            "outcome IN ('pass', 'fail', 'unknown', 'manual_review')",
            name="ck_filter_evaluations_outcome",
        ),
    )
    op.create_index(
        "idx_filter_evaluations_opportunity_time",
        "filter_evaluations",
        ["opportunity_id", "evaluated_at"],
    )
    op.create_index(
        "idx_filter_evaluations_rule_outcome", "filter_evaluations", ["rule_code", "outcome"]
    )

    op.create_table(
        "scoring_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("scoring_version", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("overall_score", sa.REAL()),
        sa.Column("confidence", sa.REAL()),
        sa.Column("fit_summary", sa.Text()),
        sa.Column("concerns", sa.Text()),
        sa.Column("structured_output_json", sa.Text()),
        sa.Column("error_summary", sa.Text()),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("completed_at", sa.Text()),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'invalid')",
            name="ck_scoring_runs_status",
        ),
        sa.CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0.0 AND overall_score <= 100.0)",
            name="ck_scoring_runs_overall_score",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_scoring_runs_confidence",
        ),
    )
    op.create_index(
        "idx_scoring_runs_opportunity_time", "scoring_runs", ["opportunity_id", "started_at"]
    )

    op.create_table(
        "score_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scoring_run_id",
            sa.Integer(),
            sa.ForeignKey("scoring_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("component_code", sa.Text(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=False),
        sa.Column("weight", sa.REAL(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.CheckConstraint("score >= 0.0 AND score <= 100.0", name="ck_score_components_score"),
        sa.CheckConstraint("weight >= 0.0", name="ck_score_components_weight"),
        sa.UniqueConstraint(
            "scoring_run_id", "component_code", name="uq_score_components_run_component"
        ),
    )

    op.create_table(
        "resume_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False, unique=True),
        sa.Column("content_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("is_master", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "imported_by", sa.Text(), nullable=False, server_default=sa.text("'scott'")
        ),
        sa.Column("imported_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column(
            "supersedes_id",
            sa.Integer(),
            sa.ForeignKey("resume_sources.id", ondelete="RESTRICT"),
        ),
        sa.Column("notes", sa.Text()),
        sa.CheckConstraint("version > 0", name="ck_resume_sources_version"),
        sa.CheckConstraint("is_master IN (0, 1)", name="ck_resume_sources_is_master"),
    )

    op.create_table(
        "generated_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resume_source_id",
            sa.Integer(),
            sa.ForeignKey("resume_sources.id", ondelete="RESTRICT"),
        ),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("storage_path", sa.Text()),
        sa.Column("content_hash", sa.Text()),
        sa.Column("provider", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("unsupported_claims_json", sa.Text()),
        sa.Column("generated_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("reviewed_at", sa.Text()),
        sa.CheckConstraint(
            "document_type IN ('tailored_resume', 'cover_letter', 'fit_report', 'proposal')",
            name="ck_generated_documents_document_type",
        ),
        sa.CheckConstraint("version > 0", name="ck_generated_documents_version"),
        sa.CheckConstraint(
            "status IN ('draft', 'validation_failed', 'ready_for_review', 'approved', "
            "'rejected', 'superseded')",
            name="ck_generated_documents_status",
        ),
        sa.UniqueConstraint(
            "opportunity_id", "document_type", "version", name="uq_generated_documents_version"
        ),
    )
    op.create_index(
        "idx_generated_documents_opportunity_status",
        "generated_documents",
        ["opportunity_id", "status"],
    )

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False, server_default=sa.text("'scott'")),
        sa.Column("rationale", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.CheckConstraint(
            "decision IN ('shortlist', 'reject', 'defer', 'request_preparation', 'reopen')",
            name="ck_review_decisions_decision",
        ),
    )
    op.create_index(
        "idx_review_decisions_opportunity_time",
        "review_decisions",
        ["opportunity_id", "created_at"],
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id", ondelete="CASCADE")
        ),
        sa.Column(
            "generated_document_id",
            sa.Integer(),
            sa.ForeignKey("generated_documents.id", ondelete="SET NULL"),
        ),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("resolved_by", sa.Text()),
        sa.Column("resolved_at", sa.Text()),
        sa.Column("expires_at", sa.Text()),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("approval_token_hash", sa.Text(), unique=True),
        sa.CheckConstraint(
            "action_type IN ('application', 'email', 'external_message', 'contract', "
            "'identity_verification', 'financial_commitment')",
            name="ck_approval_requests_action_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired', 'consumed')",
            name="ck_approval_requests_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR (status <> 'pending')",
            name="ck_approval_requests_pending_unresolved",
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_by IS NOT NULL",
            name="ck_approval_requests_resolution_actor",
        ),
    )
    op.create_index(
        "idx_approval_requests_status_time", "approval_requests", ["status", "requested_at"]
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id", ondelete="CASCADE")
        ),
        sa.Column("notification_type", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False, server_default=sa.text("'local'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("is_external", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "approval_request_id",
            sa.Integer(),
            sa.ForeignKey("approval_requests.id", ondelete="RESTRICT"),
        ),
        sa.Column("queued_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.Column("sent_at", sa.Text()),
        sa.Column("error_summary", sa.Text()),
        sa.CheckConstraint(
            "channel IN ('local', 'dashboard', 'email', 'sms', 'other')",
            name="ck_notifications_channel",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'cancelled')", name="ck_notifications_status"
        ),
        sa.CheckConstraint("is_external IN (0, 1)", name="ck_notifications_is_external"),
        sa.CheckConstraint(
            "is_external = 0 OR approval_request_id IS NOT NULL",
            name="ck_notifications_external_requires_approval",
        ),
    )
    op.create_index("idx_notifications_status_time", "notifications", ["status", "queued_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_identifier", sa.Text()),
        sa.Column("entity_type", sa.Text()),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("constitution_version", sa.Text()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text()),
        sa.Column("occurred_at", sa.Text(), nullable=False, server_default=_UTC_NOW),
        sa.CheckConstraint(
            "actor_type IN ('scott', 'system', 'ai', 'external')",
            name="ck_audit_events_actor_type",
        ),
    )
    op.create_index(
        "idx_audit_events_correlation", "audit_events", ["correlation_id", "occurred_at"]
    )
    op.create_index(
        "idx_audit_events_entity", "audit_events", ["entity_type", "entity_id", "occurred_at"]
    )

    op.execute(
        "INSERT INTO schema_versions (version, description) "
        "VALUES (1, 'Initial OpportunityEngine persistence model')"
    )

    op.execute(
        """
        CREATE TRIGGER protect_master_resume_update
        BEFORE UPDATE ON resume_sources
        WHEN OLD.is_master = 1
        BEGIN
            SELECT RAISE(ABORT, 'Master resume versions are immutable; import a new version instead.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_master_resume_delete
        BEFORE DELETE ON resume_sources
        WHEN OLD.is_master = 1
        BEGIN
            SELECT RAISE(ABORT, 'Master resume versions cannot be deleted.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_filter_evaluation_update
        BEFORE UPDATE ON filter_evaluations
        BEGIN
            SELECT RAISE(ABORT, 'Filter evaluations are append-only.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_filter_evaluation_delete
        BEFORE DELETE ON filter_evaluations
        BEGIN
            SELECT RAISE(ABORT, 'Filter evaluations are append-only.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_scoring_run_update
        BEFORE UPDATE ON scoring_runs
        WHEN OLD.status IN ('succeeded', 'failed', 'invalid')
        BEGIN
            SELECT RAISE(ABORT, 'Completed scoring runs are immutable.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_scoring_run_delete
        BEFORE DELETE ON scoring_runs
        BEGIN
            SELECT RAISE(ABORT, 'Scoring runs are append-only.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_audit_event_update
        BEFORE UPDATE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'Audit events are append-only.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_audit_event_delete
        BEFORE DELETE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'Audit events are append-only.');
        END;
        """
    )
    op.execute(
        """
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
        """
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("notifications")
    op.drop_table("approval_requests")
    op.drop_table("review_decisions")
    op.drop_table("generated_documents")
    op.drop_table("resume_sources")
    op.drop_table("score_components")
    op.drop_table("scoring_runs")
    op.drop_table("filter_evaluations")
    op.drop_table("deduplication_decisions")
    op.drop_table("opportunity_sources")
    op.drop_table("opportunities")
    op.drop_table("source_records")
    op.drop_table("collection_runs")
    op.drop_table("sources")
    op.drop_table("schema_versions")
