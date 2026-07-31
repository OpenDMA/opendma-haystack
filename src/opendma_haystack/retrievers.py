"""Retrievers for OpenDMA integration with Haystack."""

from __future__ import annotations

import re
from html import escape as escape_xml_text
from typing import Any

from haystack import Document, component
from opendma.api import OdmaDocument, OdmaId, OdmaQName
from opendma.remote import connect

from opendma_haystack._common import (
    MetadataFn,
    extract_metadata,
    handle_error,
    validate_alfresco_site_name,
)


def _split_words(query: str) -> list[str]:
    """Split a natural language query into non-empty words."""
    return re.sub(r"\s+", " ", query).strip().split()


TITLE_METADATA_KEYS = (
    "opendma:Title",
    "opendma:Name",
    "cm:name",
    "cm:title",
)


@component
class OpenDMARetriever:
    """Retrieve metadata-only Haystack Documents from OpenDMA search results."""

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str | None = None,
        query_language: str | None = None,
        top_k: int | None = None,
        raise_on_error: bool = True,
        warn_on_error: bool = True,
        metadata_fn: MetadataFn | None = None,
    ) -> None:
        """Initialize the OpenDMA retriever."""
        if not repository_id:
            raise ValueError("repository_id is required")
        if not query_language:
            raise ValueError("query_language is required")
        if top_k is not None and top_k <= 0:
            raise ValueError("top_k must be greater than 0")

        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.repository_id = repository_id
        self.query_language = query_language
        self.top_k = top_k
        self.raise_on_error = raise_on_error
        self.warn_on_error = warn_on_error
        self.metadata_fn = metadata_fn

    def _build_query(self, query: str) -> str:
        """Build the OpenDMA query from the retriever input."""
        return query

    def _document_content_from_metadata(self, metadata: dict[str, Any]) -> str:
        """Choose title-like content for metadata-only Haystack retriever documents."""
        for key in TITLE_METADATA_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
        value = metadata.get("file_name")
        if isinstance(value, str) and value.strip():
            return value
        return ""

    def _document_from_opendma_document(self, document: OdmaDocument) -> Document:
        metadata = extract_metadata(
            document=document,
            repository_id=self.repository_id,
            metadata_fn=self.metadata_fn,
        )
        return Document(
            id=f"{self.repository_id}:{metadata['opendma_id']}",
            content=self._document_content_from_metadata(metadata),
            meta=metadata,
        )

    @component.output_types(documents=list[Document])
    def run(self, query: str) -> dict[str, list[Document]]:
        """Search OpenDMA and return metadata-only Haystack Documents."""
        built_query = self._build_query(query)
        session = connect(
            endpoint=self.endpoint,
            username=self.username,
            password=self.password,
        )
        documents: list[Document] = []

        try:
            search_result = session.search(
                OdmaId(self.repository_id),
                OdmaQName.from_string(self.query_language),
                built_query,
            )

            for obj in search_result.get_objects():
                if not isinstance(obj, OdmaDocument):
                    continue
                try:
                    documents.append(self._document_from_opendma_document(obj))
                except Exception as exc:
                    handle_error(
                        f"OpenDMARetriever failed to map document {obj.get_id()}",
                        exc,
                        self.raise_on_error,
                        self.warn_on_error,
                    )
                    continue

                if self.top_k is not None and len(documents) >= self.top_k:
                    break
        finally:
            session.close()

        return {"documents": documents}


class AlfrescoRetriever(OpenDMARetriever):
    """Retrieve metadata-only Haystack Documents from Alfresco via AFTS."""

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "Alfresco",
        query_language: str = "alfresco:afts",
        sites: list[str] | None = None,
        top_k: int | None = None,
        raise_on_error: bool = True,
        warn_on_error: bool = True,
        metadata_fn: MetadataFn | None = None,
    ) -> None:
        """Initialize the Alfresco retriever."""
        if sites is not None:
            for site in sites:
                validate_alfresco_site_name(site)
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            query_language=query_language,
            top_k=top_k,
            raise_on_error=raise_on_error,
            warn_on_error=warn_on_error,
            metadata_fn=metadata_fn,
        )
        self.sites = sites

    def _build_query(self, query: str) -> str:
        normalized_query = re.sub(r"\s+", " ", query).strip()
        if not normalized_query:
            raise ValueError("query must not be empty")

        escaped_query = normalized_query.replace("\\", "\\\\").replace('"', '\\"')
        afts_query = f'TEXT:"{escaped_query}"'
        if self.sites:
            site_filters = [f'SITE:"{site}"' for site in self.sites]
            afts_query += " AND (" + " OR ".join(site_filters) + ")"
        return afts_query


