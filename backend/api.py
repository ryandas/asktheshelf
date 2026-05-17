from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import json
import os

from backend.book_rag import run_agent_streaming

app = FastAPI()

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    async def generate():
        try:
            async for token, docs in run_agent_streaming(request.message, request.thread_id):
                if token:
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                if docs:
                    seen: set[str] = set()
                    sources = []
                    for d in docs:
                        book = Path(d.metadata.get("source", "")).stem
                        if book not in seen:
                            seen.add(book)
                            sources.append({"book": book, "excerpt": d.page_content[:500]})
                    yield f"data: {json.dumps({'type': 'sources', 'content': sources})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
