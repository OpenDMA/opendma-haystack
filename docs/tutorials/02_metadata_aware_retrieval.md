# Metadata-Aware Retrieval

In this tutorial, we start with the same indexing pipeline and 2-step RAG we
have built in the previous [Basic RAG tutorial](./01_basic_rag.md). But this
time, we connect it to a real ECM system.

We choose Alfresco, as it is available at no cost in a community edition and
comes with a convenient Docker Compose deployment.

After ingesting the information from the "Sample: Web Site Design" site and
asking a couple of questions, we extend the knowledge base and ingest more,
similar content. We can observe how this degrades the response quality.

To fix this, we extend the basic RAG and enable it to take additional
information into account, like the Site where the document is stored.

> [!NOTE]
> The example in this tutorial is a bit brittle and might not always work.
> The Alfresco Sample Site is full of "Lorem Ipsum" text making similarity
> search challenging.

## Running Alfresco Community Edition

Alfresco Community Edition is available free of charge. Each new setup contains
the "Sample: Web Site Design Project" site used in this tutorial.

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

The default credentials are:

```text
admin/admin
```

## Running an OpenDMA Endpoint for Alfresco

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

## Install Dependencies

Install Haystack, the OpenDMA integration, pypdf, trafilatura and docling-haystack:

```bash
pip install haystack-ai opendma-haystack pypdf trafilatura docling-haystack
```

## Indexing Pipeline

We use the same embeddings and document store as in the previous example:

```python
import getpass
import os
from haystack.document_stores.in_memory import InMemoryDocumentStore

if not os.environ.get("OPENAI_API_KEY"):
  os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter API key for OpenAI: ")

EMBEDDING_MODEL = "text-embedding-3-large"
CHAT_MODEL = "gpt-4o-mini"

document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")
```

In this tutorial, we use a specialised version of the OpenDMAFetcher which
is capable of understanding Alfresco specific concepts, like sites. We simply
ingest all information from the Sample Site that comes pre-installed with
each new Alfresco instance:

```python
from opendma_haystack import AlfrescoFetcher

fetcher = AlfrescoFetcher(
    endpoint="http://localhost:7070/opendma/alf",
    username="admin",
    password="admin",
)
```

We use the same indexing pipeline as in the last tutorial. This time, we extend
the list of converters to be able to process different file types:

```python
from haystack import Pipeline
from haystack.components.routers import FileTypeRouter
from haystack.components.converters import HTMLToDocument, PyPDFToDocument, TextFileToDocument
from haystack_integrations.components.converters.docling import DoclingConverter
from haystack.components.preprocessors import DocumentSplitter
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.utils import Secret
from haystack.components.writers import DocumentWriter
from haystack.document_stores.types import DuplicatePolicy
from haystack import Document, component


@component
class TextDocumentFilter:
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
```

We run the indexing pipeline for the `swsdp` site.

```python
indexing_result = indexing_pipeline.run(
    {
        "fetcher": {
            "sites": ["swsdp"],
        },
    },
    include_outputs_from={"splitter"},
)

chunks = indexing_result["splitter"]["documents"]
print(f"Prepared {len(chunks)} chunks from Alfresco through OpenDMA.\n")
```

```text
Prepared 22 chunks from Alfresco through OpenDMA.
```

If you want, you can investigate the loaded documents and the content
in the vector store as in the previous tutorial.

## RAG Pipeline

We start with the same 2-step RAG pipeline we built in the previous tutorial,
with the retriever result adjusted to 10 elements (`top_k=10`):

```python
from haystack.dataclasses import ChatMessage
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack.components.builders import ChatPromptBuilder
from haystack.components.generators.chat import OpenAIChatGenerator


prompt_template = [
    ChatMessage.from_system(
        "You answer questions about information stored in a knowledge base. "
        "Use only the provided context. "
        "If the context does not contain the answer, say that you do not know."
    ),
    ChatMessage.from_user(
        """
Question: {{ question }}

Context:
{% for document in documents %}
{{ document.content }}
{% endfor %}
"""
    ),
]

rag_pipeline = Pipeline()
rag_pipeline.add_component(
    "query_embedder",
    OpenAITextEmbedder(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model=EMBEDDING_MODEL,
    ),
)
rag_pipeline.add_component(
    "retriever",
    InMemoryEmbeddingRetriever(document_store=document_store, top_k=10),
)
rag_pipeline.add_component(
    "prompt_builder",
    ChatPromptBuilder(
        template=prompt_template,
        required_variables={"question", "documents"},
    ),
)
rag_pipeline.add_component(
    "llm",
    OpenAIChatGenerator(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model=CHAT_MODEL,
    ),
)

rag_pipeline.connect("query_embedder.embedding", "retriever.query_embedding")
rag_pipeline.connect("retriever.documents", "prompt_builder.documents")
rag_pipeline.connect("prompt_builder.prompt", "llm.messages")
```

