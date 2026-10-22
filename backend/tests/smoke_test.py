"""End-to-end smoke test against a live ARTEF backend.

Starts the API in-process (TestClient), authenticates as a seeded admin and
exercises the endpoints the dashboard depends on plus the previously broken
write paths.

Run with:  python backend/tests/smoke_test.py
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import async_session_maker, init_db  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.models.user import User  # noqa: E402
from app.main import app  # noqa: E402

USERNAME = f"smoke_{uuid.uuid4().hex[:8]}"
PASSWORD = os.getenv("TEST_USER_PASSWORD", "smoke-test-password-1234")  # nosec: test fixture

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name} {detail}")
        print(f"  FAIL  {name} {detail}")


async def seed_admin() -> None:
    """Create an admin user together with the admin role."""
    from app.models.user import Role

    async with async_session_maker() as session:
        role_res = await session.execute(select(Role).where(Role.name == "admin"))
        role = role_res.scalars().first()
        if role is None:
            role = Role(
                name="admin",
                description="Administrator",
                permissions=[],
            )
            session.add(role)
            await session.flush()

        session.add(
            User(
                username=USERNAME,
                email=f"{USERNAME}@smoke.local",
                hashed_password=get_password_hash(PASSWORD),
                is_active=True,
                is_superuser=True,
                roles=[role],
            )
        )
        await session.commit()


def main() -> int:
    asyncio.run(seed_admin())

    with TestClient(app) as client:
        print("\n== health ==")
        r = client.get("/api/v1/health")
        check("GET /api/v1/health", r.status_code == 200, r.text[:120])

        r = client.get("/api/v1/ready")
        check("GET /api/v1/ready", r.status_code == 200, r.text[:120])

        print("\n== authentication ==")
        r = client.post(
            "/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD}
        )
        check("POST /api/v1/auth/login", r.status_code == 200, r.text[:200])
        if r.status_code != 200:
            return 1
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = client.get("/api/v1/auth/me", headers=headers)
        check("GET /api/v1/auth/me", r.status_code == 200, r.text[:200])

        r = client.get("/api/v1/users/me", headers=headers)
        check("GET /api/v1/users/me", r.status_code == 200, r.text[:200])

        print("\n== dashboard data path ==")
        r = client.get("/api/v1/runs/stats", headers=headers)
        check("GET /api/v1/runs/stats", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            body = r.json()
            check(
                "runs/stats has the documented shape",
                all(
                    k in body
                    for k in (
                        "total_runs",
                        "pass_rate",
                        "total_regressions",
                        "critical_findings",
                        "review_queue_count",
                    )
                ),
                str(body)[:200],
            )

        r = client.get("/api/v1/runs?limit=5", headers=headers)
        check("GET /api/v1/runs", r.status_code == 200, r.text[:200])
        check(
            "runs response exposes the total count header",
            "x-total-count" in {k.lower() for k in r.headers},
            str(dict(r.headers))[:200],
        )

        r = client.get("/api/v1/monitoring/dashboard", headers=headers)
        check("GET /api/v1/monitoring/dashboard", r.status_code == 200, r.text[:200])

        r = client.get("/api/v1/analytics?range=7d", headers=headers)
        check("GET /api/v1/analytics", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            body = r.json()
            check(
                "analytics returns real category data (may be empty)",
                isinstance(body.get("category_distribution"), list),
                str(body)[:200],
            )
            check(
                "analytics does not fabricate test-case ids",
                all(
                    not str(t.get("test_case_id", "")).startswith("tc-jailbreak-001")
                    for t in body.get("top_failing_tests", [])
                ),
            )

        print("\n== previously broken write paths ==")
        suite_name = f"smoke-suite-{uuid.uuid4().hex[:8]}"
        r = client.post(
            "/api/v1/suites",
            json={
                "name": suite_name,
                "description": "smoke",
                "test_cases": [
                    {
                        "test_case_id": "tc-smoke-1",
                        "category": "jailbreak",
                        "severity": "critical",
                        "input": "hello",
                        "expected_behavior": {
                            "type": "refusal",
                            "matcher": {"type": "refusal", "pattern": "cannot"},
                        },
                        "metadata": {"tags": ["smoke"]},
                    }
                ],
            },
            headers=headers,
        )
        check("POST /api/v1/suites", r.status_code in (200, 201), r.text[:300])
        suite_id = r.json().get("id") if r.status_code in (200, 201) else None

        if suite_id:
            r = client.get(f"/api/v1/suites/{suite_id}", headers=headers)
            check("GET /api/v1/suites/{id}", r.status_code == 200, r.text[:200])
            check(
                "the created suite has its test case",
                len(r.json().get("test_cases", [])) == 1,
                r.text[:300],
            )
            check(
                "the test case round-trips its expected behaviour",
                bool(r.json()["test_cases"][0].get("expected_behavior", {}).get("type")),
                r.text[:300],
            )

            # The write must be durable, not rolled back.
            r = client.get("/api/v1/suites/", headers=headers)
            check(
                "the created suite is persisted (not rolled back)",
                any(s["id"] == suite_id for s in r.json()),
                "suite missing from the listing",
            )

            r = client.delete(f"/api/v1/suites/{suite_id}", headers=headers)
            check("DELETE /api/v1/suites/{id}", r.status_code == 200, r.text[:200])

        r = client.get("/api/v1/agents/", headers=headers)
        check("GET /api/v1/agents", r.status_code == 200, r.text[:200])

        r = client.get("/api/v1/reports", headers=headers)
        check("GET /api/v1/reports", r.status_code == 200, r.text[:200])

        r = client.get("/api/v1/reviews/", headers=headers)
        check("GET /api/v1/reviews", r.status_code == 200, r.text[:200])

        r = client.get("/api/v1/settings/feature-flags", headers=headers)
        check("GET /api/v1/settings/feature-flags", r.status_code == 200, r.text[:200])

        print("\n== authorization ==")
        r = client.get("/api/v1/users/")
        check("unauthenticated requests are rejected", r.status_code == 401, r.text[:120])

    print(f"\n{'=' * 60}")
    print(f"PASSED: {len(PASSED)}   FAILED: {len(FAILED)}")
    for failure in FAILED:
        print(f"  - {failure}")
    print("=" * 60)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
