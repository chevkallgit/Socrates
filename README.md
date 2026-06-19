# Socrates Textbook Tutor

An AI-powered interactive audiobook for technical textbooks. Text is read aloud while an AI quizzes you, evaluates your answers, and answers follow-up questions conversationally mid-session.

> Currently in active development. See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to run the project locally.

---

## Architecture

```
Soctates/
├── pipeline/       # Python — PDF extraction, embeddings, vector DB ingestion
├── api/            # Go — session orchestration, LLM calls, TTS (planned)
└── mobile/         # React Native / Expo — iOS + Android app (planned)
```

The pipeline runs once per textbook to process and index content. The API serves that indexed content at runtime. The mobile app is the user-facing product.

```
Mobile App (React Native)
        ↕
    Go API
    ↙     ↘
LLM API   TTS API
        ↕
 ChromaDB (vector store)
        ↑
 Python pipeline (runs once)
```

---

## Pipeline (Python)

Processes a textbook PDF into a vector database that the Go API queries at runtime.

**Steps:**
1. `extract.py` — extracts and structures text from the PDF (chapters → sections → body chunks)
2. `embed.py` — generates embeddings for each chunk and loads them into ChromaDB
3. `query.py` — searches the vector DB given a natural language question

### Quickstart

```bash
cd pipeline

# Create a virtual environment (keeps dependencies isolated)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Drop your PDF in the pipeline/ directory, then run:
python extract.py --pdf "your-book.pdf" --output chunks.json

# Load chunks into the vector DB
python embed.py --input chunks.json

# Test a query
python query.py --question "What is a write-ahead log?"
```

---

## Development Status

| Layer      | Status      |
|------------|-------------|
| Pipeline   | 🔧 In progress |
| Go API     | 📋 Planned  |
| Mobile app | 📋 Planned  |

---

## Tech Stack

| Layer    | Technology                    | Why                                      |
|----------|-------------------------------|------------------------------------------|
| Pipeline | Python, pdfplumber, ChromaDB  | Best ecosystem for PDF/ML work           |
| API      | Go                            | Fast, excellent HTTP, good for learning  |
| Mobile   | React Native + Expo           | One codebase, existing React knowledge   |
| Vector DB| ChromaDB                      | Local-first, zero infrastructure         |
| LLM      | Claude API (Anthropic)        | Conversational quality, tool use         |
| TTS      | TBD                           | Evaluating options                       |
