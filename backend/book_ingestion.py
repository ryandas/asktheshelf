import asyncio
from concurrent.futures import ThreadPoolExecutor
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_community.document_loaders.parsers import TesseractBlobParser
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance
from rich.console import Console
from rich.progress import (
    Progress, TextColumn, BarColumn,
    SpinnerColumn, TimeElapsedColumn,
)
from dotenv import load_dotenv
from pathlib import Path
import builtins
import logging
import sqlite3
import fitz
import uuid
import os

logging.getLogger("langchain_pymupdf4llm").setLevel(logging.ERROR)
logging.getLogger("pymupdf4llm").setLevel(logging.ERROR)
fitz.TOOLS.mupdf_display_warnings(False)

load_dotenv()

console = Console()

# Redirect stray prints through Rich; suppress known noisy OCR messages.
_OCR_NOISE = ('Performing OCR', 'Image too small', 'Line cannot be recognized')
_real_print = builtins.print
def _filtered_print(*args, **kwargs):
    msg = ' '.join(str(a) for a in args)
    if not any(s in msg for s in _OCR_NOISE):
        console.print(*args, **kwargs)
builtins.print = _filtered_print

books_path = Path(os.environ.get('BOOKS_DIR', '/home/ded/books'))
books = list(books_path.glob('*.pdf'))

headers_to_split_on = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]

splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=headers_to_split_on,
    strip_headers=False,
    return_each_line=False,
)

embedder = HuggingFaceEmbeddings(
    model="sentence-transformers/all-mpnet-base-v2",
    model_kwargs={"device": "cpu"},
)

UPLOAD_BATCH_SIZE = 100
BOOK_CONCURRENCY = 3
DB_PATH = Path('ingestion_state.db')
ID_NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')


def chunk_id(book_name: str, chunk_idx: int) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, f"{book_name}:{chunk_idx}"))


# ── Database ──────────────────────────────────────────────────────────────────

