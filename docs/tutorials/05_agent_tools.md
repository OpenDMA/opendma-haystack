# Tool-Calling Agent with Toolset

In this tutorial, we build a simple tool-calling agent and provide it with the
OpenDMA toolset.

We observe how this agent is using its tools to gather the information required
to answer different questions.

> [!NOTE]
> This tutorial uses live LLM calls. Even with `temperature=0`, hosted models can
> change over time and may choose slightly different retrieval queries or produce
> different answer text. The exact output shown below should be treated as one
> representative run.

## Tutorial Repository

OpenDMA provides a tutorial repository which contains, among other things, the
OpenDMA Specification as a PDF file. This repository comes in a convenient Docker
image exposing the OpenDMA REST API:

```bash
docker run -p 8080:8080 ghcr.io/opendma/tutorial-xmlrepo:0.8.1
```

This allows you to follow the tutorial without preparing a real ECM system like
Alfresco, Documentum, Nuxeo or FileNet.

Make sure that this service is available by opening  (including the trailing slash):

```text
http://localhost:8080/opendma/
```

You can adjust the port if `8080` is already in use.

## Install Dependencies

Install Haystack 3, the OpenDMA integration, and pypdf:

```bash
pip install "haystack-ai>=3,<4" "opendma-haystack>=0.2.0" pypdf
```

## Initialise OpenAI API key

Make sure you have the `OPENAI_API_KEY` environment variable set.

```python
import getpass
import os

if not os.environ.get("OPENAI_API_KEY"):
  os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter API key for OpenAI: ")

CHAT_MODEL = "gpt-4o-mini"
```

## Create the Toolkit

The toolkit is instantiated for an OpenDMA REST endpoint using a fixed account
and repository.

To convert binary content into text chunks, we implement the `text_extractor`
function and provide it to the toolset.

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
    endpoint="http://localhost:8088/opendma",
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
    text_extractor=text_extractor,
)
```

## Define the system prompt

The system prompt steers the reasoning phase and the tools choice. We use the
following for our tutorial.

```python
system_prompt="""
You answer questions using documents stored in an ECM repository.

In some cases, it is sufficient to locate the relevant documents in the
repository and use the metadata of these documents to answer the user’s question.

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
```

## Create the agent loop

With the toolset and this system prompt, we can instantiate the Agent:

```python
from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret

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
```

## Helper function to inspect agent steps

To inspect the steps the agent took, we create a short helper function to
print out all messages.

```python
import re

from haystack.dataclasses import ChatMessage

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
```

## See the agent in action

Now we can start asking different questions and inspect how this agent uses
different tools to handle the request.

### Information about documents

First, let's ask a question that requires the agent to find a document in the
repository.

```python
question_spec = "Where can I find the latest OpenDMA spec?"
print(f"Question: {question_spec}\n")

result = agent.run(messages=[ChatMessage.from_user(question_spec)])
print_agent_trace(result)

last_message = result.get("last_message")
if isinstance(last_message, ChatMessage):
    print("Final answer:")
    print(last_message.text)
```

This prints out the following steps:

```text
Question: Where can I find the latest OpenDMA spec?

Message 1: system
You answer questions using documents stored in an ECM repository...

--------------------------------------------------------------------------------

Message 2: user
Where can I find the latest OpenDMA spec?

--------------------------------------------------------------------------------

Message 3: assistant
Tool call: opendma_list_children
Args: {'object_id': 'sample-folder-root', 'include_files': True}

--------------------------------------------------------------------------------

Message 4: tool
{"items": [
    {"object_id": "sample-folder-a", ...},
    {"object_id": "sample-folder-b", ...},
    {"object_id": ...

--------------------------------------------------------------------------------

Message 5: assistant
You can find the latest OpenDMA specification document titled "OpenDMA Specification 0.8" in the repository. Here are the details: - **Title**: OpenDMA Specification 0.8 - **Version**: 1.0 - **Content Type**: application/pdf If you need to access the document, please let me know!

--------------------------------------------------------------------------------

Final answer:
You can find the latest OpenDMA specification document titled "OpenDMA Specification 0.8" in the repository. Here are the details:

- **Title**: OpenDMA Specification 0.8
- **Version**: 1.0
- **Content Type**: application/pdf
```

The agent first lists the children of the root folder, finds a document in that
listing where the title suggests that it is the requested document, and then
decides to answer to the user.

### Information contained in documents

Now let's ask a question that requires the agent to read a document.

```python
question_editor = "Who is the editor of the latest OpenDMA specification?"
print(f"Question: {question_editor}\n")

result = agent.run(messages=[ChatMessage.from_user(question_editor)])
print_agent_trace(result)

last_message = result.get("last_message")
if isinstance(last_message, ChatMessage):
    print("Final answer:")
    print(last_message.text)
```

As before, the agent first tries to find a relevant document:

```text
Question: Who is the editor of the latest OpenDMA specification?

Message 1: system
You answer questions using documents stored in an ECM repository...

--------------------------------------------------------------------------------

Message 2: user
Who is the editor of the latest OpenDMA specification?

--------------------------------------------------------------------------------

Message 3: assistant
Tool call: opendma_list_children
Args: {'object_id': 'sample-folder-root', 'include_files': True}

--------------------------------------------------------------------------------

Message 4: tool
{"items": ...

--------------------------------------------------------------------------------

Message 5: assistant
Tool call: opendma_get_metadata
Args: {'object_id': 'opendma-spec-document'}

--------------------------------------------------------------------------------

Message 6: tool
{"object_id": "opendma-spec-document", "type_name": "tutorial:SampleDocument",
 "aspect_names": [], "name": "OpenDMA Specification 0.8",...}
```

Once it has identified the relevant document, it reads the text content.

```text
Message 7: assistant
Tool call: opendma_read_text
Args: {'object_id': 'opendma-spec-document'}

--------------------------------------------------------------------------------

Message 8: tool
{"chunks": [{"text": "OpenDMA – Open Document Management...
```

Reading this first chunk is already sufficient to answer the question.

```text
Message 9: assistant
The editor of the latest OpenDMA specification (Version 0.8) is Stefan Kopf.
```
