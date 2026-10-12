"""
ARTEF Library API

Python library for programmatically running evaluations, red team attacks,
and managing baselines for AI agent testing.

Usage:
    from artef import evaluate, redteam, baseline
    
    results = evaluate(
        agent="${AGENT_ENDPOINT}",
        prompts=["Tell me a joke", "Summarize this policy"],
        providers=["${PRIMARY_PROVIDER}:${PRIMARY_MODEL}", "${SECONDARY_PROVIDER}:${SECONDARY_MODEL}"],
        assertions=[
            {"type": "refusal", "expected": True},
            {"type": "safe_response", "expected": True}
        ]
    )
"""

from .core import evaluate, EvaluationResult
from .redteam import redteam_attack, RedTeamResult
from .baseline import create_baseline, compare_to_baseline, BaselineResult

__version__ = "1.0.0"
__all__ = [
    "evaluate",
    "EvaluationResult",
    "redteam_attack",
    "RedTeamResult",
    "create_baseline",
    "compare_to_baseline",
    "BaselineResult",
]
