"""The secret guard must actually catch secrets, and must not echo them.

Every case below writes a file that looks like a real leak, runs the guard the way CI
runs it, and asserts the outcome. A guard that cannot fail is decoration.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "check_secrets.py"

FAKE_SECRETS = {
    "private_key.pem": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n",
    "aws.txt": "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n",
    "github.txt": "token: ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8\n",
    "openai.txt": "OPENAI_KEY=sk-" + "A" * 32 + "\n",
    "supabase.txt": "key = eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.c2lnbmF0dXJlLXZhbHVl\n",
    "accounts.json": '{"REDACTED": {"login": "REDACTED", "password": "S3cr3t-Passw0rd-2026"}}\n',
    "path.sh": "VENV=/home/someuser/.local/share/venv\n",
}


def run_guard(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD), "--path", str(target)],
        capture_output=True, text=True, check=False,
    )


def test_guard_accepts_a_clean_tree(tmp_path):
    (tmp_path / "README.md").write_text("# Clean project\n")
    (tmp_path / "app.py").write_text("def main():\n    return 0\n")

    result = run_guard(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "no secrets found" in result.stdout


def test_guard_flags_every_secret_class(tmp_path):
    for name, content in FAKE_SECRETS.items():
        (tmp_path / name).write_text(content)

    result = run_guard(tmp_path)

    assert result.returncode == 1, result.stdout
    for name, severity in [
        ("private-key", "critical"),
        ("aws-access-key", "critical"),
        ("github-token", "critical"),
        ("openai-key", "critical"),
        ("jwt", "high"),
        ("broker-account", "high"),
        ("personal-path", "low"),
    ]:
        assert name in result.stderr, f"{name} not reported"
        assert f"[{severity}]" in result.stderr, f"{name} severity missing"


def test_guard_does_not_print_the_secret(tmp_path):
    secret = "ghp_" + "Z" * 36
    (tmp_path / "leak.txt").write_text(f"token: {secret}\n")

    result = run_guard(tmp_path)

    assert result.returncode == 1
    assert secret not in result.stderr, "the report leaked the credential it flagged"
    assert "ghp_ZZ" in result.stderr, "the masked prefix should still identify the value"


def test_guard_skips_binary_assets(tmp_path):
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"AKIAIOSFODNN7EXAMPLE" * 4)

    result = run_guard(tmp_path)

    assert result.returncode == 0, result.stderr
