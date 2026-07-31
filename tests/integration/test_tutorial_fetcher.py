"""Integration tests for OpenDMAFetcher."""

from __future__ import annotations

import pytest
from haystack.dataclasses import ByteStream

from opendma_haystack import OpenDMAFetcher


@pytest.mark.integration
def test_fetcher_fetches_document_content(tutorial_endpoint: str) -> None:
    fetcher = OpenDMAFetcher(
        endpoint=tutorial_endpoint,
        username="ignored",
        password="ignored",
        repository_id="sample-repo",
    )

    result = fetcher.run(targets=["hello-world-document"])

    assert result["streams"]
    assert isinstance(result["streams"][0], ByteStream)
    assert result["streams"][0].meta["repository_id"] == "sample-repo"
    assert result["streams"][0].meta["opendma_id"] == "hello-world-document"


@pytest.mark.integration
def test_fetcher_fetches_folder_documents(tutorial_endpoint: str) -> None:
    fetcher = OpenDMAFetcher(
        endpoint=tutorial_endpoint,
        username="ignored",
        password="ignored",
        repository_id="sample-repo",
    )

    result = fetcher.run(folder_ids=["sample-folder-root"])

    assert result["streams"]
    assert all(stream.meta["repository_id"] == "sample-repo" for stream in result["streams"])
