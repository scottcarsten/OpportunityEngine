"""Manual opportunity normalization, persistence, and hard filtering."""

import hashlib
import json
from dataclasses import asdict
from difflib import SequenceMatcher
from typing import Any, Literal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.database import Database
from backend.db.models import (
    AuditEventRecord,
    DeduplicationDecision,
    FilterEvaluation,
    Notification,
    Opportunity,
    OpportunitySource,
    ReviewDecision,
    ScoreComponent,
    ScoringRun,
    Source,
    SourceRecord,
)
from backend.models import OpportunityInput
from backend.services.audit_service import AuditEvent, AuditService
from backend.services.constitution_service import Constitution
from backend.timeutil import now_iso

# A likely-duplicate match must be at or above this ratio over the same
# organization+title+location+description identity string used for the
# exact fingerprint. Chosen conservatively: within the same organization,
# 0.85+ similarity is almost always a repost or near-duplicate rather than
# a genuinely different role with a shared boilerplate "About us" section.
_LIKELY_DUPLICATE_THRESHOLD = 0.85

# Per OE-ADR-018: a review decision is Scott's own judgment call, so unlike
# the Milestone 3 hard-filter override it drives lifecycle_status directly
# into the dedicated review states the schema already defines.
_REVIEW_DECISION_STATUS = {
    "shortlist": "shortlisted",
    "reject": "rejected",
    "defer": "deferred",
    "request_preparation": "preparing",
    "reopen": "eligible",
}


