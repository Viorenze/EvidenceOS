"""Server-side citation extraction and verification (AGENTS.md Rule 6).

Never trust citation markers from the model without checking them against
the retrieved chunks. Cleans out invalid markers from the final answer text
to prevent dangling citations.
"""

import re
from typing import Any, Dict, List, Set, Tuple


def extract_citation_numbers(text: str) -> List[int]:
    """Extract all citation indices `[n]` in appearance order, deduplicated."""
    if not text:
        return []
    matches = re.findall(r"\[(\d+)\]", text)
    seen: Set[int] = set()
    numbers: List[int] = []
    for m in matches:
        val = int(m)
        if val not in seen:
            seen.add(val)
            numbers.append(val)
    return numbers


def clean_answer_citations(text: str, valid_numbers: Set[int]) -> str:
    """Remove illegal or out-of-range [n] citation markers from the answer text.

    Ensures the final user-facing text never contains dangling references.
    """
    if not text:
        return ""

    def _replace_marker(match: re.Match) -> str:
        n = int(match.group(1))
        if n in valid_numbers:
            return match.group(0)
        # Remove illegal citation marker
        return ""

    cleaned = re.sub(r"\[(\d+)\]", _replace_marker, text)
    # Normalize excessive spaces created by removed tags
    cleaned = re.sub(r" +", " ", cleaned)
    # Normalize spaces before punctuation
    cleaned = re.sub(r" +([，。！？,.!?])", r"\1", cleaned)
    return cleaned.strip()


def verify_citations(
    answer: str,
    chunks: List[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]], bool]:
    """Validate model citations against retrieved chunks (1-indexed).

    Returns:
        (cleaned_answer, valid_citations_list, is_valid_flag)
    """
    if not answer or not chunks:
        return (answer or "", [], False)

    extracted_numbers = extract_citation_numbers(answer)
    valid_citations: List[Dict[str, Any]] = []
    valid_numbers: Set[int] = set()

    k = len(chunks)
    for n in extracted_numbers:
        # Chunks are presented to LLM 1-indexed: 1 <= n <= k
        if 1 <= n <= k:
            chunk = chunks[n - 1]
            valid_numbers.add(n)
            valid_citations.append({
                "n": n,
                "chunk_id": str(chunk.get("id", "")),
                "document": chunk.get("document_filename") or chunk.get("document", ""),
                "page": chunk.get("page"),
                "heading": chunk.get("heading"),
                "snippet": chunk.get("content", "")[:200],
            })

    cleaned_answer = clean_answer_citations(answer, valid_numbers)
    is_valid = len(valid_citations) > 0

    return (cleaned_answer, valid_citations, is_valid)
