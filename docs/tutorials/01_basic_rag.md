# Basic RAG with OpenDMA

In the first part of this tutorial, we build an indexing pipeline that ingests
PDF files from an Enterprise Content Management (ECM) system and builds a
[document store](https://docs.haystack.deepset.ai/docs/document-store).

The second part builds a simple 2-step RAG pipeline to answer questions about
the OpenDMA specification.

## Tutorial Repository

OpenDMA provides a tutorial repository contains, among other things, the OpenDMA
Specification as a PDF file. This repository comes in a convenient Docker image
exposing the OpenDMA REST API:

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

Install Haystack, the OpenDMA integration, and the pypdf dependencies:

```bash
pip install haystack-ai opendma-haystack pypdf
```

## Indexing Pipeline

### Initialise Embeddings and Vector Store

In this tutorial, we are using OpenAI embeddings and a simple in-memory document
store.

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

Refer to the official Haystack documentation to learn how to replace these
components with different generators or persistent document stores.

### OpenDMA Fetcher

The OpenDMA Fetcher retrieves documents from ECM systems exposed through
the OpenDMA API.

```python
from opendma_haystack import OpenDMAFetcher

OPENDMA_ENDPOINT = "http://localhost:8080/opendma"

fetcher = OpenDMAFetcher(
    endpoint=OPENDMA_ENDPOINT,
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
)
```

### Ingestion Pipeline

We build an ingestion pipeline to process the documents fetched from the ECM
repository through OpenDMA.

The pipeline is split based on the mime type. This pipeline only handles PDF
documents and extracts the text. The text is then split into chunks and written
to the document store.

```python
from haystack import Pipeline
from haystack.components.routers import FileTypeRouter
from haystack.components.converters import PyPDFToDocument
from haystack.components.preprocessors import DocumentSplitter
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.utils import Secret
from haystack.components.writers import DocumentWriter
from haystack.document_stores.types import DuplicatePolicy

indexing_pipeline = Pipeline()
indexing_pipeline.add_component("fetcher", fetcher)
indexing_pipeline.add_component("router", FileTypeRouter(mime_types=["application/pdf"]))
indexing_pipeline.add_component("pdf_converter", PyPDFToDocument())
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
indexing_pipeline.connect("router.application/pdf", "pdf_converter.sources")
indexing_pipeline.connect("pdf_converter.documents", "splitter.documents")
indexing_pipeline.connect("splitter.documents", "embedder.documents")
indexing_pipeline.connect("embedder.documents", "writer.documents")
```

```text
🚅 Components
  - fetcher: OpenDMAFetcher
  - router: FileTypeRouter
  - pdf_converter: PyPDFToDocument
  - splitter: DocumentSplitter
  - embedder: OpenAIDocumentEmbedder
  - writer: DocumentWriter
🛤️ Connections
  - fetcher.streams -> router.sources (list[ByteStream])
  - router.application/pdf -> pdf_converter.sources (list[str | Path | ByteStream])
  - pdf_converter.documents -> splitter.documents (list[Document])
  - splitter.documents -> embedder.documents (list[Document])
  - embedder.documents -> writer.documents (list[Document])
```

The tutorial repository contains several sample documents. We load the full
folder tree below `sample-folder-root`.

```python
indexing_result = indexing_pipeline.run(
    {
        "fetcher": {
            "folder_ids": ["sample-folder-root"],
            "recurse_folders": True,
        },
    },
    include_outputs_from={"splitter"},
)

chunks = indexing_result["splitter"]["documents"]
print(f"Prepared {len(chunks)} chunks from PDF content.\n")
```

```text
Prepared 22 chunks from PDF content.
```

After ingestion, we can inspect the text chunks and their metadata:

```python
import re

def normalize_whitespace(text: str) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


for chunk in chunks[:3]:
    content = normalize_whitespace(chunk.content or "")
    preview = content[:100] + ("..." if len(content) > 100 else "")
    print("Title:", chunk.meta.get("opendma:Title"))
    print("OpenDMA ID:", chunk.meta.get("opendma_id"))
    print("MIME type:", chunk.meta.get("mime_type"))
    print("Content:")
    print(preview)
    print("-" * 80)
```

```text
Title: OpenDMA Specification 0.8
OpenDMA ID: opendma-spec-document
MIME type: application/pdf
Content:
OpenDMA – Open Document Management Architecture Final Version: 0.8 Editor: Stefan Kopf Preface The O...
--------------------------------------------------------------------------------
Title: OpenDMA Specification 0.8
OpenDMA ID: opendma-spec-document
MIME type: application/pdf
Content:
scalar values or un-typed references to other objects. Both may either be single valued or multi val...
--------------------------------------------------------------------------------
Title: OpenDMA Specification 0.8
OpenDMA ID: opendma-spec-document
MIME type: application/pdf
Content:
valued data. Multi valued data can neither contain null values as individual elements nor can it be ...
--------------------------------------------------------------------------------
```

## RAG Pipeline

Now that we have prepared our document store, we can start building our actual
RAG pipeline.

```python
from haystack.dataclasses import ChatMessage
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack.components.builders import ChatPromptBuilder
from haystack.components.generators.chat import OpenAIChatGenerator


prompt_template = [
    ChatMessage.from_system(
        "You answer questions about OpenDMA. "
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
    InMemoryEmbeddingRetriever(document_store=document_store, top_k=3),
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

```text
🚅 Components
  - query_embedder: OpenAITextEmbedder
  - retriever: InMemoryEmbeddingRetriever
  - prompt_builder: ChatPromptBuilder
  - llm: OpenAIChatGenerator
🛤️ Connections
  - query_embedder.embedding -> retriever.query_embedding (list[float])
  - retriever.documents -> prompt_builder.documents (list[Document])
  - prompt_builder.prompt -> llm.messages (list[ChatMessage])
```

Now it is time to test what we have built. Let's ask a question about the
OpenDMA specification:

```python
question = "How are objects identified in OpenDMA?"
rag_result = rag_pipeline.run(
    {
        "query_embedder": {"text": question},
        "prompt_builder": {"question": question},
    },
    include_outputs_from={"retriever"},
)

answer = rag_result["llm"]["replies"][0].text

print(f"Question:\n{question}\n")
print(f"Answer:\n{answer}\n")
```

```text
Question:
How are objects identified in OpenDMA?

Answer:
In OpenDMA, objects are identified by a single valued property with the
qualified name `opendma:Id` and the data type "String".
```

We can also inspect the context and look at the individual text snippets that
have been used to generate this answer:

```python
for document in rag_result["retriever"]["documents"]:
    content = normalize_whitespace(document.content or "")
    preview = content[:150] + ("..." if len(content) > 150 else "")
    print("Title:", document.meta.get("opendma:Title"))
    print("Content:")
    print(preview)
    print("-" * 80)
```

```text
Title: OpenDMA Specification 0.8
Content:
OpenDMA – Open Document Management Architecture Final Version: 0.8 Editor: Stefan Kopf Preface
The Open document management architecture (OpenDMA) is ...
--------------------------------------------------------------------------------
Title: OpenDMA Specification 0.8
Content:
operations is not deﬁned. After writing a value for some property, it is not deﬁned that a
following read operation has to return this value or that i...
--------------------------------------------------------------------------------
Title: OpenDMA Specification 0.8
Content:
scalar values or un-typed references to other objects. Both may either be single valued or
multi valued. §2.1 Scalar values The OpenDMA class architec...
--------------------------------------------------------------------------------
```

This is the basic RAG flow: documents are retrieved from the vector store, and
the model generates an answer from the retrieved context.

## Next

In the next tutorial, [Metadata-Aware Retrieval](./02_metadata_aware_retrieval.md), we ingest
data from a real ECM system: Alfresco.

We observe how the quality of the RAG degrades after ingesting more information into
the knowledge base. Additional information about the documents is used to guide retrieval and
increase precision and recall.
