"""Fixtures for integration tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def tutorial_endpoint() -> str:
    """Return the configured tutorial repository endpoint or skip."""
    endpoint = os.environ.get("OPENDMA_TUTORIAL_ENDPOINT")
    if not endpoint:
        pytest.skip("OPENDMA_TUTORIAL_ENDPOINT is not set")
    return endpoint
