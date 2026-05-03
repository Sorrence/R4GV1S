"""
R4GV1S - Indexer
Reads markdown and YAML files, embeds them, and stores in Qdrant.
"""

import re
import uuid
import yaml
import argparse
from pathlib import Path
from typing import Generator

import ollama as ollama_client
import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from config.settings import settings

qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

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


# ── Embedding ─────────────────────────────────────────────────────────────────
def embed(text: str) -> list[float]:
    if settings.embed_provider == "ollama":
        resp = ollama_client.embed(model=settings.embed_model, input=text)
        return resp.embeddings[0]
    else:
        resp = _embed_client.embeddings.create(input=text, model=settings.embed_model)
        return resp.data[0].embedding


# ── Chunking ──────────────────────────────────────────────────────────────────
def chunk_markdown(text: str, source: str) -> Generator[dict, None, None]:
    sections = re.split(r'\n(?=#{1,3} )', text)
    for section in sections:
        section = section.strip()
        if len(section) < settings.chunk_min_chars:
            continue
        lines = section.splitlines()
        title = lines[0].lstrip('#').strip() if lines else "Untitled"
        if len(section) > settings.chunk_max_chars:
            for i in range(0, len(section), settings.chunk_max_chars):
                sub = section[i:i + settings.chunk_max_chars].strip()
                if len(sub) >= settings.chunk_min_chars:
                    yield {"text": sub, "title": title, "source": source, "type": "markdown"}
        else:
            yield {"text": section, "title": title, "source": source, "type": "markdown"}


def chunk_yaml_cve(data: dict, source: str) -> Generator[dict, None, None]:
    base = f"CVE: {data.get('id','')}\nTitle: {data.get('title','')}\nAffected: {data.get('affected','')}\nSeverity: {data.get('severity','')}\nTags: {', '.join(data.get('tags',[]))}"
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


# ── Indexing ──────────────────────────────────────────────────────────────────
def index_chunks(chunks: list[dict], batch_size: int = 20):
    points = []
    for i, chunk in enumerate(chunks):
        try:
            vector = embed(chunk["text"])
        except Exception as e:
            print(f"  [!] Embed error: {e}")
            continue

        payload = {k: chunk.get(k, "") for k in ["text", "title", "source", "type", "cve_id", "severity"]}
        payload["tags"] = chunk.get("tags", [])

        points.append(PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload))

        if len(points) >= batch_size:
            qdrant.upsert(collection_name=settings.collection_name, points=points)
            points = []
            print(f"  [+] {i+1}/{len(chunks)} chunks indexed", end="\r")

    if points:
        qdrant.upsert(collection_name=settings.collection_name, points=points)

    print(f"  [+] {len(chunks)} chunks done          ")


def index_path(path: str):
    p = Path(path)
    if not p.exists():
        print(f"[x] Not found: {path}")
        return

    files = list(p.rglob("*.md")) + list(p.rglob("*.yaml")) + list(p.rglob("*.yml")) if p.is_dir() else [p]
    print(f"[+] Found {len(files)} files")

    total = 0
    for i, fp in enumerate(files):
        print(f"[{i+1}/{len(files)}] {fp.name}")
        try:
            if fp.suffix == ".md":
                chunks = list(chunk_markdown(fp.read_text(encoding="utf-8", errors="ignore"), str(fp)))
            else:
                with open(fp) as f:
                    data = yaml.safe_load(f)
                chunks = list(chunk_yaml_cve(data, str(fp))) if isinstance(data, dict) else []
        except Exception as e:
            print(f"  [!] {fp.name}: {e}")
            continue

        if chunks:
            index_chunks(chunks)
            total += len(chunks)

    print(f"\n[✓] Total: {total} chunks indexed into '{settings.collection_name}'")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="R4GV1S Indexer")
    sub = parser.add_subparsers(dest="cmd")

    idx = sub.add_parser("index", help="Index a file or directory")
    idx.add_argument("path")

    sub.add_parser("stats", help="Show collection stats")

    rst = sub.add_parser("reset", help="Delete and recreate collection")

    args = parser.parse_args()
    ensure_collection()

    if args.cmd == "index":
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
