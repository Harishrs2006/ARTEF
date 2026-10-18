"""Generate the RS256 key pair that signs the access and refresh tokens.

The key files are written to ``backend/app/core/keys`` by default. They are
git-ignored, so every deployment and every CI run has to generate its own
pair. A key that is shared between environments allows a token minted in one
environment to be replayed in another.

Usage:
    python scripts/generate_keys.py [--output-dir PATH] [--force]
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "backend" / "app" / "core" / "keys"


def generate_key_pair(output_dir: Path, force: bool) -> int:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        print(
            "The 'cryptography' package is required to generate a key pair.\n"
            "Install it with: pip install cryptography",
            file=sys.stderr,
        )
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    private_path = output_dir / "private_key.pem"
    public_path = output_dir / "public_key.pem"

    if not force and private_path.exists() and public_path.exists():
        print(f"Key pair already exists in {output_dir}. Use --force to replace it.")
        return 0

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)

    # The private key must not be readable by other users.
    private_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    public_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

    print(f"Wrote {private_path}")
    print(f"Wrote {public_path}")
    print(
        "\nSet these in the environment (or .env):\n"
        f"  JWT_PRIVATE_KEY_PATH={private_path}\n"
        f"  JWT_PUBLIC_KEY_PATH={public_path}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="The directory the key pair is written to.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing key pair.",
    )
    arguments = parser.parse_args()
    return generate_key_pair(arguments.output_dir, arguments.force)


if __name__ == "__main__":
    sys.exit(main())
