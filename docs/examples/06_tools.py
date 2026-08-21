"""
Example demonstrating each tool in the OpenDMAToolset.

Run the tutorial REST service docker container:
```
docker run -p 8080:8080 ghcr.io/opendma/tutorial-xmlrepo:0.8.1
```
It will provide the tutorial XML repository. Make sure that this service is available by opening
http://localhost:8080/opendma
in a web browser.

Run with optional example dependencies:
```
uv run --extra examples python docs/examples/06_tools.py
```
"""

from __future__ import annotations

import json

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


def print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


toolset = OpenDMAToolset(
    endpoint="http://localhost:8080/opendma",
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
    text_extractor=text_extractor,
)

tools = toolset.get_tools()

print("Tools in Toolset")
for tool in tools:
    print(tool.name)

tools_by_name = {tool.name: tool for tool in tools}

print("\nTool `opendma_get_metadata` for `opendma-spec-document`:")
metadata = tools_by_name["opendma_get_metadata"].invoke(
    object_id="opendma-spec-document",
)
print_json(metadata)

print("\nTool `opendma_list_children` for `sample-folder-a`:")
children = tools_by_name["opendma_list_children"].invoke(
    object_id="sample-folder-a",
)
print_json(children)

print("\nTool `opendma_read_text` for `opendma-spec-document`:")
spec_text = tools_by_name["opendma_read_text"].invoke(
    object_id="opendma-spec-document",
)

chunks = spec_text.get("chunks", []) if isinstance(spec_text, dict) else []
print(f"Chunks returned: {len(chunks)}")
print(f"Has more: {spec_text.get('has_more') if isinstance(spec_text, dict) else None}")
for chunk in chunks:
    text = chunk.get("text", "")
    preview = text[:400] + ("..." if len(text) > 400 else "")
    print(f"\nChunk {chunk.get('chunk_index')}:")
    print(preview)
    print("Metadata:")
    print_json(chunk.get("metadata", {}))

print("\nTool `opendma_describe_class` for `tutorial:SampleDocument`:")
tutorial_document = tools_by_name["opendma_describe_class"].invoke(
    type_or_aspect_name="tutorial:SampleDocument",
)
print_json(tutorial_document)
