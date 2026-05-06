# R4GV1S

**RAG-based Pentest Assistant** — an offline-capable AI assistant for penetration testers, powered by your own knowledge base.

R4GV1S uses Retrieval-Augmented Generation (RAG) with agentic tool calling. Instead of relying on a model's training data, it searches a local vector database built from HackTricks, PayloadsAllTheThings, Nuclei Templates, and community contributions — then generates accurate, copy-paste ready commands and payloads.

![R4GV1S Screenshot](docs/screenshot.png)

---

## Features

- **Unified launcher** — single `r4gv1s.py` script to manage everything
- **Auto service management** — automatically starts Qdrant & Ollama when needed
- **Agentic search** — the model decides what to search and how many times
- **Fully local option** — runs entirely offline with Ollama
- **Cloud option** — OpenRouter free tier supported (no GPU needed)
- **Streaming UI** — token-by-token output with source attribution
- **Interactive CLI** — terminal chat with relevancy scores and history
- **Community knowledge base** — contribute CVEs, methodologies, and tool notes via PR
- **Hybrid search** — vector similarity + keyword matching

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/sorrence/r4gv1s
cd r4gv1s
```

### 2. Run the installer

```bash
python installer.py
```

The wizard will:
- Install Python dependencies
- Start Qdrant via Docker
- Let you choose your LLM provider (OpenRouter or Ollama)
- Download knowledge base sources
- Index everything into Qdrant

### 3. Launch

```bash
python r4gv1s.py
```

This opens an interactive menu where you can start the Web UI, CLI chat, index data, check status, and more.

---

## Usage

### Launcher (`r4gv1s.py`)

The unified launcher handles all service management automatically — no need to manually start Docker containers or Ollama.

```bash
python r4gv1s.py              # Interactive menu
python r4gv1s.py start        # Start web UI (auto-starts Qdrant & Ollama)
python r4gv1s.py cli          # Terminal chat mode
python r4gv1s.py index [path] # Index knowledge base
python r4gv1s.py status       # Check all services & configuration
python r4gv1s.py stop         # Stop services
python r4gv1s.py setup        # Run installer wizard
```

**Command aliases:** Each command has shortcuts for convenience:

| Command  | Aliases          |
|----------|------------------|
| `start`  | `web`, `ui`      |
| `cli`    | `chat`, `terminal` |
| `index`  | `reindex`        |
| `status` | `info`, `check`  |
| `stop`   | `kill`, `down`   |
| `setup`  | `install`, `init` |

### Web UI

```bash
python r4gv1s.py start
```

Opens at `http://localhost:8000`. Features streaming responses, source attribution, and a modern chat interface.

### CLI Chat

```bash
python r4gv1s.py cli
```

Interactive terminal chat with:
- Relevancy scores for retrieved chunks
- Chat history (persists during session)
- Readline support (↑/↓ history, Ctrl+A/E, tab)

CLI commands: `:help`, `:clear`, `:history`, `:scores`, `:exit`

### Single Query

```bash
python r4gv1s.py cli "how to exploit SSTI in Jinja2"
```

### Service Status

```bash
python r4gv1s.py status
```

Shows a dashboard of:
- Docker, Qdrant, Ollama status
- Collection stats (vector count)
- Pulled models
- Current `.env` configuration
- Knowledge base sources

---

## Manual Setup

If you prefer to set up manually without the installer:

### Dependencies

```bash
pip install -r requirements.txt
```

### Qdrant

```bash
docker run -d --name qdrant --restart unless-stopped \
  -p 6333:6333 \
  -v ~/qdrant_data:/qdrant/storage \
  qdrant/qdrant
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your settings
```

### Knowledge Base

Clone sources into `knowledge-base/`:

```bash
# MIT licensed
git clone --depth=1 https://github.com/swisskyrepo/PayloadsAllTheThings knowledge-base/payloads

# CC BY-NC 4.0 (personal use)
git clone --depth=1 https://github.com/carlospolop/hacktricks knowledge-base/hacktricks

# MIT licensed
git clone --depth=1 https://github.com/projectdiscovery/nuclei-templates knowledge-base/nuclei-templates
```

### Index

```bash
python r4gv1s.py index knowledge-base/
# or directly:
python src/indexer.py index knowledge-base/
```

---

## Configuration

All configuration lives in `.env`. See `.env.example` for all options.

### OpenRouter (recommended for most users)

```env
LLM_PROVIDER=openrouter
API_KEY=sk-or-your-key-here
LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free
EMBED_PROVIDER=ollama
EMBED_MODEL=nomic-embed-text
```

Get a free API key at [openrouter.ai/keys](https://openrouter.ai/keys).

### Fully Local (Ollama)

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:7b
EMBED_PROVIDER=ollama
EMBED_MODEL=nomic-embed-text
```

Requires [Ollama](https://ollama.com) installed. Pull models:

```bash
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```

> **Tip:** When using `python r4gv1s.py start` or `cli`, missing models are pulled automatically.

---

## Indexer

```bash
# Index a directory
python r4gv1s.py index knowledge-base/

# Index a single file
python src/indexer.py index knowledge-base/cves/CVE-2024-1234.yaml

# Show stats
python src/indexer.py stats

# Reset (deletes all indexed data)
python src/indexer.py reset
```

---

## Project Structure

```
r4gv1s/
├── r4gv1s.py              # ⭐ Unified launcher (start here)
├── installer.py            # First-time setup wizard
├── requirements.txt        # Python dependencies
├── .env.example            # Configuration template
├── src/
│   ├── api.py              # FastAPI backend (SSE streaming)
│   ├── cli.py              # Interactive CLI chat
│   ├── retriever.py        # RAG pipeline (embed → search → generate)
│   └── indexer.py          # Knowledge base indexer
├── config/
│   └── settings.py         # Settings loader (.env)
├── static/
│   └── index.html          # Web UI frontend
└── knowledge-base/         # Knowledge sources (gitignored)
    ├── _templates/          # Contribution templates
    ├── cves/                # CVE entries (yaml)
    ├── methodologies/       # Attack methodologies (markdown)
    └── tools/               # Tool usage notes (markdown)
```

---

## Architecture

```
User Query
    │
    ▼
r4gv1s.py (launcher)
    │
    ├─► Web UI ─► FastAPI (SSE stream)
    │                │
    └─► CLI Chat ────┤
                     │
                     ├─► Tool Call Loop (agentic)
                     │       │
                     │       ├─► nomic-embed-text (Ollama) → vector
                     │       └─► Qdrant similarity search → chunks
                     │
                     └─► LLM (OpenRouter / Ollama) → streaming answer
```

---

## Contributing

### Adding CVEs or Methodologies

1. Fork the repo
2. Copy a template from `knowledge-base/_templates/`
3. Fill it in and place it under the appropriate folder:
   - `knowledge-base/cves/YEAR/CVE-YYYY-XXXXX.yaml`
   - `knowledge-base/methodologies/CATEGORY/your-topic.md`
4. Submit a PR

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

> **Note:** HackTricks, PayloadsAllTheThings, and Nuclei Templates are not bundled due to licensing. The installer clones them locally.

---

## Disclaimer

R4GV1S is intended for **authorized penetration testing and security research only**. Always obtain proper written authorization before testing any system. The authors are not responsible for misuse.

---

## License

MIT License — see [LICENSE](LICENSE).

Knowledge base sources have their own licenses:
- HackTricks: CC BY-NC 4.0
- PayloadsAllTheThings: MIT
- Nuclei Templates: MIT
- GTFOBins: GPL-3.0
