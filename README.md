# R4GV1S

**RAG-based Pentest Assistant** — an offline-capable AI assistant for penetration testers, powered by your own knowledge base.

R4GV1S uses Retrieval-Augmented Generation (RAG) with agentic tool calling. Instead of relying on a model's training data, it searches a local vector database built from HackTricks, PayloadsAllTheThings, Nuclei Templates, and community contributions — then generates accurate, copy-paste ready commands and payloads.

![R4GV1S Screenshot](docs/screenshot.png)

---

## Features

- **Agentic search** — the model decides what to search and how many times
- **Fully local option** — runs entirely offline with Ollama
- **Cloud option** — OpenRouter free tier supported (no GPU needed)
- **Streaming UI** — token-by-token output with source attribution
- **Community knowledge base** — contribute CVEs, methodologies, and tool notes via PR
- **Hybrid search** — vector similarity + keyword matching

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/yourusername/r4gv1s
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

### 3. Start

```bash
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000` in your browser.

---

## Manual Setup

If you prefer to set up manually:

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

---

## Indexer CLI

```bash
# Index a directory
python src/indexer.py index knowledge-base/

# Index a single file
python src/indexer.py index knowledge-base/cves/CVE-2024-1234.yaml

# Show stats
python src/indexer.py stats

# Reset (deletes all indexed data)
python src/indexer.py reset
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

### Knowledge Base Structure

```
knowledge-base/
├── _templates/          # Contribution templates
│   ├── cve-template.yaml
│   └── methodology-template.md
├── cves/                # CVE entries (yaml)
│   └── 2024/
├── methodologies/       # Attack methodologies (markdown)
│   ├── web/
│   ├── network/
│   └── privesc/
└── tools/               # Tool usage notes (markdown)
```

> **Note:** HackTricks, PayloadsAllTheThings, and Nuclei Templates are not bundled due to licensing. The installer clones them locally.

---

## Architecture

```
User Query
    │
    ▼
FastAPI (SSE stream)
    │
    ├─► Tool Call Loop (agentic)
    │       │
    │       ├─► nomic-embed-text (Ollama) → vector
    │       └─► Qdrant similarity search → chunks
    │
    └─► LLM (OpenRouter / Ollama) → streaming answer
```

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
