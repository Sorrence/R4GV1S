#!/usr/bin/env python3
"""
R4GV1S — Unified Launcher
One script to rule them all: start services, launch web/cli, index, check status.

Usage:
    python r4gv1s.py              # Interactive menu
    python r4gv1s.py start        # Start web UI (auto-starts Qdrant & Ollama)
    python r4gv1s.py cli          # Start CLI chat (auto-starts Qdrant & Ollama)
    python r4gv1s.py index [path] # Index knowledge base
    python r4gv1s.py status       # Check service status
    python r4gv1s.py stop         # Stop all services
    python r4gv1s.py setup        # Run installer wizard
"""

import os
import sys
import time
import shutil
import signal
import socket
import subprocess
from pathlib import Path

# ── Colors ────────────────────────────────────────────────────────────────────
G   = "\033[92m"
Y   = "\033[93m"
R   = "\033[91m"
C   = "\033[96m"
DIM = "\033[2m"
B   = "\033[1m"
NC  = "\033[0m"
GRAY = "\033[90m"

ROOT = Path(__file__).parent.resolve()
ENV_FILE = ROOT / ".env"
KB_DIR = ROOT / "knowledge-base"

BANNER = f"""
{C}{B}  ██████╗ ██╗  ██╗ ██████╗ ██╗   ██╗ ██╗███████╗
  ██╔══██╗██║  ██║██╔════╝ ██║   ██║ ██║██╔════╝
  ██████╔╝███████║██║  ███╗██║   ██║ ██║███████╗
  ██╔══██╗╚════██║██║   ██║╚██╗ ██╔╝ ██║╚════██║
  ██║  ██║     ██║╚██████╔╝ ╚████╔╝  ██║███████║
  ╚═╝  ╚═╝     ╚═╝ ╚═════╝   ╚═══╝   ╚═╝╚══════╝{NC}
{GRAY}  RAG-based Pentest Assistant — Launcher{NC}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────
def ok(msg):    print(f"  {G}✓{NC} {msg}")
def warn(msg):  print(f"  {Y}⚠{NC} {msg}")
def err(msg):   print(f"  {R}✗{NC} {msg}")
def info(msg):  print(f"  {C}~{NC} {msg}")

def is_port_open(host: str, port: int) -> bool:
    """Check if a TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False

