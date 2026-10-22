"""Security regression tests for the vulnerabilities found during the audit."""

import os
import pickle
from pathlib import Path

import pytest

from app.security.model_scanner.detectors import PickleDetector
from app.security.model_scanner.report import SeverityLevel


class _Exploit:
    """A payload whose ``__reduce__`` would execute code if it were unpickled."""

    def __reduce__(self):
        return (_mark_executed, ("pwned",))


def _mark_executed(_arg: str) -> int:
    """A module-level callable so the payload can be pickled.

    If the scanner ever calls `pickle.load` on the file, this runs and the
    marker file appears.
    """
    Path(os.environ.get("ARTEF_PICKLE_MARKER", "pwned.txt")).write_text("executed")
    return 0


class TestPickleScannerDoesNotExecutePayloads:
    """The scanner must never deserialise the file it inspects.

    `pickle.load` executes arbitrary code, so a security scanner that
    unpickles the files it scans is itself a remote-code-execution vector.
    """

    @pytest.mark.asyncio
    async def test_malicious_pickle_is_reported_not_executed(self, tmp_path: Path, monkeypatch):
        marker = tmp_path / "pwned.txt"
        monkeypatch.setenv("ARTEF_PICKLE_MARKER", str(marker))

        payload = tmp_path / "evil.pkl"
        with open(payload, "wb") as handle:
            pickle.dump(_Exploit(), handle)

        detector = PickleDetector()
        findings = await detector.scan(tmp_path)

        assert not marker.exists(), "the scanner executed the pickle payload"
        assert findings, "the malicious pickle was not reported"
        assert any(f.severity == SeverityLevel.CRITICAL for f in findings)
        assert any("REDUCE" in f.description or "GLOBAL" in f.description for f in findings)

    @pytest.mark.asyncio
    async def test_benign_pickle_produces_no_critical_findings(self, tmp_path: Path):
        payload = tmp_path / "ok.pkl"
        with open(payload, "wb") as handle:
            pickle.dump({"a": 1, "b": [2, 3]}, handle)

        detector = PickleDetector()
        findings = await detector.scan(tmp_path)

        assert not any(f.severity == SeverityLevel.CRITICAL for f in findings)


class TestPasswordHashing:
    """Passwords longer than bcrypt's 72-byte limit must keep their entropy."""

    def test_long_passwords_are_not_truncated(self):
        from app.core.security import get_password_hash, verify_password

        base = "A" * 72
        password = base + "TAIL"

        hashed = get_password_hash(password)
        assert verify_password(password, hashed)

        # A password sharing the first 72 bytes must NOT verify.
        assert not verify_password(base + "OTHER", hashed)

    def test_unicode_passwords_round_trip(self):
        from app.core.security import get_password_hash, verify_password

        password = "pässwörd-🔐-with-emoji"  # nosec: test fixture
        hashed = get_password_hash(password)
        assert verify_password(password, hashed)
        assert not verify_password("password", hashed)

    def test_legacy_hashes_are_still_accepted(self):
        """Hashes created before the SHA-256 pre-hashing must keep working."""
        import bcrypt

        from app.core.security import needs_rehash, verify_password

        legacy_hash = bcrypt.hashpw(b"legacy-password", bcrypt.gensalt(rounds=4)).decode()
        assert verify_password("legacy-password", legacy_hash)
        assert needs_rehash("legacy-password", legacy_hash)

    def test_malformed_hash_does_not_raise(self):
        from app.core.security import verify_password

        assert verify_password("anything", "") is False
        assert verify_password("anything", "not-a-bcrypt-hash") is False


class TestNoGlobalErrorSuppression:
    """The frontend must not silence genuine runtime errors."""

    def test_error_handler_does_not_override_console_error(self):
        from pathlib import Path as _Path

        source = (
            _Path(__file__).resolve().parents[3]
            / "frontend"
            / "src"
            / "app"
            / "error-handler.ts"
        ).read_text(encoding="utf-8")
        # The handler must not replace console.error, and must not list
        # "Cannot read properties of undefined" as a suppression pattern.
        assert "console.error = " not in source
        assert "'Cannot read properties of undefined'" not in source
        assert '"Cannot read properties of undefined"' not in source

    def test_layout_does_not_inject_a_suppression_script(self):
        from pathlib import Path as _Path

        source = (
            _Path(__file__).resolve().parents[3]
            / "frontend"
            / "src"
            / "app"
            / "layout.tsx"
        ).read_text(encoding="utf-8")
        assert "suppress-web-vitals" not in source
        assert "reportAllChanges" not in source

    def test_suppression_script_is_removed(self):
        from pathlib import Path as _Path

        assert not (
            _Path(__file__).resolve().parents[3]
            / "frontend"
            / "public"
            / "suppress-web-vitals.js"
        ).exists()


class TestNoPiiExfiltration:
    """The user's email address must not be sent to a third-party service."""

    def test_header_does_not_use_a_remote_avatar(self):
        from pathlib import Path as _Path

        source = (
            _Path(__file__).resolve().parents[3]
            / "frontend"
            / "src"
            / "components"
            / "ui"
            / "header.tsx"
        ).read_text(encoding="utf-8")
        assert "dicebear.com" not in source


class TestRateLimiterAwaitsItsCheck:
    """The rate-limit decorator must await the coroutine it calls."""

    def test_decorator_awaits_the_check(self):
        from pathlib import Path as _Path

        source = (
            _Path(__file__).resolve().parents[3]
            / "backend"
            / "app"
            / "core"
            / "rate_limit.py"
        ).read_text(encoding="utf-8")
        assert "await rate_limiter.check_rate_limit(" in source
