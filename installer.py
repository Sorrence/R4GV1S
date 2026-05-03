#!/usr/bin/env python3
"""
R4GV1S Installer
Interactive setup wizard. Installs dependencies, configures provider, pulls models, indexes knowledge base.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

# ── Colors ────────────────────────────────────────────────────────────────────
G  = "\033[92m"   # green
Y  = "\033[93m"   # yellow
R  = "\033[91m"   # red
C  = "\033[96m"   # cyan
DIM = "\033[2m"
B  = "\033[1m"
NC = "\033[0m"

def ok(msg):   print(f"  {G}[+]{NC} {msg}")
def warn(msg): print(f"  {Y}[!]{NC} {msg}")
def err(msg):  print(f"  {R}[x]{NC} {msg}"); sys.exit(1)
def info(msg): print(f"  {C}[~]{NC} {msg}")
def ask(msg, default=""):
    val = input(f"  {B}[?]{NC} {msg} [{default}]: ").strip()
    return val if val else default

def ask_choice(msg, choices, default=0):
    print(f"\n  {B}[?]{NC} {msg}")
    for i, c in enumerate(choices):
        marker = f"{G}►{NC}" if i == default else " "
        print(f"    {marker} {i+1}. {c}")
    while True:
        raw = input(f"\n  Enter number [{default+1}]: ").strip()
        if not raw:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return idx
        except ValueError:
            pass
        warn("Invalid choice.")

def run(cmd, check=True, capture=False):
    kwargs = {"shell": True, "check": check}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)

BANNER = f"""
{C}{B}  ██████╗ ██╗  ██╗ ██████╗ ██╗   ██╗ ██╗███████╗
  ██╔══██╗██║  ██║██╔════╝ ██║   ██║ ██║██╔════╝
  ██████╔╝███████║██║  ███╗██║   ██║ ██║███████╗
  ██╔══██╗╚════██║██║   ██║╚██╗ ██╔╝ ██║╚════██║
  ██║  ██║     ██║╚██████╔╝ ╚████╔╝  ██║███████║
  ╚═╝  ╚═╝     ╚═╝ ╚═════╝   ╚═══╝   ╚═╝╚══════╝{NC}
{DIM}  RAG-based Pentest Assistant — Installer{NC}
"""

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
KB_DIR = ROOT / "knowledge-base"


# ── Steps ─────────────────────────────────────────────────────────────────────

def step_python():
    print(f"\n{B}── Python Dependencies ─────────────────────────────{NC}")
    info("Installing Python packages...")
    run("pip install -r requirements.txt --break-system-packages -q")
    ok("Python dependencies installed.")


def step_docker():
    print(f"\n{B}── Qdrant (Vector Database) ────────────────────────{NC}")

    if shutil.which("docker") is None:
        err("Docker not found. Please install Docker first: https://docs.docker.com/get-docker/")

    result = run("docker ps -a --format '{{.Names}}'", capture=True, check=False)
    if "qdrant" in result.stdout:
        warn("Qdrant container already exists, skipping.")
        run("docker start qdrant", check=False)
        ok("Qdrant started.")
        return

    info("Pulling and starting Qdrant...")
    qdrant_data = Path.home() / "qdrant_data"
    qdrant_data.mkdir(exist_ok=True)

    run(f"docker run -d --name qdrant --restart unless-stopped "
        f"-p 6333:6333 -v {qdrant_data}:/qdrant/storage qdrant/qdrant")
    ok(f"Qdrant running at http://localhost:6333 (data: {qdrant_data})")


def step_provider():
    print(f"\n{B}── LLM Provider ─────────────────────────────────────{NC}")

    choice = ask_choice(
        "Choose your LLM provider:",
        [
            "OpenRouter (free tier available, no GPU needed)",
            "Local Ollama (fully offline, GPU recommended)",
            "Custom OpenAI-compatible API",
        ],
        default=0,
    )

    env = {}

    if choice == 0:
        # OpenRouter
        env["LLM_PROVIDER"]    = "openrouter"
        env["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"

        print(f"\n  Get your free API key at: {C}https://openrouter.ai/keys{NC}")
        key = ask("OpenRouter API key (sk-or-...)", "")
        if not key:
            warn("No key entered. You can set it later in .env")
        env["API_KEY"] = key

        models = [
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-3-27b-it:free",
            "openrouter/free",
            "Enter custom model ID",
        ]
        midx = ask_choice("Choose model:", models, default=0)
        if midx == len(models) - 1:
            env["LLM_MODEL"] = ask("Model ID", "openrouter/free")
        else:
            env["LLM_MODEL"] = models[midx]

        # Embedding always local for OpenRouter users
        env["EMBED_PROVIDER"] = "ollama"
        env["EMBED_MODEL"]    = "nomic-embed-text"
        step_ollama_embed()

    elif choice == 1:
        # Ollama
        env["LLM_PROVIDER"]  = "ollama"
        env["EMBED_PROVIDER"] = "ollama"
        env["API_KEY"]        = ""

        if shutil.which("ollama") is None:
            warn("Ollama not found. Installing...")
            run("curl -fsSL https://ollama.com/install.sh | sh")

        llm_models = [
            "qwen2.5-coder:7b  (~5GB, recommended)",
            "qwen2.5-coder:14b (~10GB, better quality)",
            "deepseek-r1:8b    (~6GB, reasoning)",
            "Enter custom model",
        ]
        midx = ask_choice("Choose LLM model:", llm_models, default=0)
        model_ids = ["qwen2.5-coder:7b", "qwen2.5-coder:14b", "deepseek-r1:8b", None]
        if midx == 3:
            env["LLM_MODEL"] = ask("Model name", "qwen2.5-coder:7b")
        else:
            env["LLM_MODEL"] = model_ids[midx]

        env["EMBED_MODEL"] = "nomic-embed-text"

        info(f"Pulling {env['LLM_MODEL']}...")
        run(f"ollama pull {env['LLM_MODEL']}")
        info("Pulling nomic-embed-text...")
        run("ollama pull nomic-embed-text")
        ok("Models ready.")

    else:
        # Custom
        env["LLM_PROVIDER"]    = "openai"
        env["OPENAI_BASE_URL"] = ask("API base URL", "https://api.openai.com/v1")
        env["API_KEY"]         = ask("API key", "")
        env["LLM_MODEL"]       = ask("Model ID", "gpt-4o-mini")
        env["EMBED_PROVIDER"]  = "ollama"
        env["EMBED_MODEL"]     = "nomic-embed-text"
        step_ollama_embed()

    return env


def step_ollama_embed():
    """Pull embedding model via Ollama."""
    if shutil.which("ollama") is None:
        warn("Ollama not found. Installing for embeddings...")
        run("curl -fsSL https://ollama.com/install.sh | sh")
    info("Pulling nomic-embed-text (embedding model)...")
    run("ollama pull nomic-embed-text")
    ok("Embedding model ready.")


def step_knowledge_base():
    print(f"\n{B}── Knowledge Base ───────────────────────────────────{NC}")

    sources = {
        "PayloadsAllTheThings (MIT, ~50MB)": {
            "url":  "https://github.com/swisskyrepo/PayloadsAllTheThings",
            "dest": KB_DIR / "payloads",
        },
        "HackTricks (CC BY-NC 4.0, ~500MB)": {
            "url":  "https://github.com/carlospolop/hacktricks",
            "dest": KB_DIR / "hacktricks",
        },
        "Nuclei Templates (MIT, ~200MB)": {
            "url":  "https://github.com/projectdiscovery/nuclei-templates",
            "dest": KB_DIR / "nuclei-templates",
        },
        "GTFOBins (GPL-3.0, ~5MB)": {
            "url":  "https://github.com/GTFOBins/GTFOBins.github.io",
            "dest": KB_DIR / "gtfobins",
        },
    }

    print(f"\n  {DIM}Select knowledge sources to download (space to toggle, enter to confirm){NC}\n")
    selected = []
    names = list(sources.keys())

    for i, name in enumerate(names):
        choice = ask(f"Download {name}? (y/n)", "y")
        if choice.lower() == "y":
            selected.append(name)

    if not selected:
        warn("No sources selected. You can manually clone repos into knowledge-base/")
        return []

    KB_DIR.mkdir(exist_ok=True)
    cloned = []

    for name in selected:
        src = sources[name]
        dest = src["dest"]
        if dest.exists():
            warn(f"{dest.name} already exists, skipping.")
            cloned.append(str(dest))
            continue
        info(f"Cloning {name}...")
        run(f"git clone --depth=1 {src['url']} {dest}")
        ok(f"{dest.name} cloned.")
        cloned.append(str(dest))

    return cloned


def step_index(paths: list[str]):
    if not paths:
        return

    print(f"\n{B}── Indexing ──────────────────────────────────────────{NC}")
    warn(f"Indexing {len(paths)} source(s). This may take a while...")

    sys.path.insert(0, str(ROOT))
    from src.indexer import index_path, ensure_collection
    ensure_collection()

    for p in paths:
        info(f"Indexing {p}...")
        index_path(p)

    ok("Indexing complete.")


def step_write_env(env: dict):
    lines = [
        "# R4GV1S Configuration",
        "# Generated by installer.py",
        "",
    ]
    for k, v in env.items():
        lines.append(f"{k}={v}")

    ENV_FILE.write_text("\n".join(lines) + "\n")
    ok(f".env written to {ENV_FILE}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(BANNER)
    print(f"  Welcome! This wizard will set up R4GV1S on your system.\n")

    step_python()
    step_docker()
    env = step_provider()
    paths = step_knowledge_base()
    step_write_env(env)
    step_index(paths)

    print(f"""
{G}{B}  ╔══════════════════════════════════════╗
  ║        Setup Complete! 🎉            ║
  ╚══════════════════════════════════════╝{NC}

  Start the web UI:
  {C}python -m uvicorn src.api:app --host 127.0.0.1 --port 8000{NC}

  Then open: {C}http://localhost:8000{NC}

  Re-index anytime:
  {C}python src/indexer.py index knowledge-base/{NC}
""")


if __name__ == "__main__":
    main()
