"""Unit tests to validate the integrity of evals/dataset.jsonl against evals/corpus/."""

import json
from pathlib import Path


def test_dataset_structure_and_corpus_alignment():
    """Verify evaluation dataset contains 20 answerable, 5 unanswerable questions, and all snippets match corpus."""
    evals_dir = Path(__file__).resolve().parent.parent / "evals"
    dataset_file = evals_dir / "dataset.jsonl"
    corpus_dir = evals_dir / "corpus"

    assert dataset_file.exists(), "evals/dataset.jsonl must exist"
    assert corpus_dir.exists(), "evals/corpus/ must exist"

    questions = []
    with open(dataset_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))

    assert len(questions) == 25, f"Expected 25 questions, got {len(questions)}"

    answerable = [q for q in questions if q.get("type") == "answerable"]
    unanswerable = [q for q in questions if q.get("type") == "unanswerable"]

    assert len(answerable) == 20, f"Expected 20 answerable questions, got {len(answerable)}"
    assert len(unanswerable) == 5, f"Expected 5 unanswerable questions, got {len(unanswerable)}"

    # Validate each answerable question's gold_doc and gold_snippet
    for q in answerable:
        doc_filename = q.get("gold_doc")
        snippet = q.get("gold_snippet")

        assert doc_filename, f"Question {q['id']} must specify gold_doc"
        assert snippet, f"Question {q['id']} must specify gold_snippet"

        doc_path = corpus_dir / doc_filename
        assert doc_path.exists(), f"Corpus document '{doc_filename}' not found for question {q['id']}"

        doc_content = doc_path.read_text(encoding="utf-8")
        assert snippet in doc_content, (
            f"gold_snippet '{snippet}' for question {q['id']} was not found in {doc_filename}"
        )
