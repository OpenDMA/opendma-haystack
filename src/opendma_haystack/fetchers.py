"""Fetchers for OpenDMA integration with Haystack."""

from __future__ import annotations

from typing import Any

from haystack import Document, component
from haystack.dataclasses import ByteStream
from opendma.api import (
    OdmaDataContentElement,
    OdmaDocument,
    OdmaFolder,
    OdmaId,
    OdmaObject,
    OdmaQName,
)
from opendma.remote import connect

from opendma_haystack._common import (
    MetadataFn,
    extract_metadata,
    handle_error,
    normalize_mime_type,
    validate_alfresco_site_name,
)


def _target_from_document(
    document: Document, fallback_repository_id: str | None = None
) -> tuple[str, str]:
    """Resolve a Haystack Document into an OpenDMA fetch target."""
    repository_id = document.meta.get("repository_id") or fallback_repository_id
    document_id = document.meta.get("opendma_id")

    if not isinstance(repository_id, str) or not repository_id.strip():
        raise ValueError("Document target must provide meta['repository_id']")
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("Document target must provide meta['opendma_id']")

    return repository_id, document_id


def _target_from_string(document_id: str, repository_id: str | None) -> tuple[str, str]:
    """Resolve a raw OpenDMA document ID string into an OpenDMA fetch target."""
    if not document_id.strip():
        raise ValueError("document ID target must not be empty")
    if repository_id is None or not repository_id.strip():
        raise ValueError("repository_id is required when targets contain raw document IDs")
    return repository_id, document_id


def _resolve_target(target: str | Document, repository_id: str | None = None) -> tuple[str, str]:
    """Resolve a fetch target into repository and document identifiers."""
    if isinstance(target, Document):
        return _target_from_document(target, repository_id)
    if isinstance(target, str):
        return _target_from_string(target, repository_id)
    raise TypeError("targets must contain raw document IDs or Haystack Document objects")


@component
class OpenDMAFetcher:
    """Fetch OpenDMA document content as Haystack ByteStreams."""

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str | None = None,
        include_no_content: bool = False,
        raise_on_error: bool = True,
        warn_on_error: bool = True,
        metadata_fn: MetadataFn | None = None,
    ) -> None:
        """Initialize the OpenDMA fetcher."""
        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.repository_id = repository_id
        self.include_no_content = include_no_content
        self.raise_on_error = raise_on_error
        self.warn_on_error = warn_on_error
        self.metadata_fn = metadata_fn

    def _fetch_target(
        self, session: Any, repository_id: str, document_id: str
    ) -> ByteStream | None:
        obj: OdmaObject = session.get_object(OdmaId(repository_id), OdmaId(document_id), None)
        if not isinstance(obj, OdmaDocument):
            raise TypeError(f"OpenDMA object {document_id!r} is not a document")

        return self._fetch_document(obj, repository_id)

    def _fetch_document(self, document: OdmaDocument, repository_id: str) -> ByteStream | None:
        content_element = document.get_primary_content_element()
        if content_element is None:
            return self._empty_stream_if_requested(document, repository_id, None)

        mime_type = normalize_mime_type(content_element.get_content_type())
        if not isinstance(content_element, OdmaDataContentElement):
            return self._empty_stream_if_requested(document, repository_id, mime_type)

        content = content_element.get_content()
        if content is None:
            return self._empty_stream_if_requested(document, repository_id, mime_type)

        stream = content.get_stream()
        if stream is None:
            return self._empty_stream_if_requested(document, repository_id, mime_type)

        metadata = self._stream_metadata(document, repository_id)
        return ByteStream(data=stream.read(), meta=metadata, mime_type=mime_type)

    def _fetch_folder(
        self,
        session: Any,
        repository_id: str,
        folder_id: str,
        recurse_folders: bool,
    ) -> list[ByteStream]:
        folder: OdmaObject = session.get_object(OdmaId(repository_id), OdmaId(folder_id), None)
        if not isinstance(folder, OdmaFolder):
            raise TypeError(f"OpenDMA object {folder_id!r} is not a folder")

        streams: list[ByteStream] = []
        folders_to_process = [folder]
        while folders_to_process:
            current_folder = folders_to_process.pop()
            for containee in current_folder.get_containees():
                if not isinstance(containee, OdmaDocument):
                    continue

                stream = self._fetch_document(containee, repository_id)
                if stream is not None:
                    streams.append(stream)

            if recurse_folders:
                folders_to_process.extend(current_folder.get_sub_folders())

        return streams

    def _empty_stream_if_requested(
        self,
        document: OdmaDocument,
        repository_id: str,
        mime_type: str | None,
    ) -> ByteStream | None:
        if not self.include_no_content:
            return None
        metadata = self._stream_metadata(document, repository_id)
        return ByteStream(data=b"", meta=metadata, mime_type=mime_type)

    def _stream_metadata(
        self,
        document: OdmaDocument,
        repository_id: str,
    ) -> dict[str, Any]:
        return extract_metadata(
            document=document,
            repository_id=repository_id,
            metadata_fn=self.metadata_fn,
        )

    @component.output_types(streams=list[ByteStream])
    def run(
        self,
        targets: list[str | Document] | None = None,
        repository_id: str | None = None,
        folder_ids: list[str] | None = None,
        recurse_folders: bool = False,
    ) -> dict[str, list[ByteStream]]:
        """Fetch full content for document targets or documents in folders."""
        effective_repository_id = repository_id or self.repository_id
        if not targets and not folder_ids:
            raise ValueError("Must provide at least one of targets or folder_ids")
        if folder_ids and (effective_repository_id is None or not effective_repository_id.strip()):
            raise ValueError("repository_id is required when folder_ids are provided")

        session = connect(
            endpoint=self.endpoint,
            username=self.username,
            password=self.password,
        )
        streams: list[ByteStream] = []

        try:
            for raw_target in targets or []:
                try:
                    target_repository_id, target_document_id = _resolve_target(
                        raw_target, effective_repository_id
                    )
                    stream = self._fetch_target(session, target_repository_id, target_document_id)
                except Exception as exc:
                    handle_error(
                        "OpenDMAFetcher failed to fetch target",
                        exc,
                        self.raise_on_error,
                        self.warn_on_error,
                    )
                    continue

                if stream is not None:
                    streams.append(stream)

            for folder_id in folder_ids or []:
                try:
                    streams.extend(
                        self._fetch_folder(
                            session=session,
                            repository_id=effective_repository_id or "",
                            folder_id=folder_id,
                            recurse_folders=recurse_folders,
                        )
                    )
                except Exception as exc:
                    handle_error(
                        f"OpenDMAFetcher failed to fetch folder {folder_id}",
                        exc,
                        self.raise_on_error,
                        self.warn_on_error,
                    )
                    continue
        finally:
            session.close()

        return {"streams": streams}


