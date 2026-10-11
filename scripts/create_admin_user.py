#!/usr/bin/env python3
"""Create an admin user for ARTEF.

This bootstrap script intentionally fails closed: credentials must be provided via
environment variables and cannot fall back to weak built-in defaults.
"""

import os
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.models.user import Base, User


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Set it in your shell or .env before running this script."
        )
    return value.strip()


async def create_admin_user():
    """Create the configured admin user."""
    database_url = os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///backend/redteam_dev.db"

    admin_email = require_env("ADMIN_EMAIL")
    admin_username = require_env("ADMIN_USERNAME")
    admin_password = require_env("ADMIN_PASSWORD")
    admin_fullname = os.getenv("ADMIN_FULLNAME") or "Admin User"

    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == admin_username))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"[OK] Admin user '{admin_username}' already exists")
            return

        admin_user = User(
            id=str(uuid4()),
            email=admin_email,
            username=admin_username,
            hashed_password=get_password_hash(admin_password),
            full_name=admin_fullname,
            is_active=True,
            is_superuser=True,
        )

        session.add(admin_user)
        await session.commit()

        print("[OK] Admin user created successfully!")
        print(f"  Username: {admin_username}")
        print(f"  Password: {'*' * max(len(admin_password), 8)}")
        print(f"  Email: {admin_email}")


if __name__ == "__main__":
    try:
        asyncio.run(create_admin_user())
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