## Using our RAG

Let's ask a question about the "Sample: Web Site Design Project" we have
ingested in the vector store.

```python
question_meeting_jan = "Who attended the meeting in January 2011?"
result_meeting_jan = rag_pipeline.run(
    {
        "query_embedder": {"text": question_meeting_jan},
        "prompt_builder": {"question": question_meeting_jan},
    },
    include_outputs_from={"retriever"},
)

answer_meeting_jan = result_meeting_jan["llm"]["replies"][0].text

print(f"Question:\n{question_meeting_jan}\n")
print(f"Answer:\n{answer_meeting_jan}\n")
```

It will print out this result:

```text
Question:
Who attended the meeting in January 2011?

Answer:
The attendees of the meeting on 27th January 2011 were:

- Mike Jackson
- Benjamin Scobell
- Betty Silver
- Jimmy Pitt
- Angela Travers
```

We can also inspect the context and look at the individual text snippets that
have been used to generate this answer:

```python
import re

def normalize_whitespace(text: str) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

for document in result_meeting_jan["retriever"]["documents"][:5]:
    content = normalize_whitespace(document.content or "")
    preview = content[:150] + ("..." if len(content) > 150 else "")
    print("Title:", document.meta.get("opendma:Title"))
    print("Content:")
    print(preview)
    print("-" * 80)
```

```text
Title: Meeting Notes 2011-01-27.doc
Content:
## Meeting Notes ### Date: 27th January 2011 ### Attendees: Mike Jackson Benjamin
Scobell Betty Silver Jimmy Pitt Angela Travers ## Actions: | **Actio...
--------------------------------------------------------------------------------
Title: Meeting Notes 2011-02-03.doc
Content:
## Meeting Notes ### Date: 3rd February 2011 ### Attendees: Mike Jackson Benjamin
Scobell Betty Silver Jimmy Pitt Angela Travers ## Actions: | **Actio...
--------------------------------------------------------------------------------
Title: Meeting Notes 2011-02-10.doc
Content:
## Meeting Notes ### Date: 10th February 2011 ### Attendees: Mike Jackson Benjamin
Scobell Betty Silver Jimmy Pitt Angela Travers Izzy Previn ## Actio...
--------------------------------------------------------------------------------
Title: Meetings
Content:
This wiki page has a summary of project meetings Meeting: 2011-01-27 Key Decisions:
- Selected design number 2 - Set budget for images - Reworked proj...
--------------------------------------------------------------------------------
Title: Milestones
Content:
This wiki page has a list of project milestones | Phase | Description | Target Date |
Actual Date | | 1 | Project Initiation | 10th January 2011 | 10t...
--------------------------------------------------------------------------------
```

The retriever found all three meeting notes and presented these to the LLM to generate the response.  
This allows us to ask also less specific questions like:

```python
question_action_items = "What action items are listed in the meeting notes?"
result_action_items = rag_pipeline.run(
    {
        "query_embedder": {"text": question_action_items},
        "prompt_builder": {"question": question_action_items},
    },
    include_outputs_from={"retriever"},
)

answer_action_items = result_action_items["llm"]["replies"][0].text

print(f"Question:\n{question_action_items}\n")
print(f"Answer:\n{answer_action_items}\n")
```

```text
Question:
What action items are listed in the meeting notes?

Answer:
The action items listed in the meeting notes are:

**Meeting on 27th January 2011:**
1. Draft requirements document - Mike Jackson - Due by 3rd February 2011
2. Confirm budget - Benjamin Scobell - Due at next meeting

**Meeting on 3rd February 2011:**
1. Secure domain name - Mike Jackson - Due by 10th February 2011
2. Select agency - Betty Silver - Due at next meeting

**Meeting on 10th February 2011:**
1. Define TCO calculator spec - Izzy Previn - Due by 15th February 2011
2. Select localization agency - Betty Silver - Due at next meeting
3. Modify budget spread sheet - Mike Jackson - Due by 20th February 2011
```

```python
question_localisation = "What is the state of localisation of our new website design?"
result_localisation = rag_pipeline.run(
    {
        "query_embedder": {"text": question_localisation},
        "prompt_builder": {"question": question_localisation},
    },
    include_outputs_from={"retriever"},
)

answer_localisation = result_localisation["llm"]["replies"][0].text

print(f"Question:\n{question_localisation}\n")
print(f"Answer:\n{answer_localisation}\n")
```

