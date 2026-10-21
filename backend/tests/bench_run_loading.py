"""Measure the cost of the relationship loading strategy on the run queries.

``Run`` declares four relationships with ``lazy="joined"``. Every query
that touches the ``runs`` table therefore joins the target agent, the test
suite (and its dataset), the baseline (and its suite, dataset and approver)
and the evaluation matrix (and its suite and dataset) - ten tables in
total. The wide result set is then materialised and deserialised even
though the dashboard only reads the scalar columns of a run.

This script compares the current strategy with ``lazy="selectin"`` and
with a projection that selects only the scalar columns.
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

N_RUNS = int(os.environ.get("BENCH_RUNS", "300"))
ITERATIONS = int(os.environ.get("BENCH_ITERATIONS", "20"))


async def seed() -> tuple[str, str]:
    from uuid import uuid4 as _uuid4

    agent_id = str(_uuid4())
    suite_id = str(_uuid4())
    user_id = str(_uuid4())

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
                    id=str(_uuid4()),
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


async def bench_joined() -> list[float]:
    """The current strategy: every relationship is joined into the query."""
    timings = []
    for _ in range(ITERATIONS):
        async with async_session_maker() as session:
            start = time.perf_counter()
            result = await session.execute(select(Run).limit(5))
            rows = result.scalars().all()
            # Touch the relationships so that the loading cost is included.
            for run in rows:
                _ = run.target_agent
                _ = run.suite
                _ = run.baseline
                _ = run.matrix
            timings.append((time.perf_counter() - start) * 1000)
    return timings


async def bench_selectin() -> list[float]:
    """``lazy="selectin"``: the relationships are loaded with batched queries."""
    timings = []
    for _ in range(ITERATIONS):
        async with async_session_maker() as session:
            start = time.perf_counter()
            result = await session.execute(
                select(Run)
                .options(
                    selectinload(Run.target_agent),
                    selectinload(Run.suite),
                    selectinload(Run.baseline),
                    selectinload(Run.matrix),
                )
                .limit(5)
            )
            rows = result.scalars().all()
            for run in rows:
                _ = run.target_agent
                _ = run.suite
                _ = run.baseline
                _ = run.matrix
            timings.append((time.perf_counter() - start) * 1000)
    return timings


async def bench_projection() -> list[float]:
    """Only the scalar columns of a run are selected."""
    timings = []
    for _ in range(ITERATIONS):
        async with async_session_maker() as session:
            start = time.perf_counter()
            result = await session.execute(
                select(
                    Run.id,
                    Run.status,
                    Run.created_at,
                    Run.total_tests,
                    Run.passed_count,
                    Run.failed_count,
                    Run.inconclusive_count,
                    Run.regression_count,
                    Run.critical_count,
                    Run.high_count,
                    Run.medium_count,
                    Run.low_count,
                    Run.total_cost_usd,
                    Run.total_latency_ms,
                ).limit(5)
            )
            rows = result.all()
            _ = len(rows)
            timings.append((time.perf_counter() - start) * 1000)
    return timings


def report(name: str, timings: list[float]) -> None:
    ordered = sorted(timings)
    print(
        f"{name:<46} "
        f"median={statistics.median(timings):7.2f} ms  "
        f"mean={statistics.mean(timings):7.2f} ms  "
        f"p95={ordered[int(len(ordered) * 0.95) - 1]:7.2f} ms  "
        f"min={min(timings):7.2f} ms"
    )


async def main() -> None:
    from sqlalchemy.orm import selectinload

    globals()["selectinload"] = selectinload

    await init_db()
    agent_id, suite_id = await seed()
    print(f"\nSeeded {N_RUNS} runs. Iterations: {ITERATIONS}\n")
    try:
        print("--- loading 5 runs (the dashboard query) ---")
        report("lazy=joined (current)", await bench_joined())
        report("lazy=selectin", await bench_selectin())
        report("scalar projection only", await bench_projection())
    finally:
        await cleanup(agent_id, suite_id)
    print()


asyncio.run(main())