def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_chunks (
            chunk_id    TEXT PRIMARY KEY,
            book_name   TEXT NOT NULL,
            chunk_idx   INTEGER,
            uploaded_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS book_totals (
            book_name    TEXT PRIMARY KEY,
            total_chunks INTEGER NOT NULL,
            recorded_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS completed_books (
            book_name    TEXT PRIMARY KEY,
            completed_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def db_get_completed_books(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT book_name FROM completed_books").fetchall()
    return {row[0] for row in rows}


def db_get_uploaded_ids(conn: sqlite3.Connection, book_name: str) -> set:
    rows = conn.execute(
        "SELECT chunk_id FROM uploaded_chunks WHERE book_name = ?", (book_name,)
    ).fetchall()
    return {row[0] for row in rows}


def db_record_total(conn: sqlite3.Connection, book_name: str, total: int):
    conn.execute(
        "INSERT OR REPLACE INTO book_totals (book_name, total_chunks) VALUES (?, ?)",
        (book_name, total),
    )
    conn.commit()


def db_record_batch(conn: sqlite3.Connection, book_name: str, chunk_indices: list[int], chunk_ids: list[str]):
    conn.executemany(
        "INSERT OR IGNORE INTO uploaded_chunks (chunk_id, book_name, chunk_idx) VALUES (?, ?, ?)",
        [(cid, book_name, idx) for cid, idx in zip(chunk_ids, chunk_indices)],
    )
    conn.commit()


def db_mark_book_done(conn: sqlite3.Connection, book_name: str):
    conn.execute("INSERT OR IGNORE INTO completed_books (book_name) VALUES (?)", (book_name,))
    conn.commit()


def db_promote_complete_books(conn: sqlite3.Connection):
    """Promote books to completed if their uploaded chunk count matches the known total."""
    conn.execute("""
        INSERT OR IGNORE INTO completed_books (book_name)
        SELECT bt.book_name
        FROM book_totals bt
        WHERE (
            SELECT COUNT(*) FROM uploaded_chunks uc
            WHERE uc.book_name = bt.book_name
        ) >= bt.total_chunks
    """)
    conn.commit()


# ── Qdrant sync ───────────────────────────────────────────────────────────────

def _scroll_qdrant(client: QdrantClient) -> list[tuple[str, str]]:
    if not client.collection_exists('books'):
        return []
    records = []
    offset = None
    while True:
        results, offset = client.scroll(
            collection_name='books',
            offset=offset,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            cid = str(point.id)
            payload = point.payload or {}
            source = payload.get('metadata', {}).get('source', '')
            book_name = Path(source).name if source else 'unknown'
            records.append((cid, book_name))
        if offset is None:
            break
    return records


async def sync_from_qdrant(
    client: QdrantClient,
    conn: sqlite3.Connection,
    db_lock: asyncio.Lock,
    executor: ThreadPoolExecutor,
):
    console.print("Syncing existing Qdrant points into local DB...")
    loop = asyncio.get_running_loop()
    records = await loop.run_in_executor(executor, _scroll_qdrant, client)
    if not records:
        console.print("  Collection empty or not found, skipping sync.")
        return
    async with db_lock:
        conn.executemany(
            "INSERT OR IGNORE INTO uploaded_chunks (chunk_id, book_name) VALUES (?, ?)",
            records,
        )
        db_promote_complete_books(conn)
    console.print(f"  Synced [bold]{len(records)}[/bold] chunk IDs from Qdrant.")


# ── Chunking ──────────────────────────────────────────────────────────────────

def _load_and_chunk(book: Path, progress: Progress, task: int) -> list:
    with fitz.open(book) as pdf:
        total_pages = len(pdf)

    progress.update(task, total=total_pages, completed=0, extra=f"page 0/{total_pages}")

    loader = PyMuPDF4LLMLoader(
        file_path=book,
        mode='page',
        extract_images=True,
        images_parser=TesseractBlobParser()
    )
    chunks = []
    for page_num, doc in enumerate(loader.lazy_load(), 1):
        page_chunks = splitter.split_text(doc.page_content)
        for chunk in page_chunks:
            chunk.metadata.update(doc.metadata)
        chunks.extend(page_chunks)
        progress.update(task, completed=page_num, extra=f"page {page_num}/{total_pages}")
    return chunks


# ── Progress bar ──────────────────────────────────────────────────────────────

def make_progress() -> Progress:
    return Progress(
        TextColumn("  {task.description:<35}"),
        SpinnerColumn(finished_text="[green]✓[/green]"),
        BarColumn(bar_width=22),
        TextColumn("[dim]{task.fields[extra]}[/dim]"),
        TimeElapsedColumn(),
        console=console,
    )


# ── Book processing ───────────────────────────────────────────────────────────

async def process_book(
    book: Path,
    qdrant: QdrantVectorStore,
    sem: asyncio.Semaphore,
    db_lock: asyncio.Lock,
    conn: sqlite3.Connection,
    completed: set,
    executor: ThreadPoolExecutor,
    progress: Progress,
):
    name = book.stem[:33]
    async with sem:
        if book.name in completed:
            task = progress.add_task(f"[green]{name}", total=1, extra="already done")
            progress.update(task, completed=1)
            return

        task = progress.add_task(f"[cyan]{name}", total=None, extra="chunking…")
        loop = asyncio.get_running_loop()
        chunks = await loop.run_in_executor(executor, _load_and_chunk, book, progress, task)

        async with db_lock:
            db_record_total(conn, book.name, len(chunks))
            uploaded_ids = db_get_uploaded_ids(conn, book.name)

        all_ids = [chunk_id(book.name, i) for i in range(len(chunks))]
        pending = [
            (i, chunks[i], all_ids[i])
            for i in range(len(chunks))
            if all_ids[i] not in uploaded_ids
        ]

        if not pending:
            progress.update(task, total=1, completed=1, extra="all chunks already uploaded")
            async with db_lock:
                db_mark_book_done(conn, book.name)
                completed.add(book.name)
            progress.update(task, description=f"[green]{name}")
            return

        n_batches = (len(pending) + UPLOAD_BATCH_SIZE - 1) // UPLOAD_BATCH_SIZE
        uploaded = 0
        progress.update(task, total=len(pending), completed=0,
                        extra=f"{uploaded}/{len(pending)} chunks  batch 0/{n_batches}")

        for b_num, batch_start in enumerate(range(0, len(pending), UPLOAD_BATCH_SIZE), 1):
            batch_items = pending[batch_start:batch_start + UPLOAD_BATCH_SIZE]
            batch_indices = [item[0] for item in batch_items]
            batch_chunks = [item[1] for item in batch_items]
            batch_ids = [item[2] for item in batch_items]

            await qdrant.aadd_documents(batch_chunks, ids=batch_ids)

            async with db_lock:
                db_record_batch(conn, book.name, batch_indices, batch_ids)

            uploaded += len(batch_items)
            progress.update(task, advance=len(batch_items),
                            extra=f"{uploaded}/{len(pending)} chunks  batch {b_num}/{n_batches}")

        async with db_lock:
            db_mark_book_done(conn, book.name)
            completed.add(book.name)

        progress.update(task, description=f"[green]{name}", extra="done")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    conn = init_db()

    client = QdrantClient(
        url=os.environ['QDRANT_CLUSTER_ENDPOINT'],
        api_key=os.environ['QDRANT_API_KEY'],
    )
    qdrant = QdrantVectorStore(
        client=client,
        collection_name='books',
        embedding=embedder,
        distance=Distance.COSINE,
    )

    sem = asyncio.Semaphore(BOOK_CONCURRENCY)
    db_lock = asyncio.Lock()

    with make_progress() as progress:
        with ThreadPoolExecutor(max_workers=BOOK_CONCURRENCY) as executor:
            await sync_from_qdrant(client, conn, db_lock, executor)
            completed = db_get_completed_books(conn)

            await asyncio.gather(*[
                process_book(book, qdrant, sem, db_lock, conn, completed, executor, progress)
                for book in books
            ])

    conn.close()


asyncio.run(main())
