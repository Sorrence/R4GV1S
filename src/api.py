"""
R4GV1S - FastAPI Backend
SSE streaming chat endpoint.
"""

import json
import asyncio
import os
import sys
from typing import Optional

import ollama as ollama_client
import openai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchText

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import settings

# ── Clients ───────────────────────────────────────────────────────────────────
qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

if settings.llm_provider == "ollama":
    _llm = openai.OpenAI(
        base_url=f"{settings.ollama_base_url}/v1",
        api_key="ollama",
    )
else:
    _llm = openai.OpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.api_key,
    )

# ── Prompt & Tools ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are R4GV1S, an expert penetration testing assistant.

You have access to a `search_knowledge_base` tool backed by HackTricks, PayloadsAllTheThings, Nuclei Templates, and community contributions.

RULES:
- For casual greetings or off-topic messages, respond directly WITHOUT searching.
- For any technical security/pentest question, ALWAYS search before answering.
- Search from multiple angles if needed (2-3 searches max).
- Produce ready-to-use, copy-paste commands and payloads.
- Use {target}, {ip}, {port}, {url} as placeholders.
- Format output in Markdown. Use fenced code blocks with language tags.
- Be concise. No apologies, no filler. Direct answers only."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the pentest knowledge base (HackTricks, PayloadsAllTheThings, Nuclei Templates). "
                "Use English technical terms. Only use for security/pentest topics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query":   {"type": "string", "description": "English technical search query."},
                    "keyword": {"type": "string", "description": "Term that must appear in results (optional)."},
                },
                "required": ["query"],
            },
        },
    }
]

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="R4GV1S API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str
    history: list[dict] = []


# ── Embed ─────────────────────────────────────────────────────────────────────
def embed(text: str) -> list[float]:
    if settings.embed_provider == "ollama":
        resp = ollama_client.embed(model=settings.embed_model, input=text)
        return resp.embeddings[0]
    else:
        resp = _llm.embeddings.create(input=text, model=settings.embed_model)
        return resp.data[0].embedding


# ── Term → source path pattern map ───────────────────────────────────────────
TERM_MAP = {
    "xxe":                   "xxe",
    "xml external":          "xxe",
    "sqli":                  "sql-injection",
    "sql injection":         "sql-injection",
    "xss":                   "xss",
    "cross site scripting":  "xss",
    "ssrf":                  "ssrf",
    "lfi":                   "lfi",
    "rfi":                   "rfi",
    "ssti":                  "ssti",
    "csrf":                  "csrf",
    "path traversal":        "traversal",
    "directory traversal":   "traversal",
    "command injection":     "command-injection",
    "cmdi":                  "command-injection",
    "deserialization":       "deserializ",
    "jwt":                   "jwt",
    "oauth":                 "oauth",
    "privesc":               "privilege-escalation",
    "privilege escalation":  "privilege-escalation",
    "reverse shell":         "reverse-shell",
    "revshell":              "reverse-shell",
    "open redirect":         "open-redirect",
    "prototype pollution":   "prototype-pollution",
    "cors":                  "cors",
    "graphql":               "graphql",
    "websocket":             "websocket",
    "ldap":                  "ldap",
    "xpath":                 "xpath",
    "idor":                  "idor",
    "file upload":           "file-upload",
    "nmap":                  "nmap",
    "sqlmap":                "sqlmap",
    "mimikatz":              "mimikatz",
    "bloodhound":            "bloodhound",
    "linpeas":               "linpeas",
    "winpeas":               "winpeas",
}


def extract_path_keyword(query: str) -> Optional[str]:
    q = query.lower()
    for term, pattern in TERM_MAP.items():
        if term in q:
            return pattern
    return None


# ── Search ────────────────────────────────────────────────────────────────────
def search_knowledge_base(query: str, keyword: Optional[str] = None) -> tuple[str, list[dict]]:
    vector = embed(query)

    # Path-based filter takes priority over generic keyword
    path_kw = extract_path_keyword(query) if not keyword else None
    path_filter = None
    if path_kw:
        path_filter = Filter(
            must=[FieldCondition(key="source", match=MatchText(text=path_kw))]
        )

    # Try path filter first
    results = []
    if path_filter:
        results = qdrant.query_points(
            collection_name=settings.collection_name,
            query=vector,
            limit=settings.top_k,
            query_filter=path_filter,
            with_payload=True,
        ).points

    # Fall back to normal search if not enough results
    if len(results) < 3:
        extra_filter = None
        if keyword:
            extra_filter = Filter(
                must=[FieldCondition(key="text", match=MatchText(text=keyword))]
            )
        normal = qdrant.query_points(
            collection_name=settings.collection_name,
            query=vector,
            limit=settings.top_k,
            query_filter=extra_filter,
            with_payload=True,
        ).points
        seen = {str(r.id) for r in results}
        for r in normal:
            if str(r.id) not in seen:
                results.append(r)
        results = results[:settings.top_k]

    if not results:
        return "No results found.", []

    chunks, output = [], []
    for i, r in enumerate(results, 1):
        title  = r.payload.get("title", "")
        source = r.payload.get("source", "")
        text   = r.payload.get("text", "")[:1000]
        chunks.append({"title": title, "source": source, "score": round(r.score, 3)})
        output.append(f"[{i}] {title} ({source.split('/')[-1]})\n{text}")

    return "\n\n---\n\n".join(output), chunks


# ── SSE Stream ────────────────────────────────────────────────────────────────
async def event_stream(query: str, history: list[dict]):
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": query}]
    )

    all_chunks: list[dict] = []
    call_count = 0

    # Tool calling loop
    while call_count < settings.max_tool_calls:
        response = await asyncio.to_thread(
            _llm.chat.completions.create,
            model=settings.llm_model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=settings.temperature,
        )

        msg = response.choices[0].message

        if not msg.tool_calls:
            break

        messages.append({
            "role":    "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id":   tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            tc_id = f"tc_{call_count}"
            yield f"event: tool_start\ndata: {json.dumps({'id': tc_id, 'query': args.get('query','')})}\n\n"

            result, chunks = await asyncio.to_thread(
                search_knowledge_base,
                query=args.get("query", ""),
                keyword=args.get("keyword"),
            )
            all_chunks.extend(chunks)

            yield f"event: tool_done\ndata: {json.dumps({'id': tc_id})}\n\n"

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            call_count += 1

    # Deduplicate sources
    if all_chunks:
        seen, unique = set(), []
        for c in all_chunks:
            if c["source"] not in seen:
                seen.add(c["source"])
                unique.append(c)
        yield f"event: sources\ndata: {json.dumps(unique)}\n\n"

    # Streaming answer
    response = await asyncio.to_thread(
        _llm.chat.completions.create,
        model=settings.llm_model,
        messages=messages,
        temperature=settings.temperature,
        stream=True,
    )

    # Stream'i async loop'ta oku
    for chunk in response:
        delta = chunk.choices[0].delta
        if delta.content:
            yield f"event: token\ndata: {json.dumps({'text': delta.content})}\n\n"
            # Her token'dan sonra event loop'a dön
            await asyncio.sleep(0)

    yield f"event: done\ndata: {{}}\n\n"
# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        event_stream(req.query, req.history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "provider": settings.llm_provider, "model": settings.llm_model}


@app.get("/")
async def index():
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    return FileResponse(os.path.join(static_dir, "index.html"))


# Serve static files (frontend)
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")
