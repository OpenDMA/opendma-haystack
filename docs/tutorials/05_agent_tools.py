"""
Plain script for demonstrating OpenDMAToolset with a Haystack Agent.

Run the tutorial REST service docker container:
```
docker run -p 8080:8080 ghcr.io/opendma/tutorial-xmlrepo:0.8.1
```
It will provide the tutorial XML repository. Make sure that this service is available by opening
http://localhost:8080/opendma
in a web browser.

Run with optional example dependencies:
```
uv run --extra examples python docs/tutorials/05_agent_tools.py
```
"""

from __future__ import annotations

import getpass
import os
import re

from haystack import Document
from haystack.components.agents import Agent
from haystack.components.converters import PyPDFToDocument, TextFileToDocument
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ByteStream, ChatMessage
from haystack.utils import Secret

from opendma_haystack import OpenDMAToolset

if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter API key for OpenAI: ")

CHAT_MODEL = "gpt-4o-mini"


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


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace for compact console output."""
    text = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def print_agent_trace(result: dict[str, object]) -> None:
    """Print messages, tool calls, and tool results produced by the agent."""
    messages = result.get("messages", [])
    if not isinstance(messages, list):
        return

    for index, message in enumerate(messages, start=1):
        if not isinstance(message, ChatMessage):
            continue

        print(f"Message {index}: {message.role.value}")

        if message.tool_calls:
            for tool_call in message.tool_calls:
                print(f"Tool call: {tool_call.tool_name}")
                print(f"Args: {tool_call.arguments}")
        elif message.tool_call_result:
            print(normalize_whitespace(str(message.tool_call_result.result))[:1200])
        else:
            print(normalize_whitespace(message.text or "")[:1200])

        print(f"\n{'-' * 80}\n")


toolset = OpenDMAToolset(
    endpoint="http://localhost:8088/opendma",
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
    text_extractor=text_extractor,
)

system_prompt = """
You answer questions using documents stored in an ECM repository.

In some cases, it is sufficient to locate the relevant documents in the
repository and use the metadata of these documents to answer the users question.

In other cases, the requested information is in the documents and you need to
read the documents to answer the question. Reading documents is much more
expensive than listing children or getting metadata. Use it carefully.

Avoid guessing file names.

Avoid requesting more text chunks than needed.

Use opendma_list_children to find candidate documents.
Use opendma_get_metadata to inspect a candidate document.
Use opendma_read_text to read document text.

The root of the repository has the ID `sample-folder-root`.

Do not answer factual repository questions unless the answer is supported by
tool results. If the repository does not contain enough information, say so.
"""

agent = Agent(
    chat_generator=OpenAIChatGenerator(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model=CHAT_MODEL,
        generation_kwargs={"temperature": 0},
    ),
    tools=toolset,
    system_prompt=system_prompt,
    max_agent_steps=8,
)

question_spec = "Where can I find the latest OpenDMA spec?"
print(f"Question: {question_spec}\n")

result = agent.run(messages=[ChatMessage.from_user(question_spec)])
print_agent_trace(result)

last_message = result.get("last_message")
if isinstance(last_message, ChatMessage):
    print("Final answer:")
    print(last_message.text)

print()
print("Tool calls:", result.get("tool_call_counts"))
print("Agent steps:", result.get("step_count"))

question_editor = "Who is the editor of the latest OpenDMA specification?"
print(f"Question: {question_editor}\n")

result = agent.run(messages=[ChatMessage.from_user(question_editor)])
print_agent_trace(result)

last_message = result.get("last_message")
if isinstance(last_message, ChatMessage):
    print("Final answer:")
    print(last_message.text)

print()
print("Tool calls:", result.get("tool_call_counts"))
print("Agent steps:", result.get("step_count"))