```text
Question:
What is the state of localisation of our new website design?

Answer:
The localisation of the new website design is included in phase 1 of the project.
A localization agency is set to be selected, as per the decisions made during the project meetings.
```

> [!IMPORTANT]  
> The quality and actual text of the answers depend strongly on external factors
> we do not control.  
> We intentionally want this tutorial to be close to real world scenarios rather
> than working in a strictly constrained artificial environment.

This works pretty well so far.

However, this is just a demo scenario and not really comparable to production use cases.
The sample site in Alfresco consists only of a handful of documents, most of them with
little to no content beyond "lorem ipsum". There is not really a haystack where we
need to find our needle in.

## Adding more content

Let's see what happens after ingesting the content of additional sites with similar
content. First, we add an "Engineering" site to Alfresco:

1. Open `http://localhost:8080/share` in a web browser
2. Log in as "admin" with password "admin"
3. Open the "Sites" main menu and select "Create Site"
4. In the dialog, create a "Collaboration Site" with name "Engineering" and set the
   description to "All product engineering related documents"
5. Keep visibility "Public" and create this site
6. In the newly created "Engineering" site, navigate to "Document Library"
7. Upload [this](./sample-files/product-webui-design.txt) text file to the Document
   Library root

We ingest this new site as well into the same vector store:

```python
additional_indexing_result = indexing_pipeline.run(
    {
        "fetcher": {
            "sites": ["engineering"],
        },
    },
    include_outputs_from={"splitter"},
)

chunks = additional_indexing_result["splitter"]["documents"]
print(f"Added {len(chunks)} additional chunks from Engineering site.\n")
```

```text
Added 226 additional chunks from Engineering site.
```

Now we ask the same question again, using a larger knowledge base:

```python
result_localisation_2 = rag_pipeline.run(
    {
        "query_embedder": {"text": question_localisation},
        "prompt_builder": {"question": question_localisation},
    },
    include_outputs_from={"retriever"},
)

answer_localisation_2 = result_localisation_2["llm"]["replies"][0].text

print(f"Question:\n{question_localisation}\n")
print(f"Answer:\n{answer_localisation_2}\n")
```

```text
Question:
What is the state of localisation of our new website design?

Answer:
I do not know.
```

This demonstrates an effect called **retrieval dilution**. Let's investigate the context
retrieved from the vector store:

```python
for document in result_localisation_2["retriever"]["documents"]:
    content = normalize_whitespace(document.content or "")
    preview = content[:150] + ("..." if len(content) > 150 else "")
    print("Title:", document.meta.get("opendma:Title"))
    print("Content:")
    print(preview)
    print("-" * 80)
```

```text
Title: product-webui-design.txt
Content:
state of localisation of the new website design. The new website design is discussed from the
perspective of translation memory. The document repeated...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
refers to localisation, localized user interfaces, language support, website design, interface
consistency, translation workflows, locale management, ...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
current state of localisation of the new website design. The new website design is discussed from
the perspective of continuous delivery. The document...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
website design, interface consistency, translation workflows, locale management, internationalisation,
multilingual content, and the new website redes...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
website design, interface consistency, translation workflows, locale management, internationalisation,
multilingual content, and the new website redes...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
localisation of the new website design, the emphasis is always on possibilities, requirements,
examples, and best practices rather than actual progres...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
the current state of localisation of the new website design. The new website design is discussed
from the perspective of style guides. The document re...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
website design, interface consistency, translation workflows, locale management,
internationalisation, multilingual content, and the new website redes...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
localisation, localized user interfaces, language support, website design, interface consistency,
translation workflows, locale management, internatio...
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Content:
the current state of localisation of the new website design. The new website design is discussed
from the perspective of content modelling. The docume...
--------------------------------------------------------------------------------
```

The new Engineering site contains so many information chunks similar to the
question that the actual relevant meeting notes are no longer within the top
10 chunks retrieved from the vector store.

In this case, the `product-webui-design.txt` document has been specifically
created to cause this.

A real world ECM system contains hundreds of thousands, if not millions of
documents. A company may have numerous teams, all storing their meeting
notes in the same system. It will contain thousands of contracts, agreements,
product specifications, and more.

A plain similarity search in the entire ECM repository is very likely to return
way too many irrelevant text chunks.

## Extending the RAG pipeline with query analysis

Documents loaded through the OpenDMA ECI middleware carry additional information.
For Alfresco, we get the Content Type, additional Aspects, the property values
as well as additional information like the path or the Site.

All of this information is available as `metadata` in the Haystack `Document`s.

