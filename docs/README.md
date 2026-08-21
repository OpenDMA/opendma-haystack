# Documentation

This page explains how to use `opendma-haystack` in Haystack applications.

For installation and a short project overview, see the project
[README](../README.md).

## Core Concepts

[OpenDMA](https://opendma.org/) provides a uniform API for Enterprise Content Management (ECM) and
document management repositories. It supports Alfresco, CMOD (Content Manager
OnDemand), Documentum, FileNet P8, OpenText, OnBase, Nuxeo, SharePoint,
and many more.

`opendma-haystack` provides Haystack components for using OpenDMA as an
enterprise content source:

- `OpenDMAFetcher` fetches binary content streams and metadata from OpenDMA and
  returns Haystack `ByteStream` objects.
- `AlfrescoFetcher` extends `OpenDMAFetcher` with Alfresco site support.
- `OpenDMARetriever` runs an OpenDMA search and returns metadata-only Haystack
  `Document` objects.
- `AlfrescoRetriever`, `FileNetP8Retriever`, `DocumentumRetriever`, and
  `OnBaseRetriever` build repository-specific full-text search queries.

The fetcher and retriever have intentionally different roles. A fetcher obtains
repository content. A retriever searches a repository and returns enough
metadata to identify matching repository documents. To turn repository files
into text for RAG, connect a fetcher to Haystack converters such as
`TextFileToDocument`, `PyPDFToDocument`, `HTMLToDocument`, or
`DoclingConverter`.

`OpenDMAToolset` provides a set of tools to be used by tool-calling agents to
navigate around the repository, investigate the data model and read sections of
documents.

## [OpenDMAFetcher](./Fetcher.md)

Create an `OpenDMAFetcher` with the OpenDMA REST endpoint, optional
credentials, and a repository ID.

```python
from opendma_haystack import OpenDMAFetcher

fetcher = OpenDMAFetcher(
    endpoint="http://localhost:8080/opendma",
    username="admin",
    password="admin",
    repository_id="my-repository",
)

result = fetcher.run(targets=["hello-world-document"])
streams = result["streams"]
```

See the [OpenDMAFetcher](./Fetcher.md) documentation for target fetching,
folder traversal, Alfresco sites, metadata, and pipeline examples.

## [OpenDMARetriever](./Retriever.md)

Create an `OpenDMARetriever` with the OpenDMA REST endpoint, optional
credentials, repository ID, and query language.

```python
from opendma_haystack import OpenDMARetriever

retriever = OpenDMARetriever(
    endpoint="http://localhost:8080/opendma",
    username="admin",
    password="admin",
    repository_id="Alfresco",
    query_language="alfresco:cmis",
)

result = retriever.run(query="SELECT * FROM cmis:document")
documents = result["documents"]
```

See the [Retriever](./Retriever.md) documentation for search behavior,
metadata-only result documents, and repository-specific retrievers.

## [OpenDMAToolset](./Toolset.md)

`OpenDMAToolset` provides a set of tools to be used by agents.

```python
from opendma_haystack import OpenDMAToolset

toolset = OpenDMAToolset(
    endpoint="http://localhost:8080/opendma",
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
)

tools = toolset.get_tools()

print("Tools in Toolset")
for tool in tools:
    print(tool.name)
```

See the [Toolset](./Toolset.md) documentation for details.

## Examples and Tutorials

Runnable examples are documented in [examples/README.md](examples/README.md).

Guided Haystack application tutorials are documented in
[tutorials/README.md](tutorials/README.md).

## Development

Contributor setup, test, build, and release commands are documented in
[Development.md](Development.md).
