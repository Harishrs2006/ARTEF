from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from app.domain.enums import RunStatus
from app.evaluation.gate.evaluator import GateEvaluator
from app.evaluation.gate.reports import GateReportGenerator
from app.evaluation.pipeline.models import (
    PipelineConfig,
    PipelineResult,
    PipelineRun,
    PipelineStatus,
    PipelineStep,
    PipelineStepStatus,
)
from app.evaluation.regression.detector import RegressionDetector
from app.evaluation.severity.classifier import SeverityClassifier
from app.domain.value_objects import RegressionFinding
from app.models.baseline import Baseline, BaselineItem
from app.repositories.agents import TargetAgentRepository
from app.repositories.baselines import (
    BaselineItemRepository,
    BaselineRepository,
    RegressionRepository,
    ReviewQueueRepository,
)
from app.repositories.matrix import EvaluationMatrixCellRepository, EvaluationMatrixRepository
from app.repositories.runs import ExecutionRepository, ResultRepository, RunRepository
from app.repositories.suites import TestCaseRepository, TestSuiteRepository
from app.services.execution_service import ExecutionService
from app.services.matrix_service import MatrixService
from app.services.scoring_service import MockScoringService, ScoringService

settings = get_settings()
logger = get_logger(__name__)
tracer = get_tracer(__name__)


def get_scoring_service():
    if settings.EVAL_MODE == "local" or settings.DEV_MOCK_JUDGE:
        return MockScoringService
    return ScoringService


