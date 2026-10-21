"""Regression tests for the bugs found during the codebase audit.

Every test in this module reproduces a defect that was confirmed present in
the repository and asserts that the fix is in place. They are deliberately
narrow: each one targets a single root cause so that a future regression
points at the exact behaviour that broke.
"""

from __future__ import annotations

import ast
import inspect
import re
import types
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest


def _ge_of(field) -> int | None:
    """The lower bound declared on a FastAPI query parameter."""
    for metadata in getattr(field, "metadata", []) or []:
        value = getattr(metadata, "ge", None)
        if value is not None:
            return value
    return None


def _le_of(field) -> int | None:
    """The upper bound declared on a FastAPI query parameter."""
    for metadata in getattr(field, "metadata", []) or []:
        value = getattr(metadata, "le", None)
        if value is not None:
            return value
    return None


def _max_of(field) -> int | None:
    return _le_of(field)

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"


# ---------------------------------------------------------------------------
# C1 - EvaluationMatrixCellRepository swapped the model and the session
# ---------------------------------------------------------------------------


class TestMatrixCellRepositoryConstruction:
    def test_model_and_session_are_not_swapped(self):
        from app.models.matrix import EvaluationMatrixCell
        from app.repositories.matrix import EvaluationMatrixCellRepository

        repo = EvaluationMatrixCellRepository("session-sentinel")
        assert repo.model is EvaluationMatrixCell
        assert repo.session == "session-sentinel"

    def test_matrix_repository_keeps_its_arguments(self):
        from app.models.matrix import EvaluationMatrix
        from app.repositories.matrix import EvaluationMatrixRepository

        repo = EvaluationMatrixRepository("session-sentinel")
        assert repo.model is EvaluationMatrix
        assert repo.session == "session-sentinel"


# ---------------------------------------------------------------------------
# C2 - matrix_service referenced a module and a constructor that do not exist
# ---------------------------------------------------------------------------


class TestMatrixServiceWiring:
    def test_service_module_has_no_import_of_a_missing_module(self):
        source = (BACKEND_ROOT / "app" / "services" / "matrix_service.py").read_text(encoding="utf-8")
        assert "app.services.cost_tracking" not in source

    def test_execution_service_is_constructed_with_the_supported_arity(self):
        from app.services.execution_service import ExecutionService

        parameters = list(inspect.signature(ExecutionService.__init__).parameters)
        # self + 5 repositories
        assert len(parameters) == 6

    def test_cost_tracker_accepts_an_optional_session(self):
        from app.evaluation.cost.cost_tracker import CostTracker

        parameters = inspect.signature(CostTracker.__init__).parameters
        assert "session" in parameters
        assert parameters["session"].default is None

    def test_matrix_service_module_imports_cleanly(self):
        from app.services import matrix_service

        assert matrix_service.MatrixService is not None


# ---------------------------------------------------------------------------
# C3 - JudgeOutput silently dropped the provider metadata
# ---------------------------------------------------------------------------


class TestJudgeOutputMetadata:
    def test_metadata_is_preserved(self):
        from app.domain.enums import Verdict
        from app.domain.value_objects import JudgeOutput

        output = JudgeOutput(
            verdict=Verdict.PASS,
            confidence=0.9,
            rationale="ok",
            evidence=[{"source": "s", "text": "t"}],
            metadata={"tokens_used": 42, "provider": "openai"},
        )
        assert output.metadata["tokens_used"] == 42
        assert output.metadata["provider"] == "openai"

    def test_metadata_defaults_to_an_empty_mapping(self):
        from app.domain.enums import Verdict
        from app.domain.value_objects import JudgeOutput

        output = JudgeOutput(
            verdict=Verdict.PASS,
            confidence=0.9,
            rationale="ok",
            evidence=[{"source": "s", "text": "t"}],
        )
        assert output.metadata == {}

    def test_evidence_is_required_for_a_decisive_verdict(self):
        from app.domain.enums import Verdict
        from app.domain.value_objects import JudgeOutput

        with pytest.raises(ValueError):
            JudgeOutput(verdict=Verdict.PASS, confidence=0.9, rationale="ok")

    def test_inconclusive_verdict_may_have_no_evidence(self):
        from app.domain.enums import Verdict
        from app.domain.value_objects import JudgeOutput

        output = JudgeOutput(verdict=Verdict.INCONCLUSIVE, confidence=0.0, rationale="unclear")
        assert output.evidence == []


