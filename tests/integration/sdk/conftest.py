"""
Shared fixtures and setup for OpenRAG SDK integration tests.

All tests in this directory require a running OpenRAG instance.
Set OPENRAG_URL (default: http://localhost:3000) before running.
"""

import os
import uuid
from pathlib import Path

import httpx
import pytest

_cached_api_key: str | None = None
_base_url = os.environ.get("OPENRAG_URL", "http://localhost:3000")
_onboarding_done = False


@pytest.fixture(scope="session", autouse=True)
def ensure_onboarding():
    """Ensure the OpenRAG instance is onboarded before running tests."""
    global _onboarding_done
    if _onboarding_done:
        return

    onboarding_payload = {
        "llm_provider": "openai",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "llm_model": "gpt-4o-mini",
    }

    try:
        response = httpx.post(
            f"{_base_url}/api/onboarding",
            json=onboarding_payload,
            timeout=30.0,
        )
        if response.status_code in (200, 204):
            print("[SDK Tests] Onboarding completed successfully")
        else:
            print(f"[SDK Tests] Onboarding returned {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"[SDK Tests] Onboarding request failed: {e}")

    _onboarding_done = True


def get_api_key() -> str:
    """Get or create an API key for testing (cached for the session)."""
    global _cached_api_key
    if _cached_api_key is None:
        response = httpx.post(
            f"{_base_url}/api/keys",
            json={"name": "SDK Integration Test"},
            timeout=30.0,
        )
        if response.status_code == 401:
            pytest.skip("Cannot create API key - authentication required")
        assert response.status_code == 200, f"Failed to create API key: {response.text}"
        _cached_api_key = response.json()["api_key"]
    return _cached_api_key


@pytest.fixture
def client():
    """OpenRAG client authenticated with a valid test API key."""
    from openrag_sdk import OpenRAGClient

    return OpenRAGClient(api_key=get_api_key(), base_url=_base_url)


@pytest.fixture
def base_url() -> str:
    """The base URL of the running OpenRAG instance."""
    return _base_url


@pytest.fixture
def test_file(tmp_path) -> Path:
    """A uniquely-named markdown file ready for ingestion."""
    file_path = tmp_path / f"sdk_test_doc_{uuid.uuid4().hex[:8]}.md"
    file_path.write_text(
        f"# SDK Integration Test Document\n\n"
        f"ID: {uuid.uuid4()}\n\n"
        "This document tests the OpenRAG Python SDK.\n\n"
        "It contains unique content about purple elephants dancing.\n"
    )
    return file_path
