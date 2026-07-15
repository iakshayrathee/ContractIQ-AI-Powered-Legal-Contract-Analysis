"""Routes for contract analysis, risk reports, and plain-english summaries."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.dependencies import get_current_user
from app.db.models import AnalysisRow, ProjectRow
from app.schemas.contract import (
    AnalysisResponse,
    ContractAnalysis,
    PlainSummary,
    RiskReport,
    RiskResponse,
    SummaryResponse,
)
from app.services.contract_analysis_service import ContractAnalysisService
from app.services.project_service import ProjectService
from app.utils.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Contracts"])


async def _get_project_or_404(request: Request, project_name: str, user_id: str | None = None):
    ps: ProjectService = request.app.state.project_service
    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )
    return project


async def _get_project_row(request: Request, project_name: str, user_id: str | None = None) -> ProjectRow:
    """Get the raw DB row for a project."""
    session_factory: async_sessionmaker = request.app.state.session_factory
    async with session_factory() as session:
        query = select(ProjectRow).where(ProjectRow.name.ilike(project_name))
        if user_id is not None:
            # Only return project owned by this user (no NULL user_id fallback)
            query = query.where(ProjectRow.user_id == user_id)
        result = await session.execute(query)
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_name}' not found.",
            )
        return row


# ---------------------------------------------------------------------------
# POST /projects/{name}/analyze — trigger analysis
# ---------------------------------------------------------------------------

@router.post(
    "/{project_name}/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start contract analysis (background)",
)
@limiter.limit("5/minute")
async def analyze_contract(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> AnalysisResponse:
    project = await _get_project_or_404(request, project_name, user_id=user_id)
    
    # Check if project has any documents uploaded
    from pathlib import Path
    uploads_dir = Path("uploads") / project.collection_name
    doc_count = len([f for f in uploads_dir.iterdir() if f.is_file()]) if uploads_dir.exists() and uploads_dir.is_dir() else 0
    if doc_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No documents uploaded to this project. Upload a PDF first.",
        )

    cas: ContractAnalysisService = request.app.state.contract_analysis_service
    project_row = await _get_project_row(request, project_name, user_id=user_id)

    # Synchronously prepare analysis (cache check, input validation, DB row creation)
    row_id, status_val = await cas.prepare_analysis(
        project_name, project.collection_name, project_row.id
    )

    # If running, schedule background pipeline execution
    if status_val == "running":
        asyncio.create_task(
            cas.run_analysis_pipeline_from_row(row_id, project_name, project.collection_name)
        )
    
    # If completed (cached), fetch and return the full analysis
    if status_val == "completed":
        row = await cas.get_analysis(project_name, user_id=user_id)
        if row and row.status == "completed":
            analysis = None
            risk_report = None
            summary = None
            
            if row.analysis_json and row.analysis_json not in ("{}", "null", ""):
                try:
                    analysis = ContractAnalysis.model_validate_json(row.analysis_json)
                except Exception as e:
                    logger.warning("Failed to parse analysis_json: %s", e)
            
            if row.risk_json and row.risk_json not in ("{}", "null", ""):
                try:
                    risk_report = RiskReport.model_validate_json(row.risk_json)
                except Exception as e:
                    logger.warning("Failed to parse risk_json: %s", e)
            
            if row.summary_json and row.summary_json not in ("{}", "null", ""):
                try:
                    summary = PlainSummary.model_validate_json(row.summary_json)
                except Exception as e:
                    logger.warning("Failed to parse summary_json: %s", e)
            
            return AnalysisResponse(
                project_name=project_name,
                status="completed",
                analysis=analysis,
                risk_report=risk_report,
                summary=summary,
            )

    return AnalysisResponse(project_name=project_name, status=status_val)


# ---------------------------------------------------------------------------
# GET /projects/{name}/analysis — get cached analysis result
# ---------------------------------------------------------------------------

@router.get(
    "/{project_name}/analysis",
    response_model=AnalysisResponse,
    summary="Get contract analysis results",
)
async def get_analysis(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> AnalysisResponse:
    await _get_project_or_404(request, project_name, user_id=user_id)
    cas: ContractAnalysisService = request.app.state.contract_analysis_service

    row = await cas.get_analysis(project_name, user_id=user_id)
    if row is None:
        return AnalysisResponse(project_name=project_name, status="none")

    analysis = None
    risk_report = None
    summary = None
    
    if row.status == "completed":
        if row.analysis_json and row.analysis_json not in ("{}", "null", ""):
            try:
                analysis = ContractAnalysis.model_validate_json(row.analysis_json)
            except Exception as e:
                logger.warning("Failed to parse analysis_json for project '%s': %s", project_name, e)
        
        if row.risk_json and row.risk_json not in ("{}", "null", ""):
            try:
                risk_report = RiskReport.model_validate_json(row.risk_json)
            except Exception as e:
                logger.warning("Failed to parse risk_json for project '%s': %s", project_name, e)
        
        if row.summary_json and row.summary_json not in ("{}", "null", ""):
            try:
                summary = PlainSummary.model_validate_json(row.summary_json)
            except Exception as e:
                logger.warning("Failed to parse summary_json for project '%s': %s", project_name, e)

    return AnalysisResponse(
        project_name=project_name,
        status=row.status,
        analysis=analysis,
        risk_report=risk_report,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# GET /projects/{name}/analysis/clauses?type=termination
# ---------------------------------------------------------------------------

@router.get(
    "/{project_name}/analysis/clauses",
    summary="List extracted clauses with optional type filter",
)
async def get_clauses(
    project_name: str,
    request: Request,
    type: str | None = None,
    user_id: str = Depends(get_current_user),
) -> dict:
    await _get_project_or_404(request, project_name, user_id=user_id)
    cas: ContractAnalysisService = request.app.state.contract_analysis_service

    row = await cas.get_analysis(project_name, user_id=user_id)
    if row is None or row.status != "completed":
        raise HTTPException(status_code=404, detail="No completed analysis found. Run POST /analyze first.")

    analysis = ContractAnalysis.model_validate_json(row.analysis_json)
    clauses = analysis.clauses

    if type:
        clauses = [c for c in clauses if c.clause_type.value == type]

    return {
        "project_name": project_name,
        "total": len(clauses),
        "clauses": [c.model_dump() for c in clauses],
    }


# ---------------------------------------------------------------------------
# GET /projects/{name}/risks — risk report
# ---------------------------------------------------------------------------

@router.get(
    "/{project_name}/risks",
    response_model=RiskResponse,
    summary="Get risk analysis report",
)
async def get_risks(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> RiskResponse:
    await _get_project_or_404(request, project_name, user_id=user_id)
    cas: ContractAnalysisService = request.app.state.contract_analysis_service

    row = await cas.get_analysis(project_name, user_id=user_id)
    if row is None or row.status != "completed":
        return RiskResponse(project_name=project_name, risk_report=None)

    risk_report = None
    if row.risk_json and row.risk_json not in ("{}", "null", ""):
        try:
            risk_report = RiskReport.model_validate_json(row.risk_json)
        except Exception as e:
            logger.warning("Failed to parse risk_json for project '%s': %s", project_name, e)

    return RiskResponse(project_name=project_name, risk_report=risk_report)


# ---------------------------------------------------------------------------
# GET /projects/{name}/summary — plain-english summary
# ---------------------------------------------------------------------------

@router.get(
    "/{project_name}/summary",
    response_model=SummaryResponse,
    summary="Get plain-english contract summary",
)
async def get_summary(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> SummaryResponse:
    await _get_project_or_404(request, project_name, user_id=user_id)
    cas: ContractAnalysisService = request.app.state.contract_analysis_service

    row = await cas.get_analysis(project_name, user_id=user_id)
    if row is None or row.status != "completed":
        return SummaryResponse(project_name=project_name, summary=None)

    plain_summary = None
    if row.summary_json and row.summary_json not in ("{}", "null", ""):
        try:
            plain_summary = PlainSummary.model_validate_json(row.summary_json)
        except Exception as e:
            logger.warning("Failed to parse summary_json for project '%s': %s", project_name, e)

    return SummaryResponse(project_name=project_name, summary=plain_summary)


# ---------------------------------------------------------------------------
# GET /projects/{name}/quality — judge scores + guardrail warnings
# ---------------------------------------------------------------------------

@router.get(
    "/{project_name}/quality",
    summary="Get LLM-as-Judge quality scores and guardrail warnings",
)
async def get_quality(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Returns quality evaluation from LLM-as-Judge and output guardrails.

    Includes:
    - Judge overall score and per-dimension scores
    - Hallucination and missing clause flags
    - Unsafe statement warnings
    - Guardrail confidence scores
    - Whether the analysis was flagged for human review
    """
    await _get_project_or_404(request, project_name, user_id=user_id)
    cas: ContractAnalysisService = request.app.state.contract_analysis_service

    row = await cas.get_analysis(project_name, user_id=user_id)
    if row is None or row.status != "completed":
        raise HTTPException(
            status_code=404,
            detail="No completed analysis found. Run POST /analyze first.",
        )

    judge_data = {}
    if row.judge_json:
        try:
            judge_data = json.loads(row.judge_json)
        except Exception:
            pass

    guardrail_data = {}
    if row.guardrail_warnings_json:
        try:
            guardrail_data = json.loads(row.guardrail_warnings_json)
        except Exception:
            pass

    return {
        "project_name": project_name,
        "quality_score": row.quality_score,
        "flagged_for_review": row.flagged_for_review,
        "judge": judge_data,
        "guardrails": guardrail_data,
    }
