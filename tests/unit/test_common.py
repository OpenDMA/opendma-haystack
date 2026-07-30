"""Unit tests for pure OpenDMA Haystack helpers."""

from __future__ import annotations

import pytest
from haystack import Document

from opendma_haystack._common import (
    document_content_from_metadata,
    normalize_mime_type,
    resolve_target,
    validate_alfresco_site_name,
)


def test_normalize_mime_type_strips_parameters_and_lowercases() -> None:
    assert normalize_mime_type(" Text/Plain ; charset=utf-8 ") == "text/plain"


def test_resolve_raw_target_requires_repository_id() -> None:
    with pytest.raises(ValueError, match="repository_id is required"):
        resolve_target("document-1")


def test_resolve_document_target_uses_metadata() -> None:
    repository_id, document_id = resolve_target(
        Document(meta={"repository_id": "repo", "opendma_id": "document-1"}),
    )

    assert repository_id == "repo"
    assert document_id == "document-1"


def test_document_content_from_metadata_prefers_title() -> None:
    assert document_content_from_metadata({"opendma:Title": "Quarterly Roadmap"}) == (
        "Quarterly Roadmap"
    )


def test_document_content_from_metadata_falls_back_to_empty_string() -> None:
    assert document_content_from_metadata({}) == ""


@pytest.mark.parametrize("character", ['"', "*", "\\", ">", "<", "?", "/", ":", "|"])
def test_validate_alfresco_site_name_rejects_forbidden_characters(character: str) -> None:
    with pytest.raises(ValueError, match="Alfresco site names cannot contain"):
        validate_alfresco_site_name(f"site{character}name")
