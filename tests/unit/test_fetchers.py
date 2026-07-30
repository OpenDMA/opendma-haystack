"""Unit tests for pure OpenDMAFetcher behavior."""

from __future__ import annotations

import pytest

from opendma_haystack import OpenDMAFetcher


def test_init_stores_options() -> None:
    fetcher = OpenDMAFetcher(
        endpoint="http://localhost:8080/opendma",
        username="admin",
        password="admin",
        repository_id="repo",
        include_no_content=True,
        raise_on_error=False,
    )

    assert fetcher.endpoint == "http://localhost:8080/opendma"
    assert fetcher.repository_id == "repo"
    assert fetcher.include_no_content is True
    assert fetcher.raise_on_error is False


def test_run_requires_targets_or_folder_ids() -> None:
    fetcher = OpenDMAFetcher(endpoint="http://localhost:8080/opendma", repository_id="repo")

    with pytest.raises(ValueError, match="Must provide at least one"):
        fetcher.run()


def test_run_requires_repository_id_for_folder_ids() -> None:
    fetcher = OpenDMAFetcher(endpoint="http://localhost:8080/opendma")

    with pytest.raises(ValueError, match="repository_id is required"):
        fetcher.run(folder_ids=["folder"])
