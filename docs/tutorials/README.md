# Tutorials

If you want to follow these tutorials, we recommend [Jupyter Notebooks](https://jupyter.org/). This
interactive environment is a great way to run this code conveniently.

It is also recommended to create a virtual environment to isolate the dependencies you are going to
install from your main Python installation:

```
python -m venv .venv
source .venv/bin/activate          ## Linux / Mac
.venv\Scripts\activate             ## Windows
```

If you are using the jupyter extension in VS Code, make sure to use this virtual environment
for your kernel.

Next, install jupyter notebooks, haystack, pypdf, opendma and the opendma-haystack integration:

```bash
pip install notebook "haystack-ai>=3,<4" "opendma-haystack>=0.2.0" pypdf
```

For each tutorial, you might need to install additional packages.

## [Basic RAG](./01_basic_rag.md)
Load documents from an ECM system through the OpenDMA abstraction, index them,
and use them for question answering.

## [Metadata-Aware Retrieval](./02_metadata_aware_retrieval.md)
Use the additional information available in an ECM system to guide the information retrieval in order
to improve retrieval [precision and recall](https://en.wikipedia.org/wiki/Precision_and_recall).

## [Agentic RAG with Vector Store](./03_agentic_rag_vectorstore.md)
Agentic workflow with an orchestrator responsible for coordinating searches against
the knowledge base. The workflow can run multiple searches until relevant context is found.
