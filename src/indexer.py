"""
R4GV1S - Optimized Indexer
Batch embedding + parallel processing for faster indexing.
~5-10x faster than the original single-request indexer.
"""

import re
import uuid
import yaml
import argparse
import concurrent.futures
from pathlib import Path
from typing import Generator
from threading import Lock

import ollama as ollama_client
import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from config.settings import settings

# ── Config ────────────────────────────────────────────────────────────────────
EMBED_BATCH_SIZE  = 32    # Chunk'ları bu kadarını birden embed et
UPSERT_BATCH_SIZE = 64    # Qdrant'a bu kadarını birden yaz
MAX_WORKERS       = 4     # Paralel embed worker sayısı

qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
upsert_lock = Lock()

if settings.embed_provider != "ollama":
    _embed_client = openai.OpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.api_key,
    )


# ── Collection ────────────────────────────────────────────────────────────────
def ensure_collection():
    existing = [c.name for c in qdrant.get_collections().collections]
    if settings.collection_name not in existing:
        qdrant.create_collection(
            collection_name=settings.collection_name,
            vectors_config=VectorParams(size=settings.vector_size, distance=Distance.COSINE),
        )
        print(f"[+] Collection created: {settings.collection_name}")
    else:
        print(f"[~] Collection exists: {settings.collection_name}")


