import pytest

from app.domain.entities import TargetAgent, TestSuite as DomainTestSuite
from app.domain.value_objects import (
    CriteriaResult,
    EvidenceItem,
    JudgeOutput,
    LLMRubric,
    LLMRubricCriterion,
    MatcherConfig,
    ScoringResult,
)


def test_matcher_config_valid_regex():
    config = MatcherConfig(
        pattern=r"\d{3}-\d{2}-\d{4}",
        regex_timeout_ms=1000,
    )
    assert config.pattern == r"\d{3}-\d{2}-\d{4}"


def test_matcher_config_invalid_regex():
    with pytest.raises(ValueError, match="Invalid regex pattern"):
        MatcherConfig(pattern=r"[invalid")


def test_llm_rubric_criterion():
    criterion = LLMRubricCriterion(
        name="Accuracy",
        description="Response is factually accurate",
        weight=0.5,
        pass_threshold=0.7,
    )
    assert criterion.name == "Accuracy"
    assert criterion.weight == 0.5


def test_llm_rubric():
    rubric = LLMRubric(
        criteria=[
            LLMRubricCriterion(name="A", description="D", weight=0.5),
            LLMRubricCriterion(name="B", description="D", weight=0.5),
        ],
        overall_threshold=0.7,
    )
    assert len(rubric.criteria) == 2
    assert rubric.overall_threshold == 0.7


def test_judge_output_valid():
    output = JudgeOutput(
        verdict="PASS",
        confidence=0.9,
        rationale="Response is correct",
        evidence=[EvidenceItem(source="target_response", text="Correct answer")],
        criteria_results=[CriteriaResult(criterion="Accuracy", passed=True, evidence="Correct")],
    )
    assert output.verdict == "PASS"
    assert output.confidence == 0.9


def test_judge_output_empty_evidence_fails():
    with pytest.raises(ValueError, match="Evidence list cannot be empty"):
        JudgeOutput(
            verdict="PASS",
            confidence=0.9,
            rationale="Response is correct",
            evidence=[],
        )


def test_judge_output_criteria_consistency():
    with pytest.raises(ValueError, match="confidence too low"):
        JudgeOutput(
            verdict="PASS",
            confidence=0.9,
            rationale="Response is correct",
            evidence=[EvidenceItem(source="target_response", text="test")],
            criteria_results=[CriteriaResult(criterion="Test", passed=True, evidence="test", confidence=0.3)],
        )


def test_scoring_result():
    result = ScoringResult(
        test_case_id="TEST_001",
        verdict="PASS",
        confidence=0.9,
        execution_time_ms=100,
    )
    assert result.test_case_id == "TEST_001"
    assert result.verdict == "PASS"
    assert result.confidence == 0.9


def test_default_collection_fields_are_not_shared_between_instances():
    suite_one = DomainTestSuite(name="Suite 1")
    suite_two = DomainTestSuite(name="Suite 2")
    suite_one.test_cases.append({"id": "case-1"})

    agent_one = TargetAgent(name="Agent 1", endpoint_url="https://example.com")
    agent_two = TargetAgent(name="Agent 2", endpoint_url="https://example.org")
    agent_one.auth_config["api_key"] = "secret"

    judge_one = JudgeOutput(
        verdict="PASS",
        confidence=0.9,
        rationale="ok",
        evidence=[EvidenceItem(source="target", text="correct")],
    )
    judge_two = JudgeOutput(
        verdict="PASS",
        confidence=0.8,
        rationale="also ok",
        evidence=[EvidenceItem(source="target", text="still correct")],
    )
    judge_one.evidence.append(EvidenceItem(source="target", text="extra"))

    assert suite_two.test_cases == []
    assert "api_key" not in agent_two.auth_config
    assert len(judge_one.evidence) == 2
    assert len(judge_two.evidence) == 1
