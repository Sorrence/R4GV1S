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
        ok("Qdrant zaten çalışıyor")
        return True

    if not check_docker():
        err("Docker bulunamadı! Qdrant için Docker gerekli.")
        err("Yükleme: https://docs.docker.com/get-docker/")
        return False

    info("Qdrant başlatılıyor...")

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
        ok("Qdrant hazır (port 6333)")
        return True
    else:
        err("Qdrant başlatılamadı!")
        return False


def ensure_ollama() -> bool:
    """Start Ollama if not running. Returns True if ready."""
    if is_ollama_running():
        ok("Ollama zaten çalışıyor")
        return True

    if not check_ollama():
        warn("Ollama bulunamadı. Sadece embedding için gerekli.")
        warn("Yükleme: curl -fsSL https://ollama.com/install.sh | sh")
        return False

    info("Ollama başlatılıyor...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    if wait_for_port("localhost", 11434, timeout=20):
        ok("Ollama hazır (port 11434)")
        return True
    else:
        err("Ollama başlatılamadı!")
        return False


def ensure_services() -> bool:
    """Start all required services."""
    print(f"\n{B}── Servisler ──────────────────────────────────────────{NC}")
    qdrant_ok = ensure_qdrant()
    ollama_ok = ensure_ollama()

    if not qdrant_ok:
        err("Qdrant olmadan devam edilemez!")
        return False

    env = load_env()
    provider = env.get("LLM_PROVIDER", "openrouter")
    embed_provider = env.get("EMBED_PROVIDER", "ollama")

    if not ollama_ok and embed_provider == "ollama":
        err("Embedding provider 'ollama' ama Ollama çalışmıyor!")
        return False

    # Check if embedding model is pulled
    if ollama_ok and embed_provider == "ollama":
        embed_model = env.get("EMBED_MODEL", "nomic-embed-text")
        result = run_silent("ollama list")
        if embed_model not in result.stdout:
            info(f"Embedding modeli çekiliyor: {embed_model}...")
            subprocess.run(["ollama", "pull", embed_model], check=False)

    # Check if LLM model is pulled (only for Ollama provider)
    if provider == "ollama" and ollama_ok:
        llm_model = env.get("LLM_MODEL", "qwen2.5-coder:7b")
        result = run_silent("ollama list")
        if llm_model not in result.stdout:
            info(f"LLM modeli çekiliyor: {llm_model}...")
            subprocess.run(["ollama", "pull", llm_model], check=False)

    return True


# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_start():
    """Start the web UI with auto service management."""
    if not ENV_FILE.exists():
        err(".env dosyası bulunamadı!")
        info("Önce kurulumu çalıştırın: python r4gv1s.py setup")
        return

    if not ensure_services():
        return

    env = load_env()
    host = env.get("HOST", "127.0.0.1")
    port = env.get("PORT", "8000")

    print(f"\n{B}── Web UI ─────────────────────────────────────────────{NC}")
    ok(f"Tarayıcıda açın: {C}http://{host}:{port}{NC}")
    info(f"Durdurmak için: {Y}Ctrl+C{NC}")
    print()

    try:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "src.api:app",
             "--host", host, "--port", port],
            cwd=str(ROOT),
        )
    except KeyboardInterrupt:
        print(f"\n\n  {GRAY}Web UI durduruldu.{NC}\n")


def cmd_cli():
    """Start the CLI chat with auto service management."""
    if not ENV_FILE.exists():
        err(".env dosyası bulunamadı!")
        info("Önce kurulumu çalıştırın: python r4gv1s.py setup")
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
        print(f"\n\n  {GRAY}CLI durduruldu.{NC}\n")


def cmd_index(path: str = None):
    """Index the knowledge base."""
    if not ensure_services():
        return

    target = path or str(KB_DIR)

    if not Path(target).exists():
        err(f"Yol bulunamadı: {target}")
        if target == str(KB_DIR):
            info("Knowledge base henüz indirilmemiş.")
            info("Çalıştırın: python r4gv1s.py setup")
        return

    print(f"\n{B}── İndeksleme ─────────────────────────────────────────{NC}")
    info(f"Hedef: {target}")
    print()

    subprocess.run(
        [sys.executable, str(ROOT / "src" / "indexer.py"), "index", target],
        cwd=str(ROOT),
    )


