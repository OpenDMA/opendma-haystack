# OpenDMA Haystack

Haystack document fetchers and retrievers for [OpenDMA](https://opendma.org/).

OpenDMA is a vendor-neutral abstraction layer for enterprise content management
systems. It provides a common API for repositories such as Alfresco, CMOD,
Documentum, FileNet P8, OnBase, SharePoint, and other ECM or document management
platforms. This package connects that API to Haystack by loading and retrieving
OpenDMA repository content through Haystack fetcher and retriever components.

Use this package when you want to build Haystack applications, RAG pipelines, or
content analysis workflows on top of documents stored in ECM systems.

## Features

- Fetch binary content streams from an OpenDMA REST service by document ID or
  folder ID.
- Fetch complete Alfresco sites with the specialized `AlfrescoFetcher`.
- Search OpenDMA repositories with metadata-only Haystack retrievers.
- Use specialized retrievers for Alfresco, Documentum, FileNet P8, and OnBase.
- Preserve OpenDMA and repository metadata on Haystack `ByteStream` and
  `Document` objects.

## Installation

Install OpenDMA and this integration from PyPI:

```bash
pip install opendma-haystack
```

Install the optional examples dependencies when using the documented converter
pipelines for PDF, HTML, or Microsoft Office formats:

```bash
pip install "opendma-haystack[examples]"
```

## Quickstart

```python
from opendma_haystack import OpenDMAFetcher

fetcher = OpenDMAFetcher(
    endpoint="http://localhost:8080/opendma",
    username="admin",
    password="admin",
    repository_id="my-repository",
)

result = fetcher.run(targets=["some-document-id"])
streams = result["streams"]

for stream in streams:
    print(stream.meta.get("opendma_id"))
    print(stream.meta.get("opendma:Title"))
    print(stream.mime_type)
    print(len(stream.data))
```

`OpenDMAFetcher` returns Haystack `ByteStream` objects. Connect it to Haystack
converters such as `TextFileToDocument`, `PyPDFToDocument`, `HTMLToDocument`,
or `DoclingConverter` when you need text `Document` objects for indexing or RAG.

Use `OpenDMARetriever` when you want to search in an ECM system via OpenDMA:

```python
from opendma_haystack import OpenDMARetriever

retriever = OpenDMARetriever(
    endpoint="http://localhost:8080/opendma",
    username="admin",
    password="admin",
    repository_id="Alfresco",
    query_language="opendma:sfts",
)

result = retriever.run(query="needle keyword")
documents = result["documents"]
```

Retriever results are metadata-only locator `Document` objects. They identify
matching repository documents and can be passed to `OpenDMAFetcher` to fetch the
actual content.

## Documentation

- [Tutorials](https://github.com/OpenDMA/opendma-haystack/tree/main/docs/tutorials/README.md): guided Haystack application tutorials
- [Documentation](https://github.com/OpenDMA/opendma-haystack/tree/main/docs/README.md): component usage, fetcher options, and retriever behavior
- [Examples](https://github.com/OpenDMA/opendma-haystack/tree/main/docs/examples/README.md): runnable examples using the tutorial repository

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src tests
uv run mypy -p opendma_haystack
uv run mypy --follow-imports=skip tests
```

## Related Projects

- [Haystack](https://docs.haystack.deepset.ai/docs/intro)
- [OpenDMA](https://opendma.org/)
- [opendma-api](https://pypi.org/project/opendma-api/)
- [opendma-remote](https://pypi.org/project/opendma-remote/)
