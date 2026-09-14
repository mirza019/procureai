from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from procureai.db.models import Role
from procureai.schemas.agents import ToolEvidence

ToolFunction = Callable[..., ToolEvidence]


@dataclass(frozen=True)
class ToolContext:
    db: Session
    role: Role
    user_id: str | None = None


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    function: ToolFunction
    roles: frozenset[Role]
    description: str


class ToolRegistry:
    """Allow-listed procurement tools with server-side RBAC enforcement."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self, name: str, function: ToolFunction, *, roles: set[Role], description: str
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = RegisteredTool(name, function, frozenset(roles), description)

    def execute(self, name: str, context: ToolContext, **parameters: Any) -> ToolEvidence:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Unknown procurement tool: {name}")
        if context.role not in tool.roles:
            raise PermissionError(f"Role {context.role.value} cannot use {name}")
        return tool.function(context.db, **parameters)

    def available(self, role: Role) -> list[str]:
        return sorted(tool.name for tool in self._tools.values() if role in tool.roles)


def build_tool_registry() -> ToolRegistry:
    from procureai.ai.tools.procurement_tools import (
        compare_suppliers,
        get_cost_opportunities,
        get_executive_overview,
        get_procurement_alerts,
        get_supplier_investigation,
        rank_entities,
        rank_sourcing_candidates,
    )

    all_roles = {Role.ADMIN, Role.PROCUREMENT_ANALYST, Role.PROCUREMENT_MANAGER, Role.EXECUTIVE}
    detailed = {Role.ADMIN, Role.PROCUREMENT_ANALYST, Role.PROCUREMENT_MANAGER}
    sourcing = {Role.ADMIN, Role.PROCUREMENT_ANALYST, Role.PROCUREMENT_MANAGER}
    registry = ToolRegistry()
    registry.register(
        "rank_entities",
        rank_entities,
        roles=all_roles,
        description="Allow-listed deterministic ranking across approved procurement metrics",
    )
    registry.register(
        "get_executive_overview",
        get_executive_overview,
        roles=all_roles,
        description="Portfolio KPIs and trends",
    )
    registry.register(
        "get_procurement_alerts",
        get_procurement_alerts,
        roles=all_roles,
        description="Prioritized deterministic alerts",
    )
    registry.register(
        "get_supplier_investigation",
        get_supplier_investigation,
        roles=detailed,
        description="Detailed supplier performance and risk evidence",
    )
    registry.register(
        "compare_suppliers",
        compare_suppliers,
        roles=detailed,
        description="Supplier scorecard comparison",
    )
    registry.register(
        "get_cost_opportunities",
        get_cost_opportunities,
        roles=detailed,
        description="Deterministic price and savings opportunities",
    )
    registry.register(
        "rank_sourcing_candidates",
        rank_sourcing_candidates,
        roles=sourcing,
        description="Deterministic sourcing ranking",
    )
    return registry
