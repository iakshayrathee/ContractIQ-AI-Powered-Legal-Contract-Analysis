"""
Routes for fine-tuning model management.

Provides endpoints for listing models, checking job status, activating models,
and dataset statistics.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.dependencies import get_current_user
from app.db.models import ModelRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/finetuning", tags=["Fine-Tuning"])


@router.get("/models")
async def list_models(
    request: Request,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    List all fine-tuned models in the registry.

    Returns model metadata including status, training metrics, and evaluation scores.
    """
    session_factory: async_sessionmaker = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(ModelRegistry).order_by(ModelRegistry.created_at.desc())
        )
        models = result.scalars().all()

    return {
        "models": [
            {
                "model_id": m.model_id,
                "base_model": m.base_model,
                "status": m.status,
                "dataset_hash": m.dataset_hash,
                "n_examples": m.n_examples,
                "n_epochs": m.n_epochs,
                "train_loss": m.train_loss,
                "val_loss": m.val_loss,
                "clause_f1": m.clause_f1,
                "clause_precision": m.clause_precision,
                "clause_recall": m.clause_recall,
                "trained_at": m.trained_at.isoformat() if m.trained_at else None,
                "created_at": m.created_at.isoformat(),
                "error_message": m.error_message,
            }
            for m in models
        ]
    }


@router.get("/models/{model_id}/status")
async def get_model_status(
    model_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Get the status of a specific fine-tuning job.

    Returns job status, training progress, and any error messages.
    """
    session_factory: async_sessionmaker = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(ModelRegistry).where(ModelRegistry.model_id == model_id)
        )
        model = result.scalar_one_or_none()

    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found in registry."
        )

    return {
        "model_id": model.model_id,
        "job_id": model.job_id,
        "status": model.status,
        "base_model": model.base_model,
        "dataset_hash": model.dataset_hash,
        "n_examples": model.n_examples,
        "n_epochs": model.n_epochs,
        "train_loss": model.train_loss,
        "val_loss": model.val_loss,
        "training_tokens": model.training_tokens,
        "training_duration_seconds": model.training_duration_seconds,
        "trained_at": model.trained_at.isoformat() if model.trained_at else None,
        "error_message": model.error_message,
    }


@router.get("/dataset/stats")
async def get_dataset_stats(
    request: Request,
    threshold: float = 0.85,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Get statistics about eligible chunks for fine-tuning.

    Args:
        threshold: Judge score threshold for silver label eligibility

    Returns:
        Count of eligible chunks broken down by clause type
    """
    from collections import Counter

    from app.db.models import AnalysisRow, ProjectRow

    session_factory: async_sessionmaker = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(AnalysisRow)
            .join(ProjectRow, AnalysisRow.project_id == ProjectRow.id)
            .where(
                AnalysisRow.status == "completed",
                AnalysisRow.quality_score >= threshold,
                ProjectRow.user_id == user_id,
            )
        )
        analyses = result.scalars().all()

    # Count by clause type
    clause_type_counts = Counter()
    total_eligible = 0

    for analysis in analyses:
        try:
            import json
            analysis_data = json.loads(analysis.analysis_json)
            clauses = analysis_data.get("clauses", [])
            for clause in clauses:
                clause_type = clause.get("clause_type")
                if clause_type:
                    clause_type_counts[clause_type] += 1
            total_eligible += 1
        except Exception:
            continue

    return {
        "threshold": threshold,
        "total_eligible_analyses": total_eligible,
        "total_clauses": sum(clause_type_counts.values()),
        "clause_type_breakdown": dict(clause_type_counts),
    }


@router.post("/activate/{model_id}")
async def activate_model(
    model_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Activate a fine-tuned model for production use.

    Stores the current active model as previous_model_id before switching.
    Updates app configuration at runtime.
    """
    session_factory: async_sessionmaker = request.app.state.session_factory

    async with session_factory() as session:
        # Get the model to activate
        result = await session.execute(
            select(ModelRegistry).where(ModelRegistry.model_id == model_id)
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model '{model_id}' not found in registry."
            )

        if model.status != "ready":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Model '{model_id}' is not ready (status: {model.status})."
            )

        # Get current active model (if any)
        current_result = await session.execute(
            select(ModelRegistry).where(ModelRegistry.status == "active")
        )
        current_active = current_result.scalar_one_or_none()

        # Store previous model ID
        if current_active:
            current_active.previous_model_id = current_active.model_id
            current_active.status = "ready"  # Deactivate current

        # Activate new model
        model.status = "active"
        model.previous_model_id = current_active.model_id if current_active else None

        await session.commit()

    # Update runtime config
    request.app.state.settings.openai_model_finetuned = model_id
    request.app.state.settings.use_finetuned_model = True

    logger.info("Activated fine-tuned model: %s (previous: %s)", model_id, model.previous_model_id)

    return {
        "message": f"Model '{model_id}' activated successfully.",
        "model_id": model_id,
        "previous_model_id": model.previous_model_id,
    }


@router.post("/rollback")
async def rollback_model(
    request: Request,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Rollback to the previous active model.

    Restores the previous_model_id as the active model.
    """
    session_factory: async_sessionmaker = request.app.state.session_factory

    async with session_factory() as session:
        # Get current active model
        result = await session.execute(
            select(ModelRegistry).where(ModelRegistry.status == "active")
        )
        current_active = result.scalar_one_or_none()

        if current_active is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active model found."
            )

        if current_active.previous_model_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No previous model to rollback to."
            )

        # Get previous model
        prev_result = await session.execute(
            select(ModelRegistry).where(ModelRegistry.model_id == current_active.previous_model_id)
        )
        previous_model = prev_result.scalar_one_or_none()

        if previous_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Previous model '{current_active.previous_model_id}' not found."
            )

        # Deactivate current
        current_active.status = "ready"

        # Activate previous
        previous_model.status = "active"
        previous_model.previous_model_id = None

        await session.commit()

    # Update runtime config
    request.app.state.settings.openai_model_finetuned = previous_model.model_id
    request.app.state.settings.use_finetuned_model = True

    logger.info("Rolled back to model: %s", previous_model.model_id)

    return {
        "message": f"Rolled back to model '{previous_model.model_id}'.",
        "model_id": previous_model.model_id,
    }