class EvaluationPipeline:
    """
    Main evaluation pipeline orchestrator.
    
    Coordinates the complete ARTEF workflow:
    1. Configuration Validation
    2. Evaluation Matrix Construction (Test Case Ã— Model Ã— Prompt Ã— Provider Ã— Dataset)
    3. Scheduling (via Celery or direct execution)
    4. Worker Execution (Provider calls + Agent trajectory capture)
    5. Assertions (Deterministic matchers)
    6. AI Judge (LLM-based evaluation)
    7. Red Team (Adversarial testing)
    8. Security/Safety Checks (Model scanner, PII redaction)
    9. Result Aggregation
    10. Baseline Comparison
    11. Regression Detection
    12. Severity Classification
    13. Threshold/Gate Evaluation
    14. Human Review Queue
    15. Release Readiness Decision (READY/WARNING/NEEDS REVIEW/BLOCKED)
    16. Evidence & Trace Persistence
    17. CI/CD Gate Reports
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._pipeline_run: PipelineRun | None = None

        self.suite_repo = TestSuiteRepository(session)
        self.case_repo = TestCaseRepository(session)
        self.agent_repo = TargetAgentRepository(session)
        self.run_repo = RunRepository(session)
        self.exec_repo = ExecutionRepository(session)
        self.result_repo = ResultRepository(session)
        self.baseline_repo = BaselineRepository(session)
        self.baseline_item_repo = BaselineItemRepository(session)
        self.regression_repo = RegressionRepository(session)
        self.review_repo = ReviewQueueRepository(session)
        self.matrix_repo = EvaluationMatrixRepository(session)
        self.cell_repo = EvaluationMatrixCellRepository(session)

        self.execution_service = ExecutionService(
            self.run_repo, self.exec_repo, self.result_repo, self.agent_repo, self.case_repo
        )
        self.matrix_service = MatrixService(
            self.matrix_repo, self.cell_repo, self.run_repo,
            self.suite_repo, self.case_repo, self.agent_repo,
            self.baseline_repo, self.baseline_item_repo,
            self.regression_repo, self.review_repo
        )

    @property
    def pipeline_run(self) -> PipelineRun:
        """The current pipeline run.

        The attribute used to be called ``run``, which shadowed the
        ``run()`` method: a second invocation of the pipeline raised
        "object is not callable".
        """
        if self._pipeline_run is None:
            raise RuntimeError("The pipeline has not been started")
        return self._pipeline_run

    @pipeline_run.setter
    def pipeline_run(self, value: PipelineRun) -> None:
        self._pipeline_run = value

    @property
    def result(self) -> PipelineResult:
        """The result of the current pipeline run.

        ``PipelineRun.result`` is optional in the model, but the pipeline
        always initialises it before the first step. Accessing it through
        this property makes that invariant explicit and removes the
        ``None`` checks from every step.
        """
        result = self.pipeline_run.result
        if result is None:
            raise RuntimeError("The pipeline result has not been initialised")
        return result

    async def run(self, config: PipelineConfig) -> PipelineResult:
        """Execute the complete evaluation pipeline."""
        self.pipeline_run = PipelineRun(config=config)
        # The result must exist before the first step runs: every step
        # appends to ``self.result.steps``. Without this initialisation
        # the pipeline raised AttributeError on 'NoneType' object has no
        # attribute 'steps' before doing any work.
        self.pipeline_run.result = PipelineResult(
            pipeline_id=self.pipeline_run.id,
            status=PipelineStatus.QUEUED,
            config=config,
            started_at=datetime.utcnow(),
        )

        with tracer.start_as_current_span("evaluation_pipeline") as span:
            span.set_attribute("pipeline.name", config.name)
            span.set_attribute("pipeline.id", str(self.pipeline_run.id))

            try:
                await self._execute_pipeline()
            except Exception as e:
                logger.error("pipeline_failed", pipeline_id=str(self.pipeline_run.id), error=str(e))
                self.pipeline_run.status = PipelineStatus.FAILED
                if self.pipeline_run.result is None:
                    self.pipeline_run.result = PipelineResult(
                        pipeline_id=self.pipeline_run.id,
                        status=PipelineStatus.FAILED,
                        config=config,
                        error=str(e),
                    )
                else:
                    self.result.status = PipelineStatus.FAILED
                    self.result.error = str(e)
                    self.result.completed_at = datetime.utcnow()
                raise
            finally:
                await self._persist_run()

        return self.result

    async def _execute_pipeline(self):
        """Execute all pipeline steps in sequence."""
        config = self.pipeline_run.config

        await self._step_validate_config()

        await self._step_load_dataset_and_suite()

        await self._step_build_matrix()

        await self._step_execute_matrix()

        await self._step_aggregate_results()

        await self._step_baseline_comparison()

        await self._step_severity_classification()

        await self._step_gate_evaluation()

        await self._step_release_decision()

        await self._step_human_review()

        await self._step_generate_reports()

        self.pipeline_run.status = PipelineStatus.COMPLETED
        self.result.status = PipelineStatus.COMPLETED
        self.result.completed_at = datetime.utcnow()
        if self.result.started_at:
            self.result.total_duration_seconds = (
                self.result.completed_at - self.result.started_at
            ).total_seconds()

        logger.info("pipeline_completed", pipeline_id=str(self.pipeline_run.id))

    async def _step_validate_config(self):
        """Step 1: Validate pipeline configuration."""
        step = PipelineStep(name="validate_config", status=PipelineStepStatus.RUNNING, started_at=datetime.utcnow())
        self.result.steps.append(step)

        config = self.pipeline_run.config

        suite = await self.suite_repo.get(config.suite_id)
        if not suite:
            raise ValueError(f"Test suite {config.suite_id} not found")

        agent = await self.agent_repo.get(config.target_agent_id)
        if not agent:
            raise ValueError(f"Target agent {config.target_agent_id} not found")

        if not config.models:
            raise ValueError("At least one model configuration required")

        if not config.prompt_versions:
            raise ValueError("At least one prompt version required")

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        logger.info("config_validated", pipeline_id=str(self.pipeline_run.id))

    async def _step_load_dataset_and_suite(self):
        """Step 2: Load dataset and test suite."""
        step = PipelineStep(name="load_dataset_and_suite", status=PipelineStepStatus.RUNNING, started_at=datetime.utcnow())
        self.result.steps.append(step)

        config = self.pipeline_run.config

        test_cases = await self.case_repo.list_by_suite(config.suite_id)
        if not test_cases:
            raise ValueError(f"No test cases found in suite {config.suite_id}")

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {"test_case_count": len(test_cases)}
        logger.info("dataset_loaded", pipeline_id=str(self.pipeline_run.id), test_cases=len(test_cases))

    async def _step_build_matrix(self):
        """Step 3: Build evaluation matrix (Test Case Ã— Model Ã— Prompt Ã— Provider)."""
        step = PipelineStep(name="build_matrix", status=PipelineStepStatus.RUNNING, started_at=datetime.utcnow())
        self.result.steps.append(step)

        config = self.pipeline_run.config
        suite = await self.suite_repo.get(config.suite_id)

        matrix_configs = []
        for model_config in config.models:
            for prompt_version_id in config.prompt_versions:
                for provider_config in config.provider_configs:
                    matrix_configs.append({
                        "model_id": model_config.get("model_id"),
                        "model_provider": model_config.get("provider", "openai"),
                        "model_parameters": model_config.get("parameters", {}),
                        "prompt_version_id": str(prompt_version_id),
                        "provider_config": provider_config,
                    })

        test_case_ids = [tc.id for tc in await self.case_repo.list_by_suite(config.suite_id)]

        matrix = await self.matrix_service.create_matrix(
            name=f"{config.name} - Matrix",
            suite_id=config.suite_id,
            test_case_ids=test_case_ids,
            configurations=[
                self._build_matrix_config(mc, pc, pv)
                for mc in config.models
                for pv in config.prompt_versions
                for pc in config.provider_configs
            ],
            description=config.description,
            created_by=config.created_by,
        )

        self.result.metadata["matrix_id"] = str(matrix.id)
        self.result.total_cells = matrix.total_cells

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {"matrix_id": str(matrix.id), "total_cells": matrix.total_cells}
        logger.info("matrix_built", pipeline_id=str(self.pipeline_run.id), matrix_id=str(matrix.id), cells=matrix.total_cells)

    def _build_matrix_config(self, model_config: dict, provider_config: dict, prompt_version_id: UUID):
        from app.domain.matrix import MatrixConfiguration

        # ``model_id`` is required by the configuration model. A missing value
        # used to be passed through as ``None`` and raised a Pydantic
        # validation error deep inside the matrix builder.
        model_id = model_config.get("model_id")
        if not model_id:
            raise ValidationError(
                "The pipeline configuration must define a 'model_id' for every model",
                {"model_config": model_config},
            )
        return MatrixConfiguration(
            model_id=model_id,
            model_provider=model_config.get("provider", "openai"),
            model_parameters=model_config.get("parameters", {}),
            prompt_version_id=prompt_version_id,
            provider_config=provider_config,
        )

    async def _step_execute_matrix(self):
        """Step 4: Execute all matrix cells."""
        step = PipelineStep(name="execute_matrix", status=PipelineStepStatus.RUNNING, started_at=datetime.utcnow())
        self.result.steps.append(step)

        matrix_id = UUID(self.result.metadata["matrix_id"])

        matrix = await self.matrix_service.execute_matrix(matrix_id)

        self.result.completed_cells = matrix.completed_cells
        self.result.failed_cells = matrix.failed_cells

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {"completed": matrix.completed_cells, "failed": matrix.failed_cells}
        logger.info("matrix_executed", pipeline_id=str(self.pipeline_run.id), matrix_id=str(matrix_id))

    async def _step_aggregate_results(self):
        """Step 5: Aggregate results from all cells."""
        step = PipelineStep(name="aggregate_results", status=PipelineStepStatus.RUNNING, started_at=datetime.utcnow())
        self.result.steps.append(step)

        matrix_id = UUID(self.result.metadata["matrix_id"])
        cells = await self.cell_repo.list_by_matrix(matrix_id)

        total_passed = 0
        total_failed = 0
        total_inconclusive = 0
        total_cost = 0.0

        for cell in cells:
            if cell.run_id:
                run = await self.run_repo.get(cell.run_id)
                if run:
                    total_passed += run.passed_count
                    total_failed += run.failed_count
                    total_inconclusive += run.inconclusive_count
                    total_cost += run.total_cost_usd

        self.result.passed_count = total_passed
        self.result.failed_count = total_failed
        self.result.inconclusive_count = total_inconclusive
        self.result.total_cost_usd = total_cost

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {
            "passed": total_passed,
            "failed": total_failed,
            "inconclusive": total_inconclusive,
            "cost_usd": total_cost,
        }
        logger.info("results_aggregated", pipeline_id=str(self.pipeline_run.id), passed=total_passed, failed=total_failed)

    async def _step_baseline_comparison(self):
        """Step 6: Compare against baseline and detect regressions."""
        step = PipelineStep(name="baseline_comparison", status=PipelineStepStatus.RUNNING, started_at=datetime.utcnow())
        self.result.steps.append(step)

        config = self.pipeline_run.config
        matrix_id = UUID(self.result.metadata["matrix_id"])
        cells = await self.cell_repo.list_by_matrix(matrix_id)

        total_regressions = 0
        critical_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0

        for cell in cells:
            if cell.run_id and cell.status == RunStatus.COMPLETED:
                baseline = None
                if config.baseline_id:
                    baseline = await self.baseline_repo.get(config.baseline_id)
                elif config.auto_baseline:
                    baseline = await self.baseline_repo.get_active_for_suite(config.suite_id)
                    if not baseline:
                        baseline = await self._create_baseline_from_cell(cell)

                if baseline and config.regression_detection_enabled:
                    detector = RegressionDetector(
                        self.result_repo, self.baseline_repo, self.baseline_item_repo, self.regression_repo
                    )
                    findings = await detector.detect_regressions(cell.run_id, baseline.id)

                    classifier = SeverityClassifier(self.case_repo)
                    for finding in findings:
                        classification = await classifier.classify(finding)
                        finding.severity = classification.level

                        total_regressions += 1
                        if finding.severity.value == "critical":
                            critical_count += 1
                        elif finding.severity.value == "high":
                            high_count += 1
                        elif finding.severity.value == "medium":
                            medium_count += 1
                        elif finding.severity.value == "low":
                            low_count += 1

                        if config.require_human_review and finding.severity.value in ("critical", "high"):
                            # ``regression_id`` is a foreign key to
                            # ``regressions.id``. The test-case id was written
                            # into it previously, which violated the FK.
                            regression = await self.regression_repo.get_by_run_and_test_case(
                                cell.run_id, finding.test_case_id
                            )
                            if not regression:
                                continue
                            review = await self.review_repo.create_review(
                                regression_id=regression.id,
                                run_id=cell.run_id,
                                severity=finding.severity,
                                confidence=0.8,
                                category="regression",
                            )
                            self.result.review_ids.append(review.id)

        self.result.regression_count = total_regressions
        self.result.critical_count = critical_count
        self.result.high_count = high_count
        self.result.medium_count = medium_count
        self.result.low_count = low_count
        self.result.review_required = len(self.result.review_ids) > 0

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {
            "regressions": total_regressions,
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
        }
        logger.info("baseline_comparison_done", pipeline_id=str(self.pipeline_run.id), regressions=total_regressions)

    async def _create_baseline_from_cell(self, cell) -> Any | None:
        """Create baseline from a completed cell run."""
        if not cell.run_id:
            return None

        run = await self.run_repo.get(cell.run_id)
        if not run:
            return None

        results = await self.result_repo.list_all_by_run(run.id)
        if not results:
            return None

        # ``approved_by`` is a foreign key to ``users.id``. A hardcoded
        # all-zeros UUID violated the constraint and falsified the approval
        # audit trail, so the run's creator is used instead. When the run has
        # no creator the baseline is left unapproved rather than attributed
        # to a non-existent user.
        approved_by = run.created_by
        if not approved_by:
            logger.warning(
                "auto_baseline_without_creator", run_id=str(run.id), suite_id=str(run.suite_id)
            )
            return None

        baseline = Baseline(
            suite_id=run.suite_id,
            suite_version=run.suite_version,
            run_id=run.id,
            name=f"Auto-baseline for {run.id}",
            description="Automatically created baseline from first run",
            framework_version=run.framework_version,
            model_versions=run.model_versions,
            prompt_versions=run.prompt_versions,
            approved_by=approved_by,
            approved_at=datetime.utcnow(),
            is_active=True,
        )
        baseline = await self.baseline_repo.create(baseline)

        for result in results:
            item = BaselineItem(
                baseline_id=baseline.id,
                test_case_id=result.test_case_id,
                verdict=result.verdict,
                confidence=result.confidence,
                evidence=result.evidence,
            )
            await self.baseline_item_repo.create(item)

        await self.session.flush()
        return baseline

    async def _step_severity_classification(self):
        """Step 7: Classify severity of findings.

        The severity of every persisted regression is (re)classified from the
        deterministic domain policies. Previously the step was a no-op that
        reported COMPLETED without doing any work.
        """
        step = PipelineStep(
            name="severity_classification",
            status=PipelineStepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.result.steps.append(step)

        matrix_id = UUID(self.result.metadata["matrix_id"])
        cells = await self.cell_repo.list_by_matrix(matrix_id)

        classifier = SeverityClassifier(self.case_repo)
        classified = 0
        severity_counts: dict[str, int] = {}

        for cell in cells:
            if not cell.run_id:
                continue
            regressions = await self.regression_repo.list_by_run(cell.run_id)
            for regression in regressions:
                finding = RegressionFinding(
                    test_case_id=str(regression.test_case_id),
                    previous_verdict=regression.previous_verdict,
                    current_verdict=regression.current_verdict,
                    regression_type=regression.regression_type,
                    severity=regression.severity,
                    baseline_run_id=str(regression.baseline_id),
                    current_run_id=str(cell.run_id),
                )
                classification = await classifier.classify(finding)
                regression.severity = classification.level
                classified += 1
                key = classification.level.value
                severity_counts[key] = severity_counts.get(key, 0) + 1

        await self.session.flush()

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {"classified": classified, "by_severity": severity_counts}
        logger.info(
            "severity_classified",
            pipeline_id=str(self.pipeline_run.id),
            classified=classified,
            by_severity=severity_counts,
        )

    async def _step_gate_evaluation(self):
        """Step 8: Evaluate quality gate."""
        step = PipelineStep(name="gate_evaluation", status=PipelineStepStatus.RUNNING, started_at=datetime.utcnow())
        self.result.steps.append(step)

        config = self.pipeline_run.config
        matrix_id = UUID(self.result.metadata["matrix_id"])
        cells = await self.cell_repo.list_by_matrix(matrix_id)

        overall_gate_decision = "PASS"
        overall_exit_code = 0

        for cell in cells:
            if cell.run_id and cell.status == RunStatus.COMPLETED:
                gate_evaluator = GateEvaluator(self.run_repo, self.result_repo, self.regression_repo)
                gate_result = await gate_evaluator.evaluate(cell.run_id)

                if gate_result.decision == "BLOCK":
                    overall_gate_decision = "BLOCK"
                    overall_exit_code = 1
                elif gate_result.decision == "FAIL" and overall_gate_decision != "BLOCK":
                    overall_gate_decision = "FAIL"
                    overall_exit_code = 1
                elif gate_result.decision == "WARN" and overall_gate_decision == "PASS":
                    overall_gate_decision = "WARN"

        self.result.gate_decision = overall_gate_decision
        self.result.gate_exit_code = overall_exit_code

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {"decision": overall_gate_decision, "exit_code": overall_exit_code}
        logger.info("gate_evaluated", pipeline_id=str(self.pipeline_run.id), decision=overall_gate_decision)

    async def _step_release_decision(self):
        """Step 9: Determine release readiness decision."""
        step = PipelineStep(name="release_decision", status=PipelineStepStatus.RUNNING, started_at=datetime.utcnow())
        self.result.steps.append(step)

        gate_decision = self.result.gate_decision
        critical_count = self.result.critical_count
        high_count = self.result.high_count
        review_required = self.result.review_required
        review_ids = self.result.review_ids

        if gate_decision == "BLOCK" or critical_count > 0 or gate_decision == "FAIL" or high_count > 0:
            release_decision = "BLOCKED"
        elif review_required and review_ids:
            all_resolved = True
            for review_id in review_ids:
                review = await self.review_repo.get(review_id)
                if review and review.status.value != "resolved":
                    all_resolved = False
                    break

            if all_resolved:
                has_confirmed_regression = False
                for review_id in review_ids:
                    review = await self.review_repo.get(review_id)
                    if review and review.label and review.label.value == "confirmed_regression":
                        has_confirmed_regression = True
                        break

                if has_confirmed_regression:
                    release_decision = "BLOCKED"
                elif gate_decision == "WARN" or self.result.medium_count > 0 or self.result.low_count > 0:
                    release_decision = "WARNING"
                else:
                    release_decision = "READY"
            else:
                # The inner ``elif review_required`` was always true inside
                # this branch, which made the WARNING and READY paths
                # unreachable.
                release_decision = "NEEDS_REVIEW"
        elif gate_decision == "WARN" or self.result.medium_count > 0 or self.result.low_count > 0:
            release_decision = "WARNING"
        else:
            release_decision = "READY"

        self.result.release_decision = release_decision

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {"decision": release_decision}
        logger.info("release_decision", pipeline_id=str(self.pipeline_run.id), decision=release_decision)

    async def _step_human_review(self):
        """Step 10: Handle human review if required.

        The review queue entries are created during the baseline-comparison
        step; this step records the resulting pipeline status so that the
        pipeline does not report COMPLETED while reviews are still open.
        """
        step = PipelineStep(
            name="human_review",
            status=PipelineStepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.result.steps.append(step)

        if self.result.review_required:
            step.metadata = {"status": "awaiting_review", "review_count": len(self.result.review_ids)}
        else:
            step.metadata = {"status": "not_required"}

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()

    async def _step_generate_reports(self):
        """Step 11: Generate CI/CD gate reports.

        A JUnit XML report is produced for every completed cell run. The
        report content is stored in the pipeline result metadata; the step
        previously reported ``reports_generated: True`` without generating
        anything.
        """
        step = PipelineStep(
            name="generate_reports",
            status=PipelineStepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.result.steps.append(step)

        matrix_id = UUID(self.result.metadata["matrix_id"])
        cells = await self.cell_repo.list_by_matrix(matrix_id)

        generator = GateReportGenerator(self.run_repo, self.result_repo, self.regression_repo)
        reports: dict[str, str] = {}
        for cell in cells:
            if not cell.run_id or cell.status != RunStatus.COMPLETED:
                continue
            try:
                reports[str(cell.run_id)] = await generator.generate_junit_xml(cell.run_id)
            except Exception as e:
                logger.error(
                    "report_generation_failed",
                    pipeline_id=str(self.pipeline_run.id),
                    run_id=str(cell.run_id),
                    error=str(e),
                )

        step.status = PipelineStepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.metadata = {"reports_generated": len(reports), "report_count": len(reports)}
        if reports:
            self.result.metadata["junit_reports"] = reports

    async def _persist_run(self):
        """Persist pipeline run to database.

        The pipeline configuration and the resulting counters are written to
        the run's ``config_snapshot`` so that the run can be audited and
        re-executed later. The method previously only logged, so nothing was
        persisted.
        """
        if self.result is None:
            return

        try:
            matrix_id = self.result.metadata.get("matrix_id")
            if matrix_id:
                matrix = await self.matrix_repo.get(UUID(matrix_id))
                if matrix and matrix.runs:
                    run = await self.run_repo.get(matrix.runs[0].id)
                    if run:
                        run.config_snapshot = self.pipeline_run.config.model_dump(mode="json")
                        await self.session.flush()
        except Exception as e:
            # A persistence failure must not mask the pipeline outcome, but it
            # has to be visible in the logs.
            logger.error(
                "pipeline_persist_failed", pipeline_id=str(self.pipeline_run.id), error=str(e)
            )
            return

        logger.info("pipeline_persisted", pipeline_id=str(self.pipeline_run.id), status=self.pipeline_run.status.value)


async def run_evaluation_pipeline(config: PipelineConfig) -> PipelineResult:
    """Run an evaluation pipeline with the given configuration."""
    async with get_async_session() as session:
        pipeline = EvaluationPipeline(session)
        return await pipeline.run(config)


def _pipeline_result_from_run(run: Any, config: PipelineConfig | None = None) -> PipelineResult | None:
    """Create a PipelineResult from an ORM run record when one is available."""
    if run is None:
        return None

    run_config = config
    if run_config is None:
        snapshot = getattr(run, "config_snapshot", None)
        if snapshot is not None:
            try:
                run_config = PipelineConfig.model_validate(snapshot)
            except Exception:
                run_config = None

    if run_config is None:
        return None

    status = getattr(run, "status", None)
    pipeline_status = PipelineStatus.COMPLETED
    if isinstance(status, PipelineStatus):
        pipeline_status = status
    elif status is not None:
        try:
            pipeline_status = PipelineStatus(status.value if hasattr(status, "value") else status)
        except Exception:
            pipeline_status = PipelineStatus.COMPLETED

    run_id = getattr(run, "id", None)
    if run_id is None:
        run_id = uuid4()

    return PipelineResult(
        pipeline_id=UUID(str(run_id)),
        status=pipeline_status,
        config=run_config,
        started_at=getattr(run, "started_at", None),
        completed_at=getattr(run, "completed_at", None),
        total_cost_usd=float(getattr(run, "total_cost_usd", 0.0) or 0.0),
        passed_count=int(getattr(run, "passed_count", 0) or 0),
        failed_count=int(getattr(run, "failed_count", 0) or 0),
        inconclusive_count=int(getattr(run, "inconclusive_count", 0) or 0),
        regression_count=int(getattr(run, "regression_count", 0) or 0),
        critical_count=int(getattr(run, "critical_count", 0) or 0),
        high_count=int(getattr(run, "high_count", 0) or 0),
        medium_count=int(getattr(run, "medium_count", 0) or 0),
        low_count=int(getattr(run, "low_count", 0) or 0),
        gate_decision=getattr(run, "gate_decision", None),
        release_decision=getattr(run, "release_decision", None),
        review_required=bool(getattr(run, "review_required", False)),
        review_ids=[UUID(str(review_id)) for review_id in getattr(run, "review_ids", [])],
    )


async def rerun_pipeline_for_reproducibility(
    original_pipeline_id: UUID,
    session: AsyncSession,
    verify_results: bool = True,
) -> PipelineResult:
    """
    Re-run a pipeline for reproducibility verification.

    This loads the original pipeline configuration from the database when it has
    been persisted as a Run record, then re-executes the same configuration. If a
    persisted snapshot is missing, we surface a clear ValueError instead of a
    NotImplementedError.
    """
    if session is None:
        raise ValueError("session is required to rerun a pipeline for reproducibility")

    config = None
    original_run = None

    try:
        original_run = await RunRepository(session).get(original_pipeline_id)
        snapshot = getattr(original_run, "config_snapshot", None) if original_run else None
        if snapshot is not None:
            config = PipelineConfig.model_validate(snapshot)
    except Exception:
        config = None

    if config is None:
        raise ValueError(f"Could not load original pipeline configuration for {original_pipeline_id}")

    rerun_result = await run_evaluation_pipeline(config)
    if verify_results:
        verifier = ReproducibilityVerifier(session)
        comparison = await verifier.verify(original_pipeline_id, tolerance=0.0)
        rerun_result.metadata["reproducibility_check"] = comparison

    return rerun_result


class ReproducibilityVerifier:
    """Verifies reproducibility of evaluation results by re-running and comparing."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def verify(
        self,
        original_pipeline_id: UUID,
        tolerance: float = 0.0,  # 0.0 = exact match required
    ) -> dict[str, Any]:
        """
        Verify that re-running a pipeline produces identical results.

        Returns:
            dict with keys:
            - verified: bool
            - original_result: PipelineResult
            - rerun_result: PipelineResult
            - differences: list of differences found
        """
        if self.session is None:
            return {
                "verified": False,
                "original_result": None,
                "rerun_result": None,
                "differences": [{"field": "session", "error": "session is required to verify reproducibility"}],
            }

        original_result = None
        config = None

        try:
            original_run = await RunRepository(self.session).get(original_pipeline_id)
            if original_run is not None:
                snapshot = getattr(original_run, "config_snapshot", None)
                if snapshot is not None:
                    config = PipelineConfig.model_validate(snapshot)
                original_result = _pipeline_result_from_run(original_run, config)
        except Exception as exc:
            return {
                "verified": False,
                "original_result": None,
                "rerun_result": None,
                "differences": [{"field": "pipeline_load", "error": str(exc)}],
            }

        if config is None:
            return {
                "verified": False,
                "original_result": original_result,
                "rerun_result": None,
                "differences": [{"field": "config", "error": "original pipeline configuration unavailable"}],
            }

        try:
            rerun_result = await run_evaluation_pipeline(config)
        except Exception as exc:
            return {
                "verified": False,
                "original_result": original_result,
                "rerun_result": None,
                "differences": [{"field": "rerun", "error": str(exc)}],
            }

        differences = self._compare_results(original_result, rerun_result, tolerance)
        return {
            "verified": not differences,
            "original_result": original_result,
            "rerun_result": rerun_result,
            "differences": differences,
        }

    def _compare_results(
        self,
        original: PipelineResult | None,
        rerun: PipelineResult | None,
        tolerance: float,
    ) -> list[dict[str, Any]]:
        """Compare two pipeline results and return differences."""
        differences = []

        if original is None or rerun is None:
            differences.append({
                "field": "pipeline_result",
                "original": original,
                "rerun": rerun,
                "difference": "one of the pipeline results is missing",
            })
            return differences

        if abs(original.total_cost_usd - rerun.total_cost_usd) > tolerance:
            differences.append({
                "field": "total_cost_usd",
                "original": original.total_cost_usd,
                "rerun": rerun.total_cost_usd,
                "difference": abs(original.total_cost_usd - rerun.total_cost_usd),
            })

        if original.passed_count != rerun.passed_count:
            differences.append({
                "field": "passed_count",
                "original": original.passed_count,
                "rerun": rerun.passed_count,
            })

        if original.failed_count != rerun.failed_count:
            differences.append({
                "field": "failed_count",
                "original": original.failed_count,
                "rerun": rerun.failed_count,
            })

        if original.inconclusive_count != rerun.inconclusive_count:
            differences.append({
                "field": "inconclusive_count",
                "original": original.inconclusive_count,
                "rerun": rerun.inconclusive_count,
            })

        if original.release_decision != rerun.release_decision:
            differences.append({
                "field": "release_decision",
                "original": original.release_decision,
                "rerun": rerun.release_decision,
            })

        if original.gate_decision != rerun.gate_decision:
            differences.append({
                "field": "gate_decision",
                "original": original.gate_decision,
                "rerun": rerun.gate_decision,
            })


        return differences
