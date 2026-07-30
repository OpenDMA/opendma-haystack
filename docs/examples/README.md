# Examples

This directory contains runnable examples for `opendma-haystack`.

Run examples from the repository root, e.g.:

```bash
uv run python docs/examples/01_basic_usage.py
```

## Tutorial XML Repository Examples

The OpenDMA tutorial defines a portable sample repository in XML.
It is also made available through an OpenDMA REST service, conveniently
packaged as Docker image:

```bash
docker run -p 8080:8080 ghcr.io/opendma/tutorial-xmlrepo:0.8.1
```

Verify the service at:

```text
http://localhost:8080/opendma
```

These examples demonstrate the basic usage of the Document Fetcher with sample
content from this tutorial repository.

Features of the Tutorial XML Repository are limited, but it allows us to
explore the basic functionality of this LangChain integration without complex
setups.

### `01_basic_usage.py`

Fetches one document by document ID from the tutorial repository and prints its
metadata and content.

This is the best first example to run.

### `02_content_states.py`

Shows how `include_no_content=True` affect fetcher output.

### `03_folders.py`

Fetches documents directly contained in a folder.

This example uses `folder_ids` and does not recurse into subfolders.

### `04_folders_recurse.py`

Compares non-recursive and recursive folder loading.

It runs the loader twice:

- once with `recurse_folders=False`
- once with `recurse_folders=True`

### `05_fetcher_pipeline.py`

Demonstrates a pipeline that starts with fetching byte streams from a folder,
routing based on mime type, converting text and PDF files to Documents and
printing out the extracted Document objects at the end of the pipeline.

Run with optional `example` dependencies:

```bash
uv run --extra examples python docs/examples/05_fetcher_pipeline.py
```
