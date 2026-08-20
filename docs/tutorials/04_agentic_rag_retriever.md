# Agentic RAG using OpenDMA Retriever

The previous tutorials all use a semantic search in a vector store. This
requires to ingest all content in advance, extract text, chunk it, calculate
embeddings and store it in a vector store.

A vector store provides better retrieval results. The original question from
the user might not contain any of the words that appear in text snippets which
are needed to answer this question. A semantic search solves this problem.

The previous [Agentic RAG with Vector Store](./03_agentic_rag_vectorstore.md)
tutorial uses an orchestrator that can decide to run another search with a
different query term. It can perform multiple searches until it has decided
that either enough information has been found to answer the question or to
give up.

This raises an important question: **Do we even need a Vector Store?**

Building this knowledge base is a time consuming and costly task. More
importantly, it introduces new problems. The store needs to be kept up-to-date
with latest changes in the repository. Especially in Enterprise Scenarios,
complex access rights are a key barrier.

If an agentic workflow can perform multiple searches, is it able to formulate
search queries that reveal relevant information even without a semantic search?

> [!NOTE]
> This tutorial uses live LLM calls. Even with `temperature=0`, hosted models can
> change over time and may choose slightly different retrieval queries or produce
> different answer text. The exact output shown below should be treated as one
> representative run.

## Alfresco Repository

This tutorial is using the same Alfresco Repository and OpenDMA endpoint we have
set up during the last tutorial.

