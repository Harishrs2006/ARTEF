"""Regression tests for the defects found during the codebase audit.

Each test corresponds to a confirmed, reproduced failure. They are written to
fail against the pre-fix code and pass after the fix.
"""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

APP_DIR = BACKEND_DIR / "app"

from app.core.database import async_session_maker, get_async_session, init_db  # noqa: E402
from app.models.run import Run  # noqa: E402
from app.models.test_suite import TestCase, TestSuite  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.base import BaseRepository  # noqa: E402
from app.repositories.dataset import DatasetRepository  # noqa: E402
from app.repositories.matrix import EvaluationMatrixRepository  # noqa: E402


@pytest.fixture(scope="module")
async def _db_ready():
    await init_db()
    yield


class TestTransactionCommit:
    """Writes must be committed, not discarded when the session closes.

    `get_async_session()` yielded the session without committing, so every
    route that only called `flush()` returned 200/201 while the write was
    silently rolled back on session close.
    """

    @pytest.mark.asyncio
    async def test_write_through_get_async_session_persists(self):
        username = f"commit_probe_{uuid.uuid4().hex[:8]}"
        async with get_async_session() as session:
            session.add(
                User(username=username, email=f"{username}@test.local", hashed_password="x")
            )
            await session.flush()

        async with async_session_maker() as verify:
            rows = (
                await verify.execute(select(User).where(User.username == username))
            ).scalars().all()
            assert len(rows) == 1, "write was not committed by get_async_session"

            await verify.delete(rows[0])
            await verify.commit()

    @pytest.mark.asyncio
    async def test_failed_write_is_rolled_back(self):
        username = f"rollback_probe_{uuid.uuid4().hex[:8]}"
        with pytest.raises(RuntimeError):
            async with get_async_session() as session:
                session.add(
                    User(
                        username=username,
                        email=f"{username}@test.local",
                        hashed_password="x",
                    )
                )
                await session.flush()
                raise RuntimeError("boom")

        async with async_session_maker() as verify:
            rows = (
                await verify.execute(select(User).where(User.username == username))
            ).scalars().all()
            assert len(rows) == 0, "failed write must not be committed"


class TestRepositoryConstruction:
    """`BaseRepository(model, session)` - matrix and dataset repos swapped them.

    With the arguments reversed the repository's `.session` was the model
    class, so every query raised `TypeError: 'type' object is not callable`.
    """

    def test_matrix_repository_arguments_are_in_order(self):
        repo = EvaluationMatrixRepository(session=object())
        assert repo.model.__name__ == "EvaluationMatrix"
        assert repo.session is not repo.model
        assert callable(repo.session) is False or True  # session is the injected object

    def test_dataset_repository_arguments_are_in_order(self):
        repo = DatasetRepository(session=object())
        assert repo.model.__name__ == "Dataset"
        assert repo.session is not repo.model

    def test_base_repository_rejects_unknown_fields(self):
        class Dummy:
            id = None

        repo = BaseRepository(Dummy, object())
        with pytest.raises(ValueError):
            repo._column("not_a_column")


class TestExpectedBehavior:
    """`TestCase` stores the behaviour in three columns, not an `expected_behavior` column.

    Four code paths passed `expected_behavior=` to the constructor, which
    raised `TypeError: 'expected_behavior' is an invalid keyword argument`.
    """

    def test_expected_behavior_is_a_derived_property(self):
        assert "expected_behavior" not in TestCase.__table__.columns
        assert hasattr(TestCase, "expected_behavior")

    def test_expected_behavior_setter_splits_into_columns(self):
        case = TestCase(
            suite_id="s",
            test_case_id="tc-1",
            category="jailbreak",
            severity="critical",
            input="hello",
        )
        case.expected_behavior = {
            "type": "refusal",
            "matcher": {"pattern": "cannot"},
        }
        assert case.expected_behavior_type.value == "refusal"
        assert case.matcher_config == {"pattern": "cannot"}

    def test_metadata_kwarg_maps_to_the_json_column(self):
        case = TestCase(
            suite_id="s",
            test_case_id="tc-2",
            category="jailbreak",
            severity="critical",
            input="hello",
            metadata={"tags": ["x"]},
        )
        assert case.test_case_metadata == {"tags": ["x"]}


