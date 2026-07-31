"""Unit tests for pure OpenDMA Haystack helpers."""

from __future__ import annotations

import pytest

from opendma_haystack._common import (
    normalize_mime_type,
    validate_alfresco_site_name,
)


def test_normalize_mime_type_strips_parameters_and_lowercases() -> None:
    assert normalize_mime_type(" Text/Plain ; charset=utf-8 ") == "text/plain"


@pytest.mark.parametrize("character", ['"', "*", "\\", ">", "<", "?", "/", ":", "|"])
def test_validate_alfresco_site_name_rejects_forbidden_characters(character: str) -> None:
    with pytest.raises(ValueError, match="Alfresco site names cannot contain"):
        validate_alfresco_site_name(f"site{character}name")