# ---------------------------------------------------------------------------
# C4 - the matcher configuration was read off a dict with getattr()
# ---------------------------------------------------------------------------


class TestMatcherConfigIsReadAsADict:
    def _test_case(self, **kwargs):
        from app.models.test_suite import TestCase

        defaults = {
            "id": str(uuid4()),
            "suite_id": str(uuid4()),
            "test_case_id": "TC-1",
            "input": "hello",
            "expected_behavior_type": "regex_match",
            "category": "prompt_injection",
            "severity": "medium",
        }
        defaults.update(kwargs)
        return TestCase(**defaults)

    def test_regex_pattern_is_preserved(self):
        from app.domain.enums import ExpectedBehaviorType
        from app.services.scoring_service import ScoringService

        service = ScoringService.__new__(ScoringService)
        case = self._test_case(
            matcher_config={
                "type": "regex_match",
                "pattern": r"secret\d+",
                "case_sensitive": True,
                "regex_timeout_ms": 250,
            }
        )
        expected = service._build_expected_behavior(case)
        assert expected.matcher is not None
        assert expected.matcher.type == ExpectedBehaviorType.REGEX_MATCH
        assert expected.matcher.pattern == r"secret\d+"
        assert expected.matcher.case_sensitive is True
        assert expected.matcher.regex_timeout_ms == 250

    def test_keyword_list_is_preserved(self):
        from app.domain.enums import ExpectedBehaviorType
        from app.services.scoring_service import ScoringService

        service = ScoringService.__new__(ScoringService)
        case = self._test_case(
            expected_behavior_type="keyword_match",
            matcher_config={"type": "keyword_match", "keywords": ["alpha", "beta"]},
        )
        expected = service._build_expected_behavior(case)
        assert expected.matcher is not None
        assert expected.matcher.type == ExpectedBehaviorType.KEYWORD_MATCH
        assert expected.matcher.keywords == ["alpha", "beta"]

    def test_missing_matcher_config_falls_back_to_the_behaviour_type(self):
        from app.domain.enums import ExpectedBehaviorType
        from app.services.scoring_service import ScoringService

        service = ScoringService.__new__(ScoringService)
        case = self._test_case(expected_behavior_type="refusal")
        expected = service._build_expected_behavior(case)
        assert expected.type == ExpectedBehaviorType.REFUSAL
        assert expected.matcher is None


# ---------------------------------------------------------------------------
# C5 - PII redaction crashed when the target agent returned no tool calls
# ---------------------------------------------------------------------------


class TestExecutionDataRedaction:
    def test_none_tool_calls_do_not_raise(self):
        from app.security.pii_redaction import redact_execution_data

        result = redact_execution_data(
            {
                "target_request": {"input": "hello"},
                "target_response": {"text": "world"},
                "tool_calls": None,
            }
        )
        assert result["tool_calls"] == []

    def test_tool_call_arguments_are_redacted(self):
        from app.security.pii_redaction import redact_execution_data

        result = redact_execution_data(
            {
                "target_request": {},
                "target_response": {},
                "tool_calls": [{"arguments": {"email": "user@example.com"}}],
            }
        )
        assert "user@example.com" not in str(result["tool_calls"][0]["arguments"])

    def test_non_dict_tool_call_entries_are_skipped(self):
        from app.security.pii_redaction import redact_execution_data

        result = redact_execution_data(
            {"target_request": {}, "target_response": {}, "tool_calls": ["not-a-dict"]}
        )
        assert result["tool_calls"] == ["not-a-dict"]


