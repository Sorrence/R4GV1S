#!/usr/bin/env python3
"""
R4GV1S - CLI
Agentic RAG pipeline with relevancy scores, path-based keyword filtering, and chat history.
"""

import sys
import os

# Project root must be in path before any local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import json
import readline
import argparse

import ollama as ollama_client
import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchText

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
  {C.CYAN}:scores{C.RESET}     Toggle relevancy scores (default: on)
  {C.CYAN}:exit{C.RESET}       Quit

{C.YELLOW}Shortcuts:{C.RESET}
  {C.CYAN}↑ / ↓{C.RESET}      Previous/next command
  {C.CYAN}Ctrl+A/E{C.RESET}    Line start/end
  {C.CYAN}Ctrl+C{C.RESET}      Cancel / Quit
"""

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
    "brute":                 "brute",
    "file upload":           "file-upload",
    "subdomain":             "subdomain",
    "nmap":                  "nmap",
    "metasploit":            "metasploit",
    "sqlmap":                "sqlmap",
    "burp":                  "burp",
    "gobuster":              "gobuster",
    "ffuf":                  "ffuf",
    "hydra":                 "hydra",
    "john":                  "john",
    "hashcat":               "hashcat",
    "mimikatz":              "mimikatz",
    "bloodhound":            "bloodhound",
    "linpeas":               "linpeas",
    "winpeas":               "winpeas",
}

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

# ── Clients ───────────────────────────────────────────────────────────────────
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


# ── Embed ─────────────────────────────────────────────────────────────────────
def embed(text: str) -> list[float]:
    if settings.embed_provider == "ollama":
        resp = ollama_client.embed(model=settings.embed_model, input=text)
        return resp.embeddings[0]
    else:
        resp = llm.embeddings.create(input=text, model=settings.embed_model)
        return resp.data[0].embedding


# ── Path keyword extraction ───────────────────────────────────────────────────
def extract_path_keyword(query: str) -> str | None:
    q = query.lower()
    for term, pattern in TERM_MAP.items():
        if term in q:
            return pattern
    return None


# ── Search ────────────────────────────────────────────────────────────────────
def search(query: str, keyword: str = None) -> tuple[str, list[dict]]:
    vector = embed(query)

    # Try path-based filter first
    path_kw = extract_path_keyword(query) if not keyword else None
    path_filter = None
    if path_kw:
        path_filter = Filter(
            must=[FieldCondition(key="source", match=MatchText(text=path_kw))]
        )

    results = []
    if path_filter:
        results = qdrant.query_points(
            collection_name=settings.collection_name,
            query=vector,
            limit=settings.top_k,
            query_filter=path_filter,
            with_payload=True,
        ).points

    # Fall back to plain vector search if not enough results
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
        score  = round(r.score, 3)
        chunks.append({"title": title, "source": source, "score": score})
        output.append(f"[{i}] {title} ({source.split('/')[-1]})\n{text}")

    return "\n\n---\n\n".join(output), chunks


# ── Agentic loop ──────────────────────────────────────────────────────────────
def ask(query: str, history: list[dict], on_search=None) -> tuple[str, list[dict], list[dict]]:
    """
    Agentic RAG pipeline.
    on_search(call_num, search_query): called when model makes a search.
    Returns (answer, updated_history, all_chunks)
    """
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
            sq = args.get("query", "")

            if on_search:
                on_search(call_count, sq)

            result, chunks = search(sq, args.get("keyword"))
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


# ── Display ───────────────────────────────────────────────────────────────────
def score_bar(score: float, width: int = 12) -> str:
    filled = int(score * width)
    bar    = "█" * filled + "░" * (width - filled)
    color  = C.GREEN if score >= 0.75 else (C.YELLOW if score >= 0.55 else C.RED)
    return f"{color}{bar}{C.RESET} {score:.3f}"


def print_search(call_num: int, query: str):
    print(f"\n  {C.CYAN}[search {call_num}]{C.RESET} {C.DIM}{query}{C.RESET}")


def print_scores(chunks: list[dict]):
    if not chunks:
        return
    print(f"\n  {C.GRAY}{'─' * 62}{C.RESET}")
    print(f"  {C.YELLOW}Relevancy Scores{C.RESET}  {C.GRAY}({len(chunks)} chunks){C.RESET}\n")

    grouped: dict[str, list] = {}
    for c in chunks:
        src = c.get("source", "")
        key = "/".join(src.split("/")[-3:-1]) if src else "unknown"
        grouped.setdefault(key, []).append(c)

    for group, items in grouped.items():
        print(f"  {C.GRAY}{group}/{C.RESET}")
        for c in items:
            score = c.get("score", 0.0)
            title = c.get("title", "")
            if len(title) > 46:
                title = title[:43] + "..."
            print(f"    {C.WHITE}{title:<46}{C.RESET}  {score_bar(score)}")
        print()

    print(f"  {C.GRAY}{'─' * 62}{C.RESET}")


def print_answer(answer: str):
    print()
    in_code = False
    for line in answer.split("\n"):
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            print(f"  {C.GRAY}{line}{C.RESET}")
        elif in_code:
            print(f"  {C.GREEN}{line}{C.RESET}")
        elif s.startswith("## ") or s.startswith("# "):
            print(f"  {C.CYAN}{C.BOLD}{line}{C.RESET}")
        else:
            print(f"  {line}")
    print()


def print_error(msg: str):
    print(f"\n  {C.RED}[x]{C.RESET} {msg}\n")


# ── Interactive ───────────────────────────────────────────────────────────────
def interactive(show_scores: bool = True):
    print(BANNER)
    print(f"  {C.GRAY}Type :help for commands{C.RESET}\n")
    setup_readline()

    chat_history: list[dict] = []
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
            print(f"\n  {C.YELLOW}[~]{C.RESET} Scores: {'ON' if show_scores else 'OFF'}\n")
            continue

        print(f"  {C.GRAY}[~] Thinking...{C.RESET}")

        try:
            answer, chat_history, chunks = ask(
                query=raw,
                history=chat_history,
                on_search=lambda n, q: print_search(n, q),
            )
            turn += 1
            if show_scores:
                print_scores(chunks)
            print_answer(answer)

        except Exception as e:
            print_error(str(e))


# ── Single query ──────────────────────────────────────────────────────────────
def single(query: str, show_scores: bool):
    try:
        answer, _, chunks = ask(
            query=query,
            history=[],
            on_search=lambda n, q: print_search(n, q),
        )
        if show_scores:
            print_scores(chunks)
        print_answer(answer)
    except Exception as e:
        print_error(str(e))
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="R4GV1S — Pentest Assistant CLI")
    parser.add_argument("query", nargs="?", help="Single query mode")
    parser.add_argument("--no-scores", action="store_true", help="Hide relevancy scores")
    args = parser.parse_args()

    if args.query:
        single(args.query, not args.no_scores)
    else:
        interactive()


if __name__ == "__main__":
    main()
