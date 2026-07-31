# OpenDMA Retriever

`OpenDMARetriever` is a Haystack component that performs a repository search
through OpenDMA and returns Haystack `Document` objects for the search hits.

The returned documents are metadata-only locator documents. They are designed to
identify matching repository objects, not to contain the full repository file
text. This follows the same split used by Haystack fetcher/retriever
integrations such as Google Drive and Microsoft SharePoint:

- the retriever searches and returns document metadata
- the fetcher uses those metadata documents to fetch the binary content
- Haystack converters transform the binary content into text documents when
  needed

For installation and a short project overview, see the project
[README](../README.md).

Guided Haystack application tutorials are documented in
[tutorials/README.md](tutorials/README.md).

## Basic Usage

Create an `OpenDMARetriever` with the OpenDMA REST endpoint, optional
credentials, repository ID, and query language.

The generic `OpenDMARetriever` passes the input query through unchanged. This
keeps repository-specific query syntax explicit.

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

Use `top_k` to limit how many search result objects are returned:

```python
retriever = OpenDMARetriever(
    ...,
    query_language="opendma:sfts",
    top_k=5,
)
```

## Result Documents

Each result is a Haystack `Document` with metadata extracted from the OpenDMA
object:

- `repository_id`: OpenDMA repository ID
- `opendma_id`: OpenDMA object ID
- `opendma_class`: OpenDMA class name
- scalar OpenDMA properties, keyed by their qualified property names
- content metadata such as `mime_type`, `content_type`, and `file_name` when a
  primary content element is available

The `Document.content` value is a small title-like value derived from metadata.
It is not the full text of the repository document. Use an `OpenDMAFetcher`
after the retriever when you need the actual content.

```python
retrieval_result = retriever.run(query="contract")
fetch_result = fetcher.run(targets=retrieval_result["documents"])
streams = fetch_result["streams"]
```

## Pipeline Usage

The usual content pipeline shape is:

1. Search with an OpenDMA retriever.
2. Fetch the matching repository content with `OpenDMAFetcher`.
3. Route `ByteStream` objects by MIME type.
4. Convert supported files into Haystack text `Document` objects.

```python
from haystack import Pipeline
from haystack.components.converters import PyPDFToDocument, TextFileToDocument
from haystack.components.joiners import DocumentJoiner
from haystack.components.routers import FileTypeRouter
from opendma_haystack import AlfrescoRetriever, OpenDMAFetcher

retriever = AlfrescoRetriever(
    endpoint="http://localhost:7070/opendma/alf",
    username="admin",
    password="admin",
    sites=["swsdp"],
)
fetcher = OpenDMAFetcher(
    endpoint="http://localhost:7070/opendma/alf",
    username="admin",
    password="admin",
)

pipeline = Pipeline()
pipeline.add_component("retriever", retriever)
pipeline.add_component("fetcher", fetcher)
pipeline.add_component(
    "router",
    FileTypeRouter(mime_types=["text/plain", "application/pdf"]),
)
pipeline.add_component("text_converter", TextFileToDocument())
pipeline.add_component("pdf_converter", PyPDFToDocument())
pipeline.add_component("joiner", DocumentJoiner())

pipeline.connect("retriever.documents", "fetcher.targets")
pipeline.connect("fetcher.streams", "router.sources")
pipeline.connect("router.text/plain", "text_converter.sources")
pipeline.connect("router.application/pdf", "pdf_converter.sources")
pipeline.connect("text_converter.documents", "joiner.documents")
pipeline.connect("pdf_converter.documents", "joiner.documents")

result = pipeline.run({"retriever": {"query": "contract"}})
documents = result["joiner"]["documents"]
```

## Options

Required constructor arguments:

- `endpoint`: OpenDMA REST service endpoint
- `repository_id`: ID of the OpenDMA repository
- `query_language`: query language used to execute the input query

Optional arguments:

- `username`: username for authentication, when the OpenDMA endpoint requires it
- `password`: password for authentication, when the OpenDMA endpoint requires it
- `top_k`: maximum number of OpenDMA search result objects to return
- `raise_on_error`: raise exceptions while processing individual search results
  instead of continuing
- `warn_on_error`: emit warnings for skipped search results when
  `raise_on_error` is `False`
- `metadata_fn`: optional callable that can add or override metadata for each
  OpenDMA document

## AlfrescoRetriever

`AlfrescoRetriever` is a convenience retriever for Alfresco repositories exposed
through OpenDMA. It turns the input string into an Alfresco AFTS full-text query
while respecting escaping rules for special characters.

```python
from opendma_haystack import AlfrescoRetriever

retriever = AlfrescoRetriever(
    endpoint="http://localhost:7070/opendma/alf",
    username="admin",
    password="admin",
    sites=["swsdp"],
)

result = retriever.run(query="website design")
```

When `sites` is set, retrieval is restricted to the matching Alfresco site short
names.

`AlfrescoRetriever` supports the same options as `OpenDMARetriever`, with these
defaults and additions:

- `repository_id="Alfresco"`
- `query_language="alfresco:afts"`
- `sites`: optional Alfresco site short names used to restrict retrieval

## FileNetP8Retriever

`FileNetP8Retriever` is a convenience retriever for FileNet P8 repositories
exposed through OpenDMA. It turns the input string into a valid FileNet P8
Content Based Retrieval (CBR) query while respecting escaping rules for special
characters.

```python
from opendma_haystack import FileNetP8Retriever

retriever = FileNetP8Retriever(
    endpoint="http://localhost:8080/opendma/filenet",
    username="admin",
    password="admin",
    repository_id="FileNetP8",
)

result = retriever.run(query="contract invoice")
```

`FileNetP8Retriever` supports the same options as `OpenDMARetriever`, with this
default:

- `query_language="filenetp8:sql"`

## DocumentumRetriever

`DocumentumRetriever` is a convenience retriever for Documentum repositories
exposed through OpenDMA. It turns the input string into a valid Documentum
Full-Text Search query while respecting escaping rules for special characters.

```python
from opendma_haystack import DocumentumRetriever

retriever = DocumentumRetriever(
    endpoint="http://localhost:8080/opendma/documentum",
    username="admin",
    password="admin",
    repository_id="Documentum",
)

result = retriever.run(query="contract invoice")
```

`DocumentumRetriever` supports the same options as `OpenDMARetriever`, with this
default:

- `query_language="dctm:dql"`

## OnBaseRetriever

`OnBaseRetriever` is a convenience retriever for OnBase repositories exposed
through OpenDMA. It turns the input string into a valid OnBase full-text search
query while respecting escaping rules for special characters.

```python
from opendma_haystack import OnBaseRetriever

retriever = OnBaseRetriever(
    endpoint="http://localhost:8080/opendma/onbase",
    username="admin",
    password="admin",
    repository_id="OnBase",
)

result = retriever.run(query="contract invoice")
```

`OnBaseRetriever` supports the same options as `OpenDMARetriever`, with this
default:

- `query_language="onbase:DocumentQuery"`

## Examples

Runnable examples are documented in [examples/README.md](examples/README.md).

For a runnable Alfresco retriever pipeline example, see
[examples/12_alfresco_retriever.py](examples/12_alfresco_retriever.py).

## Development

Contributor setup, test, build, and release commands are documented in
[Development.md](Development.md).
