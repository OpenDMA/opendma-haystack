# OpenDMA Toolset

An OpenDMA Toolset provides a set of tools that can be used by agents
to browse around the repository, explore the data model, and read
sections of documents.

Toolsets consist of:

- `opendma_get_metadata`: get information about an object in the repository
- `opendma_list_children`: list objects in a container (e.g. a folder)
- `opendma_describe_class`: investigate data model in the repository
- `opendma_search`: perform a full-text search
- `opendma_read_text`: read sections of a document

This package offers specialised toolsets for various ECM vendors to cover
platform dependent features, e.g. the Sites concept in Alfresco.

For installation and a short project overview, see the project
[README](../README.md).

Guided Haystack application tutorials are documented in
[tutorials/README.md](tutorials/README.md).

## Basic Usage

Create an `OpenDMAToolset` with the OpenDMA REST endpoint, credentials,
repository ID, and optionally text extractor callback.

```python
from haystack import Document
from haystack.components.converters import PyPDFToDocument, TextFileToDocument
from haystack.dataclasses import ByteStream

from opendma_haystack import OpenDMAToolset

def text_extractor(streams: list[ByteStream]) -> list[Document]:
    """Convert text and PDF ByteStreams into Haystack Documents."""
    text_streams = [
        stream
        for stream in streams
        if stream.mime_type is not None and stream.mime_type.startswith("text/")
    ]
    pdf_streams = [stream for stream in streams if stream.mime_type == "application/pdf"]

    documents: list[Document] = []
    if text_streams:
        documents.extend(TextFileToDocument().run(sources=text_streams)["documents"])
    if pdf_streams:
        documents.extend(PyPDFToDocument().run(sources=pdf_streams)["documents"])
    return documents

toolset = OpenDMAToolset(
    endpoint="http://localhost:8080/opendma",
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
    text_extractor=text_extractor,
)
```