class FileNetP8Retriever(OpenDMARetriever):
    """Retrieve metadata-only Haystack Documents from FileNet P8 via SQL search."""

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "FileNetP8",
        query_language: str = "filenetp8:sql",
        top_k: int | None = None,
        raise_on_error: bool = True,
        warn_on_error: bool = True,
        metadata_fn: MetadataFn | None = None,
    ) -> None:
        """Initialize the FileNet P8 retriever."""
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            query_language=query_language,
            top_k=top_k,
            raise_on_error=raise_on_error,
            warn_on_error=warn_on_error,
            metadata_fn=metadata_fn,
        )

    def _build_query(self, query: str) -> str:
        words = _split_words(query)
        if not words:
            raise ValueError("query must not be empty")

        special_characters = frozenset("*?:^()[]{}@\\~")
        escaped_words = [
            "".join(
                f"\\{character}" if character in special_characters else character
                for character in word
            )
            for word in words
        ]
        content_query = " OR ".join(escaped_words).replace("'", "''")
        return (
            "SELECT d.This FROM Document d "
            "INNER JOIN ContentSearch cs ON d.This = cs.QueriedObject "
            f"WHERE CONTAINS(d.*, '{content_query}')"
        )


class DocumentumRetriever(OpenDMARetriever):
    """Retrieve metadata-only Haystack Documents from Documentum via DQL search."""

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "Documentum",
        query_language: str = "dctm:dql",
        top_k: int | None = None,
        raise_on_error: bool = True,
        warn_on_error: bool = True,
        metadata_fn: MetadataFn | None = None,
    ) -> None:
        """Initialize the Documentum retriever."""
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            query_language=query_language,
            top_k=top_k,
            raise_on_error=raise_on_error,
            warn_on_error=warn_on_error,
            metadata_fn=metadata_fn,
        )

    def _build_query(self, query: str) -> str:
        words = _split_words(query)
        if not words:
            raise ValueError("query must not be empty")

        escaped_words = [word.replace("'", "''") for word in words]
        content_query = " OR ".join(f"'{word}'" for word in escaped_words)
        return f"SELECT * FROM dm_document SEARCH DOCUMENT CONTAINS {content_query}"


class OnBaseRetriever(OpenDMARetriever):
    """Retrieve metadata-only Haystack Documents from OnBase via DocumentQuery search."""

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "OnBase",
        query_language: str = "onbase:DocumentQuery",
        top_k: int | None = None,
        raise_on_error: bool = True,
        warn_on_error: bool = True,
        metadata_fn: MetadataFn | None = None,
    ) -> None:
        """Initialize the OnBase retriever."""
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            query_language=query_language,
            top_k=top_k,
            raise_on_error=raise_on_error,
            warn_on_error=warn_on_error,
            metadata_fn=metadata_fn,
        )

    def _build_query(self, query: str) -> str:
        words = _split_words(query)
        if not words:
            raise ValueError("query must not be empty")

        full_text_query = escape_xml_text(" OR ".join(words), quote=False)
        return (
            "<DocumentQuery>"
            '<CustomQueries isList="true"></CustomQueries>'
            '<DateRanges isList="true"></DateRanges>'
            '<DisplayField isList="true"></DisplayField>'
            "<Distinct>false</Distinct>"
            '<DocumentRanges isList="true"></DocumentRanges>'
            "<DocumentTypeGroups></DocumentTypeGroups>"
            "<DocumentTypes></DocumentTypes>"
            f"<FullTextSearchString>{full_text_query}</FullTextSearchString>"
            "<NoteTypes></NoteTypes>"
            '<QueryKeywords isList="true"></QueryKeywords>'
            '<QueryRecords isList="true"></QueryRecords>'
            '<SortBy isList="true"></SortBy>'
            "<TextSearchType>2</TextSearchType>"
            "</DocumentQuery>"
        )