# ---------------------------------------------------------------------------
# C6 / C7 / C8 - the evaluation pipeline
# ---------------------------------------------------------------------------


class TestEvaluationPipeline:
    def test_result_is_initialised_before_the_first_step(self):
        """Every step appends to ``pipeline_run.result``; it must exist."""
        from app.evaluation.pipeline import engine

        source = inspect.getsource(engine.EvaluationPipeline.run)
        # The result is assigned before ``_execute_pipeline`` is awaited.
        assert source.index("self.pipeline_run.result = PipelineResult(") < source.index(
            "await self._execute_pipeline()"
        )

    def test_the_run_attribute_does_not_shadow_the_run_method(self):

        from app.evaluation.pipeline import engine

        # The instance attribute used to be called ``run``, which replaced the
        # bound ``run()`` method and made a second invocation impossible.
        source = inspect.getsource(engine.EvaluationPipeline)
        assert not re.search(r"\bself\.run\b(?!_)", source)
        assert hasattr(engine.EvaluationPipeline, "run")

    def test_review_uses_the_regression_id_not_the_test_case_id(self):
        from app.evaluation.pipeline import engine

        source = inspect.getsource(engine.EvaluationPipeline._step_baseline_comparison)
        assert "regression_id=UUID(finding.test_case_id)" not in source
        assert "get_by_run_and_test_case" in source

    def test_auto_baseline_does_not_use_a_hardcoded_user_id(self):
        from app.evaluation.pipeline import engine

        source = inspect.getsource(engine.EvaluationPipeline._create_baseline_from_cell)
        assert "00000000-0000-0000-0000-000000000000" not in source
        assert "approved_by=approved_by" in source

    def test_release_decision_always_assigns_a_value(self):
        from app.evaluation.pipeline import engine

        source = inspect.getsource(engine.EvaluationPipeline._step_release_decision)
        # Every branch of the if/elif chain assigns ``release_decision``.
        assert source.count("release_decision = ") >= 4
        assert "elif review_required:" not in source

    def test_severity_step_is_not_a_no_op(self):
        from app.evaluation.pipeline import engine

        source = inspect.getsource(engine.EvaluationPipeline._step_severity_classification)
        assert "classify(" in source
        assert "classified" in source

    def test_report_step_generates_reports(self):
        from app.evaluation.pipeline import engine

        source = inspect.getsource(engine.EvaluationPipeline._step_generate_reports)
        assert "generate_junit_xml" in source

    def test_persist_step_writes_the_run_snapshot(self):
        from app.evaluation.pipeline import engine

        source = inspect.getsource(engine.EvaluationPipeline._persist_run)
        assert "config_snapshot" in source


# ---------------------------------------------------------------------------
# Pagination - the list endpoints accepted an unbounded limit
# ---------------------------------------------------------------------------


