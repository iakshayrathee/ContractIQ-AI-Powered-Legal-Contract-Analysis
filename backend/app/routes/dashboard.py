"""Dashboard aggregation route."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.dependencies import get_current_user
from app.db.models import AnalysisRow, ProjectRow
from app.schemas.contract import DashboardStats, DashboardTrends, TimelinePoint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

TIMELINE_DAYS = 14
TREND_WINDOW_DAYS = 7

# Supported time-range filters -> number of days back. "all" = no date filter.
RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}


def _count_documents_on_disk(collection_name: str) -> int:
    """Count actual files in the uploads directory for a collection."""
    uploads_dir = Path("uploads") / collection_name
    if not uploads_dir.exists() or not uploads_dir.is_dir():
        return 0
    return len([f for f in uploads_dir.iterdir() if f.is_file()])


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize a datetime to timezone-aware UTC (SQLite may return naive)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _pct_change(current: float, previous: float) -> float | None:
    """Percentage change from ``previous`` to ``current``.

    Returns ``None`` when there is no prior-period baseline to compare against,
    so the UI can hide the trend badge instead of showing a meaningless value.
    """
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


@router.get("/stats", response_model=DashboardStats, summary="Dashboard statistics")
async def get_dashboard_stats(
    request: Request,
    time_range: str = Query(
        "all",
        alias="range",
        description="Time-range filter for analysis activity: 7d, 30d, 90d, or all.",
    ),
    user_id: str = Depends(get_current_user),
) -> DashboardStats:
    session_factory: async_sessionmaker = request.app.state.session_factory

    # Normalize the requested range; unknown values fall back to "all".
    range_key = time_range if time_range in RANGE_DAYS or time_range == "all" else "all"

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

        # Time windows for trends / timeline (all UTC).
        now = datetime.now(timezone.utc)
        current_start = now - timedelta(days=TREND_WINDOW_DAYS)
        previous_start = now - timedelta(days=2 * TREND_WINDOW_DAYS)

        # Range filter: scopes analysis-activity metrics. "all" -> no cutoff and
        # the timeline falls back to the default 14-day window.
        if range_key in RANGE_DAYS:
            timeline_days = RANGE_DAYS[range_key]
            range_start = now - timedelta(days=timeline_days)
        else:
            timeline_days = TIMELINE_DAYS
            range_start = None
        timeline_start = (now - timedelta(days=timeline_days - 1)).date()

        # Risk distribution and clause counts
        risk_distribution: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        clause_type_counts: dict[str, int] = {}
        risk_category_counts: dict[str, int] = {}
        contract_type_counts: dict[str, int] = {}
        timeline_counts: dict[str, int] = {
            (timeline_start + timedelta(days=i)).isoformat(): 0 for i in range(timeline_days)
        }
        total_risk_score = 0
        quality_total = 0.0
        quality_n = 0
        flagged_count = 0
        in_range_count = 0
        recent_analyses = []

        # Trend accumulators (period-over-period, always full dataset).
        cur_analyses = prev_analyses = 0
        cur_risk_sum = prev_risk_sum = 0

        for a, project_name in analyses_data_rows:
            created = _as_utc(a.created_at)

            # Trend bucketing runs over the full dataset (recent momentum),
            # independent of the selected range filter.
            if created is not None:
                if created >= current_start:
                    cur_analyses += 1
                    cur_risk_sum += a.overall_risk_score
                elif created >= previous_start:
                    prev_analyses += 1
                    prev_risk_sum += a.overall_risk_score

            # Recent analyses list is always full-dataset (top 10 most recent).
            recent_analyses.append({
                "project_name": project_name,
                "risk_score": a.overall_risk_score,
                "status": a.status,
                "created_at": created.isoformat() if created else "",
            })

            # Apply the range filter to all activity aggregates below.
            if range_start is not None and (created is None or created < range_start):
                continue
            in_range_count += 1
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

            # Quality signal from the judge (stored 0.0-1.0)
            if a.quality_score:
                quality_total += a.quality_score
                quality_n += 1
            if a.flagged_for_review:
                flagged_count += 1

            # Clause types + contract type (from analysis JSON)
            try:
                analysis_data = json.loads(a.analysis_json) if a.analysis_json else {}
                for clause in analysis_data.get("clauses", []):
                    ct = clause.get("clause_type", "other")
                    clause_type_counts[ct] = clause_type_counts.get(ct, 0) + 1
                contract_type = (analysis_data.get("metadata") or {}).get("contract_type")
                if contract_type:
                    contract_type_counts[contract_type] = contract_type_counts.get(contract_type, 0) + 1
            except (json.JSONDecodeError, Exception):
                pass

            # Risk categories (from risk JSON items)
            try:
                risk_data = json.loads(a.risk_json) if a.risk_json else {}
                for item in risk_data.get("items", []):
                    cat = item.get("category", "other")
                    risk_category_counts[cat] = risk_category_counts.get(cat, 0) + 1
            except (json.JSONDecodeError, Exception):
                pass

            # Timeline bucketing (within the selected window)
            if created is not None:
                day_key = created.date().isoformat()
                if day_key in timeline_counts:
                    timeline_counts[day_key] += 1

        total_analyses = in_range_count
        avg_risk = total_risk_score / total_analyses if total_analyses else 0
        high_risk_count = risk_distribution["high"] + risk_distribution["critical"]
        avg_quality = (quality_total / quality_n * 100) if quality_n else 0.0

        # Real period-over-period trends.
        cur_projects = sum(
            1 for p in projects if (d := _as_utc(p.created_at)) and d >= current_start
        )
        prev_projects = sum(
            1
            for p in projects
            if (d := _as_utc(p.created_at)) and previous_start <= d < current_start
        )
        cur_avg_risk = cur_risk_sum / cur_analyses if cur_analyses else 0
        prev_avg_risk = prev_risk_sum / prev_analyses if prev_analyses else 0

        trends = DashboardTrends(
            projects=_pct_change(cur_projects, prev_projects),
            analyses=_pct_change(cur_analyses, prev_analyses),
            risk=_pct_change(cur_avg_risk, prev_avg_risk),
        )

        analyses_timeline = [
            TimelinePoint(date=day, count=count)
            for day, count in sorted(timeline_counts.items())
        ]

        # Sort recent analyses by date, take top 10
        recent_analyses.sort(key=lambda x: x["created_at"], reverse=True)
        recent_analyses = recent_analyses[:10]

    return DashboardStats(
        total_projects=total_projects,
        total_documents=total_documents,
        total_analyses=total_analyses,
        avg_risk_score=round(avg_risk, 1),
        high_risk_count=high_risk_count,
        flagged_count=flagged_count,
        avg_quality_score=round(avg_quality, 1),
        risk_distribution=risk_distribution,
        clause_type_counts=clause_type_counts,
        risk_category_counts=risk_category_counts,
        contract_type_counts=contract_type_counts,
        analyses_timeline=analyses_timeline,
        trends=trends,
        recent_analyses=recent_analyses,
        range=range_key,
    )
