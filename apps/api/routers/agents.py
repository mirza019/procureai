from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from apps.api.dependencies import DbSession, current_user, require_roles
from procureai.ai.orchestrator import AgentOrchestrator, route_question
from procureai.db.models import AgentInteraction, ProcurementAction, Role, User
from procureai.schemas.agents import AgentRequest, ProcurementAgentResponse, Recommendation

router = APIRouter(prefix="/agents", tags=["procurement agents"])
Authenticated = Annotated[User, Depends(current_user)]
orchestrator = AgentOrchestrator()


@router.post("/query", response_model=ProcurementAgentResponse)
async def query_agent(request: AgentRequest, db: DbSession, user: Authenticated):
    try:
        return await orchestrator.execute(db, request, role=user.role, user_id=user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/morning-brief", response_model=ProcurementAgentResponse)
async def morning_brief(db: DbSession, user: Authenticated, session_id: str = "daily-brief"):
    request = AgentRequest(
        question="What should procurement management focus on this month? Return no more than five priorities.",
        session_id=session_id,
    )
    return await orchestrator.execute(db, request, role=user.role, user_id=user.id)


@router.get("/route")
def preview_route(question: str, _: Authenticated):
    return route_question(question)


class ActionCreate(BaseModel):
    recommendation: Recommendation


@router.post("/actions", status_code=201)
def create_action(
    payload: ActionCreate,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(Role.ADMIN, Role.PROCUREMENT_MANAGER))],
):
    recommendation = payload.recommendation
    action = ProcurementAction(
        action_type=recommendation.action_type,
        title=recommendation.title,
        reason=recommendation.reason,
        financial_exposure=recommendation.financial_exposure,
        priority=recommendation.priority,
        suggested_owner=recommendation.suggested_owner,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return {"action_id": action.action_id, "status": action.status}


@router.get("/actions")
def list_actions(db: DbSession, _: Authenticated):
    return [
        {
            "action_id": row.action_id,
            "type": row.action_type,
            "title": row.title,
            "priority": row.priority,
            "owner": row.suggested_owner,
            "status": row.status,
            "financial_exposure": row.financial_exposure,
        }
        for row in db.scalars(
            select(ProcurementAction).order_by(desc(ProcurementAction.created_at)).limit(100)
        )
    ]


@router.post("/actions/{action_id}/acknowledge")
def acknowledge(
    action_id: UUID,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(Role.ADMIN, Role.PROCUREMENT_MANAGER))],
):
    action = db.get(ProcurementAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    action.status = "ACKNOWLEDGED"
    action.acknowledged_at = datetime.now(UTC)
    db.commit()
    return {"action_id": action.action_id, "status": action.status}


@router.post("/actions/{action_id}/resolve")
def resolve(
    action_id: UUID,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(Role.ADMIN, Role.PROCUREMENT_MANAGER))],
):
    action = db.get(ProcurementAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    action.status = "RESOLVED"
    action.resolved_at = datetime.now(UTC)
    db.commit()
    return {"action_id": action.action_id, "status": action.status}


@router.get("/diagnostics")
def diagnostics(db: DbSession, _: Annotated[User, Depends(require_roles(Role.ADMIN))]):
    rows = list(
        db.scalars(select(AgentInteraction).order_by(desc(AgentInteraction.created_at)).limit(100))
    )
    return {
        "requests": len(rows),
        "failures": sum(row.status == "FAILED" for row in rows),
        "average_total_latency_ms": round(sum(row.total_latency_ms for row in rows) / len(rows), 1)
        if rows
        else 0,
        "average_tool_latency_ms": round(sum(row.tool_latency_ms for row in rows) / len(rows), 1)
        if rows
        else 0,
        "average_llm_latency_ms": round(sum(row.llm_latency_ms for row in rows) / len(rows), 1)
        if rows
        else 0,
        "by_agent": {
            name: sum(row.agent_name == name for row in rows)
            for name in sorted({row.agent_name for row in rows})
        },
    }