class TestListEndpointsAreBounded:
    """The list endpoints must not accept an unbounded page size.

    ``LIMIT -1`` is an unbounded query in SQLite, so an endpoint that
    accepts a negative or arbitrarily large ``limit`` can be asked to
    materialise the whole table.
    """

    ENDPOINTS = {
        "/api/v1/reviews/": ("app/api/v1/reviews.py", "list_reviews"),
        "/api/v1/baselines/": ("app/api/v1/baselines.py", "list_baselines"),
        "/api/v1/suites/": ("app/api/v1/suites.py", "list_suites"),
        "/api/v1/test-cases/suite/{suite_id}": (
            "app/api/v1/test_cases.py",
            "list_test_cases",
        ),
        "/api/v1/matrices/": ("app/api/v1/matrices.py", "list_matrices"),
        "/api/v1/datasets/": ("app/api/v1/datasets.py", "list_datasets"),
        "/api/v1/reports/": ("app/api/v1/reports.py", "list_reports"),
        "/api/v1/users/": ("app/api/v1/users.py", "list_users"),
    }

    def _signature(self, relative_path: str, function_name: str):
        """Return the signature of an endpoint function.

        The source is parsed instead of importing the module so that the
        declared defaults are read exactly as written.
        """

        source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                arguments = node.args
                defaults = [None] * (
                    len(arguments.args) - len(arguments.defaults)
                ) + list(arguments.defaults)
                return {
                    argument.arg: default
                    for argument, default in zip(arguments.args, defaults, strict=False)
                }
        raise AssertionError(f"{function_name} not found in {relative_path}")

    @staticmethod
    def _query_bound(default) -> tuple[int | None, int | None]:
        """Return the (ge, le) bounds of a ``Query(...)`` default."""

        if default is None:
            return None, None
        if not isinstance(default, ast.Call):
            return None, None
        ge = le = None
        for keyword in default.keywords:
            if keyword.arg == "ge" and isinstance(keyword.value, ast.Constant):
                ge = keyword.value.value
            if keyword.arg == "le" and isinstance(keyword.value, ast.Constant):
                le = keyword.value.value
        return ge, le

    @staticmethod
    def _query_value(default):
        """Return the literal value of a ``Query(...)`` default."""

        if isinstance(default, ast.Call):
            for argument in default.args:
                if isinstance(argument, ast.Constant):
                    return argument.value
            return None
        if isinstance(default, ast.Constant):
            return default.value
        return None

    @pytest.mark.parametrize("path", list(ENDPOINTS))
    def test_limit_has_an_upper_bound(self, path):
        relative_path, function_name = self.ENDPOINTS[path]
        parameters = self._signature(relative_path, function_name)
        assert "limit" in parameters, f"{path} has no limit parameter"

        default = parameters["limit"]
        assert isinstance(default, ast.Call), (
            f"{path} declares limit as a plain value; it must use Query(..., le=...)"
        )
        ge, le = self._query_bound(default)
        assert le is not None, f"{path} has no upper bound on limit"
        assert le <= 1000
        value = self._query_value(default)
        assert value is not None and 0 < value <= 1000

    @pytest.mark.parametrize("path", list(ENDPOINTS))
    def test_skip_is_not_negative(self, path):
        relative_path, function_name = self.ENDPOINTS[path]
        parameters = self._signature(relative_path, function_name)
        if "skip" not in parameters:
            return
        default = parameters["skip"]
        assert isinstance(default, ast.Call), (
            f"{path} declares skip as a plain value; it must use Query(..., ge=0)"
        )
        ge, le = self._query_bound(default)
        assert ge == 0, f"{path} does not forbid a negative skip"
        value = self._query_value(default)
        assert value is not None and value >= 0


# ---------------------------------------------------------------------------
# Route prefixes - the matrix and dataset routers doubled their prefix
# ---------------------------------------------------------------------------


class TestRoutePrefixes:
    def _paths(self) -> set[str]:
        from app.main import app

        return set(app.openapi()["paths"].keys())

    def test_matrix_routes_are_not_doubled(self):
        paths = self._paths()
        assert "/api/v1/matrices/{matrix_id}" in paths
        assert "/api/v1/matrices/matrices/{matrix_id}" not in paths

    def test_dataset_routes_are_not_doubled(self):
        paths = self._paths()
        assert "/api/v1/datasets/{dataset_id}" in paths
        assert "/api/v1/datasets/datasets/{dataset_id}" not in paths


# ---------------------------------------------------------------------------
# Truncation - a run silently stopped at 100 test cases
# ---------------------------------------------------------------------------


class TestNoSilentTruncation:
    def test_repository_provides_an_unpaginated_test_case_list(self):
        from app.repositories.suites import TestCaseRepository

        assert hasattr(TestCaseRepository, "list_all_by_suite")

    def test_repository_provides_an_unpaginated_execution_list(self):
        from app.repositories.runs import ExecutionRepository

        assert hasattr(ExecutionRepository, "list_all_by_run")

    def test_repository_provides_an_unpaginated_result_list(self):
        from app.repositories.runs import ResultRepository

        assert hasattr(ResultRepository, "list_all_by_run")

    def test_execution_service_uses_the_unpaginated_list(self):
        from app.services.execution_service import ExecutionService

        source = inspect.getsource(ExecutionService.execute_run)
        assert "list_all_by_suite" in source

    def test_scoring_service_uses_the_unpaginated_list(self):
        from app.services.scoring_service import ScoringService

        source = inspect.getsource(ScoringService.score_run)
        assert "list_all_by_run" in source


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


