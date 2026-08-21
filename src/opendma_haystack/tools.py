"""Haystack tools for read-only OpenDMA repository access."""

from __future__ import annotations

import base64
import fnmatch
import json
import re
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from html import escape as escape_xml_text
from time import monotonic
from typing import Any

from haystack import Document
from haystack.dataclasses import ByteStream
from haystack.tools import Tool, Toolset
from opendma.api import OdmaFolder, OdmaId, OdmaObject, OdmaQName, OdmaType
from opendma.remote import connect

from opendma_haystack._common import normalize_mime_type
from opendma_haystack.fetchers import OpenDMAFetcher

ScalarValue = str | int | float | bool | None
MetadataValue = ScalarValue | list[ScalarValue]
TextExtractor = Callable[[list[ByteStream]], list[Document]]


@dataclass
class _ReadTextCacheEntry:
    created_at: float
    documents: list[Document]


class OpenDMAToolset(Toolset):
    """Create read-only Haystack tools for a fixed OpenDMA repository."""

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str | None = None,
        text_extractor: TextExtractor | None = None,
        child_page_size: int = 50,
        read_chunk_page_size: int = 3,
        read_text_cache_enabled: bool = True,
        read_text_cache_max_objects: int = 32,
        read_text_cache_ttl_seconds: int | None = 21600,
        read_text_chunk_chars: int = 4000,
        read_text_chunk_overlap: int = 200,
    ) -> None:
        if not repository_id:
            raise ValueError("repository_id is required")
        if child_page_size <= 0:
            raise ValueError("child_page_size must be greater than 0")
        if read_chunk_page_size <= 0:
            raise ValueError("read_chunk_page_size must be greater than 0")
        if read_text_cache_max_objects <= 0:
            raise ValueError("read_text_cache_max_objects must be greater than 0")
        if read_text_cache_ttl_seconds is not None and read_text_cache_ttl_seconds <= 0:
            raise ValueError("read_text_cache_ttl_seconds must be greater than 0")
        if read_text_chunk_chars <= 0:
            raise ValueError("read_text_chunk_chars must be greater than 0")
        if read_text_chunk_overlap < 0:
            raise ValueError("read_text_chunk_overlap must not be negative")
        if read_text_chunk_overlap >= read_text_chunk_chars:
            raise ValueError("read_text_chunk_overlap must be smaller than read_text_chunk_chars")

        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.repository_id = repository_id
        self.text_extractor = text_extractor
        self.child_page_size = child_page_size
        self.read_chunk_page_size = read_chunk_page_size
        self.read_text_cache_enabled = read_text_cache_enabled
        self.read_text_cache_max_objects = read_text_cache_max_objects
        self.read_text_cache_ttl_seconds = read_text_cache_ttl_seconds
        self.read_text_chunk_chars = read_text_chunk_chars
        self.read_text_chunk_overlap = read_text_chunk_overlap
        self._read_text_cache: OrderedDict[str, _ReadTextCacheEntry] = OrderedDict()

        super().__init__(tools=self.get_tools())

    def get_tools(self) -> list[Tool]:
        """Return the tools exposed by this toolset."""
        return [
            Tool(
                name="opendma_get_metadata",
                description="Get class, aspect, and scalar metadata for one OpenDMA object.",
                parameters={
                    "type": "object",
                    "properties": {
                        "object_id": {
                            "type": "string",
                            "description": "OpenDMA object ID.",
                        },
                    },
                    "required": ["object_id"],
                },
                function=self.get_metadata,
            ),
            Tool(
                name="opendma_list_children",
                description=(
                    "List child folders and documents of an OpenDMA folder. "
                    "Use continuation_token when has_more is true."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "object_id": {
                            "type": "string",
                            "description": "OpenDMA folder object ID.",
                        },
                        "include_folders": {
                            "type": "boolean",
                            "description": "Include child folders.",
                            "default": True,
                        },
                        "include_files": {
                            "type": "boolean",
                            "description": "Include child documents.",
                            "default": True,
                        },
                        "name_pattern": {
                            "type": ["string", "null"],
                            "description": "Optional glob-style name pattern applied to child names.",
                            "default": None,
                        },
                        "continuation_token": {
                            "type": ["string", "null"],
                            "description": "Opaque continuation token returned by a previous call.",
                            "default": None,
                        },
                        "included_metadata": {
                            "type": ["array", "null"],
                            "description": "Qualified OpenDMA property names to include for each item.",
                            "items": {"type": "string"},
                            "default": None,
                        },
                    },
                    "required": ["object_id"],
                },
                function=self.list_children,
            ),
            Tool(
                name="opendma_read_text",
                description=(
                    "Read transformed text chunks from one OpenDMA document. "
                    "Use chunk_continuation_token when has_more is true."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "object_id": {
                            "type": "string",
                            "description": "OpenDMA document object ID.",
                        },
                        "chunk_continuation_token": {
                            "type": ["string", "null"],
                            "description": "Opaque continuation token returned by a previous call.",
                            "default": None,
                        },
                    },
                    "required": ["object_id"],
                },
                function=self.read_text,
            ),
            Tool(
                name="opendma_describe_class",
                description="Describe an OpenDMA type or aspect and its properties.",
                parameters={
                    "type": "object",
                    "properties": {
                        "type_or_aspect_name": {
                            "type": "string",
                            "description": "Qualified OpenDMA type or aspect name.",
                        },
                    },
                    "required": ["type_or_aspect_name"],
                },
                function=self.describe_class,
            ),
        ]

    def get_metadata(self, object_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Implementation for opendma_get_metadata."""
        try:
            input_error = self._validate_tool_input(
                tool_name="opendma_get_metadata",
                provided=kwargs,
                required={"object_id": object_id},
                allowed={"object_id"},
            )
            if input_error is not None:
                return input_error

            assert object_id is not None
            session = self._create_session()
            try:
                obj = self._get_object(session, object_id)
                return {
                    "object_id": str(obj.get_id()),
                    "type_name": str(obj.get_odma_class().get_qname()),
                    "aspect_names": [str(aspect.get_qname()) for aspect in obj.get_aspects()],
                    "name": self._object_name(obj),
                    "metadata": self._extract_metadata(obj),
                }
            finally:
                session.close()
        except Exception as exc:
            return self._tool_error("opendma_get_metadata", exc)

    def list_children(
        self,
        object_id: str | None = None,
        include_folders: bool = True,
        include_files: bool = True,
        name_pattern: str | None = None,
        continuation_token: str | None = None,
        included_metadata: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Implementation for opendma_list_children."""
        try:
            input_error = self._validate_tool_input(
                tool_name="opendma_list_children",
                provided=kwargs,
                required={"object_id": object_id},
                allowed={
                    "object_id",
                    "include_folders",
                    "include_files",
                    "name_pattern",
                    "continuation_token",
                    "included_metadata",
                },
            )
            if input_error is not None:
                return input_error

            if not include_folders and not include_files:
                raise ValueError("include_folders and include_files cannot both be false")

            assert object_id is not None
            session = self._create_session()
            try:
                folder = self._get_object(session, object_id)
                if not isinstance(folder, OdmaFolder):
                    raise ValueError(f"Object {object_id} is not an OpenDMA folder")

                offset = self._decode_offset_token(continuation_token)
                items: list[dict[str, Any]] = []
                has_more = False
                matched = 0

                for child in self._iter_children(folder, include_folders, include_files):
                    if name_pattern and not fnmatch.fnmatchcase(
                        self._object_name(child), name_pattern
                    ):
                        continue
                    if matched < offset:
                        matched += 1
                        continue
                    if len(items) >= self.child_page_size:
                        has_more = True
                        break

                    items.append(
                        self._object_item(child, included_metadata=included_metadata)
                    )
                    matched += 1

                next_offset = offset + len(items)
                return {
                    "items": items,
                    "has_more": has_more,
                    "continuation_token": self._encode_offset_token(next_offset)
                    if has_more
                    else None,
                }
            finally:
                session.close()
        except Exception as exc:
            return self._tool_error("opendma_list_children", exc)

    def read_text(
        self,
        object_id: str | None = None,
        chunk_continuation_token: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Implementation for opendma_read_text."""
        try:
            input_error = self._validate_tool_input(
                tool_name="opendma_read_text",
                provided=kwargs,
                required={"object_id": object_id},
                allowed={"object_id", "chunk_continuation_token"},
            )
            if input_error is not None:
                return input_error

            assert object_id is not None
            documents = self._read_text_documents(object_id)

            offset = self._decode_offset_token(chunk_continuation_token)
            page = documents[offset : offset + self.read_chunk_page_size]
            next_offset = offset + len(page)
            has_more = next_offset < len(documents)

            return {
                "chunks": [
                    {
                        "text": document.content or "",
                        "metadata": self._filter_metadata(document.meta, None),
                        "chunk_index": offset + index,
                    }
                    for index, document in enumerate(page)
                ],
                "has_more": has_more,
                "chunk_continuation_token": self._encode_offset_token(next_offset)
                if has_more
                else None,
            }
        except Exception as exc:
            return self._tool_error("opendma_read_text", exc)

    def describe_class(
        self,
        type_or_aspect_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Implementation for opendma_describe_class."""
        try:
            input_error = self._validate_tool_input(
                tool_name="opendma_describe_class",
                provided=kwargs,
                required={"type_or_aspect_name": type_or_aspect_name},
                allowed={"type_or_aspect_name"},
            )
            if input_error is not None:
                return input_error

            assert type_or_aspect_name is not None
            session = self._create_session()
            try:
                repository = session.get_repository(self._repository_id())
                odma_class = self._find_class(repository, type_or_aspect_name)
                if odma_class is None:
                    raise ValueError(f"OpenDMA type or aspect not found: {type_or_aspect_name}")

                declared = list(odma_class.get_declared_properties())
                declared_names = {str(prop.get_qname()) for prop in declared}
                inherited = [
                    prop
                    for prop in odma_class.get_properties()
                    if str(prop.get_qname()) not in declared_names
                ]
                parent = odma_class.get_super_class()

                return {
                    "name": str(odma_class.get_qname()),
                    "kind": "aspect" if odma_class.get_aspect() else "type",
                    "parent": str(parent.get_qname()) if parent is not None else None,
                    "inherited_properties": [
                        self._property_description(prop) for prop in inherited
                    ],
                    "declared_properties": [
                        self._property_description(prop) for prop in declared
                    ],
                }
            finally:
                session.close()
        except Exception as exc:
            return self._tool_error("opendma_describe_class", exc)

    def _create_session(self) -> Any:
        return connect(
            endpoint=self.endpoint,
            username=self.username,
            password=self.password,
        )

    def _repository_id(self) -> OdmaId:
        return OdmaId(self.repository_id)

    def _get_object(self, session: Any, object_id: str) -> OdmaObject:
        obj: OdmaObject = session.get_object(self._repository_id(), OdmaId(object_id), None)
        return obj

    def _read_text_documents(self, object_id: str) -> list[Document]:
        if not self.read_text_cache_enabled:
            return self._load_read_text_documents(object_id)

        cache_entry = self._read_text_cache.get(object_id)
        if cache_entry is not None:
            if not self._read_text_cache_entry_expired(cache_entry):
                self._read_text_cache.move_to_end(object_id)
                return cache_entry.documents
            del self._read_text_cache[object_id]

        documents = self._load_read_text_documents(object_id)
        self._read_text_cache[object_id] = _ReadTextCacheEntry(
            created_at=monotonic(),
            documents=documents,
        )
        self._read_text_cache.move_to_end(object_id)

        while len(self._read_text_cache) > self.read_text_cache_max_objects:
            self._read_text_cache.popitem(last=False)

        return documents

    def _load_read_text_documents(self, object_id: str) -> list[Document]:
        fetcher = OpenDMAFetcher(
            endpoint=self.endpoint,
            username=self.username,
            password=self.password,
            repository_id=self.repository_id,
            raise_on_error=True,
            warn_on_error=False,
        )
        streams = fetcher.run(targets=[object_id])["streams"]
        if not streams:
            raise ValueError(
                f"No content was returned for document {object_id}. "
                "The document may not exist or may have no primary content stream."
            )

        if self.text_extractor is not None:
            documents = self.text_extractor(streams)
        else:
            documents = self._default_text_extractor(streams)

        documents = self._split_text_documents(documents)
        if not documents:
            raise ValueError(
                f"No readable text content was returned for document {object_id}. "
                "Configure text_extractor to support this document type."
            )
        return documents

    def _read_text_cache_entry_expired(self, entry: _ReadTextCacheEntry) -> bool:
        if self.read_text_cache_ttl_seconds is None:
            return False
        return monotonic() - entry.created_at > self.read_text_cache_ttl_seconds

    def _default_text_extractor(self, streams: list[ByteStream]) -> list[Document]:
        documents: list[Document] = []
        for stream in streams:
            mime_type = normalize_mime_type(stream.mime_type or stream.meta.get("mime_type"))
            if mime_type is None:
                continue
            if not (
                mime_type.startswith("text/")
                or mime_type in {"application/json", "application/xml", "application/xhtml+xml"}
            ):
                continue
            documents.append(
                Document(
                    content=stream.data.decode("utf-8", errors="replace"),
                    meta=dict(stream.meta),
                )
            )
        return documents

    def _split_text_documents(self, documents: list[Document]) -> list[Document]:
        chunked_documents: list[Document] = []
        step = self.read_text_chunk_chars - self.read_text_chunk_overlap

        for document in documents:
            if document.content is None:
                continue
            text = document.content
            if not text:
                continue

            start = 0
            while start < len(text):
                end = start + self.read_text_chunk_chars
                chunked_documents.append(
                    Document(
                        content=text[start:end],
                        meta=dict(document.meta),
                    )
                )
                start += step

        return chunked_documents

    def _iter_children(
        self,
        folder: OdmaFolder,
        include_folders: bool,
        include_files: bool,
    ) -> Iterator[OdmaObject]:
        if include_folders:
            yield from folder.get_sub_folders()
        if include_files:
            yield from folder.get_containees()

    def _tool_error(self, tool_name: str, exc: Exception) -> dict[str, Any]:
        message = str(exc) or exc.__class__.__name__
        return {
            "error": True,
            "tool": tool_name,
            "error_type": exc.__class__.__name__,
            "message": message,
        }

    def _tool_input_error(self, tool_name: str, message: str) -> dict[str, Any]:
        return {
            "error": True,
            "tool": tool_name,
            "error_type": "ToolInputError",
            "message": message,
        }

    def _validate_tool_input(
        self,
        tool_name: str,
        provided: dict[str, Any],
        required: dict[str, Any],
        allowed: set[str],
    ) -> dict[str, Any] | None:
        unexpected = sorted(set(provided) - allowed)
        if unexpected:
            allowed_message = ", ".join(sorted(allowed)) if allowed else "none"
            return self._tool_input_error(
                tool_name,
                "Unexpected parameter(s): "
                + ", ".join(unexpected)
                + ". Allowed parameters: "
                + allowed_message
                + ".",
            )

        missing = [
            name
            for name, value in required.items()
            if value is None or not isinstance(value, str) or not value.strip()
        ]
        if missing:
            return self._tool_input_error(
                tool_name,
                "Missing required string parameter(s): " + ", ".join(missing) + ".",
            )

        return None

    def _extract_metadata(self, obj: OdmaObject) -> dict[str, MetadataValue]:
        metadata: dict[str, MetadataValue] = {}
        for property_info in obj.get_odma_class().get_properties():
            property_name = property_info.get_qname()
            prop = obj.get_property(property_name)
            value = self._property_value(prop)
            if value is not None:
                metadata[str(property_name)] = value
        return metadata

    def _property_value(self, prop: Any) -> MetadataValue:
        prop_type = prop.get_type()
        if prop_type == OdmaType.CONTENT:
            return None

        if prop.is_multi_value():
            raw_values = self._multi_property_values(prop, prop_type)
            return [self._scalar_value(value) for value in raw_values]

        if prop_type == OdmaType.REFERENCE:
            reference_id = prop.get_reference_id()
            return str(reference_id) if reference_id is not None else None

        return self._scalar_value(prop.get_value())

    def _multi_property_values(self, prop: Any, prop_type: Any) -> list[Any]:
        if prop_type == OdmaType.ID:
            return list(prop.get_id_list())
        if prop_type == OdmaType.GUID:
            return list(prop.get_guid_list())
        if prop_type == OdmaType.REFERENCE:
            return [
                ref_obj.get_id()
                for ref_obj in prop.get_reference_iterable()
                if ref_obj.get_id() is not None
            ]
        value = prop.get_value()
        if isinstance(value, list):
            return value
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            return list(value)
        return []

    def _scalar_value(self, value: Any) -> ScalarValue:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return str(value)

    def _object_item(
        self,
        obj: OdmaObject,
        included_metadata: list[str] | None,
    ) -> dict[str, Any]:
        return {
            "object_id": str(obj.get_id()),
            "type_name": str(obj.get_odma_class().get_qname()),
            "aspect_names": [str(aspect.get_qname()) for aspect in obj.get_aspects()],
            "name": self._object_name(obj),
            "metadata": self._filter_metadata(self._extract_metadata(obj), included_metadata),
        }

    def _object_name(self, obj: OdmaObject) -> str:
        metadata = self._extract_metadata(obj)
        for key in ("opendma:Name", "opendma:Title"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
        return str(obj.get_id())

    def _filter_metadata(
        self,
        metadata: dict[str, Any],
        included_metadata: list[str] | None,
    ) -> dict[str, MetadataValue]:
        if included_metadata is None:
            return {key: self._metadata_value(value) for key, value in metadata.items()}
        return {
            key: self._metadata_value(value)
            for key, value in metadata.items()
            if key in included_metadata
        }

    def _metadata_value(self, value: Any) -> MetadataValue:
        if isinstance(value, list):
            return [self._scalar_value(item) for item in value]
        return self._scalar_value(value)

    def _metadata_string(self, obj: OdmaObject, property_name: str) -> str:
        prop = obj.get_property(OdmaQName.from_string(property_name))
        if prop is None:
            return ""
        value = prop.get_string()
        return value or ""

    def _property_description(self, property_info: Any) -> dict[str, Any]:
        choices = [
            choice.get_display_name()
            for choice in property_info.get_choices()
            if choice.get_display_name()
        ]
        return {
            "name": str(property_info.get_qname()),
            "type": str(property_info.get_data_type()),
            "description": property_info.get_display_name(),
            "required": property_info.get_required(),
            "multi_value": property_info.get_multi_value(),
            "queryable": None,
            "possible_values": choices or None,
        }

    def _find_class(self, repository: Any, qname: str) -> Any | None:
        roots = [repository.get_root_class(), *list(repository.get_root_aspects())]
        for root in roots:
            found = self._find_class_in_tree(root, qname)
            if found is not None:
                return found
        return None

    def _find_class_in_tree(self, odma_class: Any, qname: str) -> Any | None:
        if str(odma_class.get_qname()) == qname:
            return odma_class
        for aspect in odma_class.get_aspects():
            if str(aspect.get_qname()) == qname:
                return aspect
        for included_aspect in odma_class.get_included_aspects():
            if str(included_aspect.get_qname()) == qname:
                return included_aspect
        for sub_class in odma_class.get_sub_classes():
            found = self._find_class_in_tree(sub_class, qname)
            if found is not None:
                return found
        return None

    def _encode_offset_token(self, offset: int) -> str:
        payload = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii")

    def _decode_offset_token(self, token: str | None) -> int:
        if not token:
            return 0
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
            offset = payload.get("offset")
        except Exception as exc:
            raise ValueError("Invalid continuation token") from exc
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("Invalid continuation token")
        return offset


class _SearchToolset(OpenDMAToolset):
    query_language: str

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str | None = None,
        text_extractor: TextExtractor | None = None,
        child_page_size: int = 50,
        read_chunk_page_size: int = 3,
        search_result_limit: int = 20,
        read_text_cache_enabled: bool = True,
        read_text_cache_max_objects: int = 32,
        read_text_cache_ttl_seconds: int | None = 21600,
        read_text_chunk_chars: int = 4000,
        read_text_chunk_overlap: int = 200,
    ) -> None:
        self.search_result_limit = search_result_limit
        if self.search_result_limit <= 0:
            raise ValueError("search_result_limit must be greater than 0")
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            text_extractor=text_extractor,
            child_page_size=child_page_size,
            read_chunk_page_size=read_chunk_page_size,
            read_text_cache_enabled=read_text_cache_enabled,
            read_text_cache_max_objects=read_text_cache_max_objects,
            read_text_cache_ttl_seconds=read_text_cache_ttl_seconds,
            read_text_chunk_chars=read_text_chunk_chars,
            read_text_chunk_overlap=read_text_chunk_overlap,
        )

    def get_tools(self) -> list[Tool]:
        """Return OpenDMA tools plus a platform-specific search tool."""
        return [
            *super().get_tools(),
            Tool(
                name="opendma_search",
                description=self._search_tool_description(),
                parameters=self._search_tool_parameters(),
                function=self.search,
            ),
        ]

    def search(
        self,
        full_text: str | None = None,
        in_folder: str | None = None,
        include_subfolder_in_folder: bool | None = None,
        included_metadata: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Implementation for opendma_search using a platform query language."""
        try:
            input_error = self._validate_tool_input(
                tool_name="opendma_search",
                provided=kwargs,
                required={},
                allowed={
                    "full_text",
                    "in_folder",
                    "include_subfolder_in_folder",
                    "included_metadata",
                },
            )
            if input_error is not None:
                return input_error

            query = self._build_search_query(
                full_text=full_text,
                in_folder=in_folder,
                include_subfolder_in_folder=include_subfolder_in_folder,
            )
            return self._run_search(
                query_language=self.query_language,
                query=query,
                included_metadata=included_metadata,
                search_result_limit=self.search_result_limit,
            )
        except Exception as exc:
            return self._tool_error("opendma_search", exc)

    def _run_search(
        self,
        query_language: str,
        query: str,
        included_metadata: list[str] | None,
        search_result_limit: int,
    ) -> dict[str, Any]:
        session = self._create_session()
        try:
            search_result = session.search(
                self._repository_id(),
                OdmaQName.from_string(query_language),
                query,
            )

            items = []
            for obj in search_result.get_objects():
                items.append(self._object_item(obj, included_metadata=included_metadata))
                if len(items) >= search_result_limit:
                    break

            return {
                "items": items,
                "has_more": False,
                "continuation_token": None,
            }
        finally:
            session.close()

    def _search_tool_description(self) -> str:
        return (
            "Search documents via OpenDMA using full text. "
            "Use in_folder to restrict the search to a folder."
        )

    def _search_tool_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "full_text": {
                    "type": ["string", "null"],
                    "description": "Optional full-text query.",
                    "default": None,
                },
                "in_folder": {
                    "type": ["string", "null"],
                    "description": "Optional folder restriction.",
                    "default": None,
                },
                "include_subfolder_in_folder": {
                    "type": ["boolean", "null"],
                    "description": "Whether to include subfolders when in_folder is set.",
                    "default": None,
                },
                "included_metadata": {
                    "type": ["array", "null"],
                    "description": "Qualified OpenDMA property names to include for each item.",
                    "items": {"type": "string"},
                    "default": None,
                },
            },
        }

    def _build_search_query(
        self,
        full_text: str | None,
        in_folder: str | None,
        include_subfolder_in_folder: bool | None,
    ) -> str:
        raise NotImplementedError

    def _split_words(self, full_text: str | None) -> list[str]:
        if full_text is None:
            return []
        return re.sub(r"\s+", " ", full_text).strip().split()


class AlfrescoToolset(_SearchToolset):
    """Create read-only Haystack tools for Alfresco via OpenDMA."""

    query_language = "alfresco:afts"

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "Alfresco",
        text_extractor: TextExtractor | None = None,
        child_page_size: int = 50,
        read_chunk_page_size: int = 3,
        search_result_limit: int = 20,
        read_text_cache_enabled: bool = True,
        read_text_cache_max_objects: int = 32,
        read_text_cache_ttl_seconds: int | None = 21600,
        read_text_chunk_chars: int = 4000,
        read_text_chunk_overlap: int = 200,
    ) -> None:
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            text_extractor=text_extractor,
            child_page_size=child_page_size,
            read_chunk_page_size=read_chunk_page_size,
            search_result_limit=search_result_limit,
            read_text_cache_enabled=read_text_cache_enabled,
            read_text_cache_max_objects=read_text_cache_max_objects,
            read_text_cache_ttl_seconds=read_text_cache_ttl_seconds,
            read_text_chunk_chars=read_text_chunk_chars,
            read_text_chunk_overlap=read_text_chunk_overlap,
        )

    def get_tools(self) -> list[Tool]:
        """Return OpenDMA tools plus Alfresco-specific tools."""
        return [
            *super().get_tools(),
            Tool(
                name="alfresco_list_sites",
                description=(
                    "List Alfresco sites with short name, title, description, "
                    "and root folder object ID."
                ),
                parameters={"type": "object", "properties": {}},
                function=self.list_sites,
            ),
        ]

    def list_sites(self, **kwargs: Any) -> list[dict[str, Any]] | dict[str, Any]:
        """Implementation for alfresco_list_sites."""
        try:
            input_error = self._validate_tool_input(
                tool_name="alfresco_list_sites",
                provided=kwargs,
                required={},
                allowed=set(),
            )
            if input_error is not None:
                return input_error

            session = self._create_session()
            try:
                search_result = session.search(
                    self._repository_id(),
                    OdmaQName.from_string("alfresco:afts"),
                    'TYPE:"st:site"',
                )

                sites = []
                for obj in search_result.get_objects():
                    if not isinstance(obj, OdmaFolder):
                        continue
                    sites.append(
                        {
                            "short_name": self._metadata_string(obj, "alfresco:cm:name"),
                            "title": self._metadata_string(obj, "alfresco:cm:title"),
                            "description": self._metadata_string(
                                obj,
                                "alfresco:cm:description",
                            ),
                            "root_folder_id": str(obj.get_id()),
                        }
                    )
                return sites
            finally:
                session.close()
        except Exception as exc:
            return [self._tool_error("alfresco_list_sites", exc)]

    def _search_tool_description(self) -> str:
        return (
            "Search Alfresco documents via OpenDMA using full text. "
            "Use in_folder to restrict the search to an Alfresco folder."
        )

    def _build_search_query(
        self,
        full_text: str | None,
        in_folder: str | None,
        include_subfolder_in_folder: bool | None,
    ) -> str:
        query_parts = []

        if full_text is not None:
            normalized_text = re.sub(r"\s+", " ", full_text).strip()
            if normalized_text:
                query_parts.append(f'TEXT:"{self._escape_afts_phrase(normalized_text)}"')

        if in_folder is not None:
            normalized_folder = in_folder.strip()
            if normalized_folder:
                folder_operator = "ANCESTOR" if include_subfolder_in_folder else "PARENT"
                folder_ref = self._alfresco_node_ref(normalized_folder)
                query_parts.append(f'{folder_operator}:"{self._escape_afts_phrase(folder_ref)}"')

        if not query_parts:
            raise ValueError("full_text or in_folder must be provided")

        return " AND ".join(query_parts)

    def _alfresco_node_ref(self, object_id: str) -> str:
        if object_id.startswith("workspace://"):
            return object_id
        if object_id.startswith("node:"):
            return f"workspace://SpacesStore/{object_id.removeprefix('node:')}"
        return object_id

    def _escape_afts_phrase(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')


class FileNetP8Toolset(_SearchToolset):
    """Create read-only Haystack tools for FileNet P8 via OpenDMA."""

    query_language = "filenetp8:sql"

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "FileNetP8",
        text_extractor: TextExtractor | None = None,
        child_page_size: int = 50,
        read_chunk_page_size: int = 3,
        search_result_limit: int = 20,
        read_text_cache_enabled: bool = True,
        read_text_cache_max_objects: int = 32,
        read_text_cache_ttl_seconds: int | None = 21600,
        read_text_chunk_chars: int = 4000,
        read_text_chunk_overlap: int = 200,
    ) -> None:
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            text_extractor=text_extractor,
            child_page_size=child_page_size,
            read_chunk_page_size=read_chunk_page_size,
            search_result_limit=search_result_limit,
            read_text_cache_enabled=read_text_cache_enabled,
            read_text_cache_max_objects=read_text_cache_max_objects,
            read_text_cache_ttl_seconds=read_text_cache_ttl_seconds,
            read_text_chunk_chars=read_text_chunk_chars,
            read_text_chunk_overlap=read_text_chunk_overlap,
        )

    def _search_tool_description(self) -> str:
        return (
            "Search FileNet P8 documents via OpenDMA using full text. "
            "Use in_folder to restrict the search to a FileNet folder."
        )

    def _build_search_query(
        self,
        full_text: str | None,
        in_folder: str | None,
        include_subfolder_in_folder: bool | None,
    ) -> str:
        query_parts = []
        join = ""

        words = self._split_words(full_text)
        if words:
            join = " INNER JOIN ContentSearch cs ON d.This = cs.QueriedObject"
            content_query = " OR ".join(self._escape_content_search_word(word) for word in words)
            content_query = self._escape_sql_string_literal(content_query)
            query_parts.append(f"CONTAINS(d.*, '{content_query}')")

        if in_folder is not None:
            normalized_folder = in_folder.strip()
            if normalized_folder:
                folder_operator = "INSUBFOLDER" if include_subfolder_in_folder else "INFOLDER"
                folder_id = self._filenet_folder_id(normalized_folder)
                query_parts.append(f"d.This {folder_operator} {folder_id}")

        if not query_parts:
            raise ValueError("full_text or in_folder must be provided")

        return f"SELECT d.This FROM Document d{join} WHERE {' AND '.join(query_parts)}"

    def _escape_content_search_word(self, value: str) -> str:
        special_characters = frozenset("*?:^()[]{}@\\~")
        return "".join(
            f"\\{character}" if character in special_characters else character
            for character in value
        )

    def _escape_sql_string_literal(self, value: str) -> str:
        return value.replace("'", "''")

    def _filenet_folder_id(self, object_id: str) -> str:
        parts = object_id.split(":")
        if len(parts) != 3:
            raise ValueError(
                "FileNet folder object ID must have the format 'objectstore:<classId>:<objectId>'"
            )
        if parts[0] != "objectstore":
            raise ValueError("FileNet folder object ID must start with 'objectstore:'")
        folder_id = parts[2]
        if not folder_id.startswith("{") or not folder_id.endswith("}"):
            raise ValueError("FileNet folder object ID must end with a braced object ID")
        return folder_id


class DocumentumToolset(_SearchToolset):
    """Create read-only Haystack tools for Documentum via OpenDMA."""

    query_language = "dctm:dql"

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "Documentum",
        text_extractor: TextExtractor | None = None,
        child_page_size: int = 50,
        read_chunk_page_size: int = 3,
        search_result_limit: int = 20,
        read_text_cache_enabled: bool = True,
        read_text_cache_max_objects: int = 32,
        read_text_cache_ttl_seconds: int | None = 21600,
        read_text_chunk_chars: int = 4000,
        read_text_chunk_overlap: int = 200,
    ) -> None:
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            text_extractor=text_extractor,
            child_page_size=child_page_size,
            read_chunk_page_size=read_chunk_page_size,
            search_result_limit=search_result_limit,
            read_text_cache_enabled=read_text_cache_enabled,
            read_text_cache_max_objects=read_text_cache_max_objects,
            read_text_cache_ttl_seconds=read_text_cache_ttl_seconds,
            read_text_chunk_chars=read_text_chunk_chars,
            read_text_chunk_overlap=read_text_chunk_overlap,
        )

    def _search_tool_description(self) -> str:
        return (
            "Search Documentum documents via OpenDMA using full text. "
            "Use in_folder to restrict the search to a Documentum folder."
        )

    def _build_search_query(
        self,
        full_text: str | None,
        in_folder: str | None,
        include_subfolder_in_folder: bool | None,
    ) -> str:
        content_query = self._documentum_content_query(full_text)
        folder_query = self._documentum_folder_query(in_folder, include_subfolder_in_folder)

        if content_query is None and folder_query is None:
            raise ValueError("full_text or in_folder must be provided")

        query = "SELECT * FROM dm_document"
        if content_query is not None:
            query += f" SEARCH DOCUMENT CONTAINS {content_query}"
        if folder_query is not None:
            query += f" WHERE {folder_query}"
        return query

    def _documentum_content_query(self, full_text: str | None) -> str | None:
        words = self._split_words(full_text)
        if not words:
            return None
        return " OR ".join(f"'{self._escape_dql_string_literal(word)}'" for word in words)

    def _documentum_folder_query(
        self,
        in_folder: str | None,
        include_subfolder_in_folder: bool | None,
    ) -> str | None:
        if in_folder is None:
            return None
        normalized_folder = in_folder.strip()
        if not normalized_folder:
            return None
        folder_id = self._escape_dql_string_literal(normalized_folder)
        if include_subfolder_in_folder:
            return f"FOLDER(ID('{folder_id}'), DESCEND)"
        return f"FOLDER(ID('{folder_id}'))"

    def _escape_dql_string_literal(self, value: str) -> str:
        return value.replace("'", "''")


class OnBaseToolset(_SearchToolset):
    """Create read-only Haystack tools for OnBase via OpenDMA."""

    query_language = "onbase:DocumentQuery"

    def __init__(
        self,
        endpoint: str,
        username: str | None = None,
        password: str | None = None,
        repository_id: str = "OnBase",
        text_extractor: TextExtractor | None = None,
        child_page_size: int = 50,
        read_chunk_page_size: int = 3,
        search_result_limit: int = 20,
        read_text_cache_enabled: bool = True,
        read_text_cache_max_objects: int = 32,
        read_text_cache_ttl_seconds: int | None = 21600,
        read_text_chunk_chars: int = 4000,
        read_text_chunk_overlap: int = 200,
    ) -> None:
        super().__init__(
            endpoint=endpoint,
            username=username,
            password=password,
            repository_id=repository_id,
            text_extractor=text_extractor,
            child_page_size=child_page_size,
            read_chunk_page_size=read_chunk_page_size,
            search_result_limit=search_result_limit,
            read_text_cache_enabled=read_text_cache_enabled,
            read_text_cache_max_objects=read_text_cache_max_objects,
            read_text_cache_ttl_seconds=read_text_cache_ttl_seconds,
            read_text_chunk_chars=read_text_chunk_chars,
            read_text_chunk_overlap=read_text_chunk_overlap,
        )

    def _search_tool_description(self) -> str:
        return "Search OnBase documents via OpenDMA using full text."

    def _search_tool_parameters(self) -> dict[str, Any]:
        parameters = super()._search_tool_parameters()
        parameters["properties"].pop("in_folder")
        parameters["properties"].pop("include_subfolder_in_folder")
        return parameters

    def _build_search_query(
        self,
        full_text: str | None,
        in_folder: str | None,
        include_subfolder_in_folder: bool | None,  # noqa: ARG002
    ) -> str:
        if in_folder is not None:
            raise ValueError("Restricting OnBase searches to a folder is not available")

        words = self._split_words(full_text)
        if not words:
            raise ValueError("full_text must not be empty")

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
