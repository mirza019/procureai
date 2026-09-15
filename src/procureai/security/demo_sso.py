"""Replaceable authentication provider for the portfolio demo."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import jwt

from procureai.db.models import Role


@dataclass(frozen=True)
class DemoIdentity:
    name: str
    role: Role
    label: str
    icon: str
    landing_page: str
    description: str


IDENTITIES = {
    Role.EXECUTIVE: DemoIdentity("Demo Executive", Role.EXECUTIVE, "Executive", "business_center", "/", "Strategic procurement performance, risk and value."),
    Role.PROCUREMENT_MANAGER: DemoIdentity("Demo Manager", Role.PROCUREMENT_MANAGER, "Procurement Manager", "inventory_2", "/procurement", "Supplier performance, sourcing, cost and action management."),
    Role.PROCUREMENT_ANALYST: DemoIdentity("Demo Analyst", Role.PROCUREMENT_ANALYST, "Procurement Analyst", "query_stats", "/procurement", "Detailed procurement analytics, exceptions and investigation."),
    Role.ADMIN: DemoIdentity("Demo Administrator", Role.ADMIN, "Administrator", "admin_panel_settings", "/pipelines", "Pipeline, data quality and platform administration."),
}


class AuthProvider(Protocol):
    def authenticate(self, selected_role: str) -> tuple[str, DemoIdentity]: ...
    def verify(self, token: str) -> DemoIdentity | None: ...


class DemoSSOProvider:
    """Issue signed, allow-listed demo sessions; replaceable by an Entra provider."""

    def __init__(self, secret: str) -> None:
        self.secret = secret

    def authenticate(self, selected_role: str) -> tuple[str, DemoIdentity]:
        try:
            role = Role(selected_role)
            identity = IDENTITIES[role]
        except (ValueError, KeyError) as exc:
            raise PermissionError("Invalid demo role") from exc
        now = datetime.now(UTC)
        token = jwt.encode({"sub": identity.name, "role": role.value, "iat": now, "exp": now + timedelta(hours=8)}, self.secret, algorithm="HS256")
        return token, identity

    def verify(self, token: str) -> DemoIdentity | None:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            role = Role(payload["role"])
            identity = IDENTITIES[role]
            return identity if payload.get("sub") == identity.name else None
        except (jwt.PyJWTError, ValueError, KeyError):
            return None


def public_identity(identity: DemoIdentity) -> dict:
    data = asdict(identity)
    data["role"] = identity.role.value
    return data