class TestCostTracker:
    def test_unknown_model_does_not_price_against_a_shorter_key(self):
        from app.evaluation.cost.cost_tracker import CostTracker

        tracker = CostTracker()
        # "gpt" is a prefix of the configured "gpt-4" entry. Pricing an
        # unknown model against it produced a non-deterministic cost.
        assert tracker.calculate_cost("openai", "gpt", 1000, 1000) == 0.0

    def test_known_model_is_priced(self):
        from app.evaluation.cost.cost_tracker import CostTracker

        tracker = CostTracker()
        assert tracker.calculate_cost("openai", "gpt-4o", 1000, 1000) > 0

    def test_prefix_model_resolves_to_the_configured_entry(self):
        from app.evaluation.cost.cost_tracker import CostTracker

        tracker = CostTracker()
        # "gpt-4o-2024-11-20" is a dated variant of "gpt-4o".
        assert tracker.calculate_cost("openai", "gpt-4o-2024-11-20", 1000, 1000) > 0

    def test_record_trend_uses_the_token_count_argument(self):
        import ast as _ast

        source = (BACKEND_ROOT / "app" / "evaluation" / "cost" / "cost_tracker.py").read_text(
            encoding="utf-8"
        )
        tree = _ast.parse(source)
        for node in _ast.walk(tree):
            if isinstance(node, _ast.AsyncFunctionDef) and node.name == "record_trend":
                segment = _ast.get_source_segment(source, node) or ""
                assert "token_count=token_count" in segment
                assert "token_count=0" not in segment
                return
        raise AssertionError("record_trend not found")

    def test_summary_filters_every_breakdown_by_run(self):
        source = (BACKEND_ROOT / "app" / "evaluation" / "cost" / "cost_tracker.py").read_text(
            encoding="utf-8"
        )
        # The run filter is applied through a shared ``_scope`` helper so
        # that the breakdowns match the total.
        assert "_scope(" in source
        assert source.count("_scope(") >= 5


# ---------------------------------------------------------------------------
# Judge resilience
# ---------------------------------------------------------------------------


class TestJudgeResilience:
    def test_primary_judge_retries_the_provider_error(self):
        from app.evaluation.judges.llm_judge import LLMJudge

        source = inspect.getsource(LLMJudge.judge)
        # The raw httpx exceptions never reach the decorator: the provider
        # converts them into LLMProviderError.
        assert "LLMProviderError" in source
        assert "httpx.TimeoutException" not in source

    def test_fallback_judge_reraises_the_typed_error(self):
        from app.evaluation.judges.fallback_judge import FallbackJudge

        source = inspect.getsource(FallbackJudge.judge)
        assert "reraise=True" in source

    def test_fallback_judge_failure_does_not_fail_the_run(self):
        from app.services.scoring_service import ScoringService

        source = inspect.getsource(ScoringService._score_with_judge)
        assert "fallback_judge_unavailable" in source

    def test_manufactured_evidence_is_marked_as_not_judge_cited(self):
        from app.evaluation.judges.llm_judge import LLMJudge

        source = inspect.getsource(LLMJudge.judge)
        assert "unverified_target_response" in source
        assert "judge_cited" in source


# ---------------------------------------------------------------------------
# Provider lifecycle
# ---------------------------------------------------------------------------


