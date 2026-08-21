"""Unit tests for pure OpenDMA toolset behavior."""

from __future__ import annotations

import pytest
from haystack.dataclasses import ByteStream

from opendma_haystack import (
    AlfrescoToolset,
    DocumentumToolset,
    FileNetP8Toolset,
    OnBaseToolset,
    OpenDMAToolset,
)


def test_open_dma_toolset_requires_repository_id() -> None:
    with pytest.raises(ValueError, match="repository_id is required"):
        OpenDMAToolset(endpoint="http://localhost:8080/opendma")


def test_open_dma_toolset_exposes_core_tools() -> None:
    toolset = OpenDMAToolset(endpoint="http://localhost:8080/opendma", repository_id="repo")

    assert [tool.name for tool in toolset.get_tools()] == [
        "opendma_get_metadata",
        "opendma_list_children",
        "opendma_read_text",
        "opendma_describe_class",
    ]
    assert [tool.name for tool in toolset.tools] == [
        "opendma_get_metadata",
        "opendma_list_children",
        "opendma_read_text",
        "opendma_describe_class",
    ]


def test_open_dma_tool_returns_error_for_missing_required_parameter() -> None:
    toolset = OpenDMAToolset(endpoint="http://localhost:8080/opendma", repository_id="repo")
    metadata_tool = next(tool for tool in toolset.get_tools() if tool.name == "opendma_get_metadata")

    result = metadata_tool.invoke()

    assert result == {
        "error": True,
        "tool": "opendma_get_metadata",
        "error_type": "ToolInputError",
        "message": "Missing required string parameter(s): object_id.",
    }


def test_open_dma_tool_returns_error_for_unexpected_parameter() -> None:
    toolset = OpenDMAToolset(endpoint="http://localhost:8080/opendma", repository_id="repo")
    metadata_tool = next(tool for tool in toolset.get_tools() if tool.name == "opendma_get_metadata")

    result = metadata_tool.invoke(document_id="doc1")

    assert result == {
        "error": True,
        "tool": "opendma_get_metadata",
        "error_type": "ToolInputError",
        "message": "Unexpected parameter(s): document_id. Allowed parameters: object_id.",
    }


def test_open_dma_list_children_tool_returns_error_when_includes_are_false() -> None:
    toolset = OpenDMAToolset(endpoint="http://localhost:8080/opendma", repository_id="repo")
    list_tool = next(tool for tool in toolset.get_tools() if tool.name == "opendma_list_children")

    result = list_tool.invoke(object_id="folder1", include_folders=False, include_files=False)

    assert result == {
        "error": True,
        "tool": "opendma_list_children",
        "error_type": "ValueError",
        "message": "include_folders and include_files cannot both be false",
    }


def test_alfresco_toolset_exposes_search_and_site_tools() -> None:
    toolset = AlfrescoToolset(endpoint="http://localhost:8080/opendma")

    assert [tool.name for tool in toolset.get_tools()] == [
        "opendma_get_metadata",
        "opendma_list_children",
        "opendma_read_text",
        "opendma_describe_class",
        "opendma_search",
        "alfresco_list_sites",
    ]


def test_alfresco_list_sites_tool_returns_error_for_unexpected_parameter() -> None:
    toolset = AlfrescoToolset(endpoint="http://localhost:8080/opendma")
    list_sites_tool = next(tool for tool in toolset.get_tools() if tool.name == "alfresco_list_sites")

    result = list_sites_tool.invoke(site="swsdp")

    assert result == {
        "error": True,
        "tool": "alfresco_list_sites",
        "error_type": "ToolInputError",
        "message": "Unexpected parameter(s): site. Allowed parameters: none.",
    }


def test_open_dma_toolset_encodes_and_decodes_offset_tokens() -> None:
    toolset = OpenDMAToolset(endpoint="http://localhost:8080/opendma", repository_id="repo")
    token = toolset._encode_offset_token(12)

    assert toolset._decode_offset_token(token) == 12


