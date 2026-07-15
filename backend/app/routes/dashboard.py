"""Dashboard aggregation route."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.dependencies import get_current_user
from app.db.models import AnalysisRow, ProjectRow
from app.schemas.contract import DashboardStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _count_documents_on_disk(collection_name: str) -> int:
    """Count actual files in the uploads directory for a collection."""
    uploads_dir = Path("uploads") / collection_name
    if not uploads_dir.exists() or not uploads_dir.is_dir():
        return 0
    return len([f for f in uploads_dir.iterdir() if f.is_file()])


@router.get("/stats", response_model=DashboardStats, summary="Dashboard statistics")
async def get_dashboard_stats(
    request: Request,
    user_id: str = Depends(get_current_user),
) -> DashboardStats:
    session_factory: async_sessionmaker = request.app.state.session_factory

    async with session_factory() as session:
        # Total projects
        proj_result = await session.execute(
            select(func.count(ProjectRow.id)).where(ProjectRow.user_id == user_id)
        )
        total_projects = proj_result.scalar() or 0

        # Get all projects for doc counts (count files on disk, not Qdrant points)
        projects_result = await session.execute(
            select(ProjectRow).where(ProjectRow.user_id == user_id)
        )
        projects = projects_result.scalars().all()
        total_documents = sum(_count_documents_on_disk(p.collection_name) for p in projects)

        # Completed analyses (solves N+1 and filters by user_id)
        analyses_result = await session.execute(
            select(AnalysisRow, ProjectRow.name)
            .join(ProjectRow, AnalysisRow.project_id == ProjectRow.id)
            .where(AnalysisRow.status == "completed")
            .where(ProjectRow.user_id == user_id)
        )
        analyses_data_rows = analyses_result.all()

        # Risk distribution and clause counts
        risk_distribution: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        clause_type_counts: dict[str, int] = {}
        total_risk_score = 0
        recent_analyses = []

        for a, project_name in analyses_data_rows:
            total_risk_score += a.overall_risk_score

            # Risk level
            if a.overall_risk_score <= 30:
                risk_distribution["low"] += 1
            elif a.overall_risk_score <= 60:
                risk_distribution["medium"] += 1
            elif a.overall_risk_score <= 80:
                risk_distribution["high"] += 1
            else:
                risk_distribution["critical"] += 1

            # Clause types
            try:
                analysis_data = json.loads(a.analysis_json) if a.analysis_json else {}
                for clause in analysis_data.get("clauses", []):
                    ct = clause.get("clause_type", "other")
                    clause_type_counts[ct] = clause_type_counts.get(ct, 0) + 1
            except (json.JSONDecodeError, Exception):
                pass

            # For recent analyses
            recent_analyses.append({
                "project_name": project_name,
                "risk_score": a.overall_risk_score,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            })

        avg_risk = total_risk_score / len(analyses_data_rows) if analyses_data_rows else 0

        # Sort recent analyses by date, take top 10
        recent_analyses.sort(key=lambda x: x["created_at"], reverse=True)
        recent_analyses = recent_analyses[:10]

    return DashboardStats(
        total_projects=total_projects,
        total_documents=total_documents,
        avg_risk_score=round(avg_risk, 1),
        risk_distribution=risk_distribution,
        clause_type_counts=clause_type_counts,
        recent_analyses=recent_analyses,
    )
