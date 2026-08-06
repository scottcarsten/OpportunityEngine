"""Read-only pipeline reporting: volume, quality, and estimated value.

No `constitution` dependency - nothing here is a governed decision, just
descriptive statistics over data other services already produce and
audit. See `OE-ADR-031`.
"""

from typing import Any

from sqlalchemy import func, select

from backend.database import Database
from backend.db.models import CollectionRun, Opportunity, ScoringRun, Source

# Ordered so the report always shows every status, even at zero, rather
# than only whatever happens to have rows today.
_ALL_STATUSES = (
    "new",
    "eligible",
    "ineligible",
    "shortlisted",
    "deferred",
    "rejected",
    "preparing",
    "expired",
)

# A value estimate should reflect the live pipeline, not closed-out
# history - excludes ineligible/rejected/expired.
_ACTIVE_STATUSES = ("new", "eligible", "shortlisted", "deferred", "preparing")


class ReportingService:
    """Aggregate volume, quality, and value statistics for the dashboard's pipeline."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def build_report(self) -> dict[str, Any]:
        return {
            "by_status": self._counts_by_status(),
            "by_source": self._volume_by_source(),
            "quality": self._quality_summary(),
            "value_by_period": self._value_by_period(),
        }

    def _counts_by_status(self) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.execute(
                select(Opportunity.lifecycle_status, func.count())
                .group_by(Opportunity.lifecycle_status)
            ).all()
        counts = {status: count for status, count in rows}
        return [
            {"status": status, "count": counts.get(status, 0)} for status in _ALL_STATUSES
        ]

    def _volume_by_source(self) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.execute(
                select(
                    Source.name,
                    func.count(CollectionRun.id).label("run_count"),
                    func.coalesce(func.sum(CollectionRun.records_seen), 0).label("records_seen"),
                    func.coalesce(
                        func.sum(CollectionRun.records_created), 0
                    ).label("records_created"),
                    func.max(CollectionRun.completed_at).label("last_run_at"),
                )
                .select_from(Source)
                .outerjoin(CollectionRun, CollectionRun.source_id == Source.id)
                .group_by(Source.id)
                .order_by(Source.name)
            ).mappings().all()
        return [dict(row) for row in rows]

    def _quality_summary(self) -> dict[str, Any]:
        with self.database.session() as session:
            latest_run_ids = (
                select(func.max(ScoringRun.id))
                .where(ScoringRun.overall_score.is_not(None))
                .group_by(ScoringRun.opportunity_id)
                .scalar_subquery()
            )
            rows = session.execute(
                select(
                    ScoringRun.overall_score,
                    ScoringRun.confidence,
                    Opportunity.lifecycle_status,
                )
                .join(Opportunity, Opportunity.id == ScoringRun.opportunity_id)
                .where(ScoringRun.id.in_(latest_run_ids))
            ).all()

        if not rows:
            return {"scored_count": 0, "avg_score": None, "min_score": None,
                     "max_score": None, "avg_confidence": None, "by_status": []}

        scores = [row.overall_score for row in rows]
        confidences = [row.confidence for row in rows if row.confidence is not None]

        by_status: dict[str, list[float]] = {}
        for row in rows:
            by_status.setdefault(row.lifecycle_status, []).append(row.overall_score)

        return {
            "scored_count": len(rows),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "avg_confidence": sum(confidences) / len(confidences) if confidences else None,
            "by_status": [
                {"status": status, "count": len(values), "avg_score": sum(values) / len(values)}
                for status, values in sorted(by_status.items())
            ],
        }

    def _value_by_period(self) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.execute(
                select(
                    Opportunity.compensation_period,
                    func.count(),
                    func.min(Opportunity.compensation_min),
                    func.max(Opportunity.compensation_max),
                )
                .where(Opportunity.lifecycle_status.in_(_ACTIVE_STATUSES))
                .group_by(Opportunity.compensation_period)
            ).all()

        buckets: dict[str, dict[str, Any]] = {}
        for period, count, min_comp, max_comp in rows:
            key = period if period and period != "unknown" else "unspecified"
            bucket = buckets.setdefault(
                key, {"period": key, "count": 0, "min": None, "max": None}
            )
            bucket["count"] += count
            if min_comp is not None:
                bucket["min"] = min_comp if bucket["min"] is None else min(bucket["min"], min_comp)
            if max_comp is not None:
                bucket["max"] = max_comp if bucket["max"] is None else max(bucket["max"], max_comp)

        return sorted(buckets.values(), key=lambda bucket: bucket["period"])