```python
print("Imported from Site `Sample: Web Site Design Project`")
print("=" * 80)
for document in indexing_result["splitter"]["documents"][:3]:
    print("Title:", document.meta.get("opendma:Title"))
    print("Site:", document.meta.get("alfresco:Site"))
    print("Path:", document.meta.get("alfresco:Path"))
    print("-" * 80)
print("\nImported from Site `Engineering`")
print("=" * 80)
for document in additional_indexing_result["splitter"]["documents"][:3]:
    print("Title:", document.meta.get("opendma:Title"))
    print("Site:", document.meta.get("alfresco:Site"))
    print("Path:", document.meta.get("alfresco:Path"))
    print("-" * 80)
```

```text
Imported from Site `Sample: Web Site Design Project`
================================================================================
Title: Meetings
Site: swsdp
Path: /Company Home/Sites/swsdp/wiki
--------------------------------------------------------------------------------
Title: Milestones
Site: swsdp
Path: /Company Home/Sites/swsdp/wiki
--------------------------------------------------------------------------------
Title: Project Contract.pdf
Site: swsdp
Path: /Company Home/Sites/swsdp/documentLibrary/Agency Files/Contracts
--------------------------------------------------------------------------------

Imported from Site `Engineering`
================================================================================
Title: product-webui-design.txt
Site: engineering
Path: /Company Home/Sites/engineering/documentLibrary
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Site: engineering
Path: /Company Home/Sites/engineering/documentLibrary
--------------------------------------------------------------------------------
Title: product-webui-design.txt
Site: engineering
Path: /Company Home/Sites/engineering/documentLibrary
--------------------------------------------------------------------------------
```

We can use this information to guide the retrieval process and ultimately get
better results. This is achieved by adding an additional query analysis step in
front of our RAG pipeline.

This step looks at the initial user question and selects a Site where the file
is most likely located. Additionally, this step generates an optimized query
string for the semantic search.

We use OpenDMA to get the list of sites with their descriptions from Alfresco.

```python
from opendma.api import OdmaId, OdmaQName
import opendma.remote

opendma_session = opendma.remote.connect(
    endpoint="http://localhost:7070/opendma/alf",
    username="admin",
    password="admin",
)

sites_search_result = opendma_session.search(
    OdmaId("Alfresco"),
    OdmaQName.from_string("alfresco:afts"),
    'TYPE:"st:site"',
)

sites = [
    {
        "id": site_obj.get_property(
            OdmaQName.from_string("alfresco:cm:name")
        ).get_string(),
        "title": site_obj.get_property(
            OdmaQName.from_string("alfresco:cm:title")
        ).get_string(),
        "description": site_obj.get_property(
            OdmaQName.from_string("alfresco:cm:description")
        ).get_string(),
    }
    for site_obj in sites_search_result.get_objects()
]

opendma_session.close()

for site in sites:
    print(site)
```

```text
{'id': 'swsdp', 'title': 'Sample: Web Site Design Project', 'description': 'This is a Sample Alfresco Team site.'}
{'id': 'engineering', 'title': 'Engineering', 'description': 'All product engineering related documents'}
```

Based on this list of sites, we create a small Haystack component that analyses
the question and produces two values:

1. An optimized query string for semantic search.
2. A metadata filter that restricts retrieval to the selected Alfresco site.

```python
import json
from typing import Any

from haystack import component
from haystack.dataclasses import ChatMessage
from haystack.components.builders import ChatPromptBuilder
from haystack.components.generators.chat import OpenAIChatGenerator


@component
class SearchParameterParser:
    @component.output_types(query=str, filters=dict[str, Any])
    def run(self, replies: list[ChatMessage]) -> dict[str, Any]:
        data = json.loads(replies[0].text or "{}")
        return {
            "query": data["query"],
            "filters": {
                "operator": "AND",
                "conditions": [
                    {
                        "field": "meta.alfresco:Site",
                        "operator": "==",
                        "value": data["site"],
                    },
                    {
                        "field": "meta.opendma:CheckedOut",
                        "operator": "==",
                        "value": False,
                    },
                ],
            },
        }
```

The prompt includes the available sites and asks the model to return strict
JSON. In a production application, you would normally add stronger validation
around the parsed JSON, or use a provider-specific structured output feature.

```python
site_descriptions = "\n".join(
    f"- id: {site['id']}, title: {site['title']}, description: {site['description']}"
    for site in sites
)

query_analysis_template = [
    ChatMessage.from_system(
        "You select the best Alfresco site for answering a question and produce "
        "a focused semantic search query. "
        "Return only compact JSON with keys query and site. "
        "The site value must be one of the listed site ids."
    ),
    ChatMessage.from_user(
        """
Available sites:
{{ site_descriptions }}

Question:
{{ question }}
"""
    ),
]
```