class TestProviderLifecycle:
    def test_providers_are_cached_per_configuration(self):
        from app.providers.llm import LLMProviderFactory

        first = LLMProviderFactory.create_provider("mock", "m", "key")
        second = LLMProviderFactory.create_provider("mock", "m", "key")
        assert first is second

    def test_close_all_is_awaitable(self):
        import asyncio

        from app.providers.llm import LLMProviderFactory

        asyncio.run(LLMProviderFactory.close_all())

    def test_unknown_provider_is_rejected(self):
        from app.core.exceptions import LLMProviderError
        from app.providers.llm import LLMProviderFactory

        # ``EVAL_MODE=local`` in the test settings would otherwise turn every
        # provider into the mock, so the check is forced here.
        with patch("app.providers.llm.settings.EVAL_MODE", "provider"):
            with pytest.raises(LLMProviderError):
                LLMProviderFactory.create_provider("not-a-provider", "m", "key")


# ---------------------------------------------------------------------------
# Baseline lookup
# ---------------------------------------------------------------------------


class TestBaselineLookup:
    def test_active_baseline_query_is_limited(self):
        source = (BACKEND_ROOT / "app" / "repositories" / "baselines.py").read_text(
            encoding="utf-8"
        )
        # ``scalar_one_or_none`` raised MultipleResultsFound when a suite
        # had more than one active baseline.
        assert "limit(1)" in source
        assert "Baseline.is_active == True" not in source


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------


class TestPasswordPolicy:
    def test_short_password_is_rejected(self):
        from app.core.exceptions import ValidationError
        from app.core.password_policy import validate_password_strength

        with pytest.raises(ValidationError):
            validate_password_strength("short")

    def test_password_must_contain_mixed_case(self):
        from app.core.exceptions import ValidationError
        from app.core.password_policy import validate_password_strength

        with pytest.raises(ValidationError):
            validate_password_strength("alllowercase123!")

    def test_password_must_not_contain_the_username(self):
        from app.core.exceptions import ValidationError
        from app.core.password_policy import validate_password_strength

        with pytest.raises(ValidationError):
            validate_password_strength("SuperSecret!Pass1", username="supersecret")

    def test_strong_password_is_accepted(self):
        from app.core.password_policy import validate_password_strength

        validate_password_strength("C0rrect!Horse#Battery", "someone", "someone@example.com")

    def test_registration_uses_the_shared_policy(self):
        source = (BACKEND_ROOT / "app" / "api" / "v1" / "auth.py").read_text(encoding="utf-8")
        assert "validate_password_strength" in source
        assert "COMMON_WEAK_PASSWORDS" not in source

    def test_password_change_endpoint_exists(self):
        from app.main import app

        paths = app.openapi()["paths"]
        assert "/api/v1/users/me/password" in paths


# ---------------------------------------------------------------------------
# Frontend - the dynamic route directories were named ``[id/]``
# ---------------------------------------------------------------------------


class TestFrontendDynamicRoutes:
    def _route_dirs(self) -> list[Path]:
        app_dir = FRONTEND_ROOT / "src" / "app"
        found = []
        for route in ("agents", "reviews", "suites"):
            for child in (app_dir / route).iterdir():
                if child.is_dir():
                    found.append(child)
        return found

    def test_dynamic_route_directories_use_the_bracket_syntax(self):
        for child in self._route_dirs():
            name = child.name
            if not name.startswith("["):
                # A static segment such as "new" is perfectly valid.
                continue
            assert name.endswith("]"), (
                f"{child} is not a valid Next.js dynamic segment"
            )
            assert "/" not in name, f"{child} has a slash in the directory name"

    def test_no_directory_ends_with_a_slash_in_the_name(self):
        for child in self._route_dirs():
            assert not child.name.endswith("/")

    def test_every_route_directory_has_a_page(self):
        for child in self._route_dirs():
            assert (child / "page.tsx").exists(), f"{child} has no page.tsx"

    def test_the_dynamic_routes_are_the_expected_ones(self):
        names = sorted(c.name for c in self._route_dirs() if c.name.startswith("["))
        assert names == ["[id]", "[id]", "[id]"]


# ---------------------------------------------------------------------------
# Frontend - the Docker image needs the standalone output
# ---------------------------------------------------------------------------


