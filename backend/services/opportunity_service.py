"""Manual opportunity normalization, persistence, and hard filtering."""

import hashlib
import json
import sqlite3
from dataclasses import asdict
from typing import Any

from backend.database import Database
from backend.models import OpportunityInput
from backend.services.constitution_service import Constitution


class OpportunityService:
    """Provide the first complete manual opportunity workflow."""

    def __init__(self, database: Database, constitution: Constitution) -> None:
        self.database = database
        self.constitution = constitution

    def create_manual(self, supplied: OpportunityInput) -> tuple[int, bool]:
        """Normalize, deduplicate, filter, and persist a manual opportunity."""
        normalized = self._normalize(supplied)
        fingerprint = self._fingerprint(normalized)
        payload = json.dumps(asdict(normalized), sort_keys=True)
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        with self.database.locked_connection() as connection:
            existing = connection.execute(
                "SELECT id FROM opportunities WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing is not None:
                return int(existing["id"]), False

            try:
                connection.execute("BEGIN")
                source_id = self._ensure_manual_source(connection)
                opportunity_id = self._insert_opportunity(
                    connection, normalized, fingerprint
                )
                source_record_id = self._insert_source_record(
                    connection, source_id, normalized.source_url, payload, payload_hash
                )
                connection.execute(
                    """
                    INSERT INTO opportunity_sources (
                        opportunity_id, source_record_id, is_primary
                    )
                    VALUES (?, ?, 1)
                    """,
                    (opportunity_id, source_record_id),
                )
                lifecycle_status = self._evaluate_filters(
                    connection, opportunity_id, normalized
                )
                connection.execute(
                    """
                    UPDATE opportunities
                    SET lifecycle_status = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ?
                    """,
                    (lifecycle_status, opportunity_id),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return opportunity_id, True

    def list_opportunities(self) -> list[dict[str, Any]]:
        """Return opportunities newest first for the review inbox."""
        with self.database.locked_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    title,
                    organization_name,
                    remote_status,
                    engagement_type,
                    tax_type,
                    lifecycle_status,
                    created_at
                FROM opportunities
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_opportunity(self, opportunity_id: int) -> dict[str, Any] | None:
        """Return one opportunity with its constitutional evaluations."""
        with self.database.locked_connection() as connection:
            opportunity = connection.execute(
                "SELECT * FROM opportunities WHERE id = ?",
                (opportunity_id,),
            ).fetchone()
            if opportunity is None:
                return None
            filters = connection.execute(
                """
                SELECT rule_code, outcome, evidence, explanation, evaluated_at
                FROM filter_evaluations
                WHERE opportunity_id = ?
                ORDER BY id
                """,
                (opportunity_id,),
            ).fetchall()
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
    def _ensure_manual_source(connection: sqlite3.Connection) -> int:
        connection.execute(
            """
            INSERT INTO sources (name, source_type, base_url)
            VALUES ('Manual entry', 'manual', NULL)
            ON CONFLICT(name) DO NOTHING
            """
        )
        row = connection.execute(
            "SELECT id FROM sources WHERE name = 'Manual entry'"
        ).fetchone()
        return int(row["id"])

    @staticmethod
    def _insert_opportunity(
        connection: sqlite3.Connection,
        opportunity: OpportunityInput,
        fingerprint: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO opportunities (
                fingerprint,
                title,
                organization_name,
                description,
                canonical_url,
                location_text,
                remote_status,
                engagement_type,
                tax_type,
                schedule_text,
                compensation_min,
                compensation_max,
                compensation_period,
                requires_travel,
                requires_relocation,
                requires_clearance,
                replaces_full_time_work
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fingerprint,
                opportunity.title,
                opportunity.organization_name or None,
                opportunity.description,
                opportunity.source_url or None,
                opportunity.location_text or None,
                opportunity.remote_status,
                opportunity.engagement_type,
                opportunity.tax_type,
                opportunity.schedule_text or None,
                opportunity.compensation_min,
                opportunity.compensation_max,
                opportunity.compensation_period,
                opportunity.requires_travel,
                opportunity.requires_relocation,
                opportunity.requires_clearance,
                opportunity.replaces_full_time_work,
            ),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _insert_source_record(
        connection: sqlite3.Connection,
        source_id: int,
        source_url: str,
        payload: str,
        payload_hash: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO source_records (
                source_id,
                canonical_url,
                payload_hash,
                raw_payload_json,
                retrieved_at
            )
            VALUES (
                ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
            """,
            (source_id, source_url or None, payload_hash, payload),
        )
        return int(cursor.lastrowid)

    def _evaluate_filters(
        self,
        connection: sqlite3.Connection,
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

        correlation_id = f"manual-opportunity-{opportunity_id}"
        for rule_code, outcome, evidence, explanation in evaluations:
            connection.execute(
                """
                INSERT INTO filter_evaluations (
                    opportunity_id,
                    constitution_version,
                    rule_code,
                    outcome,
                    evidence,
                    explanation,
                    evaluator_version,
                    correlation_id
                )
                VALUES (?, ?, ?, ?, ?, ?, 'hard-filters-v1', ?)
                """,
                (
                    opportunity_id,
                    self.constitution.version,
                    rule_code,
                    outcome,
                    evidence,
                    explanation,
                    correlation_id,
                ),
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

