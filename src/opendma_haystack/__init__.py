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
from opendma_haystack.tools import (
    AlfrescoToolset,
    DocumentumToolset,
    FileNetP8Toolset,
    OnBaseToolset,
    OpenDMAToolset,
)

__version__ = "0.2.0"

__all__ = [
    "AlfrescoRetriever",
    "AlfrescoFetcher",
    "AlfrescoToolset",
    "DocumentumRetriever",
    "DocumentumToolset",
    "FileNetP8Retriever",
    "FileNetP8Toolset",
    "OnBaseRetriever",
    "OnBaseToolset",
    "OpenDMAFetcher",
    "OpenDMARetriever",
    "OpenDMAToolset",
]
