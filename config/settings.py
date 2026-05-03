"""
R4GV1S - Settings
Loads from .env or environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: str   = os.getenv("LLM_PROVIDER", "openrouter")   # ollama | openrouter | openai
    llm_model: str      = os.getenv("LLM_MODEL", "openrouter/free")
    api_key: str        = os.getenv("API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    temperature: float  = float(os.getenv("TEMPERATURE", "0.2"))

    # ── Embedding ─────────────────────────────────────────────────────────────
    embed_provider: str = os.getenv("EMBED_PROVIDER", "ollama")     # ollama | openai
    embed_model: str    = os.getenv("EMBED_MODEL", "nomic-embed-text")
    vector_size: int    = int(os.getenv("VECTOR_SIZE", "768"))

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str      = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int      = int(os.getenv("QDRANT_PORT", "6333"))
    collection_name: str  = os.getenv("COLLECTION_NAME", "pentest_kb")

    # ── RAG ───────────────────────────────────────────────────────────────────
    top_k: int           = int(os.getenv("TOP_K", "6"))
    max_tool_calls: int  = int(os.getenv("MAX_TOOL_CALLS", "4"))
    chunk_min_chars: int = int(os.getenv("CHUNK_MIN_CHARS", "100"))
    chunk_max_chars: int = int(os.getenv("CHUNK_MAX_CHARS", "1500"))

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))


settings = Settings()