Now we build an extended RAG pipeline. Compared to the previous 2-step RAG,
there is one additional step at the beginning:

```text
question -> query analysis -> embedding retrieval with metadata filter -> response synthesis
```

The analyzed query is embedded. The generated filter is passed into the
`InMemoryEmbeddingRetriever` through its `filters` input socket.

```python
metadata_aware_rag_pipeline = Pipeline()
metadata_aware_rag_pipeline.add_component(
    "query_analysis_prompt_builder",
    ChatPromptBuilder(
        template=query_analysis_template,
        required_variables={"question", "site_descriptions"},
    ),
)
metadata_aware_rag_pipeline.add_component(
    "query_analysis_llm",
    OpenAIChatGenerator(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model=CHAT_MODEL,
        generation_kwargs={"response_format": {"type": "json_object"}},
    ),
)
metadata_aware_rag_pipeline.add_component("search_parameter_parser", SearchParameterParser())
metadata_aware_rag_pipeline.add_component(
    "query_embedder",
    OpenAITextEmbedder(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model=EMBEDDING_MODEL,
    ),
)
metadata_aware_rag_pipeline.add_component(
    "retriever",
    InMemoryEmbeddingRetriever(document_store=document_store, top_k=10),
)
metadata_aware_rag_pipeline.add_component(
    "prompt_builder",
    ChatPromptBuilder(
        template=prompt_template,
        required_variables={"question", "documents"},
    ),
)
metadata_aware_rag_pipeline.add_component(
    "llm",
    OpenAIChatGenerator(
        api_key=Secret.from_env_var("OPENAI_API_KEY"),
        model=CHAT_MODEL,
    ),
)

metadata_aware_rag_pipeline.connect(
    "query_analysis_prompt_builder.prompt",
    "query_analysis_llm.messages",
)
metadata_aware_rag_pipeline.connect(
    "query_analysis_llm.replies",
    "search_parameter_parser.replies",
)
metadata_aware_rag_pipeline.connect(
    "search_parameter_parser.query",
    "query_embedder.text",
)
metadata_aware_rag_pipeline.connect(
    "query_embedder.embedding",
    "retriever.query_embedding",
)
metadata_aware_rag_pipeline.connect(
    "search_parameter_parser.filters",
    "retriever.filters",
)
metadata_aware_rag_pipeline.connect(
    "retriever.documents",
    "prompt_builder.documents",
)
metadata_aware_rag_pipeline.connect(
    "prompt_builder.prompt",
    "llm.messages",
)
```

We can inspect the query analysis and retrieved context by asking Haystack to
include intermediate component outputs in the pipeline result:

```python
result_localisation_3 = metadata_aware_rag_pipeline.run(
    {
        "query_analysis_prompt_builder": {
            "question": question_localisation,
            "site_descriptions": site_descriptions,
        },
        "prompt_builder": {
            "question": question_localisation,
        },
    },
    include_outputs_from={"search_parameter_parser", "retriever"},
)

answer_localisation_3 = result_localisation_3["llm"]["replies"][0].text

print("Analyzed query:")
print("Query:", result_localisation_3["search_parameter_parser"]["query"])
print("Filters:", result_localisation_3["search_parameter_parser"]["filters"])
print()

print(f"Question:\n{question_localisation}\n")
print(f"Answer:\n{answer_localisation_3}\n")
```

```text
Analyzed query:
Query: state of localisation of new website design
Filters: {'operator': 'AND', 'conditions': [{'field': 'meta.alfresco:Site', 'operator': '==', 'value': 'swsdp'},
         {'field': 'meta.opendma:CheckedOut', 'operator': '==', 'value': False}]}

Question:
What is the state of localisation of our new website design?

Answer:
The state of localisation of the new website design is that localization has been
included in phase 1 of the project.
```

We can again inspect the retrieved context:

```python
for document in result_localisation_3["retriever"]["documents"]:
    content = normalize_whitespace(document.content or "")
    preview = content[:150] + ("..." if len(content) > 150 else "")
    print("Title:", document.meta.get("opendma:Title"))
    print("Site:", document.meta.get("alfresco:Site"))
    print("Content:")
    print(preview)
    print("-" * 80)
```

The vector store still contains the Engineering documents that caused retrieval
dilution before. The difference is that retrieval is now constrained by metadata
from the ECM system.

This is the advantage of using OpenDMA as document source for Haystack. The RAG
application does not only receive text chunks. It also receives repository
metadata that can guide retrieval and improve the quality of the generated
answer.