class OpportunityService:
    """Provide the first complete manual opportunity workflow."""

    def __init__(self, database: Database, constitution: Constitution) -> None:
        self.database = database
        self.constitution = constitution

    def create_manual(self, supplied: OpportunityInput) -> tuple[int, bool]:
        """Normalize, deduplicate, filter, and persist a manual opportunity."""
        with self.database.session() as session:
            source_id = self.ensure_source(session, "Manual entry", "manual", None)
            return self._ingest(
                session, supplied, source_id=source_id, external_id=None, collection_run_id=None
            )

    def ingest_collected(
        self,
        session: Session,
        supplied: OpportunityInput,
        *,
        source_id: int,
        external_id: str,
        collection_run_id: int,
    ) -> tuple[int, bool]:
        """Normalize, deduplicate, filter, and persist a collected opportunity.

        Reuses the exact manual-entry fingerprint short-circuit: if the
        normalized listing matches an already-known opportunity, no new
        `source_record` is created here. Recording that repeat sighting as a
        `deduplication_decisions` row is Milestone 3 scope.
        """
        return self._ingest(
            session,
            supplied,
            source_id=source_id,
            external_id=external_id,
            collection_run_id=collection_run_id,
        )

    def _ingest(
        self,
        session: Session,
        supplied: OpportunityInput,
        *,
        source_id: int,
        external_id: str | None,
        collection_run_id: int | None,
    ) -> tuple[int, bool]:
        normalized = self._normalize(supplied)
        fingerprint = self._fingerprint(normalized)
        payload = json.dumps(asdict(normalized), sort_keys=True)
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        existing_id = session.execute(
            select(Opportunity.id).where(Opportunity.fingerprint == fingerprint)
        ).scalar_one_or_none()
        if existing_id is not None:
            return int(existing_id), False

        try:
            opportunity_row = self._insert_opportunity(session, normalized, fingerprint)
            self._detect_likely_duplicates(session, opportunity_row, normalized)
            source_record_id = self._insert_source_record(
                session,
                source_id,
                normalized.source_url,
                payload,
                payload_hash,
                external_id=external_id,
                collection_run_id=collection_run_id,
            )
            session.add(
                OpportunitySource(
                    opportunity_id=opportunity_row.id,
                    source_record_id=source_record_id,
                    is_primary=1,
                )
            )
            lifecycle_status = self._evaluate_filters(session, opportunity_row.id, normalized)
            opportunity_row.lifecycle_status = lifecycle_status
            opportunity_row.updated_at = now_iso()
            if lifecycle_status in ("eligible", "new"):
                # Created once, at ingest, not on every later status change -
                # a re-decision is already visible in that opportunity's own
                # review-decision history (OE-ADR-018).
                session.add(
                    Notification(
                        opportunity_id=opportunity_row.id,
                        notification_type="opportunity_needs_review",
                        channel="dashboard",
                        subject=f"Review needed: {opportunity_row.title}",
                        body=(
                            f"\"{opportunity_row.title}\" at "
                            f"{opportunity_row.organization_name or 'an unspecified organization'} "
                            f"is {lifecycle_status} and awaiting your review."
                        ),
                    )
                )
            session.commit()
        except Exception:
            session.rollback()
            raise

        return opportunity_row.id, True

    def override_lifecycle_status(
        self, opportunity_id: int, new_status: Literal["eligible", "ineligible"], rationale: str
    ) -> None:
        """Let Scott explicitly override a hard-filter outcome, always audited.

        Never mutates `filter_evaluations` (those rows are append-only and
        DB-trigger-protected) — the original rule outcome stays visible
        exactly as it was. AI/automation must never call this; nothing in
        the codebase does. See `OE-ADR-016`.
        """
        rationale = rationale.strip()
        if not rationale:
            raise ValueError("rationale is required")
        if new_status not in ("eligible", "ineligible"):
            raise ValueError("new_status must be 'eligible' or 'ineligible'")

        with self.database.session() as session:
            opportunity = session.execute(
                select(Opportunity).where(Opportunity.id == opportunity_id)
            ).scalar_one_or_none()
            if opportunity is None:
                raise ValueError(f"opportunity not found: {opportunity_id}")

            try:
                previous_status = opportunity.lifecycle_status
                opportunity.lifecycle_status = new_status
                opportunity.updated_at = now_iso()
                AuditService(session).record(
                    AuditEvent(
                        event_type="hard_filter_override",
                        actor_type="scott",
                        entity_type="opportunity",
                        entity_id=opportunity_id,
                        constitution_version=self.constitution.version,
                        summary=(
                            f"Overrode lifecycle status from {previous_status} to {new_status}."
                        ),
                        details={
                            "previous_status": previous_status,
                            "new_status": new_status,
                            "rationale": rationale,
                        },
                    )
                )
            except Exception:
                session.rollback()
                raise

    def record_review_decision(
        self,
        opportunity_id: int,
        decision: Literal["shortlist", "reject", "defer", "request_preparation", "reopen"],
        rationale: str | None = None,
        actor: str = "scott",
    ) -> None:
        """Record Scott's review decision and move lifecycle_status accordingly.

        Per ARCHITECTURE.md §5.6, the review queue presents evidence; Scott
        decides. No transition is blocked — he can re-shortlist something
        already rejected. See `OE-ADR-018`.
        """
        new_status = _REVIEW_DECISION_STATUS.get(decision)
        if new_status is None:
            raise ValueError(f"unsupported review decision: {decision}")

        with self.database.session() as session:
            opportunity = session.execute(
                select(Opportunity).where(Opportunity.id == opportunity_id)
            ).scalar_one_or_none()
            if opportunity is None:
                raise ValueError(f"opportunity not found: {opportunity_id}")

            try:
                previous_status = opportunity.lifecycle_status
                opportunity.lifecycle_status = new_status
                opportunity.updated_at = now_iso()
                session.add(
                    ReviewDecision(
                        opportunity_id=opportunity_id,
                        decision=decision,
                        actor=actor,
                        rationale=rationale or None,
                    )
                )
                AuditService(session).record(
                    AuditEvent(
                        event_type="review_decision",
                        actor_type="scott",
                        entity_type="opportunity",
                        entity_id=opportunity_id,
                        constitution_version=self.constitution.version,
                        summary=(
                            f"Recorded review decision '{decision}': "
                            f"status now {new_status}."
                        ),
                        details={
                            "decision": decision,
                            "previous_status": previous_status,
                            "new_status": new_status,
                            "rationale": rationale,
                        },
                    )
                )
            except Exception:
                session.rollback()
                raise

    def mark_notifications_sent(self, opportunity_id: int) -> None:
        """Mark this opportunity's queued notifications as sent (viewed)."""
        with self.database.session() as session:
            session.execute(
                update(Notification)
                .where(
                    Notification.opportunity_id == opportunity_id,
                    Notification.status == "queued",
                )
                .values(status="sent", sent_at=now_iso())
            )
            session.commit()

    def count_pending_review(self) -> int:
        """Count opportunities with a queued internal notification."""
        with self.database.session() as session:
            return session.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.status == "queued")
            ).scalar_one()

    def list_opportunities(self) -> list[dict[str, Any]]:
        """Return opportunities newest first for the review inbox."""
        with self.database.session() as session:
            rows = session.execute(
                select(
                    Opportunity.id,
                    Opportunity.title,
                    Opportunity.organization_name,
                    Opportunity.remote_status,
                    Opportunity.engagement_type,
                    Opportunity.tax_type,
                    Opportunity.lifecycle_status,
                    Opportunity.created_at,
                ).order_by(Opportunity.created_at.desc(), Opportunity.id.desc())
            ).mappings().all()
        return [dict(row) for row in rows]

    def get_opportunity(self, opportunity_id: int) -> dict[str, Any] | None:
        """Return one opportunity with its constitutional evaluations."""
        with self.database.session() as session:
            opportunity = session.execute(
                select(Opportunity.__table__).where(Opportunity.id == opportunity_id)
            ).mappings().first()
            if opportunity is None:
                return None
            filters = session.execute(
                select(
                    FilterEvaluation.rule_code,
                    FilterEvaluation.outcome,
                    FilterEvaluation.evidence,
                    FilterEvaluation.explanation,
                    FilterEvaluation.evaluated_at,
                )
                .where(FilterEvaluation.opportunity_id == opportunity_id)
                .order_by(FilterEvaluation.id)
            ).mappings().all()
            retained_side = session.execute(
                select(
                    DeduplicationDecision.duplicate_opportunity_id.label("other_id"),
                    Opportunity.title.label("other_title"),
                    DeduplicationDecision.confidence,
                    DeduplicationDecision.explanation,
                )
                .join(Opportunity, Opportunity.id == DeduplicationDecision.duplicate_opportunity_id)
                .where(DeduplicationDecision.retained_opportunity_id == opportunity_id)
            ).mappings().all()
            duplicate_side = session.execute(
                select(
                    DeduplicationDecision.retained_opportunity_id.label("other_id"),
                    Opportunity.title.label("other_title"),
                    DeduplicationDecision.confidence,
                    DeduplicationDecision.explanation,
                )
                .join(Opportunity, Opportunity.id == DeduplicationDecision.retained_opportunity_id)
                .where(DeduplicationDecision.duplicate_opportunity_id == opportunity_id)
            ).mappings().all()
            override_rows = session.execute(
                select(
                    AuditEventRecord.summary,
                    AuditEventRecord.details_json,
                    AuditEventRecord.occurred_at,
                )
                .where(
                    AuditEventRecord.entity_type == "opportunity",
                    AuditEventRecord.entity_id == opportunity_id,
                    AuditEventRecord.event_type == "hard_filter_override",
                )
                .order_by(AuditEventRecord.id.desc())
            ).mappings().all()
            scoring_run_rows = session.execute(
                select(ScoringRun.__table__)
                .where(ScoringRun.opportunity_id == opportunity_id)
                .order_by(ScoringRun.id.desc())
            ).mappings().all()
            component_rows = session.execute(
                select(
                    ScoreComponent.scoring_run_id,
                    ScoreComponent.component_code,
                    ScoreComponent.score,
                    ScoreComponent.weight,
                    ScoreComponent.explanation,
                )
                .where(
                    ScoreComponent.scoring_run_id.in_(
                        [row["id"] for row in scoring_run_rows]
                    )
                )
                .order_by(ScoreComponent.id)
            ).mappings().all()
            source_row = session.execute(
                select(
                    Source.name,
                    Source.source_type,
                    SourceRecord.canonical_url,
                    SourceRecord.retrieved_at,
                )
                .join(SourceRecord, SourceRecord.source_id == Source.id)
                .join(
                    OpportunitySource,
                    OpportunitySource.source_record_id == SourceRecord.id,
                )
                .where(
                    OpportunitySource.opportunity_id == opportunity_id,
                    OpportunitySource.is_primary == 1,
                )
            ).mappings().first()
            review_decision_rows = session.execute(
                select(
                    ReviewDecision.decision,
                    ReviewDecision.actor,
                    ReviewDecision.rationale,
                    ReviewDecision.created_at,
                )
                .where(ReviewDecision.opportunity_id == opportunity_id)
                .order_by(ReviewDecision.id.desc())
            ).mappings().all()

        result = dict(opportunity)
        result["source"] = dict(source_row) if source_row is not None else None
        result["review_decisions"] = [dict(row) for row in review_decision_rows]
        result["filters"] = [dict(row) for row in filters]
        result["likely_duplicates"] = [dict(row) for row in retained_side] + [
            dict(row) for row in duplicate_side
        ]
        result["override_history"] = [
            {
                "summary": row["summary"],
                "occurred_at": row["occurred_at"],
                **json.loads(row["details_json"] or "{}"),
            }
            for row in override_rows
        ]
        components_by_run: dict[int, list[dict[str, Any]]] = {}
        for row in component_rows:
            components_by_run.setdefault(row["scoring_run_id"], []).append(dict(row))
        result["scoring_runs"] = [
            {**dict(run), "components": components_by_run.get(run["id"], [])}
            for run in scoring_run_rows
        ]
        return result

    @staticmethod
    def _normalize(supplied: OpportunityInput) -> OpportunityInput:
        def clean(value: str) -> str:
            return " ".join(value.split())

        title = clean(supplied.title)
        description = clean(supplied.description)
        if not title:
            raise ValueError("title is required")
        if not description:
            raise ValueError("description is required")
        if (
            supplied.compensation_min is not None
            and supplied.compensation_max is not None
            and supplied.compensation_min > supplied.compensation_max
        ):
            raise ValueError("minimum compensation cannot exceed maximum")

        return OpportunityInput(
            title=title,
            organization_name=clean(supplied.organization_name),
            description=description,
            source_url=clean(supplied.source_url),
            location_text=clean(supplied.location_text),
            remote_status=supplied.remote_status,
            engagement_type=supplied.engagement_type,
            tax_type=supplied.tax_type,
            schedule_text=clean(supplied.schedule_text),
            compensation_min=supplied.compensation_min,
            compensation_max=supplied.compensation_max,
            compensation_period=supplied.compensation_period,
            requires_travel=supplied.requires_travel,
            requires_relocation=supplied.requires_relocation,
            requires_clearance=supplied.requires_clearance,
            replaces_full_time_work=supplied.replaces_full_time_work,
        )

    @staticmethod
    def _identity_string(
        organization_name: str, title: str, location_text: str, description: str
    ) -> str:
        return "\n".join(
            (
                (organization_name or "").casefold(),
                (title or "").casefold(),
                (location_text or "").casefold(),
                (description or "").casefold(),
            )
        )

    @classmethod
    def _fingerprint(cls, opportunity: OpportunityInput) -> str:
        identity = cls._identity_string(
            opportunity.organization_name,
            opportunity.title,
            opportunity.location_text,
            opportunity.description,
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _detect_likely_duplicates(
        self, session: Session, new_row: Opportunity, normalized: OpportunityInput
    ) -> None:
        """Flag likely duplicates via similarity review (ARCHITECTURE.md §5.3, layer 4).

        Only compares against opportunities sharing the same organization —
        scoped at ingest time against what already exists, not a batch
        reconciliation sweep across all pairs. Both records remain separate;
        nothing here suppresses or merges an opportunity.
        """
        if not normalized.organization_name:
            return

        target_org = normalized.organization_name.casefold()
        new_identity = self._identity_string(
            normalized.organization_name,
            normalized.title,
            normalized.location_text,
            normalized.description,
        )

        candidates = session.execute(
            select(Opportunity).where(
                Opportunity.id != new_row.id,
                Opportunity.organization_name.isnot(None),
            )
        ).scalars().all()

        for candidate in candidates:
            if candidate.organization_name.casefold() != target_org:
                continue
            candidate_identity = self._identity_string(
                candidate.organization_name,
                candidate.title,
                candidate.location_text,
                candidate.description,
            )
            ratio = SequenceMatcher(None, new_identity, candidate_identity).ratio()
            if ratio < _LIKELY_DUPLICATE_THRESHOLD:
                continue
            session.add(
                DeduplicationDecision(
                    retained_opportunity_id=candidate.id,
                    duplicate_opportunity_id=new_row.id,
                    method="similarity",
                    confidence=ratio,
                    explanation=(
                        f"Title/description similarity {ratio:.2f} for organization "
                        f"'{normalized.organization_name}'."
                    ),
                    decided_by="system",
                )
            )

    @staticmethod
    def ensure_source(session: Session, name: str, source_type: str, base_url: str | None) -> int:
        """Return the id of a `sources` row, creating it if it doesn't exist yet."""
        session.execute(
            sqlite_insert(Source)
            .values(name=name, source_type=source_type, base_url=base_url)
            .on_conflict_do_nothing(index_elements=["name"])
        )
        return session.execute(select(Source.id).where(Source.name == name)).scalar_one()

    @staticmethod
    def _insert_opportunity(
        session: Session,
        opportunity: OpportunityInput,
        fingerprint: str,
    ) -> Opportunity:
        row = Opportunity(
            fingerprint=fingerprint,
            title=opportunity.title,
            organization_name=opportunity.organization_name or None,
            description=opportunity.description,
            canonical_url=opportunity.source_url or None,
            location_text=opportunity.location_text or None,
            remote_status=opportunity.remote_status,
            engagement_type=opportunity.engagement_type,
            tax_type=opportunity.tax_type,
            schedule_text=opportunity.schedule_text or None,
            compensation_min=opportunity.compensation_min,
            compensation_max=opportunity.compensation_max,
            compensation_period=opportunity.compensation_period,
            requires_travel=opportunity.requires_travel,
            requires_relocation=opportunity.requires_relocation,
            requires_clearance=opportunity.requires_clearance,
            replaces_full_time_work=opportunity.replaces_full_time_work,
        )
        session.add(row)
        session.flush()
        return row

    @staticmethod
    def _insert_source_record(
        session: Session,
        source_id: int,
        source_url: str,
        payload: str,
        payload_hash: str,
        *,
        external_id: str | None = None,
        collection_run_id: int | None = None,
    ) -> int:
        row = SourceRecord(
            source_id=source_id,
            collection_run_id=collection_run_id,
            external_id=external_id,
            canonical_url=source_url or None,
            payload_hash=payload_hash,
            raw_payload_json=payload,
            retrieved_at=now_iso(),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    def _evaluate_filters(
        self,
        session: Session,
        opportunity_id: int,
        opportunity: OpportunityInput,
    ) -> str:
        hard_filters = self.constitution.raw["hard_filters"]
        evaluations = [
            self._remote_evaluation(opportunity.remote_status, hard_filters),
            self._boolean_evaluation(
                "NO_TRAVEL",
                opportunity.requires_travel,
                hard_filters.get("travel") is False,
                "The opportunity must not require travel.",
            ),
            self._boolean_evaluation(
                "NO_RELOCATION",
                opportunity.requires_relocation,
                hard_filters.get("relocation") is False,
                "The opportunity must not require relocation.",
            ),
            self._boolean_evaluation(
                "NO_CLEARANCE",
                opportunity.requires_clearance,
                hard_filters.get("clearance_required") is False,
                "The opportunity must not require an existing clearance.",
            ),
            self._boolean_evaluation(
                "NO_FULL_TIME_REPLACEMENT",
                opportunity.replaces_full_time_work,
                hard_filters.get("full_time_replacement") is False,
                "The opportunity must not replace Scott's full-time employment.",
            ),
        ]

        correlation_id = f"opportunity-{opportunity_id}-hard-filters"
        for rule_code, outcome, evidence, explanation in evaluations:
            session.add(
                FilterEvaluation(
                    opportunity_id=opportunity_id,
                    constitution_version=self.constitution.version,
                    rule_code=rule_code,
                    outcome=outcome,
                    evidence=evidence,
                    explanation=explanation,
                    evaluator_version="hard-filters-v1",
                    correlation_id=correlation_id,
                )
            )

        outcomes = {evaluation[1] for evaluation in evaluations}
        if "fail" in outcomes:
            return "ineligible"
        if "manual_review" in outcomes:
            return "new"
        return "eligible"

    @staticmethod
    def _remote_evaluation(
        remote_status: str, hard_filters: dict[str, Any]
    ) -> tuple[str, str, str, str]:
        if hard_filters.get("remote_only") is not True:
            return (
                "REMOTE_ONLY",
                "pass",
                remote_status,
                "The constitution does not require remote-only work.",
            )
        if remote_status == "remote":
            return (
                "REMOTE_ONLY",
                "pass",
                remote_status,
                "The opportunity is explicitly remote.",
            )
        if remote_status == "unknown":
            return (
                "REMOTE_ONLY",
                "manual_review",
                remote_status,
                "Remote status is unknown and requires Scott's review.",
            )
        return (
            "REMOTE_ONLY",
            "fail",
            remote_status,
            "The opportunity is not fully remote.",
        )

    @staticmethod
    def _boolean_evaluation(
        rule_code: str,
        observed: bool | None,
        rule_enabled: bool,
        requirement: str,
    ) -> tuple[str, str, str, str]:
        if not rule_enabled:
            return (rule_code, "pass", str(observed), "The rule is not enabled.")
        if observed is None:
            return (
                rule_code,
                "manual_review",
                "unknown",
                f"{requirement} The listing is unclear.",
            )
        if observed:
            return (rule_code, "fail", "yes", requirement)
        return (rule_code, "pass", "no", requirement)
