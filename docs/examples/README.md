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
explore the basic functionality of this Haystack integration without complex
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

## Alfresco Examples

Alfresco Community Edition is available free of charge. We use it to explore
features of this Haystack integration that require a full ECM repository.

Each new setup contains the "Sample: Web Site Design Project" site, which will
be used by these examples.

### Running Alfresco Community Edition

If you do not already have an Alfresco system running, start one with Docker
Compose:

```bash
git clone https://github.com/Alfresco/acs-deployment.git
cd acs-deployment/docker-compose
docker compose -f community-compose.yaml up -d
```

Verify that Alfresco is running by opening:

```text
http://localhost:8080/share
```

The default credentials are: user `admin` and password `admin`

### Running an OpenDMA Endpoint for Alfresco

The quickest way to map Alfresco to the OpenDMA data model and expose an OpenDMA
REST endpoint is to run the [ECI Server](https://github.com/xaldon/eci-server).
It is available free of charge for non-production use.

Start it with Docker Compose:

```bash
git clone https://github.com/xaldon/eci-server.git
cd eci-server/docker_compose
docker compose up -d
```

After the service is running:

1. Open the web UI at `http://localhost:7070`.
2. Initialize the admin account.
3. Accept the license agreement.
4. Install a free-of-charge license key.
5. Navigate to "Admin" > "Connections".
6. Add a new connection to `Alfresco Content Services`.
7. Choose "Automatically detect parameters with Smart Setup" for target server `host.docker.internal`.
8. Save the new connection as `Alfresco @ host.docker.internal`.
9. Navigate to "Admin" > "REST Endpoints".
10. Add a new REST Endpoint.
11. Set the slug to `opendma/alf`.
12. Select the `Alfresco @ host.docker.internal` connection.
13. Keep the proposed "Inbound Authentication" ("HTTP Basic" and "Propagate Inbound").
14. Save the new REST Endpoint

The example expects the OpenDMA endpoint at:

```text
http://localhost:7070/opendma/alf
```

To verify this REST endpoint, you can open `http://localhost:7070/opendma/alf/` (with a trailing slash)
in a web browser and authenticate with your Alfresco credentials (`admin/admin` by default).

### `11_alfresco_fetcher.py`

Fetches all files from the Alfresco "Sample: Web Site Design Project" site
(`swsdp`) with `AlfrescoFetcher` and processes fetched files in a pipeline.

Run with optional `example` dependencies:

```bash
uv run --extra examples python docs/examples/11_alfresco_fetcher.py
```

Looking at the `alfresco:Path` you can see that it includes information from the Wiki
and Links as well, not just files from the Document Library.  

### `12_alfresco_retriever.py`

Performs a full-text search in the Alfresco "Sample: Web Site Design Project" site
(`swsdp`) with `AlfrescoRetriever`, fetches the byte stream of all found files,
and processes fetched files in a pipeline.

Run with optional `example` dependencies:

```bash
uv run --extra examples python docs/examples/12_alfresco_retriever.py
```

## Notes

Examples are intentionally small and print results to the console. They are meant
to show component behavior, not full RAG pipelines.

For package installation, API overview, and content handler guidance, see the
project [README](../../README.md) and [documentation](../README.md).
