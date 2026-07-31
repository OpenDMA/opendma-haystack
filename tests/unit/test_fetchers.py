"""Unit tests for pure OpenDMAFetcher behavior."""

from __future__ import annotations

import pytest

from opendma_haystack import AlfrescoFetcher, OpenDMAFetcher


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


def test_alfresco_fetcher_defaults_repository_id() -> None:
    fetcher = AlfrescoFetcher(
        endpoint="http://localhost:8080/opendma",
        sites=["swsdp"],
    )

    assert fetcher.repository_id == "Alfresco"
    assert fetcher.sites == ["swsdp"]


def test_alfresco_fetcher_requires_source() -> None:
    fetcher = AlfrescoFetcher(endpoint="http://localhost:8080/opendma")

    with pytest.raises(ValueError, match="Must provide at least one"):
        fetcher.run()


@pytest.mark.parametrize("character", ['"', "*", "\\", ">", "<", "?", "/", ":", "|"])
def test_alfresco_fetcher_rejects_invalid_constructor_site_names(character: str) -> None:
    with pytest.raises(ValueError, match="Alfresco site names cannot contain"):
        AlfrescoFetcher(
            endpoint="http://localhost:8080/opendma",
            sites=[f"site{character}name"],
        )


def test_alfresco_fetcher_rejects_invalid_run_site_names() -> None:
    fetcher = AlfrescoFetcher(endpoint="http://localhost:8080/opendma")

    with pytest.raises(ValueError, match="Alfresco site names cannot end with a period"):
        fetcher.run(sites=["site."])