The `endpoint` expects an OpenDMA REST service. The quickest way to map your ECM
to the OpenDMA data model and expose such an endpoint is to run the
[ECI Server](https://github.com/xaldon/eci-server).
It is available free of charge for non-production use.

Documents are read in pages of chunks with a continuation token. To optimise
performance, the toolset caches chunks in memory after the binary data has been
transformed by the callback. This mechanism can be controlled with these
parameters:

- `read_chunk_page_size`: Number of chunks to be returned in a single tool call. Default `3`.
- `read_text_cache_enabled`: Enable chunk caching. Default `True`.
- `read_text_cache_max_objects`: Cache size in number of documents. Default `32`.
- `read_text_cache_ttl_seconds`: Duration in seconds after which documents in cache are re-read. Default 6hrs `21600`.

## Tools

Call `get_tools()` to get the list of Haystack tools:

```python
tools = toolset.get_tools()
tools_by_name = {tool.name: tool for tool in tools}
```

### `opendma_get_metadata`

Gets class, aspect, and scalar metadata for one OpenDMA object.

Input:

- `object_id` required string: OpenDMA object ID.

Output:

- `object_id`: OpenDMA object ID.
- `type_name`: qualified OpenDMA class name.
- `aspect_names`: list of qualified OpenDMA aspect names.
- `name`: display name derived from OpenDMA metadata.
- `metadata`: key/value pairs containing scalar OpenDMA property values.

Example:

```python
metadata = tools_by_name["opendma_get_metadata"].invoke(
    object_id="opendma-spec-document",
)
print(metadata)
```

### `opendma_list_children`

Lists child folders and documents of an OpenDMA folder.

Input:

- `object_id` required string: OpenDMA folder object ID.
- `include_folders` optional boolean: include child folders. Default `True`.
- `include_files` optional boolean: include child documents. Default `True`.
- `name_pattern` optional string: glob-style name pattern applied to child names.
- `continuation_token` optional string: token returned by a previous call.
- `included_metadata` optional list of string: qualified OpenDMA property names to include.

Output:

- `items`: list of matching child objects.
- `has_more`: whether more child objects are available.
- `continuation_token`: token for the next call when `has_more` is true.

Each item contains:

- `object_id`: OpenDMA object ID.
- `type_name`: qualified OpenDMA class name.
- `aspect_names`: list of qualified OpenDMA aspect names.
- `name`: display name derived from OpenDMA metadata.
- `metadata`: selected metadata values.

Example:

```python
children = tools_by_name["opendma_list_children"].invoke(
    object_id="sample-folder-a",
)
print(children)
```

### `opendma_read_text`

Reads transformed text chunks from one OpenDMA document.

Input:

- `object_id` required string: OpenDMA document object ID.
- `chunk_continuation_token` optional string: token returned by a previous call.

Output:

- `chunks`: list of text chunks.
- `has_more`: whether more chunks are available.
- `chunk_continuation_token`: token for the next call when `has_more` is true.

Each chunk contains:

- `text`: transformed text.
- `metadata`: metadata from the Haystack `Document` returned by the text extractor.
- `chunk_index`: zero-based index of the chunk within the source document.

Example:

```python
spec_text = tools_by_name["opendma_read_text"].invoke(
    object_id="opendma-spec-document",
)
print(spec_text)
```

Without a custom `text_extractor`, `opendma_read_text` can only decode textual
byte streams such as `text/plain`, JSON, and XML-like formats. Configure
`text_extractor` when your repositories contain PDF, HTML, Microsoft Office, or
other rich formats.

### `opendma_describe_class`

Describes an OpenDMA type or aspect and its properties.

Input:

- `type_or_aspect_name` required string: qualified OpenDMA type or aspect name.

Output:

- `name`: qualified OpenDMA class or aspect name.
- `kind`: `type` or `aspect`.
- `parent`: qualified parent type name, if present.
- `inherited_properties`: properties inherited from parent types or aspects.
- `declared_properties`: properties declared directly on this type or aspect.

Each property contains:

- `name`: qualified OpenDMA property name.
- `type`: OpenDMA property type.
- `description`: display name or description.
- `required`: whether the property is required.
- `multi_value`: whether the property can contain multiple values.
- `queryable`: whether the property can be used in queries, if known.
- `possible_values`: list of allowed values, if known.

Example:

```python
tutorial_document = tools_by_name["opendma_describe_class"].invoke(
    type_or_aspect_name="tutorial:SampleDocument",
)
print(tutorial_document)
```

### `opendma_search`

Performs a repository search and returns matching OpenDMA objects.
The search backend and query syntax depend on the toolset implementation.

`OpenDMAToolset` itself does not expose `opendma_search`. Use a specialised
toolset such as `AlfrescoToolset`, `FileNetP8Toolset`, `DocumentumToolset`, or
`OnBaseToolset` when repository search should be available to the agent.

Input:

- `full_text` optional string: full-text query.
- `in_folder` optional string: folder object ID used to restrict the search.
- `include_subfolder_in_folder` optional boolean: include subfolders when `in_folder` is set.
- `included_metadata` optional list of string: qualified OpenDMA property names to include.

Output:

- `items`: list of matching objects.
- `has_more`: whether more objects are available.
- `continuation_token`: token for the next call when `has_more` is true.

Each item contains the same fields as `opendma_list_children` items.

Example:

```python
results = tools_by_name["opendma_search"].invoke(
    full_text="contract invoice",
)
print(results)
```

## AlfrescoToolset

`AlfrescoToolset` configures `opendma_search` for Alfresco AFTS and adds the
Alfresco-specific `alfresco_list_sites` tool.

```python
from opendma_haystack import AlfrescoToolset

toolset = AlfrescoToolset(
    endpoint="http://localhost:7070/opendma/alf",
    username="admin",
    password="admin",
    repository_id="Alfresco",
    text_extractor=text_extractor,
)

tools_by_name = {tool.name: tool for tool in toolset.get_tools()}
```

The `endpoint` expects an OpenDMA REST service. The quickest way to map your
Alfresco deployment to the OpenDMA data model and expose such an endpoint is
to run the [ECI Server](https://github.com/xaldon/eci-server).
It is available free of charge for non-production use.

The search tool converts `full_text` into an Alfresco `TEXT` query. If
`in_folder` is set, the search is restricted to direct children of that folder.
Set `include_subfolder_in_folder=True` to include descendants.

```python
results = tools_by_name["opendma_search"].invoke(
    full_text="contract invoice",
    in_folder="node:5515d3e1-bb2a-42ed-833c-52802a367033",
    include_subfolder_in_folder=True,
)
```

Additional tools:

- `alfresco_list_sites`: discover Alfresco sites and their root folder IDs

### `alfresco_list_sites`

Lists Alfresco sites.

Input:

- No input parameters.

Output:

- List of site descriptions.

Each site description contains:

- `short_name`: Alfresco site short name.
- `title`: site title.
- `description`: site description.
- `root_folder_id`: OpenDMA object ID of the site root folder.

Example:

```python
sites = tools_by_name["alfresco_list_sites"].invoke()
print(sites)
```

## FileNetP8Toolset

`FileNetP8Toolset` configures `opendma_search` for FileNet P8 SQL full-text
search.

```python
from opendma_haystack import FileNetP8Toolset

toolset = FileNetP8Toolset(
    endpoint="http://localhost:8080/opendma/filenet",
    username="admin",
    password="admin",
    repository_id="FileNetP8",
    text_extractor=text_extractor,
)
```

The `endpoint` expects an OpenDMA REST service. The quickest way to map your
FileNet P8 deployment to the OpenDMA data model and expose such an endpoint is
to run the [ECI Server](https://github.com/xaldon/eci-server).
It is available free of charge for non-production use.

The search tool splits `full_text` into words, escapes FileNet content-search
special characters, joins the terms with `OR`, and places the result into a
FileNet `CONTAINS` clause.

If `in_folder` is set, it must be an OpenDMA ID backed by a FileNet object store
object ID in this format:

```text
objectstore:<classId>:<objectId>
```

The `<objectId>` part must be a braced FileNet object ID, for example
`{01234567-89AB-CDEF-0123-456789ABCDEF}`. Folder restrictions use `INFOLDER` by
default and `INSUBFOLDER` when `include_subfolder_in_folder=True`.

```python
results = tools_by_name["opendma_search"].invoke(
    full_text="contract invoice",
    in_folder="objectstore:Folder:{01234567-89AB-CDEF-0123-456789ABCDEF}",
    include_subfolder_in_folder=True,
)
```

## DocumentumToolset

`DocumentumToolset` configures `opendma_search` for Documentum DQL full-text
search.

```python
from opendma_haystack import DocumentumToolset

toolset = DocumentumToolset(
    endpoint="http://localhost:8080/opendma/documentum",
    username="admin",
    password="admin",
    repository_id="Documentum",
    text_extractor=text_extractor,
)
```

The `endpoint` expects an OpenDMA REST service. The quickest way to map your
Documentum deployment to the OpenDMA data model and expose such an endpoint is
to run the [ECI Server](https://github.com/xaldon/eci-server).
It is available free of charge for non-production use.

The search tool splits `full_text` into words, escapes DQL string literals,
joins the terms with `OR`, and places the result into a
`SEARCH DOCUMENT CONTAINS` clause.

If `in_folder` is set, it is used as the Documentum object ID in a `FOLDER`
predicate. Set `include_subfolder_in_folder=True` to add `DESCEND`.

```python
results = tools_by_name["opendma_search"].invoke(
    full_text="contract invoice",
    in_folder="0b00000180000123",
    include_subfolder_in_folder=True,
)
```

## OnBaseToolset

`OnBaseToolset` configures `opendma_search` for OnBase `DocumentQuery`
full-text search.

```python
from opendma_haystack import OnBaseToolset

toolset = OnBaseToolset(
    endpoint="http://localhost:8080/opendma/onbase",
    username="admin",
    password="admin",
    repository_id="OnBase",
    text_extractor=text_extractor,
)
```

The `endpoint` expects an OpenDMA REST service. The quickest way to map your
OnBase deployment to the OpenDMA data model and expose such an endpoint is
to run the [ECI Server](https://github.com/xaldon/eci-server).
It is available free of charge for non-production use.

The search tool splits `full_text` into words, joins the terms with `OR`, XML
escapes the result, and places it into `FullTextSearchString`.

The OnBase toolset exposes an OnBase-specific search schema without folder
restriction parameters because OnBase folder restrictions are not available.

```python
results = tools_by_name["opendma_search"].invoke(
    full_text="contract invoice",
)
```
