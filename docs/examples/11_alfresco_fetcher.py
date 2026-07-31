"""
Basic example of AlfrescoFetcher retrieving all files from the "Sample: Web Site Design
Project" site and processing them in a pipeline.

See docs/examples/README.md for instructions on running Alfresco Community Edition
and the OpenDMA endpoint used by this example.
"""

from __future__ import annotations

from haystack import Pipeline
from haystack.components.converters import HTMLToDocument, PyPDFToDocument, TextFileToDocument
from haystack.components.joiners import DocumentJoiner
from haystack.components.routers import FileTypeRouter
from haystack_integrations.components.converters.docling import DoclingConverter

from opendma_haystack import AlfrescoFetcher

fetcher = AlfrescoFetcher(
    endpoint="http://localhost:7070/opendma/alf",
    username="admin",
    password="admin",
    repository_id="Alfresco",
)

pipeline = Pipeline()
pipeline.add_component("fetcher", fetcher)
pipeline.add_component(
    "router",
    FileTypeRouter(
        mime_types=[
            "text/plain",
            "text/html",
            "application/pdf",
            "application/msword",
        ],
    ),
)
pipeline.add_component("text_converter", TextFileToDocument())
pipeline.add_component("html_converter", HTMLToDocument())
pipeline.add_component("pdf_converter", PyPDFToDocument())
pipeline.add_component("word_converter", DoclingConverter())
pipeline.add_component("joiner", DocumentJoiner())

pipeline.connect("fetcher.streams", "router.sources")
pipeline.connect("router.text/plain", "text_converter.sources")
pipeline.connect("router.text/html", "html_converter.sources")
pipeline.connect("router.application/pdf", "pdf_converter.sources")
pipeline.connect("router.application/msword", "word_converter.sources")
pipeline.connect("text_converter.documents", "joiner.documents")
pipeline.connect("html_converter.documents", "joiner.documents")
pipeline.connect("pdf_converter.documents", "joiner.documents")
pipeline.connect("word_converter.documents", "joiner.documents")

result = pipeline.run(
    {
        "fetcher": {"sites": ["swsdp"]},
    },
    include_outputs_from={"router"},
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
