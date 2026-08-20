# Agentic RAG with Vector Store

This tutorial is a continuation of the previous [Metadata-Aware Retrieval](./02_metadata_aware_retrieval.md).

The previous RAG pipeline followed a straight path by first retrieving context
from a knowledge base and then synthesising a response for the user.

Here, we show an agentic approach where an orchestrator can choose to run multiple
searches against the knowledge base until it has discovered enough information to
respond to the question.

We provide the orchestrator with two tools:
- ``list_sites``: reads available Alfresco sites through the OpenDMA API
- ``search_content``: runs similarity search, optionally restricted to one site

The agent loops between the orchestrator and the tools, with the orchestrator
deciding for its next move:
- List all available sites
- Re-run the search with different query terms
- Run the search against a different site
- Run the search globally against the entire knowledge base
- Respond to the user

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

We use the same OpenAI chat and embedding models as in previous tutorials. For our
knowledge base, we use the in-memory document store.

```python
import getpass
import os
from haystack.document_stores.in_memory import InMemoryDocumentStore

if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter API key for OpenAI: ")

document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")

EMBEDDING_MODEL = "text-embedding-3-large"
CHAT_MODEL = "gpt-4o-mini"
```

## Ingestion

The repository may contain more sites than this RAG application should use.
We define an explicit list of sites in scope and use it both for ingestion
and for filtering the site list exposed to the agent.

We use the `AlfrescoFetcher` as source for the ingestion pipeline.

```python
from opendma_haystack import AlfrescoFetcher

ALFRESCO_ENDPOINT = "http://localhost:7070/opendma/alf"
ALFRESCO_USERNAME = "admin"
ALFRESCO_PASSWORD = "admin"
ALFRESCO_SITES_IN_SCOPE = ["swsdp", "engineering"]

fetcher = AlfrescoFetcher(
    endpoint=ALFRESCO_ENDPOINT,
    username=ALFRESCO_USERNAME,
    password=ALFRESCO_PASSWORD,
    repository_id="Alfresco",
)
```

The pipeline is the same as in the previous tutorial.

```python
from haystack import Document, Pipeline, component
from haystack.components.routers import FileTypeRouter
from haystack.components.converters import HTMLToDocument, PyPDFToDocument, TextFileToDocument
from haystack_integrations.components.converters.docling import DoclingConverter
from haystack.components.preprocessors import DocumentSplitter
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.utils import Secret
from haystack.components.writers import DocumentWriter
from haystack.document_stores.types import DuplicatePolicy

@component
class TextDocumentFilter:
    """Drop documents that cannot be split because they have no text content."""

    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document]) -> dict[str, list[Document]]:
        return {
            "documents": [
                document
                for document in documents
                if document.content is not None and document.content.strip()
            ]
        }

indexing_pipeline = Pipeline()
indexing_pipeline.add_component("fetcher", fetcher)
indexing_pipeline.add_component(
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
indexing_pipeline.add_component("text_converter", TextFileToDocument())
indexing_pipeline.add_component("html_converter", HTMLToDocument())
indexing_pipeline.add_component("pdf_converter", PyPDFToDocument())
indexing_pipeline.add_component("word_converter", DoclingConverter())
indexing_pipeline.add_component("text_filter", TextDocumentFilter())
indexing_pipeline.add_component(
    "splitter",
    DocumentSplitter(split_by="word", split_length=250, split_overlap=40),
)
indexing_pipeline.add_component(
    "embedder",
    OpenAIDocumentEmbedder(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model=EMBEDDING_MODEL,
    ),
)
indexing_pipeline.add_component(
    "writer",
    DocumentWriter(document_store=document_store, policy=DuplicatePolicy.OVERWRITE),
)

indexing_pipeline.connect("fetcher.streams", "router.sources")
indexing_pipeline.connect("router.text/plain", "text_converter.sources")
indexing_pipeline.connect("router.text/html", "html_converter.sources")
indexing_pipeline.connect("router.application/pdf", "pdf_converter.sources")
indexing_pipeline.connect("router.application/msword", "word_converter.sources")
indexing_pipeline.connect("text_converter.documents", "text_filter.documents")
indexing_pipeline.connect("html_converter.documents", "text_filter.documents")
indexing_pipeline.connect("pdf_converter.documents", "text_filter.documents")
indexing_pipeline.connect("word_converter.documents", "text_filter.documents")
indexing_pipeline.connect("text_filter.documents", "splitter.documents")
indexing_pipeline.connect("splitter.documents", "embedder.documents")
indexing_pipeline.connect("embedder.documents", "writer.documents")

for site in ALFRESCO_SITES_IN_SCOPE:
    print(f"Ingesting site: {site}")
    result = indexing_pipeline.run(
        {
            "fetcher": {
                "sites": [site],
            },
        },
        include_outputs_from={"splitter"},
    )
    chunks = result["splitter"]["documents"]
    print(f"Prepared {len(chunks)} chunks from site {site}.\n")

print(f"Document store contains {document_store.count_documents()} chunks.\n")
```

```text
Ingesting site: swsdp
Prepared 22 chunks from site swsdp.

Ingesting site: engineering
Prepared 226 chunks from site engineering.

Document store contains 248 chunks.
```

## Tools

For our tools, we prepare a small helper to get the list of sites from Alfresco.
This list is filtered down to the `ALFRESCO_SITES_IN_SCOPE` which have been
ingested in the knowledge base.

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
```

For our agent, we implement two tools: `list_sites` and `search_content`. In Haystack,
these tools are simple functions annotated as `@tool`.

```python
from typing import Any
import re
from haystack.tools import tool
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever

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