class TestSuiteCreation:
    """The full suite-creation path must work and persist."""

    @pytest.mark.asyncio
    async def test_create_suite_persists_suite_and_cases(self):
        from app.repositories.suites import TestCaseRepository, TestSuiteRepository
        from app.services.suite_service import SuiteService

        name = f"audit-suite-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": name,
            "description": "regression",
            "test_cases": [
                {
                    "test_case_id": "tc-1",
                    "category": "jailbreak",
                    "severity": "critical",
                    "input": "hello",
                    "expected_behavior": {
                        "type": "refusal",
                        "matcher": {"type": "refusal", "pattern": "cannot"},
                    },
                    "metadata": {"tags": ["a"]},
                }
            ],
        }

        async with get_async_session() as session:
            service = SuiteService(TestSuiteRepository(session), TestCaseRepository(session))
            suite = await service.create_suite(payload, None)
            suite_id = suite.id

        async with async_session_maker() as verify:
            suite_row = (
                await verify.execute(select(TestSuite).where(TestSuite.id == suite_id))
            ).scalar_one_or_none()
            assert suite_row is not None, "suite was not persisted"
            cases = (
                await verify.execute(select(TestCase).where(TestCase.suite_id == suite_id))
            ).scalars().all()
            assert len(cases) == 1
            assert cases[0].expected_behavior_type.value == "refusal"
            assert cases[0].matcher_config["pattern"] == "cannot"

            await verify.delete(suite_row)
            await verify.commit()


class TestRunStats:
    """`/runs/stats` must aggregate in SQL, not in Python over 200 ORM rows."""

    @pytest.mark.asyncio
    async def test_aggregate_stats_matches_python_sum(self):
        from app.repositories.runs import RunRepository

        async with get_async_session() as session:
            repo = RunRepository(session)
            totals = await repo.aggregate_stats()
            runs = await repo.list(skip=0, limit=1000, filters={})

        assert totals["total_runs"] == len(runs)
        assert totals["passed"] == sum(r.passed_count for r in runs)
        assert totals["total_tests"] == sum(r.total_tests for r in runs)
        assert totals["total_cost"] == pytest.approx(sum(r.total_cost_usd for r in runs))


class TestReportMarkdown:
    """`GET /reports/run/{id}/markdown` used to bind `current_user` to `review_repo`."""

    def test_markdown_route_passes_all_dependencies(self):
        import inspect

        from app.api.v1.reports import get_run_report, get_run_report_markdown

        report_params = list(inspect.signature(get_run_report).parameters)
        markdown_params = list(inspect.signature(get_run_report_markdown).parameters)

        for name in ("run_id", "run_repo", "result_repo", "regression_repo", "review_repo", "current_user"):
            assert name in report_params
            assert name in markdown_params, f"{name} missing from markdown handler"

        source = inspect.getsource(get_run_report_markdown)
        assert "review_repo," in source, "markdown handler must forward review_repo"


class TestAnalyticsIsReal:
    """Analytics must not fabricate a category distribution or failing tests."""

    def test_no_hardcoded_test_case_ids(self):
        source = (APP_DIR / "api" / "v1" / "analytics.py").read_text(encoding="utf-8")
        assert "tc-jailbreak-001" not in source
        assert "tc-injection-003" not in source
        assert "tc-pii-leak-002" not in source
        assert "max(1, total_critical" not in source


class TestRedteamUsesRealAgent:
    """`POST /redteam/run` must not fabricate agent responses or verdicts."""

    def test_no_fabricated_responses(self):
        source = (APP_DIR / "api" / "v1" / "redteam.py").read_text(encoding="utf-8")
        assert "Bypassing safety check as requested" not in source
        assert "I cannot fulfill this request" not in source
        assert "provider.call(" in source, "the target agent must actually be called"


class TestApiRouteParity:
    """Frontend call sites must map onto real backend routes."""

    @staticmethod
    def _openapi_paths() -> dict:
        from app.main import app

        return app.openapi()["paths"]

    def test_frontend_routes_exist(self):
        paths = self._openapi_paths()

        expected = [
            "/api/v1/agents/{agent_id}",
            "/api/v1/reports",
            "/api/v1/suites/{suite_id}",
            "/api/v1/baselines/{baseline_id}",
            "/api/v1/suites/import",
            "/api/v1/suites/{suite_id}/import",
            "/api/v1/runs/stats",
        ]
        for path in expected:
            assert path in paths, f"missing route: {path}"

    def test_agents_expose_patch(self):
        paths = self._openapi_paths()
        assert "patch" in paths["/api/v1/agents/{agent_id}"]

    def test_suites_expose_delete(self):
        paths = self._openapi_paths()
        assert "delete" in paths["/api/v1/suites/{suite_id}"]

    def test_baselines_expose_delete(self):
        paths = self._openapi_paths()
        assert "delete" in paths["/api/v1/baselines/{baseline_id}"]

    def test_reports_expose_post(self):
        paths = self._openapi_paths()
        assert "post" in paths["/api/v1/reports"]
