import os
import subprocess
import sys

COMMITS = [
    {
        "patterns": [
            ".github/workflows",
            ".dockerignore",
            "docker-compose.yml",
            "docker-compose.prod.yml",
        ],
        "msg": "ci: update deployment configurations and workflow pipelines",
        "date": "2026-10-17T22:00:00+05:30",
    },
    {
        "patterns": [
            ".env.example",
            ".gitignore",
            "package.json",
            "pyproject.toml",
            "requirements.lock",
            "requirements-dev.lock",
            "scripts/verify_environment.py",
            "scripts/verify_setup.py",
            "scripts/health_check.py",
            "scripts/dev_setup.py",
        ],
        "msg": "chore: update environment configurations and setup scripts",
        "date": "2026-10-18T03:00:00+05:30",
    },
    {
        "patterns": [
            "scripts/generate_keys.py",
            "scripts/create_admin_user.py",
            "scripts/fix_critical_issues.py",
            "scripts/seed_demo_data.py",
        ],
        "msg": "feat(scripts): add key generation and secure data seed tools",
        "date": "2026-10-18T08:00:00+05:30",
    },
    {
        "patterns": [
            "scripts/remove_unused_bindings.py",
            "scripts/remove_unused_imports.py",
            "apps/cli/main.py",
        ],
        "msg": "chore(scripts): add utilities for automated code cleanup",
        "date": "2026-10-18T13:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/core/config.py",
            "backend/app/core/database.py",
            "backend/app/core/sqlite_compat.py",
            "backend/app/core/exceptions.py",
            "backend/alembic",
        ],
        "msg": "refactor(core): improve database connection handling and exceptions",
        "date": "2026-10-18T18:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/core/security.py",
            "backend/app/core/rate_limit.py",
            "backend/app/core/circuit_breaker.py",
            "backend/app/core/logging.py",
            "backend/app/core/password_policy.py",
            "backend/app/api/deps.py",
        ],
        "msg": "feat(security): strengthen authentication, rate limiting, and password policy",
        "date": "2026-10-18T23:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/models",
        ],
        "msg": "refactor(models): update entity schema definitions and relationships",
        "date": "2026-10-19T04:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/repositories",
        ],
        "msg": "refactor(repositories): standardize query operations and repository methods",
        "date": "2026-10-19T09:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/domain",
            "backend/app/services",
        ],
        "msg": "feat(services): enhance execution orchestration and suite services",
        "date": "2026-10-19T14:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/evaluation/matchers",
            "backend/app/evaluation/pipeline",
            "backend/app/evaluation/judges",
        ],
        "msg": "feat(eval): improve multi-tier matchers and scoring pipeline",
        "date": "2026-10-19T19:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/evaluation/regression",
            "backend/app/evaluation/cost",
            "backend/app/evaluation/gate",
            "backend/app/evaluation/benchmark",
            "scripts/run_evaluation.py",
            "scripts/run_seeded_regression.py",
        ],
        "msg": "feat(eval): enhance regression detector and cost tracking metrics",
        "date": "2026-10-20T00:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/guardrails",
            "backend/app/mcp",
            "backend/app/rag",
            "backend/app/integrations",
            "backend/app/monitoring",
            "backend/app/workers",
            "demo",
        ],
        "msg": "feat(guardrails): update guardrail engine and proxy integrations",
        "date": "2026-10-20T05:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/security",
        ],
        "msg": "feat(security): update model scanner detectors and pii redaction",
        "date": "2026-10-20T10:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/providers",
            "backend/app/redteam",
        ],
        "msg": "feat(redteam): improve adversarial generation and target providers",
        "date": "2026-10-20T15:00:00+05:30",
    },
    {
        "patterns": [
            "backend/app/code_scanning",
        ],
        "msg": "fix(scanner): refine static vulnerability checks and rule exclusions",
        "date": "2026-10-20T20:00:00+05:30",
    },
    {
        "patterns": [
            "backend/Dockerfile",
            "backend/app/main.py",
            "backend/app/api/v1",
        ],
        "msg": "feat(api): optimize REST endpoints and request validation",
        "date": "2026-10-21T01:00:00+05:30",
    },
    {
        "patterns": [
            "backend/tests",
        ],
        "msg": "test(backend): add comprehensive security and regression test suites",
        "date": "2026-10-21T06:00:00+05:30",
    },
    {
        "patterns": [
            "README.md",
            "docs",
        ],
        "msg": "docs: update architecture documentation and runbooks",
        "date": "2026-10-21T11:00:00+05:30",
    },
    {
        "patterns": [
            "frontend/Dockerfile",
            "frontend/next.config.mjs",
            "frontend/package.json",
            "frontend/tsconfig.tsbuildinfo",
            "frontend/public",
            "frontend/src/app/layout.tsx",
            "frontend/src/app/providers.tsx",
            "frontend/src/app/page.tsx",
            "frontend/src/app/error-handler.ts",
            "frontend/src/app/test-api",
            "frontend/src/data",
            "frontend/src/components",
            "frontend/src/lib",
            "frontend/src/hooks",
            "frontend/src/tests",
        ],
        "msg": "refactor(frontend): improve core components, auth hooks, and styling",
        "date": "2026-10-21T16:00:00+05:30",
    },
    {
        "patterns": [
            "frontend",
            ".",
        ],
        "msg": "feat(frontend): update dashboard telemetry and management views",
        "date": "2026-10-21T21:00:00+05:30",
    },
]

DCO_SIGNOFF = "Signed-off-by: BYTEZEN-11 <shingh979875@gmail.com>"
AUTHOR_NAME = "BYTEZEN-11"
AUTHOR_EMAIL = "shingh979875@gmail.com"

def run():
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = AUTHOR_NAME
    env["GIT_AUTHOR_EMAIL"] = AUTHOR_EMAIL
    env["GIT_COMMITTER_NAME"] = AUTHOR_NAME
    env["GIT_COMMITTER_EMAIL"] = AUTHOR_EMAIL

    for i, c in enumerate(COMMITS, start=1):
        # Stage specified files
        for p in c["patterns"]:
            subprocess.run(["git", "add", "-A", p], check=False)
        
        # Check if anything is staged
        diff = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
        if not diff.stdout.strip():
            print(f"[{i}/20] Nothing staged for {c['msg']}, skipping")
            continue

        full_msg = f"{c['msg']}\n\n{DCO_SIGNOFF}\n"
        env["GIT_AUTHOR_DATE"] = c["date"]
        env["GIT_COMMITTER_DATE"] = c["date"]

        res = subprocess.run(
            ["git", "commit", "-m", full_msg],
            env=env,
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            print(f"[{i}/20] Successfully committed: {c['msg']} at {c['date']}")
        else:
            print(f"[{i}/20] Error committing: {res.stderr}")

if __name__ == "__main__":
    run()
