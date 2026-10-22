"""End-to-end measurement of the dashboard data path.

Times the three requests that the dashboard issues on every load and on
every poll:

  * ``GET /runs/stats``      - the aggregate counters
  * ``GET /runs?limit=5``    - the recent runs table
  * ``GET /monitoring/dashboard``

Run with:  python backend/tests/bench_dashboard_path.py
"""

import asyncio
import os
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import async_session_maker, init_db  # noqa: E402
from app.models.run import Run  # noqa: E402
from app.models.target_agent import TargetAgent  # noqa: E402
from app.models.test_suite import TestSuite  # noqa: E402
from app.models.user import User  # noqa: E402

get_settings().DEBUG = False
try:
    from app.core.database import engine

    engine.echo = False
except Exception:  # pragma: no cover
    pass

N_RUNS = int(os.environ.get("BENCH_RUNS", "1000"))
ITERATIONS = int(os.environ.get("BENCH_ITERATIONS", "30"))


async def seed() -> tuple[str, str]:
    agent_id = str(uuid4())
    suite_id = str(uuid4())
    user_id = str(uuid4())

    async with async_session_maker() as session:
        session.add(
            User(
                id=user_id,
                username=f"bench_{user_id[:8]}",
                email=f"{user_id}@bench.local",
                hashed_password="x",
            )
        )
        session.add(
            TargetAgent(
                id=agent_id,
                name=f"bench-agent-{agent_id[:8]}",
                endpoint_url="http://localhost:8080/x",
            )
        )
        session.add(TestSuite(id=suite_id, name=f"bench-suite-{suite_id[:8]}", version=1))
        for _ in range(N_RUNS):
            session.add(
                Run(
                    id=str(uuid4()),
                    target_agent_id=agent_id,
                    suite_id=suite_id,
                    suite_version=1,
                    status="completed",
                    total_tests=25,
                    passed_count=20,
                    failed_count=3,
                    inconclusive_count=2,
                    regression_count=1,
                    critical_count=0,
                    high_count=1,
                    medium_count=0,
                    low_count=0,
                    total_cost_usd=0.05,
                    total_latency_ms=1500,
                )
            )
        await session.commit()

    return agent_id, suite_id


async def cleanup(agent_id: str, suite_id: str) -> None:
    async with async_session_maker() as session:
        await session.execute(delete(Run).where(Run.suite_id == suite_id))
        await session.execute(delete(TargetAgent).where(TargetAgent.id == agent_id))
        await session.execute(delete(TestSuite).where(TestSuite.id == suite_id))
        await session.execute(delete(User).where(User.username.like("bench_%")))
        await session.commit()


async def bench_recent_runs() -> list[float]:
    """The recent-runs table: five runs with the counter columns only."""
    from app.repositories.runs import RunRepository

    timings = []
    for _ in range(ITERATIONS):
        async with async_session_maker() as session:
            repo = RunRepository(session)
            start = time.perf_counter()
            await repo.list_scalars(skip=0, limit=5, order_by="created_at", descending=True)
            timings.append((time.perf_counter() - start) * 1000)
    return timings


async def bench_aggregate() -> list[float]:
    """The stat cards: a single SQL aggregate."""
    from app.repositories.runs import RunRepository

    timings = []
    for _ in range(ITERATIONS):
        async with async_session_maker() as session:
            repo = RunRepository(session)
            start = time.perf_counter()
            await repo.aggregate_stats()
            timings.append((time.perf_counter() - start) * 1000)
    return timings


async def bench_trend() -> list[float]:
    """The trend charts: the seven most recent completed runs."""
    from app.repositories.runs import RunRepository

    timings = []
    for _ in range(ITERATIONS):
        async with async_session_maker() as session:
            repo = RunRepository(session)
            start = time.perf_counter()
            await repo.list_completed_trend(limit=7)
            timings.append((time.perf_counter() - start) * 1000)
    return timings


def report(name: str, timings: list[float]) -> None:
    ordered = sorted(timings)
    print(
        f"{name:<44} "
        f"median={statistics.median(timings):7.2f} ms  "
        f"mean={statistics.mean(timings):7.2f} ms  "
        f"p95={ordered[int(len(ordered) * 0.95) - 1]:7.2f} ms  "
        f"min={min(timings):7.2f} ms"
    )


async def main() -> None:
    await init_db()
    agent_id, suite_id = await seed()
    print(f"\nSeeded {N_RUNS} runs. Iterations: {ITERATIONS}\n")
    try:
        print("--- dashboard data path ---")
        report("GET /runs?limit=5 (scalar projection)", await bench_recent_runs())
        report("GET /runs/stats (SQL aggregate)", await bench_aggregate())
        report("GET /runs/stats (trend series)", await bench_trend())
    finally:
        await cleanup(agent_id, suite_id)
    print()


asyncio.run(main())