def wait_for_port(host: str, port: int, timeout: int = 30, label: str = "") -> bool:
    """Wait until a port becomes available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(host, port):
            return True
        time.sleep(1)
    return False

def run_silent(cmd: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run a command silently."""
    return subprocess.run(
        cmd, shell=True, check=check,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

def load_env() -> dict:
    """Load .env file as dict."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# ── Service Checks ────────────────────────────────────────────────────────────
def check_docker() -> bool:
    """Check if Docker is available."""
    return shutil.which("docker") is not None

def check_ollama() -> bool:
    """Check if Ollama is available."""
    return shutil.which("ollama") is not None

def is_qdrant_running() -> bool:
    """Check if Qdrant is reachable on its port."""
    env = load_env()
    host = env.get("QDRANT_HOST", "localhost")
    port = int(env.get("QDRANT_PORT", "6333"))
    return is_port_open(host, port)

def is_ollama_running() -> bool:
    """Check if Ollama API is responding."""
    return is_port_open("localhost", 11434)

def is_webui_running() -> bool:
    """Check if the web UI is responding."""
    env = load_env()
    port = int(env.get("PORT", "8000"))
    return is_port_open("127.0.0.1", port)


# ── Service Management ───────────────────────────────────────────────────────
def ensure_qdrant() -> bool:
    """Start Qdrant if not running. Returns True if ready."""
    if is_qdrant_running():
        ok("Qdrant is already running")
        return True

    if not check_docker():
        err("Docker not found! Docker is required for Qdrant.")
        err("Install: https://docs.docker.com/get-docker/")
        return False

    info("Starting Qdrant...")

    # Check if container exists but is stopped
    result = run_silent("docker ps -a --format '{{.Names}}'")
    if "qdrant" in result.stdout:
        run_silent("docker start qdrant")
    else:
        # Create new container
        qdrant_data = Path.home() / "qdrant_data"
        qdrant_data.mkdir(exist_ok=True)
        run_silent(
            f"docker run -d --name qdrant --restart unless-stopped "
            f"-p 6333:6333 -v {qdrant_data}:/qdrant/storage qdrant/qdrant"
        )

    if wait_for_port("localhost", 6333, timeout=30):
        ok("Qdrant ready (port 6333)")
        return True
    else:
        err("Failed to start Qdrant!")
        return False


def ensure_ollama() -> bool:
    """Start Ollama if not running. Returns True if ready."""
    if is_ollama_running():
        ok("Ollama is already running")
        return True

    if not check_ollama():
        warn("Ollama not found. Only required for embedding.")
        warn("Install: curl -fsSL https://ollama.com/install.sh | sh")
        return False

    info("Starting Ollama...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    if wait_for_port("localhost", 11434, timeout=20):
        ok("Ollama ready (port 11434)")
        return True
    else:
        err("Failed to start Ollama!")
        return False


def ensure_services() -> bool:
    """Start all required services."""
    print(f"\n{B}── Services ───────────────────────────────────────────{NC}")
    qdrant_ok = ensure_qdrant()
    ollama_ok = ensure_ollama()

    if not qdrant_ok:
        err("Cannot continue without Qdrant!")
        return False

    env = load_env()
    provider = env.get("LLM_PROVIDER", "openrouter")
    embed_provider = env.get("EMBED_PROVIDER", "ollama")

    if not ollama_ok and embed_provider == "ollama":
        err("Embedding provider is 'ollama' but Ollama is not running!")
        return False

    # Check if embedding model is pulled
    if ollama_ok and embed_provider == "ollama":
        embed_model = env.get("EMBED_MODEL", "nomic-embed-text")
        result = run_silent("ollama list")
        if embed_model not in result.stdout:
            info(f"Pulling embedding model: {embed_model}...")
            subprocess.run(["ollama", "pull", embed_model], check=False)

    # Check if LLM model is pulled (only for Ollama provider)
    if provider == "ollama" and ollama_ok:
        llm_model = env.get("LLM_MODEL", "qwen2.5-coder:7b")
        result = run_silent("ollama list")
        if llm_model not in result.stdout:
            info(f"Pulling LLM model: {llm_model}...")
            subprocess.run(["ollama", "pull", llm_model], check=False)

    return True


# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_start():
    """Start the web UI with auto service management."""
    if not ENV_FILE.exists():
        err(".env file not found!")
        info("Run the installer first: python r4gv1s.py setup")
        return

    if not ensure_services():
        return

    env = load_env()
    host = env.get("HOST", "127.0.0.1")
    port = env.get("PORT", "8000")

    print(f"\n{B}── Web UI ─────────────────────────────────────────────{NC}")
    ok(f"Open in browser: {C}http://{host}:{port}{NC}")
    info(f"To stop: {Y}Ctrl+C{NC}")
    print()

    try:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "src.api:app",
             "--host", host, "--port", port],
            cwd=str(ROOT),
        )
    except KeyboardInterrupt:
        print(f"\n\n  {GRAY}Web UI stopped.{NC}\n")


def cmd_cli():
    """Start the CLI chat with auto service management."""
    if not ENV_FILE.exists():
        err(".env file not found!")
        info("Run the installer first: python r4gv1s.py setup")
        return

    if not ensure_services():
        return

    print(f"\n{B}── CLI Chat ───────────────────────────────────────────{NC}\n")

    try:
        subprocess.run(
            [sys.executable, str(ROOT / "src" / "cli.py")],
            cwd=str(ROOT),
        )
    except KeyboardInterrupt:
        print(f"\n\n  {GRAY}CLI stopped.{NC}\n")


def cmd_index(path: str = None):
    """Index the knowledge base."""
    if not ensure_services():
        return

    target = path or str(KB_DIR)

    if not Path(target).exists():
        err(f"Path not found: {target}")
        if target == str(KB_DIR):
            info("Knowledge base has not been downloaded yet.")
            info("Run: python r4gv1s.py setup")
        return

    print(f"\n{B}── Indexing ───────────────────────────────────────────{NC}")
    info(f"Target: {target}")
    print()

    subprocess.run(
        [sys.executable, str(ROOT / "src" / "indexer.py"), "index", target],
        cwd=str(ROOT),
    )


def cmd_status():
    """Show status of all services."""
    print(f"\n{B}── Service Status ──────────────────────────────────────{NC}\n")

    env = load_env()
    provider = env.get("LLM_PROVIDER", "?")
    llm_model = env.get("LLM_MODEL", "?")
    embed_model = env.get("EMBED_MODEL", "?")

    # Docker
    if check_docker():
        ok(f"Docker               {DIM}installed{NC}")
    else:
        err(f"Docker               {DIM}not found{NC}")

    # Qdrant
    if is_qdrant_running():
        ok(f"Qdrant               {DIM}running (port 6333){NC}")
        # Show collection stats
        try:
            sys.path.insert(0, str(ROOT))
            from qdrant_client import QdrantClient
            q = QdrantClient(
                host=env.get("QDRANT_HOST", "localhost"),
                port=int(env.get("QDRANT_PORT", "6333")),
            )
            coll = env.get("COLLECTION_NAME", "pentest_kb")
            info_data = q.get_collection(coll)
            ok(f"  Collection          {DIM}{coll} ({info_data.points_count} vectors){NC}")
        except Exception:
            warn(f"  Collection          {DIM}could not be read{NC}")
    else:
        err(f"Qdrant               {DIM}not running{NC}")

    # Ollama
    if check_ollama():
        if is_ollama_running():
            ok(f"Ollama               {DIM}running (port 11434){NC}")
            # Show pulled models
            result = run_silent("ollama list")
            if result.returncode == 0:
                models = []
                for line in result.stdout.strip().splitlines()[1:]:  # Skip header
                    name = line.split()[0] if line.split() else ""
                    if name:
                        models.append(name)
                if models:
                    info(f"  Models              {DIM}{', '.join(models[:5])}{NC}")
        else:
            warn(f"Ollama               {DIM}installed but not running{NC}")
    else:
        warn(f"Ollama               {DIM}not found{NC}")

    # Web UI
    webui_port = int(env.get("PORT", "8000"))
    if is_port_open("127.0.0.1", webui_port):
        ok(f"Web UI               {DIM}running (port {webui_port}){NC}")
    else:
        info(f"Web UI               {DIM}not running{NC}")

    # Config
    print(f"\n{B}── Configuration ───────────────────────────────────────{NC}\n")
    if ENV_FILE.exists():
        ok(f".env                 {DIM}exists{NC}")
        info(f"  LLM Provider        {DIM}{provider}{NC}")
        info(f"  LLM Model           {DIM}{llm_model}{NC}")
        info(f"  Embed Model         {DIM}{embed_model}{NC}")
    else:
        err(f".env                 {DIM}not found{NC}")

    # Knowledge base
    print(f"\n{B}── Knowledge Base ──────────────────────────────────────{NC}\n")
    if KB_DIR.exists():
        kb_dirs = [d for d in KB_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")]
        if kb_dirs:
            for d in sorted(kb_dirs):
                file_count = sum(1 for _ in d.rglob("*") if _.is_file())
                ok(f"  {d.name:<22} {DIM}{file_count} files{NC}")
        else:
            warn("  Source directory is empty")
    else:
        warn("  knowledge-base/ directory not found")

    print()


def cmd_stop():
    """Stop all running services."""
    print(f"\n{B}── Stop Services ───────────────────────────────────────{NC}\n")

    # Stop Qdrant
    if check_docker():
        result = run_silent("docker ps --format '{{.Names}}'")
        if "qdrant" in result.stdout:
            info("Stopping Qdrant...")
            run_silent("docker stop qdrant")
            ok("Qdrant stopped")
        else:
            info("Qdrant is already stopped")

    # Note: We don't stop Ollama since other apps might use it
    if is_ollama_running():
        warn("Ollama is running — other applications might be using it")
        warn("To stop manually: systemctl stop ollama")

    print()


def cmd_setup():
    """Run the installer wizard."""
    subprocess.run(
        [sys.executable, str(ROOT / "installer.py")],
        cwd=str(ROOT),
    )


# ── Interactive Menu ──────────────────────────────────────────────────────────
def interactive_menu():
    """Show interactive menu when no arguments given."""
    print(BANNER)

    options = [
        ("Start Web UI",        "Start services and open in browser",        cmd_start),
        ("Start CLI Chat",      "Q&A via terminal",                          cmd_cli),
        ("Index",               "Index knowledge base into Qdrant",          lambda: cmd_index()),
        ("Check Status",        "Show status of all services",               cmd_status),
        ("Stop Services",       "Stop Qdrant and other services",            cmd_stop),
        ("Setup Wizard",        "Initial setup / configuration",             cmd_setup),
    ]

    print(f"  {B}What would you like to do?{NC}\n")
    for i, (name, desc, _) in enumerate(options, 1):
        print(f"    {C}{i}.{NC} {B}{name:<22}{NC} {GRAY}{desc}{NC}")

    print(f"\n    {GRAY}0. Exit{NC}")
    print()

    while True:
        try:
            raw = input(f"  {B}Choice [1]:{NC} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  {GRAY}Exit.{NC}\n")
            return

        if raw == "0":
            print(f"\n  {GRAY}Exit.{NC}\n")
            return

        if not raw:
            raw = "1"

        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                print()
                options[idx][2]()
                return
        except ValueError:
            pass

        warn("Invalid choice, please try again.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        interactive_menu()
        return

    cmd = sys.argv[1].lower()

    if cmd in ("start", "web", "ui"):
        print(BANNER)
        cmd_start()
    elif cmd in ("cli", "chat", "terminal"):
        print(BANNER)
        cmd_cli()
    elif cmd in ("index", "reindex"):
        print(BANNER)
        path = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_index(path)
    elif cmd in ("status", "info", "check"):
        print(BANNER)
        cmd_status()
    elif cmd in ("stop", "kill", "down"):
        print(BANNER)
        cmd_stop()
    elif cmd in ("setup", "install", "init"):
        cmd_setup()
    elif cmd in ("help", "-h", "--help"):
        print(BANNER)
        print(f"""  {B}Usage:{NC}
    python r4gv1s.py              {GRAY}# Interactive menu{NC}
    python r4gv1s.py start        {GRAY}# Start Web UI{NC}
    python r4gv1s.py cli          {GRAY}# Start CLI chat{NC}
    python r4gv1s.py index [path] {GRAY}# Index knowledge base{NC}
    python r4gv1s.py status       {GRAY}# Show service status{NC}
    python r4gv1s.py stop         {GRAY}# Stop services{NC}
    python r4gv1s.py setup        {GRAY}# Setup wizard{NC}

  {B}Aliases:{NC}
    start  = web, ui
    cli    = chat, terminal
    index  = reindex
    status = info, check
    stop   = kill, down
    setup  = install, init
""")
    else:
        err(f"Unknown command: {cmd}")
        info("For help: python r4gv1s.py help")


if __name__ == "__main__":
    main()
