# OpenDMA Fetcher

`OpenDMAFetcher` is a Haystack component that fetches repository content through
OpenDMA and returns Haystack `ByteStream` objects.

The fetcher does not convert files into text. This matches Haystack's fetcher
model: fetching and conversion are separate steps. Use Haystack converters such
as `TextFileToDocument`, `PyPDFToDocument`, `HTMLToDocument`, or
`DoclingConverter` after the fetcher when you need text `Document` objects for
indexing or RAG.

For installation and a short project overview, see the project
[README](../README.md).

Guided Haystack application tutorials are documented in
[tutorials/README.md](tutorials/README.md).

## Basic Usage

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

result = fetcher.run(targets=["some-document-id"])

for stream in result["streams"]:
    print(stream.mime_type)
    print(stream.meta)
    print(len(stream.data))
```

Each returned `ByteStream` contains:

- `data`: the repository content bytes
- `mime_type`: the MIME type from the OpenDMA primary content element
- `meta`: OpenDMA metadata, including scalar OpenDMA properties and content
  metadata such as `repository_id`, `opendma_id`, `opendma_class`,
  `mime_type`, `content_type`, and `file_name`

The `mime_type` and `content_type` metadata values currently both contain the
MIME type. `mime_type` is the native Haystack field used by `ByteStream` and
file routing components. `content_type` is included as conventional metadata for
code that expects a content-type-like key.

## Fetching Targets

Fetch specific OpenDMA document IDs by passing `targets` to `run()`:

```python
result = fetcher.run(targets=["doc-1", "doc-2"])
```

Target strings are treated as opaque OpenDMA object IDs. They are not parsed as
URIs. For example, a string starting with `opendma://` is still just an object
ID from the fetcher's point of view.

`targets` can also contain Haystack `Document` objects returned by an
OpenDMA retriever. In that case, the fetcher reads `repository_id` and
`opendma_id` from `document.meta`.

```python
retrieval_result = retriever.run(query="contract")
fetch_result = fetcher.run(targets=retrieval_result["documents"])
```

The metadata from input `Document` targets is used only to identify the
repository object. It is not copied to the output `ByteStream`. Output metadata
is extracted from OpenDMA.

## Folder Traversal

Fetch all documents directly contained in folders:

```python
result = fetcher.run(folder_ids=["folder-1"])
```

Set `recurse_folders=True` to include documents in subfolders:

```python
result = fetcher.run(
    folder_ids=["folder-1"],
    recurse_folders=True,
)
```

`targets` and `folder_ids` can be used in the same call:

```python
result = fetcher.run(
    targets=["doc-1", "doc-2"],
    folder_ids=["folder-1"],
    recurse_folders=True,
)
```

The fetcher does not deduplicate results. If the same document is addressed by
multiple inputs, it can appear multiple times in the output.

## Repository Selection

`repository_id` is normally configured on the fetcher:

```python
fetcher = OpenDMAFetcher(
    endpoint="http://localhost:8080/opendma",
    username="admin",
    password="admin",
    repository_id="sample-repo",
)
```

You can also provide `repository_id` per `run()` call:

```python
result = fetcher.run(
    repository_id="sample-repo",
    targets=["doc-1"],
)
```

This is useful when the same component instance is reused in a pipeline where
the repository is selected at runtime.

The effective repository ID is required whenever raw string targets or
`folder_ids` are used. For `Document` targets returned by an OpenDMA retriever,
the repository ID can come from `document.meta["repository_id"]`.

## Missing Content

OpenDMA documents without a primary content element, or whose primary content
element has no content stream, are skipped by default.

Use `include_no_content=True` when you want a placeholder stream for these
documents:

```python
fetcher = OpenDMAFetcher(
    endpoint="http://localhost:8080/opendma",
    username="admin",
    password="admin",
    repository_id="sample-repo",
    include_no_content=True,
)
```

The placeholder is a `ByteStream` with the document metadata and empty data.

There is no `include_unhandled_content` option. The fetcher only returns bytes;
MIME-type support is handled by downstream converters.

## Error Handling

Individual object failures do not have to stop a larger fetch run.

Use `raise_on_error=False` to skip failed objects and continue:

```python
fetcher = OpenDMAFetcher(
    endpoint="http://localhost:8080/opendma",
    username="admin",
    password="admin",
    repository_id="sample-repo",
    raise_on_error=False,
)
```

Use `warn_on_error=False` together with `raise_on_error=False` to continue
without warnings:

```python
fetcher = OpenDMAFetcher(
    ...,
    raise_on_error=False,
    warn_on_error=False,
)
```

## Pipeline Usage

In an indexing pipeline, connect the fetcher to a `FileTypeRouter` and then to
format-specific converters.

```python
from haystack import Pipeline
from haystack.components.converters import PyPDFToDocument, TextFileToDocument
from haystack.components.joiners import DocumentJoiner
from haystack.components.routers import FileTypeRouter
from opendma_haystack import OpenDMAFetcher

fetcher = OpenDMAFetcher(
    endpoint="http://localhost:8080/opendma",
    username="admin",
    password="admin",
    repository_id="sample-repo",
)

pipeline = Pipeline()
pipeline.add_component("fetcher", fetcher)
pipeline.add_component(
    "router",
    FileTypeRouter(mime_types=["text/plain", "application/pdf"]),
)
pipeline.add_component("text_converter", TextFileToDocument())
pipeline.add_component("pdf_converter", PyPDFToDocument())
pipeline.add_component("joiner", DocumentJoiner())

pipeline.connect("fetcher.streams", "router.sources")
pipeline.connect("router.text/plain", "text_converter.sources")
pipeline.connect("router.application/pdf", "pdf_converter.sources")
pipeline.connect("text_converter.documents", "joiner.documents")
pipeline.connect("pdf_converter.documents", "joiner.documents")

result = pipeline.run(
    {"fetcher": {"folder_ids": ["sample-folder-root"], "recurse_folders": True}}
)
documents = result["joiner"]["documents"]
```

Install the optional examples dependencies when using the documented converter
examples:

```bash
uv run --extra examples python docs/examples/05_fetcher_pipeline.py
```

## AlfrescoFetcher

`AlfrescoFetcher` is a convenience subclass for Alfresco repositories exposed
through OpenDMA.

It adds Alfresco-specific defaults:

- `repository_id="Alfresco"`
- `sites`: optional Alfresco site short names

```python
from opendma_haystack import AlfrescoFetcher

fetcher = AlfrescoFetcher(
    endpoint="http://localhost:7070/opendma/alf",
    username="admin",
    password="admin",
)

result = fetcher.run(sites=["swsdp"])
```

When `sites` is set, `AlfrescoFetcher` searches the Alfresco site folders by
short name and recursively fetches all documents below those site folders.
Site traversal is always recursive. The `recurse_folders` parameter only affects
explicit `folder_ids`.

`AlfrescoFetcher` can combine sites, folders, and targets in one run:

```python
result = fetcher.run(
    sites=["swsdp"],
    folder_ids=["some-folder"],
    recurse_folders=False,
    targets=["some-document"],
)
```

For a runnable Alfresco pipeline example, see
[examples/11_alfresco_fetcher.py](examples/11_alfresco_fetcher.py).

## Examples

Runnable examples are documented in [examples/README.md](examples/README.md).

## Development

Contributor setup, test, build, and release commands are documented in
[Development.md](Development.md).
