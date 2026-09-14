import os

from sqlalchemy import select

from procureai.db.models import Role, User
from procureai.db.session import SessionLocal
from procureai.security.auth import hash_password
from procureai.synthetic.demo import load_demo_data


def main() -> None:
    """Create demo users and an idempotent connected procurement dataset."""
    if os.getenv("APP_ENV", "development") == "production":
        raise RuntimeError("Demo bootstrap is disabled in production")
    password = os.getenv("DEMO_ADMIN_PASSWORD", "ProcureAI-Demo-2026!")
    users = [
        (os.getenv("DEMO_ADMIN_EMAIL", "admin@procureai.local"), "Demo Administrator", Role.ADMIN),
        ("analyst@procureai.local", "Demo Analyst", Role.PROCUREMENT_ANALYST),
        ("manager@procureai.local", "Demo Manager", Role.PROCUREMENT_MANAGER),
        ("executive@procureai.local", "Demo Executive", Role.EXECUTIVE),
    ]
    with SessionLocal() as db:
        for email, name, role in users:
            if not db.scalar(select(User).where(User.email == email)):
                db.add(
                    User(
                        email=email,
                        hashed_password=hash_password(password),
                        full_name=name,
                        role=role,
                    )
                )
        db.commit()
        result = load_demo_data(db, po_count=int(os.getenv("DEMO_PO_COUNT", "2500")))
        print(f"ProcureAI demo ready: {result}")


if __name__ == "__main__":
    main()