class AlfrescoFetcher(OpenDMAFetcher):
    """Fetch OpenDMA document content from Alfresco, including whole sites."""

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "Alfresco",
        sites: list[str] | None = None,
        include_no_content: bool = False,
        raise_on_error: bool = True,
        warn_on_error: bool = True,
        metadata_fn: MetadataFn | None = None,
    ) -> None:
        """Initialize the Alfresco fetcher."""
        self._validate_sites(sites)
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            include_no_content=include_no_content,
            raise_on_error=raise_on_error,
            warn_on_error=warn_on_error,
            metadata_fn=metadata_fn,
        )
        self.sites = sites

    @staticmethod
    def _validate_sites(sites: list[str] | None) -> None:
        if sites is not None:
            for site in sites:
                validate_alfresco_site_name(site)

    def _fetch_sites(
        self,
        session: Any,
        repository_id: str,
        sites: list[str],
    ) -> list[ByteStream]:
        query_parts = [f'=cm:name:"{site}"' for site in sites]
        afts_query = 'TYPE:"st:site" AND (' + " OR ".join(query_parts) + ")"
        search_result = session.search(
            OdmaId(repository_id),
            OdmaQName.from_string("alfresco:afts"),
            afts_query,
        )

        streams: list[ByteStream] = []
        for site in search_result.get_objects():
            if not isinstance(site, OdmaFolder):
                continue
            for subfolder in site.get_sub_folders():
                folders_to_process = [subfolder]
                while folders_to_process:
                    current_folder = folders_to_process.pop()
                    for containee in current_folder.get_containees():
                        if not isinstance(containee, OdmaDocument):
                            continue
                        stream = self._fetch_document(containee, repository_id)
                        if stream is not None:
                            streams.append(stream)
                    folders_to_process.extend(current_folder.get_sub_folders())

        return streams

    @component.output_types(streams=list[ByteStream])
    def run(
        self,
        targets: list[str | Document] | None = None,
        repository_id: str | None = None,
        folder_ids: list[str] | None = None,
        recurse_folders: bool = False,
        sites: list[str] | None = None,
    ) -> dict[str, list[ByteStream]]:
        """Fetch full content for document targets, folders, or Alfresco sites."""
        effective_repository_id = repository_id or self.repository_id
        effective_sites = sites if sites is not None else self.sites
        self._validate_sites(effective_sites)

        if not targets and not folder_ids and not effective_sites:
            raise ValueError("Must provide at least one of targets, folder_ids, or sites")
        if folder_ids and (effective_repository_id is None or not effective_repository_id.strip()):
            raise ValueError("repository_id is required when folder_ids are provided")
        if effective_sites and (
            effective_repository_id is None or not effective_repository_id.strip()
        ):
            raise ValueError("repository_id is required when sites are provided")
        if effective_repository_id is None:
            effective_repository_id = ""

        session = connect(
            endpoint=self.endpoint,
            username=self.username,
            password=self.password,
        )
        streams: list[ByteStream] = []

        try:
            for raw_target in targets or []:
                try:
                    target_repository_id, target_document_id = _resolve_target(
                        raw_target, effective_repository_id
                    )
                    stream = self._fetch_target(session, target_repository_id, target_document_id)
                except Exception as exc:
                    handle_error(
                        "AlfrescoFetcher failed to fetch target",
                        exc,
                        self.raise_on_error,
                        self.warn_on_error,
                    )
                    continue

                if stream is not None:
                    streams.append(stream)

            for folder_id in folder_ids or []:
                try:
                    streams.extend(
                        self._fetch_folder(
                            session=session,
                            repository_id=effective_repository_id,
                            folder_id=folder_id,
                            recurse_folders=recurse_folders,
                        )
                    )
                except Exception as exc:
                    handle_error(
                        f"AlfrescoFetcher failed to fetch folder {folder_id}",
                        exc,
                        self.raise_on_error,
                        self.warn_on_error,
                    )
                    continue

            if effective_sites:
                try:
                    streams.extend(
                        self._fetch_sites(session, effective_repository_id, effective_sites)
                    )
                except Exception as exc:
                    handle_error(
                        "AlfrescoFetcher failed to fetch sites",
                        exc,
                        self.raise_on_error,
                        self.warn_on_error,
                    )
        finally:
            session.close()

        return {"streams": streams}