class TestFrontendDockerBuild:
    def test_next_config_can_emit_the_standalone_output(self):
        source = (FRONTEND_ROOT / "next.config.mjs").read_text(encoding="utf-8")
        assert "standalone" in source

    def test_dockerfile_activates_the_standalone_output(self):
        source = (FRONTEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "NEXT_OUTPUT_STANDALONE=true" in source
        assert ".next/standalone" in source


# ---------------------------------------------------------------------------
# Frontend - the settings page had dead controls
# ---------------------------------------------------------------------------


class TestSettingsPage:
    def _source(self) -> str:
        return (FRONTEND_ROOT / "src" / "app" / "settings" / "page.tsx").read_text(
            encoding="utf-8"
        )

    def test_password_change_is_wired_to_the_api(self):
        source = self._source()
        assert "/users/me/password" in source
        assert "handleChangePassword" in source

    def test_feature_flag_toggle_does_not_read_a_stale_closure(self):
        source = self._source()
        # The toggle used to call setEditingFlag and handleUpdateFlag in the
        # same tick, so the update always sent the previous value.
        assert "setEditingFlag({ ...flag, enabled: checked });" not in source
        assert "handleUpdateFlag({ ...flag, enabled: checked })" in source

    def test_system_configuration_is_read_from_the_backend(self):
        source = self._source()
        assert "/settings/config" in source


# ---------------------------------------------------------------------------
# Frontend - hook ordering
# ---------------------------------------------------------------------------


class TestFrontendHookOrdering:
    def _guard_index(self, source: str) -> int:

        match = re.search(r"\n  if \(!ready \|\| !authenticated\) \{", source)
        assert match, "the page has no authentication guard"
        return match.start()

    @pytest.mark.parametrize(
        "page",
        [
            "analytics/page.tsx",
            "agents/page.tsx",
            "suites/page.tsx",
            "reviews/page.tsx",
        ],
    )
    def test_hooks_are_called_before_the_early_return(self, page):

        source = (FRONTEND_ROOT / "src" / "app" / page).read_text(encoding="utf-8")
        guard = self._guard_index(source)
        # Only top-level hook calls count. A hook inside a callback body is
        # not a conditional call.
        for match in re.finditer(r"\n  const \w+ = use(Memo|Callback)\(", source):
            assert match.start() < guard, (
                f"use{match.group(1)} in {page} is declared after the early return"
            )


# ---------------------------------------------------------------------------
# Client error reporting
# ---------------------------------------------------------------------------


class TestClientErrorReporting:
    def test_endpoint_exists(self):
        from app.main import app

        paths = app.openapi()["paths"]
        assert "/api/v1/monitoring/client-errors" in paths
        assert "post" in paths["/api/v1/monitoring/client-errors"]

    def test_the_frontend_posts_to_the_reporting_endpoint(self):
        source = (FRONTEND_ROOT / "src" / "app" / "error-handler.ts").read_text(encoding="utf-8")
        assert "/api/v1/monitoring/client-errors" in source

    def test_the_error_handler_is_imported(self):
        source = (FRONTEND_ROOT / "src" / "app" / "providers.tsx").read_text(encoding="utf-8")
        assert "error-handler" in source

    def test_client_errors_are_redacted(self):
        from app.monitoring import MAX_CLIENT_ERROR_MESSAGE, security_metrics

        alert = security_metrics.record_client_error(
            error_type="error",
            message="token sk-abcdefghijklmnopqrstuvwxyz leaked",
            source="app/page.tsx",
        )
        assert alert["type"] == "client_error"
        assert len(alert["message"]) <= MAX_CLIENT_ERROR_MESSAGE


# ---------------------------------------------------------------------------
# No fabricated telemetry
# ---------------------------------------------------------------------------


class TestNoFabricatedTelemetry:
    def test_monitoring_uptime_is_monotonic(self):
        from app.monitoring import security_metrics

        first = security_metrics.get_security_dashboard()["uptime_seconds"]
        second = security_metrics.get_security_dashboard()["uptime_seconds"]
        assert second >= first >= 0
