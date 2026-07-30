"""Fetchers for OpenDMA integration with Haystack."""

from __future__ import annotations

from typing import Any

from haystack import Document, component
from haystack.dataclasses import ByteStream
from opendma.api import OdmaDataContentElement, OdmaDocument, OdmaFolder, OdmaId
from opendma.remote import connect

from opendma_haystack._common import (
    MetadataFn,
    extract_metadata,
    handle_error,
    normalize_mime_type,
    resolve_target,
)


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
        obj = session.get_object(OdmaId(repository_id), OdmaId(document_id), None)
        if not isinstance(obj, OdmaDocument):
            raise TypeError(f"OpenDMA object {document_id!r} is not a document")

        return self._fetch_document(obj, repository_id)

    def _fetch_document(self, document: Any, repository_id: str) -> ByteStream | None:
        content_element = document.get_primary_content_element()
        if content_element is None:
            return self._empty_stream_if_requested(document, repository_id, None, None)

        mime_type = normalize_mime_type(content_element.get_content_type())
        if not isinstance(content_element, OdmaDataContentElement):
            return self._empty_stream_if_requested(document, repository_id, mime_type, None)

        file_name = content_element.get_file_name()
        content = content_element.get_content()
        if content is None:
            return self._empty_stream_if_requested(document, repository_id, mime_type, file_name)

        stream = content.get_stream()
        if stream is None:
            return self._empty_stream_if_requested(document, repository_id, mime_type, file_name)

        metadata = self._stream_metadata(document, repository_id, mime_type, file_name)
        return ByteStream(data=stream.read(), meta=metadata, mime_type=mime_type)

    def _fetch_folder(
        self,
        session: Any,
        repository_id: str,
        folder_id: str,
        recurse_folders: bool,
    ) -> list[ByteStream]:
        folder = session.get_object(OdmaId(repository_id), OdmaId(folder_id), None)
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
        document: Any,
        repository_id: str,
        mime_type: str | None,
        file_name: str | None,
    ) -> ByteStream | None:
        if not self.include_no_content:
            return None
        metadata = self._stream_metadata(document, repository_id, mime_type, file_name)
        return ByteStream(data=b"", meta=metadata, mime_type=mime_type)

    def _stream_metadata(
        self,
        document: Any,
        repository_id: str,
        mime_type: str | None,
        file_name: str | None,
    ) -> dict[str, Any]:
        return extract_metadata(
            document=document,
            repository_id=repository_id,
            mime_type=mime_type,
            file_name=file_name,
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
                    target_repository_id, target_document_id = resolve_target(
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
