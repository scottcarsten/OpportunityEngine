"""Manual opportunity normalization, persistence, and hard filtering."""

import hashlib
import json
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.database import Database
from backend.db.models import (
    FilterEvaluation,
    Opportunity,
    OpportunitySource,
    Source,
    SourceRecord,
)
from backend.models import OpportunityInput
from backend.services.constitution_service import Constitution
from backend.timeutil import now_iso


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
            session.commit()
        except Exception:
            session.rollback()
            raise

        return opportunity_row.id, True

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
        result = dict(opportunity)
        result["filters"] = [dict(row) for row in filters]
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
    def _fingerprint(opportunity: OpportunityInput) -> str:
        identity = "\n".join(
            (
                opportunity.organization_name.casefold(),
                opportunity.title.casefold(),
                opportunity.location_text.casefold(),
                opportunity.description.casefold(),
            )
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

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
