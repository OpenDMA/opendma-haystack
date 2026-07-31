"""Unit tests for pure OpenDMA retriever behavior."""

from __future__ import annotations

import pytest

from opendma_haystack import (
    AlfrescoRetriever,
    DocumentumRetriever,
    FileNetP8Retriever,
    OnBaseRetriever,
    OpenDMARetriever,
)


def test_open_dma_retriever_requires_repository_id() -> None:
    with pytest.raises(ValueError, match="repository_id is required"):
        OpenDMARetriever(
            endpoint="http://localhost:8080/opendma",
            query_language="test:query",
        )


def test_open_dma_retriever_requires_query_language() -> None:
    with pytest.raises(ValueError, match="query_language is required"):
        OpenDMARetriever(
            endpoint="http://localhost:8080/opendma",
            repository_id="repo",
        )


@pytest.mark.parametrize("top_k", [0, -1])
def test_open_dma_retriever_rejects_non_positive_top_k(top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k must be greater than 0"):
        OpenDMARetriever(
            endpoint="http://localhost:8080/opendma",
            repository_id="repo",
            query_language="test:query",
            top_k=top_k,
        )


def test_open_dma_retriever_passes_query_through() -> None:
    retriever = OpenDMARetriever(
        endpoint="http://localhost:8080/opendma",
        repository_id="repo",
        query_language="test:query",
    )

    assert retriever._build_query("raw query") == "raw query"


def test_open_dma_retriever_document_content_from_metadata_prefers_title() -> None:
    retriever = OpenDMARetriever(
        endpoint="http://localhost:8080/opendma",
        repository_id="repo",
        query_language="test:query",
    )

    assert retriever._document_content_from_metadata({"opendma:Title": "Quarterly Roadmap"}) == (
        "Quarterly Roadmap"
    )


def test_open_dma_retriever_document_content_from_metadata_falls_back_to_empty_string() -> None:
    retriever = OpenDMARetriever(
        endpoint="http://localhost:8080/opendma",
        repository_id="repo",
        query_language="test:query",
    )

    assert retriever._document_content_from_metadata({}) == ""


def test_alfresco_retriever_builds_afts_query() -> None:
    retriever = AlfrescoRetriever(
        endpoint="http://localhost:8080/opendma",
        sites=["swsdp"],
    )

    assert retriever.repository_id == "Alfresco"
    assert retriever.query_language == "alfresco:afts"
    assert retriever._build_query("website design") == ('TEXT:"website design" AND (SITE:"swsdp")')


def test_alfresco_retriever_escapes_afts_phrase() -> None:
    retriever = AlfrescoRetriever(endpoint="http://localhost:8080/opendma")

    assert retriever._build_query(r'website "design" \ localisation') == (
        r'TEXT:"website \"design\" \\ localisation"'
    )


def test_alfresco_retriever_adds_multiple_site_filters() -> None:
    retriever = AlfrescoRetriever(
        endpoint="http://localhost:8080/opendma",
        sites=["swsdp", "engineering"],
    )

    assert retriever._build_query("website design") == (
        'TEXT:"website design" AND (SITE:"swsdp" OR SITE:"engineering")'
    )


def test_filenetp8_retriever_builds_sql_query() -> None:
    retriever = FileNetP8Retriever(endpoint="http://localhost:8080/opendma")

    assert retriever.repository_id == "FileNetP8"
    assert retriever.query_language == "filenetp8:sql"
    assert retriever._build_query("foo bar") == (
        "SELECT d.This FROM Document d "
        "INNER JOIN ContentSearch cs ON d.This = cs.QueriedObject "
        "WHERE CONTAINS(d.*, 'foo OR bar')"
    )


def test_filenetp8_retriever_escapes_sql_query() -> None:
    retriever = FileNetP8Retriever(endpoint="http://localhost:8080/opendma")

    assert retriever._build_query("owner's name?") == (
        "SELECT d.This FROM Document d "
        "INNER JOIN ContentSearch cs ON d.This = cs.QueriedObject "
        "WHERE CONTAINS(d.*, 'owner''s OR name\\?')"
    )


def test_documentum_retriever_builds_dql_query() -> None:
    retriever = DocumentumRetriever(endpoint="http://localhost:8080/opendma")

    assert retriever.repository_id == "Documentum"
    assert retriever.query_language == "dctm:dql"
    assert retriever._build_query("foo bar") == (
        "SELECT * FROM dm_document SEARCH DOCUMENT CONTAINS 'foo' OR 'bar'"
    )


def test_documentum_retriever_escapes_dql_query() -> None:
    retriever = DocumentumRetriever(endpoint="http://localhost:8080/opendma")

    assert retriever._build_query("owner's name") == (
        "SELECT * FROM dm_document SEARCH DOCUMENT CONTAINS 'owner''s' OR 'name'"
    )


def test_onbase_retriever_builds_document_query() -> None:
    retriever = OnBaseRetriever(endpoint="http://localhost:8080/opendma")

    assert retriever.repository_id == "OnBase"
    assert retriever.query_language == "onbase:DocumentQuery"
    assert "<FullTextSearchString>foo OR bar</FullTextSearchString>" in retriever._build_query(
        "foo bar"
    )


def test_onbase_retriever_escapes_xml_query() -> None:
    retriever = OnBaseRetriever(endpoint="http://localhost:8080/opendma")
    query = retriever._build_query("<test foo bar")

    assert "<FullTextSearchString>&lt;test OR foo OR bar</FullTextSearchString>" in query
    assert "<TextSearchType>2</TextSearchType>" in query


@pytest.mark.parametrize(
    "retriever",
    [
        AlfrescoRetriever(endpoint="http://localhost:8080/opendma"),
        FileNetP8Retriever(endpoint="http://localhost:8080/opendma"),
        DocumentumRetriever(endpoint="http://localhost:8080/opendma"),
        OnBaseRetriever(endpoint="http://localhost:8080/opendma"),
    ],
)
def test_system_specific_retrievers_reject_empty_query(
    retriever: AlfrescoRetriever | FileNetP8Retriever | DocumentumRetriever | OnBaseRetriever,
) -> None:
    with pytest.raises(ValueError, match="query must not be empty"):
        retriever._build_query("  \n\t  ")
