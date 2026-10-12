# Complete Configuration Guide - No Hardcoded Values

## Overview

This guide documents all configuration options available in ARTEF. **No values are hardcoded** - everything can be configured via environment variables.

## Quick Reference

| Category | Count | Documentation Section |
|----------|-------|-----------------------|
| Database & Storage | 15+ | [Database](#database-configuration) |
| Network & Timeouts | 20+ | [Timeouts](#timeout-configuration) |
| Security | 10+ | [Security](#security-configuration) |
| LLM Providers | 15+ | [LLM](#llm-configuration) |
| Seeding & Development | 15+ | [Development](#development-configuration) |
| Features & Flags | 10+ | [Features](#feature-flags) |

## Core Configuration

### Database Configuration

```bash
# PostgreSQL (Production)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
DATABASE_POOL_SIZE=20
DATABASE_POOL_TIMEOUT=30
DATABASE_MAX_OVERFLOW=10

# SQLite (Development - no credentials needed)
DATABASE_URL=sqlite+aiosqlite:///./artef.db
```

### Redis Configuration

```bash
REDIS_URL=redis://host:6379/0
REDIS_MAX_CONNECTIONS=50

# Celery queues
CELERY_BROKER_URL=redis://host:6379/1
CELERY_RESULT_BACKEND=redis://host:6379/2
```

### Storage Configuration

```bash
# S3/MinIO
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
S3_BUCKET=artef-artifacts
S3_REGION=us-east-1

# Local storage fallback
LOCAL_STORAGE_PATH=/var/artef/storage
```

## Timeout Configuration

All timeout values are configurable to suit your environment:

```bash
# HTTP and API timeouts (seconds)
DEFAULT_HTTP_TIMEOUT=60
DEFAULT_AGENT_TIMEOUT=30
DEFAULT_EMBEDDINGS_TIMEOUT=30

# Regex pattern matching timeout (milliseconds)
DEFAULT_REGEX_TIMEOUT_MS=1000
DEFAULT_COMPILE_TIMEOUT=1.0
```

## Retry Configuration

Control retry behavior for resilience:

```bash
# General retry settings
DEFAULT_MAX_RETRIES=3
DEFAULT_AGENT_MAX_RETRIES=3
DEFAULT_RETRY_DELAY=60

# Circuit breaker (prevents cascading failures)
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2
CIRCUIT_BREAKER_TIMEOUT=30.0
```

## Celery Task Configuration

Fine-tune background task behavior:

```bash
# Evaluation tasks
CELERY_EVALUATION_MAX_RETRIES=3
CELERY_EVALUATION_RETRY_DELAY=60

# Red team tasks
CELERY_REDTEAM_MAX_RETRIES=2
CELERY_REDTEAM_RETRY_DELAY=60

# Regression analysis
CELERY_REGRESSION_MAX_RETRIES=2
CELERY_REGRESSION_RETRY_DELAY=30
```

## Text Processing Limits

Control memory usage and prevent DoS:

```bash
# String truncation limits
MAX_INPUT_LENGTH=2000
MAX_RESPONSE_LENGTH=4000
MAX_CRITERIA_LENGTH=3000
MAX_LOG_STRING_LENGTH=1000
```

## Security Configuration

### Network Security

```bash
# Trusted proxy IPs (comma-separated)
TRUSTED_PROXY_IPS=127.0.0.1,::1

# IP blocking
BLOCK_PRIVATE_IPS=true
BLOCK_LOCALHOST_IN_PRODUCTION=true
```

### Authentication

```bash
# JWT configuration
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=/path/to/private.pem
JWT_PUBLIC_KEY_PATH=/path/to/public.pem
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Secret key (minimum 32 characters)
SECRET_KEY=your-secure-random-secret-key-here
```

### CORS

```bash
# Comma-separated origins
CORS_ORIGINS=https://app.yourdomain.com,https://api.yourdomain.com
CORS_ALLOW_CREDENTIALS=true
```

## LLM Configuration

### Primary Judge (Evaluation)

```bash
PRIMARY_JUDGE_PROVIDER=openai
PRIMARY_JUDGE_MODEL=gpt-4o-2024-08-06
PRIMARY_JUDGE_API_KEY=your_api_key
PRIMARY_JUDGE_BASE_URL=https://api.openai.com/v1
```

### Secondary Judge (Fallback)

```bash
SECONDARY_JUDGE_PROVIDER=anthropic
SECONDARY_JUDGE_MODEL=claude-3-5-sonnet-20241022
SECONDARY_JUDGE_API_KEY=your_api_key
SECONDARY_JUDGE_BASE_URL=https://api.anthropic.com/v1
```

### Generator (Red Team)

```bash
GENERATOR_PROVIDER=openai
GENERATOR_MODEL=gpt-4o-2024-08-06
GENERATOR_API_KEY=your_api_key
GENERATOR_BASE_URL=https://api.openai.com/v1
```

### Embeddings

```bash
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_API_KEY=your_api_key
EMBEDDING_BASE_URL=https://api.openai.com/v1
```

### Provider Defaults

```bash
# Override default URLs if using proxies/custom endpoints
OPENAI_DEFAULT_BASE_URL=https://api.openai.com/v1
OPENAI_API_VERSION=2023-12-01
ANTHROPIC_DEFAULT_BASE_URL=https://api.anthropic.com/v1
ANTHROPIC_API_VERSION=2023-06-01
```

## Development Configuration

### Seed Data Users

```bash
# Admin user
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure_password_here
ADMIN_FULLNAME=Admin User

# Test user passwords (dev only!)
SEED_ADMIN_PASSWORD=dev_password
SEED_SAFETY_PASSWORD=dev_password
SEED_ML_PASSWORD=dev_password
SEED_QA_PASSWORD=dev_password
SEED_REVIEWER_PASSWORD=dev_password
SEED_VIEWER_PASSWORD=dev_password

# Email domain for test users
SEED_EMAIL_DOMAIN=yourdomain.com
```

### Seed Data Agents

```bash
# Production agent endpoints
SEED_PROD_AGENT_URL=https://api.yourdomain.com/chat
SEED_STAGING_AGENT_URL=https://staging-api.yourdomain.com/chat
SEED_MOCK_AGENT_V1_URL=https://mock1.yourdomain.com/chat
SEED_MOCK_AGENT_V2_URL=https://mock2.yourdomain.com/chat

# Agent authentication
SEED_AGENT_AUTH_TOKEN=your_secure_token

# Agent behavior settings
SEED_AGENT_TIMEOUT=30
SEED_AGENT_MAX_RETRIES=3
SEED_MOCK_AGENT_TIMEOUT=5
SEED_MOCK_AGENT_MAX_RETRIES=1
```

### Development Flags

```bash
# Enable/disable seed data on startup
DEV_SEED_DATA=true

# Use mock providers (no API calls)
DEV_MOCK_TARGET_AGENT=true
DEV_MOCK_JUDGE=true

# Evaluation mode
EVAL_MODE=local  # or 'production'
```

## Feature Flags

Enable or disable specific features:

```bash
# Advanced features
FEATURE_ADVERSARIAL_GENERATOR=true
FEATURE_REDTEAM_AGENT=true
FEATURE_SECONDARY_JUDGE=true
FEATURE_RAG_RETRIEVAL=true
FEATURE_STREAMING_RESPONSES=false
FEATURE_EXPERIMENTAL_UI=false
```

## Red Team Configuration

```bash
# Red team agent settings
REDTEAM_MAX_TURNS=8
REDTEAM_TURN_TIMEOUT_SECONDS=30

# Adversarial generation
ADVERSARIAL_GENERATION_ENABLED=true
ADVERSARIAL_NOVELTY_THRESHOLD=0.75
ADVERSARIAL_BATCH_SIZE=10
ADVERSARIAL_MAX_RETRIES=3
```

## CI/CD Gate Configuration

```bash
# Gate actions for different severity levels
GATE_CRITICAL_ACTION=block
GATE_HIGH_ACTION=block
GATE_MEDIUM_ACTION=warn
GATE_LOW_ACTION=warn
GATE_INCONCLUSIVE_ACTION=fail
GATE_INFRA_FAILURE_ACTION=fail
```

## Monitoring & Observability

### OpenTelemetry

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.yourdomain.com
OTEL_SERVICE_NAME=artef-production
OTEL_TRACES_SAMPLER=parentbased_always_on
OTEL_METRICS_EXPORT_INTERVAL_MS=60000
```

### Prometheus

```bash
PROMETHEUS_METRICS_PORT=9090
```

### Alerting

```bash
# Webhook URLs for alerts
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
ALERT_CRITICAL_WEBHOOK_URL=https://pagerduty.com/YOUR/WEBHOOK/URL
```

## Data Retention

```bash
# Retention periods (days, 0 = keep forever)
TRANSCRIPT_RETENTION_DAYS=365
CRITICAL_FINDINGS_RETENTION_DAYS=0
REPORT_RETENTION_DAYS=365
AUDIT_LOG_RETENTION_DAYS=2555
```

## Cost Management

```bash
COST_PER_RUN_LIMIT_USD=5.0
COST_DAILY_LIMIT_USD=100.0
COST_TRACKING_ENABLED=true
```

## Rate Limiting

```bash
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
```

## Environment-Specific Examples

### Local Development

```bash
# Copy and customize
cp .env.example .env

# Minimal local config uses SQLite and mock providers
DATABASE_URL=sqlite+aiosqlite:///./artef.db
EVAL_MODE=local
DEV_MOCK_JUDGE=true
DEV_MOCK_TARGET_AGENT=true
```

### Production

```bash
# Use real services
DATABASE_URL=postgresql+asyncpg://artef:${DB_PASSWORD}@db.prod:5432/artef
REDIS_URL=redis://redis.prod:6379/0
S3_ENDPOINT_URL=https://s3.amazonaws.com
EVAL_MODE=production

# Secure settings
BLOCK_PRIVATE_IPS=true
BLOCK_LOCALHOST_IN_PRODUCTION=true
DEV_SEED_DATA=false
DEV_MOCK_TARGET_AGENT=false
DEV_MOCK_JUDGE=false

# Real API keys (use secrets manager!)
PRIMARY_JUDGE_API_KEY=${OPENAI_API_KEY}
SECONDARY_JUDGE_API_KEY=${ANTHROPIC_API_KEY}
```

### CI/CD Pipeline

```bash
# Test environment settings
DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/artef_test
EVAL_MODE=production
SEED_EMAIL_DOMAIN=ci.internal

# Faster timeouts for CI
DEFAULT_HTTP_TIMEOUT=10
DEFAULT_AGENT_TIMEOUT=5
SEED_AGENT_TIMEOUT=10
```

## Configuration Best Practices

### Security

1. **Never commit `.env` files** to version control
2. **Use secret managers** in production (AWS Secrets Manager, HashiCorp Vault, etc.)
3. **Rotate credentials** regularly
4. **Use different credentials** per environment
5. **Set minimum SECRET_KEY length** to 32 characters

### Performance

1. **Tune timeouts** based on your infrastructure
2. **Adjust pool sizes** for your traffic patterns
3. **Configure retries** appropriate to your SLAs
4. **Use circuit breakers** to prevent cascading failures

### Development

1. **Use local defaults** for quick setup
2. **Mock external services** during development
3. **Seed test data** only in dev/test environments
4. **Document custom values** for your team

## Verification

Test your configuration:

```bash
# Check all environment variables are loaded
python scripts/verify_environment.py

# Run health checks
curl http://localhost:8000/api/v1/health

# Verify database connection
python scripts/check_database.py
```

## Troubleshooting

### Common Issues

**Problem**: "Database connection failed"
- Check `DATABASE_URL` format
- Verify network connectivity
- Ensure database exists

**Problem**: "API key invalid"
- Verify `*_API_KEY` variables are set
- Check for trailing spaces
- Confirm key is not expired

**Problem**: "Timeout errors"
- Increase relevant timeout values
- Check network latency
- Review circuit breaker settings

## Additional Resources

- [Environment Variables Reference](.env.example) - Complete list
- [Security Best Practices](security.md) - Security guidelines
- [Deployment Guide](deployment.md) - Production deployment
- [Docker Configuration](docker-compose.prod.yml) - Container setup

---

**Last Updated**: January 2026  
**Maintainer**: ARTEF Development Team  
**Status**: ✅ Complete - No hardcoded values
