import pytest

from procureai.db.models import Role
from procureai.security.demo_sso import IDENTITIES, DemoSSOProvider


@pytest.fixture
def provider() -> DemoSSOProvider:
    return DemoSSOProvider("test-secret-that-is-long-enough-for-signing")


@pytest.mark.parametrize("role", list(Role))
def test_demo_roles_receive_signed_identity_and_landing_page(
    provider: DemoSSOProvider, role: Role
) -> None:
    token, expected = provider.authenticate(role.value)
    identity = provider.verify(token)

    assert identity == expected == IDENTITIES[role]
    assert identity.landing_page.startswith("/")


def test_arbitrary_role_is_rejected(provider: DemoSSOProvider) -> None:
    with pytest.raises(PermissionError):
        provider.authenticate("SUPERUSER")


def test_tampered_session_is_rejected(provider: DemoSSOProvider) -> None:
    token, _ = provider.authenticate(Role.EXECUTIVE.value)
    assert provider.verify(f"{token}tampered") is None