# ── Batch Embedding ───────────────────────────────────────────────────────────
def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a single request."""
    if settings.embed_provider == "ollama":
        resp = ollama_client.embed(model=settings.embed_model, input=texts)
        return resp.embeddings
    else:
        resp = _embed_client.embeddings.create(input=texts, model=settings.embed_model)
        return [r.embedding for r in resp.data]


# ── Chunking ──────────────────────────────────────────────────────────────────
def chunk_markdown(text: str, source: str) -> Generator[dict, None, None]:
    sections = re.split(r'\n(?=#{1,3} )', text)
    for section in sections:
        section = section.strip()
        if len(section) < settings.chunk_min_chars:
            continue

        lines    = section.splitlines()
        raw_title = lines[0].lstrip('#').strip() if lines else ""
        filename  = Path(source).stem.replace('-', ' ').replace('_', ' ')
        title     = f"{filename} — {raw_title}" if raw_title else filename

        if len(section) > settings.chunk_max_chars:
            for i in range(0, len(section), settings.chunk_max_chars):
                sub = section[i:i + settings.chunk_max_chars].strip()
                if len(sub) >= settings.chunk_min_chars:
                    yield {"text": sub, "title": title, "source": source, "type": "markdown"}
        else:
            yield {"text": section, "title": title, "source": source, "type": "markdown"}


def chunk_yaml_cve(data: dict, source: str) -> Generator[dict, None, None]:
    base = (
        f"CVE: {data.get('id','')}\n"
        f"Title: {data.get('title','')}\n"
        f"Affected: {data.get('affected','')}\n"
        f"Severity: {data.get('severity','')}\n"
        f"Tags: {', '.join(data.get('tags',[]))}"
    )
    yield {
        "text":     base.strip(),
        "title":    data.get("title", data.get("id", "Unknown CVE")),
        "source":   source,
        "type":     "cve_info",
        "cve_id":   data.get("id", ""),
        "severity": data.get("severity", ""),
        "tags":     data.get("tags", []),
    }
    for cmd in data.get("commands", []):
        yield {
            "text":     f"CVE: {data.get('id','')} — {cmd.get('description','')}\n{cmd.get('cmd','')}",
            "title":    f"{data.get('id','')} — {cmd.get('description','')}",
            "source":   source,
            "type":     "cve_command",
            "cve_id":   data.get("id", ""),
            "severity": data.get("severity", ""),
            "tags":     data.get("tags", []),
        }


# ── File processing ───────────────────────────────────────────────────────────
def process_file(fp: Path) -> list[dict]:
    try:
        if fp.suffix == ".md":
            return list(chunk_markdown(fp.read_text(encoding="utf-8", errors="ignore"), str(fp)))
        elif fp.suffix in (".yaml", ".yml"):
            with open(fp) as f:
                data = yaml.safe_load(f)
            return list(chunk_yaml_cve(data, str(fp))) if isinstance(data, dict) else []
    except Exception as e:
        print(f"  [!] {fp.name}: {e}")
    return []


# ── Batch indexing ────────────────────────────────────────────────────────────
def index_chunks_batch(chunks: list[dict], total_indexed: list, total_chunks: int):
    """
    Embed chunks in batches, upsert to Qdrant.
    Thread-safe via upsert_lock.
    """
    points = []

    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i:i + EMBED_BATCH_SIZE]
        texts = [c["text"] for c in batch]

        try:
            vectors = embed_batch(texts)
        except Exception as e:
            print(f"  [!] Embed error: {e}")
            continue

        for chunk, vector in zip(batch, vectors):
            payload = {
                "text":     chunk["text"],
                "title":    chunk.get("title", ""),
                "source":   chunk.get("source", ""),
                "type":     chunk.get("type", "markdown"),
                "cve_id":   chunk.get("cve_id", ""),
                "severity": chunk.get("severity", ""),
                "tags":     chunk.get("tags", []),
            }
            points.append(PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload))

        # Upsert when batch is full
        if len(points) >= UPSERT_BATCH_SIZE:
            with upsert_lock:
                qdrant.upsert(collection_name=settings.collection_name, points=points)
                total_indexed[0] += len(points)
                print(f"  [+] {total_indexed[0]}/{total_chunks} indexed", end="\r")
            points = []

    # Remaining
    if points:
        with upsert_lock:
            qdrant.upsert(collection_name=settings.collection_name, points=points)
            total_indexed[0] += len(points)
            print(f"  [+] {total_indexed[0]}/{total_chunks} indexed", end="\r")


# ── Main index function ───────────────────────────────────────────────────────
def index_path(path: str):
    p = Path(path)
    if not p.exists():
        print(f"[x] Not found: {path}")
        return

    files = (
        list(p.rglob("*.md")) + list(p.rglob("*.yaml")) + list(p.rglob("*.yml"))
        if p.is_dir() else [p]
    )
    print(f"[+] Found {len(files)} files")

    # Process files in parallel to extract chunks
    all_chunks = []
    print("[~] Reading and chunking files...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_file, fp): fp for fp in files}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            chunks = future.result()
            all_chunks.extend(chunks)
            done += 1
            print(f"  [~] {done}/{len(files)} files chunked ({len(all_chunks)} chunks)", end="\r")

    print(f"\n[+] Total chunks to index: {len(all_chunks)}")

    if not all_chunks:
        print("[!] No chunks found.")
        return

    # Split chunks into worker batches and embed in parallel
    total_indexed = [0]
    chunk_batches = [
        all_chunks[i:i + max(1, len(all_chunks) // MAX_WORKERS)]
        for i in range(0, len(all_chunks), max(1, len(all_chunks) // MAX_WORKERS))
    ]

    print(f"[~] Embedding and indexing with {MAX_WORKERS} workers...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(index_chunks_batch, batch, total_indexed, len(all_chunks))
            for batch in chunk_batches
        ]
        concurrent.futures.wait(futures)

    print(f"\n[✓] Done. {total_indexed[0]} chunks indexed into '{settings.collection_name}'")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    global MAX_WORKERS, EMBED_BATCH_SIZE
    parser = argparse.ArgumentParser(description="R4GV1S Indexer (optimized)")
    sub = parser.add_subparsers(dest="cmd")

    idx = sub.add_parser("index", help="Index a file or directory")
    idx.add_argument("path")
    idx.add_argument("--workers", type=int, default=MAX_WORKERS, help="Parallel workers")
    idx.add_argument("--batch",   type=int, default=EMBED_BATCH_SIZE, help="Embed batch size")

    sub.add_parser("stats",  help="Show collection stats")
    sub.add_parser("reset",  help="Delete and recreate collection")

    args = parser.parse_args()
    ensure_collection()

    if args.cmd == "index":
        MAX_WORKERS      = args.workers
        EMBED_BATCH_SIZE = args.batch
        index_path(args.path)

    elif args.cmd == "stats":
        info = qdrant.get_collection(settings.collection_name)
        print(f"[+] Vectors: {info.points_count}")

    elif args.cmd == "reset":
        confirm = input("[!] This will delete all data. Type 'yes' to confirm: ")
        if confirm == "yes":
            qdrant.delete_collection(settings.collection_name)
            ensure_collection()
            print("[+] Collection reset.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