query_embedder = OpenAITextEmbedder(
    api_key=Secret.from_env_var("OPENAI_API_KEY"),
    model=EMBEDDING_MODEL,
)
retriever = InMemoryEmbeddingRetriever(document_store=document_store, top_k=8)

def build_metadata_filter(site: str | None) -> dict[str, Any]:
    """Build a Haystack metadata filter for active Alfresco documents."""
    conditions: list[dict[str, Any]] = [
        {
            "field": "meta.opendma:CheckedOut",
            "operator": "==",
            "value": False,
        },
    ]
    if site:
        conditions.insert(
            0,
            {
                "field": "meta.alfresco:Site",
                "operator": "==",
                "value": site,
            },
        )
    return {"operator": "AND", "conditions": conditions}

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
    """Search indexed Alfresco content. Use site to restrict search to an Alfresco site."""
    site_filter = site.strip() or None
    if site_filter and site_filter not in ALFRESCO_SITES_IN_SCOPE:
        return (
            f"Site {site_filter!r} is not in scope for this RAG application. "
            "Use list_sites to inspect available in-scope sites."
        )

    query_embedding = query_embedder.run(text=query)["embedding"]
    documents = retriever.run(
        query_embedding=query_embedding,
        filters=build_metadata_filter(site_filter),
        top_k=top_k,
    )["documents"]

    if not documents:
        return "No indexed document chunks matched this search."

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
                f"Content:\n{content}"
            )
        )

    return "\n\n---\n\n".join(formatted_results)
```

## Agent

With these two tools, we can define our Agent.

```python
from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator

orchestrator_prompt = """
You answer questions about documents stored in Alfresco.

You have two tools:

- list_sites: use this when the question implies a project, team, department,
  business area, or site, but you do not know which Alfresco site is relevant.
- search_content: use this to search indexed Alfresco document content. Prefer
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

We can see how the orchestrator first decides to get a list of sites and the
`list_sites` tool returns that list:

```text
Message 1: system
You answer questions about documents stored in Alfresco....

--------------------------------------------------------------------------------

Message 2: user
What is the state of localisation of our new website design?

--------------------------------------------------------------------------------

Message 3: assistant
Tool call: list_sites
Args: {}

--------------------------------------------------------------------------------

Message 4: tool
- swsdp: Sample: Web Site Design Project - This is a Sample Alfresco Team site.
- engineering: Engineering - All product engineering related documents
```

Next, the orchestrator decides to run a search scoped to the `swsdp` site with
the query term "localisation of new website design".

The tool returns the search result to the agent.

```text
Message 5: assistant
Tool call: search_content
Args: {'query': 'localisation of new website design', 'site': 'swsdp'}

--------------------------------------------------------------------------------

Message 6: tool
Result 1
Title: Meetings
Site: swsdp
Path: /Company Home/Sites/swsdp/wiki
Content: This wiki page has a summary of project meetings Meeting: 2011-01-27
Key Decisions: - Selected design number 2 - Set budget for images - Reworked project
timeline Full meeting report is here Meeting: 2011-02-03 Key Decisions: - Reviewed
mockup progress - Allocated resources for QA of site - Identified an issue with
domain registration in Hong Kong Full meeting report is here Meeting: 2011-02-10
Key Decisions: - Reviewed progress - Decided to included TCO calculator in phase 1
- Decided to include localisation in phase 1 - Adjusted budgets inline with new
additions Full meeting report is here
---
Result 2
Title: Project Contract.pdf
Site: swsdp
Path: /Company Home/Sites/swsdp/documentLibrary/Agency Files/Contracts
Content: Contract for Redesign of Corporate Web Site Prepared By: Alice Beecher
Moresby, Garland and Wedge 1st February 2011 Contract Company Confidential Table
of Contents Contract for Redesign...
```

With this search result, the orchestrator decides to return the final answer
to the user.

```text
Message 7: assistant
The state of localization for the new website design is currently in the planning
phase. A key decision was made during the meeting on February 10, 2011, to include
localization in the first phase of the project. There is also mention of selecting
a localization agency, which indicates that steps are being taken to ensure that
localization is addressed adequately in the website's development. If you would
like more detailed or specific information about the localization process or any
related actions, please let me know!
```

## Conclusion and Further Reading

This tutorial demonstrates the benefits of using OpenDMA in an agentic RAG
application when your content is stored in an ECM system like Alfresco,
CMOD, Documentum, FileNet P8, Nuxeo, OpenText, and the like.

The additional information contained in these systems, like the site name in Alfresco,
can help the orchestrator choose where and how to search for relevant context.

Haystack provides a wealth of tutorials showing different strategies for
answer generation, agentic chat bots, or applications working on unstructured
data in general.

Head over to the open source [OpenDMA](https://opendma.org) project to learn
how to connect your ECM to Haystack.

The approach demonstrated here requires setting up a vector store in advance. This
can be a very time consuming and expensive operation. Even worse, it might
introduce security and compliance risks as the data in the vector store is no
longer under the access control of your ECM.

An [Agentic RAG with OpenDMA Retriever](./04_agentic_rag_retriever.md) leverages
the full text search capability built into many ECM systems, like Alfresco. With
an agent as orchestrator, the RAG can run multiple keyword based full text
searches to compensate for the lack of similarity search offered by vector stores.
