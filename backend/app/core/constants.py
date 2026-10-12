"""
Application constants - Centralized configuration values.
All values can be overridden via environment variables.
"""

import os
from typing import Dict, Any

# ============================================================================
# NETWORK & TIMING DEFAULTS
# ============================================================================

# Default timeouts (in seconds)
DEFAULT_HTTP_TIMEOUT = int(os.getenv("DEFAULT_HTTP_TIMEOUT", "60"))
DEFAULT_AGENT_TIMEOUT = int(os.getenv("DEFAULT_AGENT_TIMEOUT", "30"))
DEFAULT_EMBEDDINGS_TIMEOUT = int(os.getenv("DEFAULT_EMBEDDINGS_TIMEOUT", "30"))
DEFAULT_REGEX_TIMEOUT_MS = int(os.getenv("DEFAULT_REGEX_TIMEOUT_MS", "1000"))
DEFAULT_COMPILE_TIMEOUT = float(os.getenv("DEFAULT_COMPILE_TIMEOUT", "1.0"))

# Default retry values
DEFAULT_MAX_RETRIES = int(os.getenv("DEFAULT_MAX_RETRIES", "3"))
DEFAULT_AGENT_MAX_RETRIES = int(os.getenv("DEFAULT_AGENT_MAX_RETRIES", "3"))
DEFAULT_RETRY_DELAY = int(os.getenv("DEFAULT_RETRY_DELAY", "60"))

# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_SUCCESS_THRESHOLD", "2"))
CIRCUIT_BREAKER_TIMEOUT = float(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "30.0"))

# ============================================================================
# AGENT CONFIGURATION
# ============================================================================

# Agent timeout/retry defaults
SEED_AGENT_TIMEOUT = int(os.getenv("SEED_AGENT_TIMEOUT", "30"))
SEED_AGENT_MAX_RETRIES = int(os.getenv("SEED_AGENT_MAX_RETRIES", "3"))
SEED_MOCK_AGENT_TIMEOUT = int(os.getenv("SEED_MOCK_AGENT_TIMEOUT", "5"))
SEED_MOCK_AGENT_MAX_RETRIES = int(os.getenv("SEED_MOCK_AGENT_MAX_RETRIES", "1"))

# ============================================================================
# TEXT PROCESSING LIMITS
# ============================================================================

# String truncation limits
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "2000"))
MAX_RESPONSE_LENGTH = int(os.getenv("MAX_RESPONSE_LENGTH", "4000"))
MAX_CRITERIA_LENGTH = int(os.getenv("MAX_CRITERIA_LENGTH", "3000"))
MAX_LOG_STRING_LENGTH = int(os.getenv("MAX_LOG_STRING_LENGTH", "1000"))

# ============================================================================
# SECURITY & NETWORKING
# ============================================================================

# Trusted proxy IPs (for rate limiting)
TRUSTED_PROXY_IPS = set(os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(","))

# Private IP blocking
BLOCK_PRIVATE_IPS = os.getenv("BLOCK_PRIVATE_IPS", "true").lower() == "true"
BLOCK_LOCALHOST_IN_PRODUCTION = os.getenv("BLOCK_LOCALHOST_IN_PRODUCTION", "true").lower() == "true"

# ============================================================================
# LLM PROVIDER DEFAULTS
# ============================================================================

# OpenAI defaults
OPENAI_DEFAULT_BASE_URL = os.getenv("OPENAI_DEFAULT_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2023-12-01")

# Anthropic defaults
ANTHROPIC_DEFAULT_BASE_URL = os.getenv("ANTHROPIC_DEFAULT_BASE_URL", "https://api.anthropic.com/v1")
ANTHROPIC_API_VERSION = os.getenv("ANTHROPIC_API_VERSION", "2023-06-01")

# ============================================================================
# CELERY TASK CONFIGURATION
# ============================================================================

# Task retry settings
CELERY_EVALUATION_MAX_RETRIES = int(os.getenv("CELERY_EVALUATION_MAX_RETRIES", "3"))
CELERY_EVALUATION_RETRY_DELAY = int(os.getenv("CELERY_EVALUATION_RETRY_DELAY", "60"))

CELERY_REDTEAM_MAX_RETRIES = int(os.getenv("CELERY_REDTEAM_MAX_RETRIES", "2"))
CELERY_REDTEAM_RETRY_DELAY = int(os.getenv("CELERY_REDTEAM_RETRY_DELAY", "60"))

CELERY_REGRESSION_MAX_RETRIES = int(os.getenv("CELERY_REGRESSION_MAX_RETRIES", "2"))
CELERY_REGRESSION_RETRY_DELAY = int(os.getenv("CELERY_REGRESSION_RETRY_DELAY", "30"))

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_timeout_config() -> Dict[str, Any]:
    """Get all timeout configurations as a dictionary."""
    return {
        "http_timeout": DEFAULT_HTTP_TIMEOUT,
        "agent_timeout": DEFAULT_AGENT_TIMEOUT,
        "embeddings_timeout": DEFAULT_EMBEDDINGS_TIMEOUT,
        "regex_timeout_ms": DEFAULT_REGEX_TIMEOUT_MS,
        "compile_timeout": DEFAULT_COMPILE_TIMEOUT,
    }


def get_retry_config() -> Dict[str, Any]:
    """Get all retry configurations as a dictionary."""
    return {
        "max_retries": DEFAULT_MAX_RETRIES,
        "agent_max_retries": DEFAULT_AGENT_MAX_RETRIES,
        "retry_delay": DEFAULT_RETRY_DELAY,
    }


def get_circuit_breaker_config() -> Dict[str, Any]:
    """Get circuit breaker configuration."""
    return {
        "failure_threshold": CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        "success_threshold": CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
        "timeout": CIRCUIT_BREAKER_TIMEOUT,
    }


# ============================================================================
# CONSTANTS (Non-configurable)
# ============================================================================

# HTTP status codes
HTTP_STATUS_OK = 200
HTTP_STATUS_UNAUTHORIZED = 401
HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_REQUEST_TOO_LARGE = 413
HTTP_STATUS_INTERNAL_ERROR = 500

# Request template defaults
DEFAULT_REQUEST_TEMPLATE = {"input": "{input}"}
DEFAULT_RESPONSE_EXTRACTION = {"response": "response"}

# Auth config types
AUTH_CONFIG_NONE = {"type": "none"}
AUTH_CONFIG_BEARER_TEMPLATE = {"type": "bearer", "token": "{token}"}
