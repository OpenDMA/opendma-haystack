"""
Example of using OpenDMAFetcher in a Haystack indexing-style pipeline.

OpenDMAFetcher returns ByteStreams, not text Documents. To make content useful for LLMs,
route those ByteStreams to Haystack converters that can parse the underlying formats.

Run the tutorial REST service docker container:
```
docker run -p 8080:8080 ghcr.io/opendma/tutorial-xmlrepo:0.8.1
```
It will provide the tutorial XML repository. Make sure that this service is available by opening
http://localhost:8080/opendma
in a web browser.
"""

from __future__ import annotations

from haystack import Pipeline
from haystack.components.converters import PyPDFToDocument, TextFileToDocument
from haystack.components.joiners import DocumentJoiner
from haystack.components.routers import FileTypeRouter

from opendma_haystack import OpenDMAFetcher

fetcher = OpenDMAFetcher(
    endpoint="http://localhost:8080/opendma",
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
)

pipeline = Pipeline()
pipeline.add_component("fetcher", fetcher)
pipeline.add_component(
    "router",
    FileTypeRouter(
        mime_types=[
            "text/plain",
            "application/pdf",
        ],
    ),
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
    {
        "fetcher": {
            "folder_ids": ["sample-folder-root"],
            "recurse_folders": True,
        },
    }
)

documents = result["joiner"]["documents"]
print(f"Converted {len(documents)} documents")

for document in documents:
    content = document.content or ""
    preview = content[:200] + ("..." if len(content) > 200 else "")
    print(f"ID: {document.id}")
    print(f"Title: {document.meta.get('opendma:Title')}")
    print(f"MIME type: {document.meta.get('mime_type')}")
    print("Content preview:")
    print(preview)
    print(f"{'-' * 80}\n")

unclassified = result["router"].get("unclassified", [])
if unclassified:
    print(f"\nUnclassified streams: {len(unclassified)}")
    for stream in unclassified:
        print(
            f"  ID: {stream.meta.get('opendma_id')}, "
            f"MIME type: {stream.mime_type}, bytes: {len(stream.data)}"
        )
