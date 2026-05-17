# asktheshelf

A RAG-powered chatbot that lets you query your technical book collection using natural language. Ask questions about Data Engineering and Apache Spark — answers are grounded in your PDF library with source citations.

## Stack

- **Backend** — FastAPI + LangChain agent (Claude) + Qdrant vector store
- **Frontend** — Next.js 16, React 19, Tailwind CSS 4
- **Embeddings** — `sentence-transformers/all-mpnet-base-v2` (CPU)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/yourusername/asktheshelf.git
cd asktheshelf
```

**Backend:**
```bash
cp .env.example .env   # fill in your keys
uv sync
```

**Frontend:**
```bash
cd frontend
cp .env.example .env.local   # set BACKEND_URL if not using default
npm install
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `QDRANT_CLUSTER_ENDPOINT` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key |
| `LIGHT_MODEL` | Claude model ID (e.g. `claude-haiku-4-5-20251001`) |
| `BOOKS_DIR` | Path to directory containing your PDF books (default: `/home/ded/books`) |
| `CORS_ORIGINS` | Comma-separated allowed origins (default: `http://localhost:3000`) |

### 3. Ingest your books

Place PDFs in your `BOOKS_DIR`, then run:

```bash
uv run python -m backend.book_ingestion
```

This is idempotent — re-running only uploads new or missing chunks.

### 4. Run

**Backend:**
```bash
uv run uvicorn backend.api:app --port 8001 --reload
```

**Frontend:**
```bash
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).
