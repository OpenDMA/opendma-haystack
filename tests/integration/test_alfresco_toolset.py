"""Integration tests for the Alfresco OpenDMA toolset."""

from __future__ import annotations

import pytest

from opendma_haystack import AlfrescoToolset


@pytest.mark.integration
def test_list_sites_returns_consecutive_pages(alfresco_endpoint: str) -> None:
    toolset = AlfrescoToolset(
        endpoint=alfresco_endpoint,
        username="admin",
        password="admin",
        site_page_size=1,
    )
    list_sites = next(tool for tool in toolset.get_tools() if tool.name == "alfresco_list_sites")

    first_page = list_sites.invoke()
    assert len(first_page["sites"]) == 1
    assert first_page["has_more"] is True
    assert first_page["continuation_token"] is not None

    second_page = list_sites.invoke(continuation_token=first_page["continuation_token"])

    assert len(second_page["sites"]) == 1
    assert first_page["sites"][0]["root_folder_id"] != second_page["sites"][0]["root_folder_id"]
