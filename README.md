# Socrates Textbook Tutor

An AI-powered interactive tutor for technical textbooks. You ask questions about a book and get answers grounded in its actual contents, with the source passages cited. The longer-term vision is an interactive audiobook: text read aloud while an AI quizzes you, evaluates your answers, and handles follow-up questions conversationally mid-session.

> Currently in active development. See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to run the project locally.

---

## Architecture

```
Socrates/
├── pipeline/       # Python — PDF extraction, embeddings, vector DB ingestion
├── api/            # Python / FastAPI — retrieval + RAG over the vector store
└── mobile/         # React Native / Expo — iOS + Android app (planned)
```

The **pipeline** runs once per textbook to process and index its content into ChromaDB. The **API** serves that indexed content at runtime — semantic search and retrieval-augmented answers. The **mobile app** is the user-facing product (planned).

```
Mobile App / Web (planned)
        ↕
     FastAPI          ← Single Owner of ChromaDB
    ↙      ↘
Claude API   ChromaDB (vector store)
             ↑
      Python pipeline (runs once per book)
```

FastAPI owns ChromaDB directly: the same process loads the embedding model, embeds incoming queries, retrieves chunks, and calls Claude. There's no separate service in front of the vector store — the API layer and the embedding runtime are the same process, so a query is embedded and searched without a cross-language network hop.

---

## Pipeline (Python)

Processes a textbook PDF into a vector database that the API queries at runtime.

**Steps:**
1. `extract.py` — extracts and structures text from the PDF (chapters → sections → body chunks)
2. `embed.py` — generates embeddings for each chunk and loads them into ChromaDB
3. `query.py` — searches the vector DB given a natural-language question (useful for testing without the API)

### Quickstart

```powershell
cd pipeline

# Create a virtual environment (keeps dependencies isolated)
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # macOS/Linux: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Drop your PDF in the pipeline/ directory, then run:
python extract.py --pdf "your-book.pdf" --output chunks.json

# Load chunks into the vector DB (writes to pipeline/chroma_db)
python embed.py --input chunks.json

# Test a query directly against the vector DB
python query.py --question "What is a write-ahead log?"
```

The pipeline writes its ChromaDB data to `pipeline/chroma_db`. That folder is the persistent store the API reads from at runtime.

---

## API (Python / FastAPI)

The runtime read layer. Embeds queries, retrieves passages from ChromaDB, and — for `/ask` — augments a Claude call with the retrieved context. See [api/README.md](./api/README.md) for full detail.

### Quickstart

Two processes: the ChromaDB server, and the API.

```powershell
# 1. Serve the vector DB the pipeline built (run from pipeline/)
cd pipeline
chroma run --port 8001 --path .\chroma_db

# 2. In a second terminal, start the API (run from api/)
cd api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Interactive docs (Swagger): http://localhost:8000/docs

The Anthropic API key (needed only for `/ask`) goes in `api/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### Endpoints

| Endpoint       | Purpose                                                        |
|----------------|---------------------------------------------------------------|
| `POST /search` | Semantic retrieval — returns the most relevant passages       |
| `POST /ask`    | RAG — retrieves, then answers grounded in the passages, cited |
| `GET /health`  | Liveness probe                                                |

---

## Development Status

| Layer            | Status         |
|------------------|----------------|
| Pipeline         | ✅ Working      |
| API (search/ask) | ✅ Working      |
| TTS / audiobook  | 📋 Future      |
| Quizzing         | 📋 Future      |
| Mobile app       | 📋 Planned     |

---

## Tech Stack

| Layer     | Technology                        | Why                                             |
|-----------|-----------------------------------|-------------------------------------------------|
| Pipeline  | Python, pdfplumber, ChromaDB      | Best ecosystem for PDF/ML work                  |
| API       | Python, FastAPI                   | Same runtime as the embedder — single owner of ChromaDB, no cross-language hop |
| Embeddings| sentence-transformers (MiniLM)    | Local, fast, no API cost for retrieval          |
| Vector DB | ChromaDB                          | Local-first, zero infrastructure                |
| LLM       | Claude API (Anthropic)            | Conversational quality, grounded answers        |
| Mobile    | React Native + Expo               | One codebase, existing React knowledge          |
| TTS       | TBD                               | Evaluating options (future)                     |
