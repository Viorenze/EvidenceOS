"""Server-side citation extraction and verification (AGENTS.md Rule 6).

Why this citation verification design works (Interview Reference):
1. Citation contract and normalization:
   Supports [1], Chinese full-width 【1】, and comma-separated [1, 2].
   Normalizes them before validation to prevent false refusals when domestic LLMs
   emit full-width brackets or aggregated citations.
2. Code and subscript preservation:
   Fenced code blocks (```) and inline code (`) are shielded from citation cleaning.
   Variable access notation like `data[0]` is explicitly preserved via negative
   lookbehind (`(?<![a-zA-Z0-9_])`), preventing data corruption in technical answers.
3. Clean answer post-processing:
   Only invalid markers in prose are stripped, preserving indentation and code whitespace.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple


def extract_citation_numbers(text: str) -> List[int]:
    """Extract all citation indices `[n]` in appearance order, deduplicated.

    Supports `[1]`, Chinese full-width `【1】`, and grouped citations `[1, 2]`.
    Ignores subscript notations in code like `data[0]`.
    """
    if not text:
        return []

    # Strip code blocks and inline code to prevent false positives from code
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`[^`\n]+`", "", cleaned)

    # Normalize full-width Chinese brackets
    cleaned = re.sub(r"【(\d+(?:\s*,\s*\d+)*)】", r"[\1]", cleaned)

    # Match bracketed numbers not preceded by identifier characters
    matches = re.findall(r"(?<![a-zA-Z0-9_])\[(\d+(?:\s*,\s*\d+)*)\]", cleaned)
    seen: Set[int] = set()
    numbers: List[int] = []
    for m in matches:
        for part in m.split(","):
            part_str = part.strip()
            if part_str.isdigit():
                val = int(part_str)
                if val not in seen:
                    seen.add(val)
                    numbers.append(val)
    return numbers


def clean_answer_citations(text: str, valid_numbers: Set[int]) -> str:
    """Remove illegal or out-of-range citation markers from prose.

    Preserves code blocks, inline code, and programming subscripts (e.g. data[0]).
    Only cleans dangling citation markers and their associated trailing space.
    """
    if not text:
        return ""

    # Split by fenced code blocks and inline code to shield code content from tampering
    parts = re.split(r"(```[\s\S]*?```|`[^`\n]+`)", text)

    for i in range(0, len(parts), 2):
        part = parts[i]

        # Normalize Chinese brackets in prose
        part = re.sub(r"【(\d+(?:\s*,\s*\d+)*)】", r"[\1]", part)

        def _replace_marker(match: re.Match) -> str:
            raw_nums = match.group(1)
            nums = [int(n.strip()) for n in raw_nums.split(",") if n.strip().isdigit()]
            valid = [n for n in nums if n in valid_numbers]
            if not valid:
                return ""
            if len(valid) == len(nums) and len(valid) == 1:
                return f"[{valid[0]}]"
            return "".join(f"[{n}]" for n in valid)

        part = re.sub(r"(?<![a-zA-Z0-9_])\[(\d+(?:\s*,\s*\d+)*)\]", _replace_marker, part)
        # Normalize double spaces and space before punctuation created by removed markers
        part = re.sub(r"  +", " ", part)
        part = re.sub(r" +([，。！？,.!?])", r"\1", part)
        parts[i] = part

    return "".join(parts).strip()


def verify_citations(
    answer: str,
    chunks: List[Dict[str, Any]],
    snippet_chars: int = 200,
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
                "snippet": chunk.get("content", "")[:snippet_chars],
            })

    cleaned_answer = clean_answer_citations(answer, valid_numbers)
    is_valid = len(valid_citations) > 0

    return (cleaned_answer, valid_citations, is_valid)