def cmd_status():
    """Show status of all services."""
    print(f"\n{B}── Servis Durumu ───────────────────────────────────────{NC}\n")

    env = load_env()
    provider = env.get("LLM_PROVIDER", "?")
    llm_model = env.get("LLM_MODEL", "?")
    embed_model = env.get("EMBED_MODEL", "?")

    # Docker
    if check_docker():
        ok(f"Docker               {DIM}yüklü{NC}")
    else:
        err(f"Docker               {DIM}bulunamadı{NC}")

    # Qdrant
    if is_qdrant_running():
        ok(f"Qdrant               {DIM}çalışıyor (port 6333){NC}")
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
            ok(f"  Koleksiyon          {DIM}{coll} ({info_data.points_count} vektör){NC}")
        except Exception:
            warn(f"  Koleksiyon          {DIM}okunamadı{NC}")
    else:
        err(f"Qdrant               {DIM}çalışmıyor{NC}")

    # Ollama
    if check_ollama():
        if is_ollama_running():
            ok(f"Ollama               {DIM}çalışıyor (port 11434){NC}")
            # Show pulled models
            result = run_silent("ollama list")
            if result.returncode == 0:
                models = []
                for line in result.stdout.strip().splitlines()[1:]:  # Skip header
                    name = line.split()[0] if line.split() else ""
                    if name:
                        models.append(name)
                if models:
                    info(f"  Modeller            {DIM}{', '.join(models[:5])}{NC}")
        else:
            warn(f"Ollama               {DIM}yüklü ama çalışmıyor{NC}")
    else:
        warn(f"Ollama               {DIM}bulunamadı{NC}")

    # Web UI
    webui_port = int(env.get("PORT", "8000"))
    if is_port_open("127.0.0.1", webui_port):
        ok(f"Web UI               {DIM}çalışıyor (port {webui_port}){NC}")
    else:
        info(f"Web UI               {DIM}çalışmıyor{NC}")

    # Config
    print(f"\n{B}── Yapılandırma ────────────────────────────────────────{NC}\n")
    if ENV_FILE.exists():
        ok(f".env                 {DIM}mevcut{NC}")
        info(f"  LLM Provider        {DIM}{provider}{NC}")
        info(f"  LLM Model           {DIM}{llm_model}{NC}")
        info(f"  Embed Model         {DIM}{embed_model}{NC}")
    else:
        err(f".env                 {DIM}bulunamadı{NC}")

    # Knowledge base
    print(f"\n{B}── Knowledge Base ──────────────────────────────────────{NC}\n")
    if KB_DIR.exists():
        kb_dirs = [d for d in KB_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")]
        if kb_dirs:
            for d in sorted(kb_dirs):
                file_count = sum(1 for _ in d.rglob("*") if _.is_file())
                ok(f"  {d.name:<22} {DIM}{file_count} dosya{NC}")
        else:
            warn("  Kaynak dizini boş")
    else:
        warn("  knowledge-base/ dizini bulunamadı")

    print()


def cmd_stop():
    """Stop all running services."""
    print(f"\n{B}── Servisleri Durdur ───────────────────────────────────{NC}\n")

    # Stop Qdrant
    if check_docker():
        result = run_silent("docker ps --format '{{.Names}}'")
        if "qdrant" in result.stdout:
            info("Qdrant durduruluyor...")
            run_silent("docker stop qdrant")
            ok("Qdrant durduruldu")
        else:
            info("Qdrant zaten durmuş")

    # Note: We don't stop Ollama since other apps might use it
    if is_ollama_running():
        warn("Ollama çalışıyor — başka uygulamalar kullanıyor olabilir")
        warn("Manuel durdurmak için: systemctl stop ollama")

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
        ("Web UI Başlat",       "Servisleri başlat ve tarayıcıda aç",        cmd_start),
        ("CLI Chat Başlat",     "Terminal üzerinden soru-cevap",              cmd_cli),
        ("İndeksle",            "Knowledge base'i Qdrant'a indeksle",        lambda: cmd_index()),
        ("Durum Kontrol",       "Tüm servislerin durumunu göster",           cmd_status),
        ("Servisleri Durdur",   "Qdrant ve diğer servisleri durdur",         cmd_stop),
        ("Kurulum Sihirbazı",   "İlk kurulum / yapılandırma",               cmd_setup),
    ]

    print(f"  {B}Ne yapmak istiyorsunuz?{NC}\n")
    for i, (name, desc, _) in enumerate(options, 1):
        print(f"    {C}{i}.{NC} {B}{name:<22}{NC} {GRAY}{desc}{NC}")

    print(f"\n    {GRAY}0. Çıkış{NC}")
    print()

    while True:
        try:
            raw = input(f"  {B}Seçim [1]:{NC} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  {GRAY}Çıkış.{NC}\n")
            return

        if raw == "0":
            print(f"\n  {GRAY}Çıkış.{NC}\n")
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

        warn("Geçersiz seçim, tekrar deneyin.")


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
        print(f"""  {B}Kullanım:{NC}
    python r4gv1s.py              {GRAY}# İnteraktif menü{NC}
    python r4gv1s.py start        {GRAY}# Web UI başlat{NC}
    python r4gv1s.py cli          {GRAY}# CLI chat başlat{NC}
    python r4gv1s.py index [yol]  {GRAY}# Knowledge base indeksle{NC}
    python r4gv1s.py status       {GRAY}# Servis durumunu göster{NC}
    python r4gv1s.py stop         {GRAY}# Servisleri durdur{NC}
    python r4gv1s.py setup        {GRAY}# Kurulum sihirbazı{NC}

  {B}Kısayollar:{NC}
    start  = web, ui
    cli    = chat, terminal
    index  = reindex
    status = info, check
    stop   = kill, down
    setup  = install, init
""")
    else:
        err(f"Bilinmeyen komut: {cmd}")
        info("Yardım için: python r4gv1s.py help")


if __name__ == "__main__":
    main()