def test_open_dma_toolset_rejects_invalid_offset_token() -> None:
    toolset = OpenDMAToolset(endpoint="http://localhost:8080/opendma", repository_id="repo")

    with pytest.raises(ValueError, match="Invalid continuation token"):
        toolset._decode_offset_token("not-a-token")


def test_open_dma_toolset_default_text_extractor_reads_text_streams() -> None:
    toolset = OpenDMAToolset(endpoint="http://localhost:8080/opendma", repository_id="repo")
    documents = toolset._default_text_extractor(
        [
            ByteStream(
                data=b"Hello",
                mime_type="text/plain; charset=utf-8",
                meta={"opendma_id": "doc1"},
            ),
            ByteStream(data=b"%PDF", mime_type="application/pdf", meta={"opendma_id": "doc2"}),
        ]
    )

    assert len(documents) == 1
    assert documents[0].content == "Hello"
    assert documents[0].meta["opendma_id"] == "doc1"


def test_open_dma_toolset_splits_text_documents() -> None:
    toolset = OpenDMAToolset(
        endpoint="http://localhost:8080/opendma",
        repository_id="repo",
        read_text_chunk_chars=5,
        read_text_chunk_overlap=1,
    )
    documents = toolset._default_text_extractor(
        [ByteStream(data=b"abcdefghij", mime_type="text/plain", meta={})]
    )

    chunks = toolset._split_text_documents(documents)

    assert [chunk.content for chunk in chunks] == ["abcde", "efghi", "ij"]


def test_alfresco_toolset_builds_afts_query() -> None:
    toolset = AlfrescoToolset(endpoint="http://localhost:8080/opendma")

    assert toolset._build_search_query(
        full_text="website design",
        in_folder="node:abc",
        include_subfolder_in_folder=True,
    ) == 'TEXT:"website design" AND ANCESTOR:"workspace://SpacesStore/abc"'


def test_alfresco_toolset_escapes_afts_query() -> None:
    toolset = AlfrescoToolset(endpoint="http://localhost:8080/opendma")

    assert toolset._build_search_query(
        full_text=r'website "design" \ localisation',
        in_folder=None,
        include_subfolder_in_folder=None,
    ) == r'TEXT:"website \"design\" \\ localisation"'


def test_filenetp8_toolset_builds_sql_query() -> None:
    toolset = FileNetP8Toolset(endpoint="http://localhost:8080/opendma")

    assert toolset._build_search_query(
        full_text="owner's name?",
        in_folder="objectstore:folder:{123}",
        include_subfolder_in_folder=False,
    ) == (
        "SELECT d.This FROM Document d "
        "INNER JOIN ContentSearch cs ON d.This = cs.QueriedObject "
        "WHERE CONTAINS(d.*, 'owner''s OR name\\?') AND d.This INFOLDER {123}"
    )


def test_documentum_toolset_builds_dql_query() -> None:
    toolset = DocumentumToolset(endpoint="http://localhost:8080/opendma")

    assert toolset._build_search_query(
        full_text="owner's name",
        in_folder="folder-id",
        include_subfolder_in_folder=True,
    ) == (
        "SELECT * FROM dm_document SEARCH DOCUMENT CONTAINS 'owner''s' OR 'name' "
        "WHERE FOLDER(ID('folder-id'), DESCEND)"
    )


def test_onbase_toolset_builds_document_query() -> None:
    toolset = OnBaseToolset(endpoint="http://localhost:8080/opendma")
    query = toolset._build_search_query(
        full_text="<test foo",
        in_folder=None,
        include_subfolder_in_folder=None,
    )

    assert "<FullTextSearchString>&lt;test OR foo</FullTextSearchString>" in query
    assert "<TextSearchType>2</TextSearchType>" in query


def test_onbase_toolset_search_schema_does_not_include_folder_filters() -> None:
    toolset = OnBaseToolset(endpoint="http://localhost:8080/opendma")
    search_tool = next(tool for tool in toolset.get_tools() if tool.name == "opendma_search")

    assert "in_folder" not in search_tool.parameters["properties"]
    assert "include_subfolder_in_folder" not in search_tool.parameters["properties"]
