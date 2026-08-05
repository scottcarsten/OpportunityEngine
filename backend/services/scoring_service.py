"""Explainable, advisory scoring of eligible opportunities."""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import select, update

from backend.database import Database
from backend.db.models import Opportunity, ScoreComponent, ScoringRun
from backend.scoring.base import COMPONENT_WEIGHTS, ScoringProvider
from backend.services.constitution_service import Constitution
from backend.timeutil import now_iso


class ScoringService:
    """Run a scoring provider against one eligible opportunity.

    Never writes to `opportunities.lifecycle_status` — that absence of a
    code path is the structural enforcement of "a score never implies
    permission to act." Re-scoring always inserts a new `ScoringRun`;
    history is never overwritten (`OE-ADR-007`).
    """

    def __init__(
        self, database: Database, constitution: Constitution, provider: ScoringProvider
    ) -> None:
        self.database = database
        self.constitution = constitution
        self.provider = provider

    def score_opportunity(self, opportunity_id: int) -> dict:
        with self.database.session() as session:
            opportunity = session.execute(
                select(Opportunity.__table__).where(Opportunity.id == opportunity_id)
            ).mappings().first()
            if opportunity is None:
                raise ValueError(f"opportunity not found: {opportunity_id}")
            if opportunity["lifecycle_status"] != "eligible":
                raise ValueError(
                    "only opportunities with lifecycle_status 'eligible' can be scored"
                )

            opportunity_dict = dict(opportunity)
            payload = json.dumps(opportunity_dict, sort_keys=True, default=str)
            input_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

            run = ScoringRun(
                opportunity_id=opportunity_id,
                status="running",
                scoring_version=self.provider.scoring_version,
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                prompt_version=self.provider.prompt_version,
                input_hash=input_hash,
                correlation_id=str(uuid4()),
                started_at=now_iso(),
            )
            session.add(run)
            session.flush()
            run_id = run.id
            session.commit()

        try:
            result = self.provider.score(opportunity_dict, self.constitution)
        except Exception as exc:
            with self.database.session() as session:
                session.execute(
                    update(ScoringRun)
                    .where(ScoringRun.id == run_id)
                    .values(status="failed", completed_at=now_iso(), error_summary=str(exc))
                )
                session.commit()
            return {"scoring_run_id": run_id, "status": "failed", "error_summary": str(exc)}

        overall_score = sum(
            next(c.score for c in result.components if c.code == code) * weight
            for code, weight in COMPONENT_WEIGHTS.items()
        )

        with self.database.session() as session:
            session.execute(
                update(ScoringRun)
                .where(ScoringRun.id == run_id)
                .values(
                    status="succeeded",
                    completed_at=now_iso(),
                    overall_score=overall_score,
                    confidence=result.confidence,
                    fit_summary=result.fit_summary,
                    concerns=result.concerns,
                    structured_output_json=json.dumps(result.structured_payload),
                )
            )
            for component in result.components:
                session.add(
                    ScoreComponent(
                        scoring_run_id=run_id,
                        component_code=component.code,
                        score=component.score,
                        weight=COMPONENT_WEIGHTS[component.code],
                        explanation=component.explanation,
                    )
                )
            session.commit()

        return {"scoring_run_id": run_id, "status": "succeeded", "overall_score": overall_score}