Please follow the [Running Alfresco](./02_metadata_aware_retrieval.md#running-alfresco-community-edition)
and [Running an OpenDMA Endpoint](02_metadata_aware_retrieval.md#running-an-opendma-endpoint-for-alfresco)
instructions if you have skipped the previous tutorial. Also make sure to
[add the "Engineering" site](./02_metadata_aware_retrieval.md#adding-more-content) as well.

## Install Dependencies

Install Haystack 3, the OpenDMA integration, pypdf, trafilatura and docling-haystack:

```bash
pip install "haystack-ai>=3,<4" "opendma-haystack>=0.2.0" pypdf trafilatura docling-haystack
```

## Setup

We use the same OpenAI chat model as in previous tutorials. This tutorial does
not use embeddings because retrieval is handled by Alfresco full-text search
through OpenDMA.

```python
import getpass
import os

if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter API key for OpenAI: ")

CHAT_MODEL = "gpt-4o-mini"

ALFRESCO_ENDPOINT = "http://localhost:7070/opendma/alf"
ALFRESCO_USERNAME = "admin"
ALFRESCO_PASSWORD = "admin"
ALFRESCO_SITES_IN_SCOPE = ["swsdp", "engineering"]
```

## How Search Works in Haystack

In the vector store tutorial, the `search_content` tool runs a similarity search
against content that was ingested and converted in advance.

Here, we use the full-text search capability of Alfresco through OpenDMA. In
Haystack, this is a two-step process:

1. `AlfrescoRetriever` searches Alfresco and returns metadata-only Haystack
   `Document` objects. These documents identify matching OpenDMA objects.
2. `OpenDMAFetcher` fetches the binary content for those objects. Haystack
   converters then turn the fetched `ByteStream` objects into text `Document`s.

This follows the Haystack architecture used by repository integrations: the
retriever locates documents, the fetcher retrieves content, and converters parse
the file formats.

## Search Pipeline

The complete search flow looks like this:

```text
AlfrescoRetriever -> OpenDMAFetcher -> FileTypeRouter -> converters -> TextDocumentFilter -> DocumentJoiner
```

The `search_content` tool runs the retriever first. If Alfresco does not return
any search hits, the tool can return a clean "no matches" response to the agent.
Only when the retriever found matching OpenDMA objects do we run the content
pipeline below to fetch and convert those documents.

```python
from haystack import Document, Pipeline, component
from haystack.components.converters import HTMLToDocument, PyPDFToDocument, TextFileToDocument
from haystack.components.joiners import DocumentJoiner
from haystack.components.routers import FileTypeRouter
from haystack_integrations.components.converters.docling import DoclingConverter

from opendma_haystack import AlfrescoRetriever, OpenDMAFetcher


@component
class TextDocumentFilter:
    """Drop documents that do not contain text after conversion."""

    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document]) -> dict[str, list[Document]]:
        return {
            "documents": [
                document
                for document in documents
                if document.content is not None and document.content.strip()
            ]
        }


def build_content_pipeline() -> Pipeline:
    """Build a content pipeline for one agent tool invocation."""
    fetcher = OpenDMAFetcher(
        endpoint=ALFRESCO_ENDPOINT,
        username=ALFRESCO_USERNAME,
        password=ALFRESCO_PASSWORD,
    )

    search_pipeline = Pipeline()
    search_pipeline.add_component("fetcher", fetcher)
    search_pipeline.add_component(
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
    search_pipeline.add_component("text_converter", TextFileToDocument())
    search_pipeline.add_component("html_converter", HTMLToDocument())
    search_pipeline.add_component("pdf_converter", PyPDFToDocument())
    search_pipeline.add_component("word_converter", DoclingConverter())
    search_pipeline.add_component("text_filter", TextDocumentFilter())
    search_pipeline.add_component("joiner", DocumentJoiner())

    search_pipeline.connect("fetcher.streams", "router.sources")
    search_pipeline.connect("router.text/plain", "text_converter.sources")
    search_pipeline.connect("router.text/html", "html_converter.sources")
    search_pipeline.connect("router.application/pdf", "pdf_converter.sources")
    search_pipeline.connect("router.application/msword", "word_converter.sources")
    search_pipeline.connect("text_converter.documents", "text_filter.documents")
    search_pipeline.connect("html_converter.documents", "text_filter.documents")
    search_pipeline.connect("pdf_converter.documents", "text_filter.documents")
    search_pipeline.connect("word_converter.documents", "text_filter.documents")
    search_pipeline.connect("text_filter.documents", "joiner.documents")

    return search_pipeline
```

## Search Tool

The `search_content` tool creates an `AlfrescoRetriever` for the requested site,
runs the Alfresco full-text search, and checks whether any repository objects
matched. It then fetches the matching files, converts them to text, and returns
compact context to the agent.

Compared to vector store retrieval, keyword choice matters more. The agent may
need to retry with simpler or broader terms when Alfresco full-text search does
not return a result.

```python
import re

from haystack.tools import tool


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace for compact console output and tool responses."""
    text = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


@tool
def search_content(
    query: str,
    site: str = "",
    top_k: int = 8,
) -> str:
    """Search Alfresco content. Use site to restrict search to an Alfresco site."""
    site_filter = site.strip() or None
    if site_filter and site_filter not in ALFRESCO_SITES_IN_SCOPE:
        return (
            f"Site {site_filter!r} is not in scope for this RAG application. "
            "Use list_sites to inspect available in-scope sites."
        )

    retriever = AlfrescoRetriever(
        endpoint=ALFRESCO_ENDPOINT,
        username=ALFRESCO_USERNAME,
        password=ALFRESCO_PASSWORD,
        repository_id="Alfresco",
        sites=[site_filter] if site_filter else None,
        top_k=top_k,
    )
    retrieval_result = retriever.run(query=query)
    targets = retrieval_result["documents"]

    if not targets:
        return "No document chunks matched this search."

    content_pipeline = build_content_pipeline()
    result = content_pipeline.run({"fetcher": {"targets": targets}})
    documents = result.get("joiner", {}).get("documents", [])
    if not documents:
        return "No matched documents could be converted to text."

    formatted_results = []
    for index, document in enumerate(documents, start=1):
        content = normalize_whitespace(document.content or "")
        if len(content) > 1200:
            content = content[:1200] + "..."

        formatted_results.append(
            (
                f"Result {index}\n"
                f"Title: {document.meta.get('opendma:Title')}\n"
                f"Site: {document.meta.get('alfresco:Site')}\n"
                f"Path: {document.meta.get('alfresco:Path')}\n"
                f"OpenDMA ID: {document.meta.get('opendma_id')}\n"
                f"Content:\n{content}"
            )
        )

    return "\n\n---\n\n".join(formatted_results)
```

## Tools

We use the same `list_sites` tool as before.

```python
from opendma.api import OdmaId, OdmaObject, OdmaQName
import opendma.remote

def get_property_string(obj: OdmaObject, qname: str) -> str:
    """Read an OpenDMA string property, returning an empty string when absent."""
    prop = obj.get_property(OdmaQName.from_string(qname))
    if prop is None:
        return ""
    value = prop.get_string()
    return value or ""


def load_sites_from_opendma() -> list[dict[str, str]]:
    """Load in-scope Alfresco site metadata through OpenDMA."""
    session = opendma.remote.connect(
        endpoint=ALFRESCO_ENDPOINT,
        username=ALFRESCO_USERNAME,
        password=ALFRESCO_PASSWORD,
    )
    try:
        search_result = session.search(
            OdmaId("Alfresco"),
            OdmaQName.from_string("alfresco:afts"),
            'TYPE:"st:site"',
        )
        discovered_sites = [
            {
                "id": get_property_string(site_obj, "alfresco:cm:name"),
                "title": get_property_string(site_obj, "alfresco:cm:title"),
                "description": get_property_string(site_obj, "alfresco:cm:description"),
            }
            for site_obj in search_result.get_objects()
            if isinstance(site_obj, OdmaObject)
        ]
        return [site for site in discovered_sites if site["id"] in ALFRESCO_SITES_IN_SCOPE]
    finally:
        session.close()

@tool
def list_sites() -> str:
    """Return in-scope Alfresco sites with short name, title, and description."""
    sites = load_sites_from_opendma()
    if not sites:
        return "No Alfresco sites were returned by the OpenDMA endpoint."

    return "\n".join(
        (
            f"- {site['id']}: {site['title'] or site['id']}"
            f" - {site['description'] or 'No description'}"
        )
        for site in sites
    )
```

## Agent

With these two tools, we can define our Agent.

```python
from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret

orchestrator_prompt = """
You answer questions about documents stored in Alfresco.

You have two tools:

- list_sites: use this when the question implies a project, team, department,
  business area, or site, but you do not know which Alfresco site is relevant.
- search_content: use this to search Alfresco document content. Prefer
  a site-restricted search when a relevant site is known.

Use search_content before answering factual questions about repository content.
If search results are weak or irrelevant, search again with a better query,
call list_sites, or retry search_content with a site filter.

Do not answer factual repository questions unless the answer is supported by
retrieved context. If repeated searches do not find enough context, say that the
available context does not contain the answer.
"""

agent = Agent(
    chat_generator=OpenAIChatGenerator(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model=CHAT_MODEL,
        generation_kwargs={"temperature": 0},
    ),
    tools=[list_sites, search_content],
    system_prompt=orchestrator_prompt,
    max_agent_steps=8,
)
```

## Running the agentic RAG

Let's run the agent with a sample question.

We print the messages, tool calls, and tool results produced during the agent run.

```python
from haystack.dataclasses import ChatMessage

question = "What is the state of localisation of our new website design?"
print(f"Question: {question}\n")

result = agent.run(messages=[ChatMessage.from_user(question)])

for index, message in enumerate(result["messages"], start=1):
    print(f"Message {index}: {message.role.value}")

    if message.tool_calls:
        for tool_call in message.tool_calls:
            print(f"Tool call: {tool_call.tool_name}")
            print(f"Args: {tool_call.arguments}")
    elif message.tool_call_result:
        print(normalize_whitespace(str(message.tool_call_result.result))[:1000])
    else:
        print(normalize_whitespace(message.text or "")[:1000])

    print(f"\n{'-' * 80}\n")

print("Final answer:")
print(result["last_message"].text)
print()
print("Tool calls:", result["tool_call_counts"])
print("Agent steps:", result["step_count"])
```

## Investigate agentic RAG steps

We can see the individual steps taken by the orchestrator. Pay attention to the
search tool calls (`Tool call: search_content`).

```text
Question: What is the state of localisation of our new website design?

Message 1: system
You answer questions about documents stored in Alfresco...

--------------------------------------------------------------------------------

Message 2: user
What is the state of localisation of our new website design?

--------------------------------------------------------------------------------

Message 3: assistant
Tool call: list_sites
Args: {}

--------------------------------------------------------------------------------

Message 4: tool
- engineering: Engineering - All product engineering related documents
- swsdp: Sample: Web Site Design Project - This is a Sample Alfresco Team site.

--------------------------------------------------------------------------------

Message 5: assistant
Tool call: search_content
Args: {'query': 'localisation of new website design', 'site': 'swsdp'}

--------------------------------------------------------------------------------

Message 6: tool
No document chunks matched this search.

--------------------------------------------------------------------------------

Message 7: assistant
Tool call: search_content
Args: {'query': 'localization', 'site': 'swsdp'}

--------------------------------------------------------------------------------

Message 8: tool
Result 1
Title: Meeting Notes 2011-02-10.doc
Site: swsdp
Path: /Company Home/Sites/swsdp/documentLibrary/Meeting Notes
OpenDMA ID: node:a8290263-4178-48f5-a0b0-be155a424828
Content:
## Meeting Notes ### Date: 10th February 2011 ### Attendees: Mike Jackson...

--------------------------------------------------------------------------------

Message 9: assistant
The state of localization for the new website design is...

--------------------------------------------------------------------------------

Final answer:
The state of localization for the new website design is mentioned in the meeting notes dated February 10, 2011. Key points include:

- Localization was decided to be included in phase 1 of the project.
- Betty Silver was assigned to select a localization agency by the next meeting.

If you need more specific details or further information, please let me know!

Tool calls: {'list_sites': 1, 'search_content': 2}
Agent steps: 4
```

The agent needs two search attempts to find the relevant information, even
lexical search.

## Conclusion

With an agentic RAG workflow, it is possible to avoid the additional vector store
required for a semantic search.

