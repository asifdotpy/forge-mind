"""Regression tests for secret-safe token handling in the Notion sync script.

These tests guard against:
  1. The historically leaked Notion integration token ever being re-committed.
     The leak is only referenced by its SHA-256 digest — never in cleartext —
     so this test file itself can never be flagged as containing the secret.
  2. The sync script silently falling back to a hardcoded token.
  3. The fail-fast behaviour when NOTION_TOKEN is absent from the environment.
"""
import hashlib
import importlib.util
import re
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_notion_brain.py"

# SHA-256 of the historical leaked token (removed in 2026-08).
# Storing the digest (one-way) lets us detect the secret without re-embedding it.
LEAKED_TOKEN_SHA256 = "7b24cc06d9b7def4fe99e1cde0d232f3c8b79e7593f05d227a5d6edad701a9bd"

_NTN_TOKEN_RE = re.compile(r"ntn_[A-Za-z0-9_\-]+")


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _leaked_tokens_in(text: str):
    """Return any ntn_-prefixed tokens in text whose digest matches the leak."""
    return [tok for tok in _NTN_TOKEN_RE.findall(text) if _sha256(tok) == LEAKED_TOKEN_SHA256]


def _load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_notion_brain", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_leaked_token_is_not_in_sync_source():
    src = SCRIPT_PATH.read_text()
    assert not _leaked_tokens_in(src), "leaked Notion token must never return"


def test_no_committed_token_fallback_in_sync_source():
    src = SCRIPT_PATH.read_text()
    # There must be no hardcoded credential fallback inside get_notion_token().
    assert "DEFAULT_TOKEN" not in src


def test_get_notion_token_fails_fast_without_env(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    # Point the auto-loader at a non-existent env file so the real (local,
    # user-owned) .env cannot satisfy the lookup in this test.
    monkeypatch.setenv("NOTION_ENV_FILE", str(Path(__file__).with_name("does_not_exist.env")))
    mod = _load_sync_module()
    with pytest.raises(SystemExit):
        mod.get_notion_token()


def test_get_notion_token_loads_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    env_file = tmp_path / "test.env"
    env_file.write_text('NOTION_TOKEN="ntn_dummy_from_dotenv"\n')
    monkeypatch.setenv("NOTION_ENV_FILE", str(env_file))
    mod = _load_sync_module()
    assert mod.get_notion_token() == "ntn_dummy_from_dotenv"


def test_get_notion_token_env_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("NOTION_TOKEN", "ntn_env_wins")
    env_file = tmp_path / "test.env"
    env_file.write_text("NOTION_TOKEN=ntn_dummy_from_dotenv\n")
    monkeypatch.setenv("NOTION_ENV_FILE", str(env_file))
    mod = _load_sync_module()
    assert mod.get_notion_token() == "ntn_env_wins"


def test_get_notion_token_reads_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "ntn_test_dummy_token")
    mod = _load_sync_module()
    assert mod.get_notion_token() == "ntn_test_dummy_token"