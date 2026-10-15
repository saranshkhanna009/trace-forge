"""Inspectably simple evidence retrieval for maintenance documents."""

from __future__ import annotations

import re

from .models import EvidenceChunk, EvidenceHit


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", re.IGNORECASE)


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_RE.findall(text))


def retrieve(query: str, chunks: list[EvidenceChunk], top_k: int = 5) -> list[EvidenceHit]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    query_terms = set(tokenize(query))
    if not query_terms:
        return []
    normalized_query = " ".join(tokenize(query))
    hits: list[EvidenceHit] = []
    for chunk in chunks:
        chunk_terms = set(tokenize(chunk.text))
        overlap = tuple(sorted(query_terms & chunk_terms))
        if not overlap:
            continue
        score = len(overlap) / len(query_terms)
        normalized_text = " ".join(tokenize(chunk.text))
        if normalized_query in normalized_text:
            score = min(1.0, score + 0.2)
        hits.append(EvidenceHit(chunk=chunk, score=round(score, 6), overlap_terms=overlap))
    hits.sort(key=lambda item: (-item.score, item.chunk.id))
    return hits[:top_k]
