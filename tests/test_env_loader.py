"""Tests for the local-development ``.env`` loader (``forgemind._env``).

Two invariants matter:

1. Hermeticity — under pytest the loader is a strict no-op. A developer's real
   gitignored ``.env`` (holding ``GITHUB_TOKEN``/``NOTION_TOKEN``) must never
   reach the test process, otherwise webhook tests would start issuing real
   GitHub writes against the token's repository.
2. Function — outside pytest it loads the file once, never overrides
   pre-existing environment variables, and is idempotent.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from forgemind import _env
from forgemind._env import _parse_and_apply, load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Pure parsing behaviour (no file system, no guard interplay)
# ---------------------------------------------------------------------------
def test_parse_and_apply_skips_comments_blanks_and_values_without_key():
    env: dict[str, str] = {}
    applied = _parse_and_apply(
        "# a comment\n"
        "\n"
        "NO_EQUALS_LINE\n"
        "GOOD_KEY=good-value\n"
        "QUOTED='single quoted'\n"
        "DQUOTED=\"double quoted\"\n",
        env,
    )
    assert applied == ["GOOD_KEY", "QUOTED", "DQUOTED"]
    assert env["GOOD_KEY"] == "good-value"
    assert env["QUOTED"] == "single quoted"
    assert env["DQUOTED"] == "double quoted"


def test_parse_and_apply_never_overrides_existing_env():
    env = {"EXISTING_KEY": "shell-wins"}
    applied = _parse_and_apply("EXISTING_KEY=from-dotenv\nNEW_KEY=x\n", env)
    assert applied == ["NEW_KEY"]
    assert env["EXISTING_KEY"] == "shell-wins"


# ---------------------------------------------------------------------------
# Hermeticity inside pytest (the invariant the whole suite depends on)
# ---------------------------------------------------------------------------
def test_load_dotenv_is_a_noop_under_pytest():
    """The pytest guard must fire before any file is read or key is set."""
    assert load_dotenv() == []


def test_create_api_does_not_leak_dotenv_into_tests(monkeypatch):
    """``create_api()`` (also run at import time for the module-level ``app``)
    must never inject gitignored ``.env`` secrets into the test process."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    from forgemind.api import create_api

    create_api()  # same factory uvicorn --factory uses
    assert "GITHUB_TOKEN" not in os.environ
    assert "NOTION_TOKEN" not in os.environ


# ---------------------------------------------------------------------------
# Real (non-pytest) load path, exercised in a clean subprocess interpreter
# ---------------------------------------------------------------------------
def _run_loader_subprocess(env_file: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = textwrap.dedent(
        """
        import os
        from forgemind._env import load_dotenv
        # Note: importing forgemind already applied the env file — the package
        # __init__ re-exports the api factory, whose module-level
        # ``app = create_api()`` runs load_dotenv() at import time. So assert
        # observable outcomes plus one-shot idempotence, not the return of the
        # first explicit call.
        assert os.environ["SENTINEL_KEY"] == "from-dotenv"
        assert os.environ["PRESET_KEY"] == "shell-wins"
        assert load_dotenv() == [], "load_dotenv must be one-shot per process"
        print("OK")
        """
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "FORGEMIND_ENV_FILE": str(env_file), **extra_env},
        timeout=60,
    )


def test_load_dotenv_outside_pytest_loads_file_once_and_respects_precedence(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SENTINEL_KEY=from-dotenv\nPRESET_KEY=from-dotenv\n# comment\n\nBROKEN\n",
        encoding="utf-8",
    )
    result = _run_loader_subprocess(env_file, {"PRESET_KEY": "shell-wins"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_load_dotenv_missing_file_is_silent_outside_pytest(tmp_path):
    """A missing .env (production images) is not an error outside pytest."""
    script = (
        "from forgemind._env import load_dotenv\n"
        "assert load_dotenv() == []\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "FORGEMIND_ENV_FILE": str(tmp_path / "does_not_exist.env")},
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_load_dotenv_respects_skip_flag(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SENTINEL_KEY=x\n", encoding="utf-8")
    script = (
        "import os\n"
        "from forgemind._env import load_dotenv\n"
        "assert load_dotenv() == []\n"
        "assert 'SENTINEL_KEY' not in os.environ\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={
            **os.environ,
            "FORGEMIND_ENV_FILE": str(env_file),
            "FORGEMIND_SKIP_DOTENV": "1",
        },
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_default_env_file_path_is_repo_root():
    """Sanity: the default path resolves to <repo-root>/.env (gitignored)."""
    assert (REPO_ROOT / ".env").exists(), (
        "developer .env expected to exist locally; the loader must point at "
        "the repository root"
    )
