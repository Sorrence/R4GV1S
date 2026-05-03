#!/usr/bin/env python3
"""
R4GV1S - CLI
Agentic RAG pipeline with relevancy scores and chat history.
"""

import sys
import json
import readline
import argparse
import sys
import os

# Project root'u path'e ekle — config ve src modüllerini bulsun
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import json
import readline
import argparse

from config.settings import settings

# ── Colors ────────────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"
    WHITE  = "\033[97m"

BANNER = f"""
{C.CYAN}{C.BOLD}  ██████╗ ██╗  ██╗ ██████╗ ██╗   ██╗ ██╗███████╗
  ██╔══██╗██║  ██║██╔════╝ ██║   ██║ ██║██╔════╝
  ██████╔╝███████║██║  ███╗██║   ██║ ██║███████╗
  ██╔══██╗╚════██║██║   ██║╚██╗ ██╔╝ ██║╚════██║
  ██║  ██║     ██║╚██████╔╝ ╚████╔╝  ██║███████║
  ╚═╝  ╚═╝     ╚═╝ ╚═════╝   ╚═══╝   ╚═╝╚══════╝{C.RESET}
{C.GRAY}  RAG-based Pentest Assistant — CLI{C.RESET}
"""

HELP = f"""
{C.YELLOW}Commands:{C.RESET}
  {C.CYAN}:help{C.RESET}       Show this message
  {C.CYAN}:clear{C.RESET}      Clear chat history
  {C.CYAN}:history{C.RESET}    Show chat history
  {C.CYAN}:scores{C.RESET}     Toggle relevancy score display (default: on)
  {C.CYAN}:exit{C.RESET}       Quit

{C.YELLOW}Shortcuts:{C.RESET}
  {C.CYAN}↑ / ↓{C.RESET}      Previous/next command
  {C.CYAN}Ctrl+A/E{C.RESET}    Line start/end
  {C.CYAN}Ctrl+C{C.RESET}      Cancel / Quit
"""


# ── Readline ──────────────────────────────────────────────────────────────────
def setup_readline():
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind('"\\e[A": previous-history')
    readline.parse_and_bind('"\\e[B": next-history')
    readline.parse_and_bind('"\\e[C": forward-char')
    readline.parse_and_bind('"\\e[D": backward-char')
    readline.parse_and_bind('"\\C-a": beginning-of-line')
    readline.parse_and_bind('"\\C-e": end-of-line')
    readline.set_history_length(500)


# ── Score bar ─────────────────────────────────────────────────────────────────
def score_bar(score: float, width: int = 12) -> str:
    """Visual bar for relevancy score (0.0 - 1.0)."""
    filled = int(score * width)
    bar    = "█" * filled + "░" * (width - filled)

    if score >= 0.75:
        color = C.GREEN
    elif score >= 0.55:
        color = C.YELLOW
    else:
        color = C.RED

    return f"{color}{bar}{C.RESET} {score:.3f}"


# ── Output ────────────────────────────────────────────────────────────────────
def print_search(query: str, call_num: int):
    print(f"\n  {C.CYAN}[search {call_num}]{C.RESET} {C.DIM}{query}{C.RESET}")


def print_chunks(chunks: list[dict], show_scores: bool):
    """Print retrieved chunks with relevancy scores."""
    if not chunks or not show_scores:
        return

    print(f"\n  {C.GRAY}{'─' * 60}{C.RESET}")
    print(f"  {C.YELLOW}Relevancy Scores{C.RESET}  {C.GRAY}({len(chunks)} chunks){C.RESET}\n")

    seen = set()
    grouped: dict[str, list] = {}

    # Group by search query (we don't have it, group by source dir)
    for c in chunks:
        src = c.get("source", "")
        fname = src.split("/")[-1] if src else "unknown"
        key = "/".join(src.split("/")[-3:-1]) if src else "unknown"  # last 2 dirs
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((fname, c))

    for group, items in grouped.items():
        print(f"  {C.GRAY}{group}/{C.RESET}")
        for fname, c in items:
            score = c.get("score", 0.0)
            title = c.get("title", fname)
            # Truncate long titles
            if len(title) > 45:
                title = title[:42] + "..."
            bar = score_bar(score)
            print(f"    {C.WHITE}{title:<45}{C.RESET}  {bar}")
        print()

    print(f"  {C.GRAY}{'─' * 60}{C.RESET}")


def print_answer(answer: str):
    print()
    # Simple syntax highlight for code blocks
    in_code = False
    for line in answer.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            print(f"  {C.GRAY}{line}{C.RESET}")
            continue
        if in_code:
            print(f"  {C.GREEN}{line}{C.RESET}")
        else:
            # Highlight markdown headers
            if stripped.startswith("## "):
                print(f"  {C.CYAN}{C.BOLD}{line}{C.RESET}")
            elif stripped.startswith("# "):
                print(f"  {C.CYAN}{C.BOLD}{line}{C.RESET}")
            elif stripped.startswith("- ") or stripped.startswith("* "):
                print(f"  {line}")
            else:
                print(f"  {line}")
    print()


