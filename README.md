# OpenDMA Haystack

Integrate Haystack with Enterprise Content Management systems such as Alfresco,
CMOD, Documentum, FileNet P8, OnBase, SharePoint, and other platforms.

[OpenDMA](https://opendma.org/) is a vendor-neutral abstraction layer for
Enterprise Content Management. It provides a common API for repositories allowing
developers to build applications that access content stored on different
platforms, including federating across multiple repositories.

This package connects that API to Haystack with components to retrieve and fetch
OpenDMA documents as part of pipelines.

A convenient Toolset allows agentic applications to browse through complex
repository layouts to retrieve information.

See our [examples](https://github.com/OpenDMA/opendma-haystack/tree/main/docs/examples/README.md)
and [tutorials](https://github.com/OpenDMA/opendma-haystack/tree/main/docs/tutorials/README.md)
to learn how to build RAG pipelines and tool-calling agents.

## Features

- Tools to browse an ECM repository, e.g. to enable agents to discover relevant documents.
- Tools for reading text chunks of documents, e.g. to allow agents to read sections of documents.
- Fetch binary content streams by document ID or folder ID, e.g. to build a knowledge base.
- Search repositories with metadata-only Haystack retrievers, e.g. to use an existing repository as knowledge base.
- Preserve full metadata on every Haystack `ByteStream` and `Document`, e.g. to scope RAG retrieval to a subset of relevant items.

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

The `OpenDMAToolset` provides various tools to allow agents to browse repository
layouts and read sections of text documents:

```python
from opendma_haystack import OpenDMAToolset
from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret
from haystack.dataclasses import ChatMessage

toolset = OpenDMAToolset(
    endpoint="http://localhost:8080/opendma",
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
)

agent = Agent(
    chat_generator=OpenAIChatGenerator(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    ),
    tools=toolset,
    system_prompt="You are...",
)

result = agent.run(messages=[ChatMessage.from_user(
  "Where can I find the latest meeting notes of project orion?")])

print(result.get("last_message").text)
```

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
