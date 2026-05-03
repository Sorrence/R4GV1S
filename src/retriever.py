"""
R4GV1S - Retriever + Generator
Agentic RAG with tool calling. Supports both local (Ollama) and cloud (OpenRouter/OpenAI-compatible) LLMs.
"""

import json
import os
from typing import Optional

import ollama as ollama_client
import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchText

from config.settings import settings

# ── Clients ──────────────────────────────────────────────────────────────────
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

# ── System Prompt ─────────────────────────────────────────────────────────────
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
                "Search the pentest knowledge base. "
                "Contains HackTricks, PayloadsAllTheThings, Nuclei Templates, and community notes. "
                "Use English technical terms for best results. "
                "Only use for security/pentest topics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "English technical search query. Be specific.",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "A term that must appear in results (optional).",
                    },
                },
                "required": ["query"],
            },
        },
    }
]


# ── Embedding ─────────────────────────────────────────────────────────────────
def embed(text: str) -> list[float]:
    if settings.embed_provider == "ollama":
        resp = ollama_client.embed(model=settings.embed_model, input=text)
        return resp.embeddings[0]
    else:
        resp = _llm.embeddings.create(input=text, model=settings.embed_model)
        return resp.data[0].embedding


# ── Search ────────────────────────────────────────────────────────────────────
def search_knowledge_base(query: str, keyword: Optional[str] = None) -> tuple[str, list[dict]]:
    vector = embed(query)

    qdrant_filter = None
    if keyword:
        qdrant_filter = Filter(
            must=[FieldCondition(key="text", match=MatchText(text=keyword))]
        )

    results = qdrant.query_points(
        collection_name=settings.collection_name,
        query=vector,
        limit=settings.top_k,
        query_filter=qdrant_filter,
        with_payload=True,
    ).points

    if not results:
        return "No results found for this query.", []

    chunks, output = [], []
    for i, r in enumerate(results, 1):
        title  = r.payload.get("title", "")
        source = r.payload.get("source", "")
        text   = r.payload.get("text", "")[:1000]
        chunks.append({"title": title, "source": source, "score": round(r.score, 3)})
        output.append(f"[{i}] {title} ({source.split('/')[-1]})\n{text}")

    return "\n\n---\n\n".join(output), chunks


# ── Agentic Loop ──────────────────────────────────────────────────────────────
def run_agentic(messages: list[dict]) -> tuple[str, list[dict]]:
    all_chunks: list[dict] = []
    call_count = 0

    while call_count < settings.max_tool_calls:
        response = _llm.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=settings.temperature,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or "", all_chunks

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

            result, chunks = search_knowledge_base(
                query=args.get("query", ""),
                keyword=args.get("keyword"),
            )
            all_chunks.extend(chunks)

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })
            call_count += 1

    # Fallback: answer without tools
    response = _llm.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=settings.temperature,
    )
    return response.choices[0].message.content or "", all_chunks


# ── Public API ────────────────────────────────────────────────────────────────
def ask(
    query: str,
    history: list[dict] | None = None,
) -> tuple[str, list[dict], list[dict]]:
    """
    Full RAG pipeline.
    Returns: (answer, updated_history, used_chunks)
    """
    if history is None:
        history = []

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": query}]
    )

    answer, chunks = run_agentic(messages)

    history = history + [
        {"role": "user",      "content": query},
        {"role": "assistant", "content": answer},
    ]

    return answer, history, chunks