def print_error(msg: str):
    print(f"\n  {C.RED}[x]{C.RESET} {msg}\n")


def print_info(msg: str):
    print(f"  {C.GRAY}[~]{C.RESET} {msg}")


# ── Agentic ask with score visibility ────────────────────────────────────────
def ask_with_scores(query: str, history: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """
    Runs the agentic RAG pipeline, printing search queries as they happen.
    Returns (answer, updated_history, all_chunks_with_scores)
    """
    import json
    import ollama as ollama_client
    import openai
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchText

    from config.settings import settings

    qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

    if settings.llm_provider == "ollama":
        llm = openai.OpenAI(
            base_url=f"{settings.ollama_base_url}/v1",
            api_key="ollama",
        )
    else:
        llm = openai.OpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.api_key,
        )

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
                        "query":   {"type": "string"},
                        "keyword": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
        }
    ]

    def embed(text):
        if settings.embed_provider == "ollama":
            resp = ollama_client.embed(model=settings.embed_model, input=text)
            return resp.embeddings[0]
        else:
            resp = llm.embeddings.create(input=text, model=settings.embed_model)
            return resp.data[0].embedding

    def search(query, keyword=None):
        vector = embed(query)
        qfilter = None
        if keyword:
            qfilter = Filter(must=[FieldCondition(key="text", match=MatchText(text=keyword))])
        results = qdrant.query_points(
            collection_name=settings.collection_name,
            query=vector,
            limit=settings.top_k,
            query_filter=qfilter,
            with_payload=True,
        ).points
        if not results:
            return "No results.", []
        chunks, output = [], []
        for i, r in enumerate(results, 1):
            title  = r.payload.get("title", "")
            source = r.payload.get("source", "")
            text   = r.payload.get("text", "")[:1000]
            score  = round(r.score, 3)
            chunks.append({"title": title, "source": source, "score": score})
            output.append(f"[{i}] {title} ({source.split('/')[-1]})\n{text}")
        return "\n\n---\n\n".join(output), chunks

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": query}]
    )

    all_chunks = []
    call_count = 0

    while call_count < settings.max_tool_calls:
        response = llm.chat.completions.create(
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
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            call_count += 1
            print_search(args.get("query", ""), call_count)

            result, chunks = search(args.get("query", ""), args.get("keyword"))
            all_chunks.extend(chunks)

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # Final answer
    response = llm.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=settings.temperature,
    )
    answer = response.choices[0].message.content or ""

    history = history + [
        {"role": "user",      "content": query},
        {"role": "assistant", "content": answer},
    ]

    return answer, history, all_chunks


# ── Interactive mode ──────────────────────────────────────────────────────────
def interactive(show_scores: bool = True):
    print(BANNER)
    print(f"  {C.GRAY}Type :help for commands{C.RESET}\n")
    setup_readline()

    chat_history = []
    turn = 0

    while True:
        try:
            prompt = f"  {C.CYAN}r4gv1s{C.RESET}{C.GRAY}({turn}){C.RESET}> "
            raw = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  {C.GRAY}Goodbye.{C.RESET}\n")
            break

        if not raw:
            continue

        if raw in (":exit", ":quit", "exit", "quit"):
            print(f"\n  {C.GRAY}Goodbye.{C.RESET}\n")
            break

        if raw == ":help":
            print(HELP)
            continue

        if raw == ":clear":
            chat_history = []
            turn = 0
            print(f"\n  {C.YELLOW}[~]{C.RESET} History cleared.\n")
            continue

        if raw == ":history":
            if not chat_history:
                print(f"\n  {C.GRAY}No history.{C.RESET}\n")
            else:
                print()
                for m in chat_history:
                    color = C.CYAN if m["role"] == "user" else C.GREEN
                    short = m["content"][:100] + "..." if len(m["content"]) > 100 else m["content"]
                    print(f"  {color}[{m['role']}]{C.RESET} {short}")
                print()
            continue

        if raw == ":scores":
            show_scores = not show_scores
            state = "ON" if show_scores else "OFF"
            print(f"\n  {C.YELLOW}[~]{C.RESET} Relevancy scores: {state}\n")
            continue

        # Query
        print_info("Thinking...")

        try:
            answer, chat_history, chunks = ask_with_scores(raw, chat_history)
            turn += 1
            print_chunks(chunks, show_scores)
            print_answer(answer)

        except Exception as e:
            print_error(str(e))


# ── Single query mode ─────────────────────────────────────────────────────────
def single(query: str, show_scores: bool):
    try:
        answer, _, chunks = ask_with_scores(query, [])
        if show_scores:
            print_chunks(chunks, True)
        print_answer(answer)
    except Exception as e:
        print_error(str(e))
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="R4GV1S — Pentest Assistant CLI")
    parser.add_argument("query",   nargs="?",          help="Single query mode")
    parser.add_argument("--no-scores", action="store_true", help="Hide relevancy scores")
    args = parser.parse_args()

    show = not args.no_scores

    if args.query:
        single(args.query, show)
    else:
        interactive(show)


if __name__ == "__main__":
    main()
