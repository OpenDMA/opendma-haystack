"""Haystack components for OpenDMA."""

from __future__ import annotations

from opendma_haystack.fetchers import AlfrescoFetcher, OpenDMAFetcher
from opendma_haystack.retrievers import (
    AlfrescoRetriever,
    DocumentumRetriever,
    FileNetP8Retriever,
    OnBaseRetriever,
    OpenDMARetriever,
)

__version__ = "0.1.0.dev1"

__all__ = [
    "AlfrescoRetriever",
    "AlfrescoFetcher",
    "DocumentumRetriever",
    "FileNetP8Retriever",
    "OnBaseRetriever",
    "OpenDMAFetcher",
    "OpenDMARetriever",
]
