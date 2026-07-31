"""Shared helpers for OpenDMA Haystack components."""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

from opendma.api import OdmaDataContentElement, OdmaDocument

MetadataFn = Callable[[OdmaDocument], dict[str, Any]]

SCALAR_PROPERTY_TYPES = {
    "STRING",
    "INTEGER",
    "SHORT",
    "LONG",
    "FLOAT",
    "DOUBLE",
    "BOOLEAN",
    "DATETIME",
}


def normalize_mime_type(mime_type: str | None) -> str | None:
    """Normalize a MIME type value for Haystack metadata and routing."""
    if mime_type is None:
        return None
    return mime_type.split(";", 1)[0].strip().lower() or None


def extract_metadata(
    document: OdmaDocument,
    repository_id: str,
    metadata_fn: MetadataFn | None = None,
) -> dict[str, Any]:
    """Extract OpenDMA document metadata suitable for Haystack."""
    metadata: dict[str, Any] = {
        "repository_id": repository_id,
        "opendma_id": str(document.get_id()),
        "opendma_class": str(document.get_odma_class().get_qname()),
    }

    content_element = document.get_primary_content_element()
    if content_element is not None:
        mime_type = normalize_mime_type(content_element.get_content_type())
    else:
        mime_type = None

    if mime_type is not None:
        metadata["mime_type"] = mime_type
        metadata["content_type"] = mime_type

    if isinstance(content_element, OdmaDataContentElement):
        file_name = content_element.get_file_name()
        if file_name:
            metadata["file_name"] = file_name

    for property_info in document.get_odma_class().get_properties():
        property_qname = property_info.get_qname()
        prop = document.get_property(property_qname)
        metadata_key = str(property_qname)
        prop_type_name = prop.get_type().name

        if prop_type_name in SCALAR_PROPERTY_TYPES:
            metadata[metadata_key] = prop.get_value()
        elif prop_type_name == "ID":
            if prop.is_multi_value():
                metadata[metadata_key] = [str(value) for value in prop.get_value()]
            else:
                value = prop.get_value()
                if value is not None:
                    metadata[metadata_key] = str(value)
        elif prop_type_name == "REFERENCE":
            if prop.is_multi_value():
                referenced_ids = []
                for ref_obj in prop.get_reference_iterable():
                    ref_id = ref_obj.get_id()
                    if ref_id is not None:
                        referenced_ids.append(str(ref_id))
                metadata[metadata_key] = referenced_ids
            else:
                ref_id = prop.get_reference_id()
                if ref_id is not None:
                    metadata[metadata_key] = str(ref_id)

    if metadata_fn is not None:
        metadata.update(metadata_fn(document))

    return metadata


def handle_error(message: str, exc: Exception, raise_on_error: bool, warn_on_error: bool) -> None:
    """Apply common per-item error behavior."""
    if raise_on_error:
        raise exc
    if warn_on_error:
        warnings.warn(f"{message}: {exc}", RuntimeWarning, stacklevel=3)


def validate_alfresco_site_name(site: str) -> None:
    """Validate an Alfresco site short name."""
    invalid_characters = frozenset('"*\\><?/:|')
    if any(character in site for character in invalid_characters):
        raise ValueError(
            "Alfresco site names cannot contain any of these characters: "
            r'" * \ > < ? / : |'
        )
    if site.endswith("."):
        raise ValueError("Alfresco site names cannot end with a period")
    if site.endswith(" "):
        raise ValueError("Alfresco site names cannot end with a space")
