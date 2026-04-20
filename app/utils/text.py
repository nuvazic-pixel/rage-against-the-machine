import re
import hashlib
import nltk
from typing import Optional


def tokenize(text: str) -> list[str]:
    """Consistent word tokenizer for BM25 and cache keys."""
    return re.findall(r"\b\w+\b", text.lower())


def stable_cache_key(query: str, prefix: str = "search") -> str:
    """Deterministic Redis key — stable across process restarts."""
    normalized = " ".join(tokenize(query))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def min_max_normalize(values: list[float]) -> list[float]:
    if not values:
        return values
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def extract_obsidian_links(text: str) -> list[str]:
    """Extract [[wiki-links]] from markdown."""
    return re.findall(r"\[\[(.*?)\]\]", text)


def chunk_text(text: str, max_chars: int = 300, overlap_sentences: int = 1) -> list[str]:
    """
    Sentence-aware chunking with overlap.
    Falls back to character chunking if NLTK fails.
    """
    try:
        sentences = nltk.sent_tokenize(text)
    except Exception:
        # Simple fallback
        return _char_chunk(text, max_chars)

    if not sentences:
        return [text] if text.strip() else []

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_len = 0

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        if current_len + len(sent) > max_chars and current_sentences:
            chunks.append(" ".join(current_sentences))
            # Keep last N sentences as overlap
            current_sentences = current_sentences[-overlap_sentences:] if overlap_sentences else []
            current_len = sum(len(s) for s in current_sentences)

        current_sentences.append(sent)
        current_len += len(sent)

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return [c for c in chunks if c.strip()]


def _char_chunk(text: str, size: int = 300, overlap: int = 50) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return [c for c in chunks if c.strip()]
