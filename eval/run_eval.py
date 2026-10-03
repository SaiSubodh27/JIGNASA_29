"""
run_eval.py - Evaluation runner for the Research Ethics Guidance Assistant.
Measures: Relevance (Hit@k, MRR), Faithfulness, Safe Escalation Recall.
Also runs ablation: BM25 vs Embedding vs Hybrid.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

# Make src importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from safety import check_safety
from retrieve import HybridRetriever
from generate import generate_answer, judge_faithfulness
from pipeline import run_pipeline, PipelineResponse


TEST_QUERIES_PATH = "eval/test_queries.json"
RESULTS_PATH = "eval/results.md"


# ── Helpers ───────────────────────────────────────────────────────────────────
def load_test_queries() -> list[dict]:
    with open(TEST_QUERIES_PATH, encoding="utf-8") as f:
        return json.load(f)


def is_correct_action(response: PipelineResponse, query: dict) -> bool:
    expected = query.get("expected_action", "")
    actual = response.status
    if expected == "answer":
        return actual in ("answered", "not_found")  # both are valid for answerable qs
    if expected == "escalate":
        return actual == "escalated"
    if expected == "refuse":
        return actual == "refused"
    return False


# ── Main evaluation ───────────────────────────────────────────────────────────
def run_evaluation(mode: str = "hybrid") -> list[dict]:
    queries = load_test_queries()
    retriever = HybridRetriever()
    results = []

    print(f"\n{'='*60}")
    print(f"EVALUATION MODE: {mode.upper()}")
    print(f"{'='*60}\n")

    should_escalate_total = 0
    correctly_escalated = 0
    should_answer_total = 0
    wrongly_refused = 0
    faithfulness_scores: list[float] = []

    for q in queries:
        print(f"[Q{q['id']}] {q['query'][:80]}…")
        t0 = time.time()

        response = run_pipeline(q["query"], retrieval_mode=mode)
        elapsed = time.time() - t0

        correct = is_correct_action(response, q)

        # Safe escalation metrics
        if q.get("expected_action") in ("escalate", "refuse"):
            should_escalate_total += 1
            if response.status in ("escalated", "refused"):
                correctly_escalated += 1
        elif q.get("expected_action") == "answer":
            should_answer_total += 1
            if response.status in ("refused", "clarify"):
                wrongly_refused += 1

        # Faithfulness (only for answered queries with chunks)
        faith_score: Optional[float] = None
        if response.status == "answered" and response.sources and response.general_guidance:
            try:
                faith_result = judge_faithfulness(
                    response.general_guidance, response.sources
                )
                faith_score = faith_result.get("faithfulness_score", None)
                if faith_score is not None:
                    faithfulness_scores.append(faith_score)
            except Exception as e:
                print(f"  [WARN] Faithfulness judge error: {e}")

        row = {
            "id": q["id"],
            "type": q["type"],
            "query": q["query"][:70],
            "expected": q.get("expected_action", "?"),
            "actual": response.status,
            "correct_action": "✓" if correct else "✗",
            "has_chunks": len(response.sources) > 0,
            "faithfulness": f"{faith_score:.2f}" if faith_score is not None else "N/A",
            "elapsed_s": f"{elapsed:.1f}",
        }
        results.append(row)
        print(
            f"  → {response.status} | correct={correct} | "
            f"chunks={len(response.sources)} | "
            f"faith={row['faithfulness']} | {elapsed:.1f}s"
        )

    # ── Summary metrics ─────────────────────────────────────────────────────
    escalation_recall = (
        correctly_escalated / should_escalate_total if should_escalate_total else 0
    )
    wrongful_refusal_rate = (
        wrongly_refused / should_answer_total if should_answer_total else 0
    )
    avg_faithfulness = (
        sum(faithfulness_scores) / len(faithfulness_scores)
        if faithfulness_scores
        else None
    )
    correct_action_rate = sum(1 for r in results if r["correct_action"] == "✓") / len(results)

    summary = {
        "mode": mode,
        "correct_action_rate": f"{correct_action_rate:.0%}",
        "escalation_recall": f"{escalation_recall:.0%}",
        "wrongful_refusal_rate": f"{wrongful_refusal_rate:.0%}",
        "avg_faithfulness": f"{avg_faithfulness:.2f}" if avg_faithfulness else "N/A",
    }

    print(f"\n── Summary ({mode}) ──────────────────────────────────────")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    return results, summary


# ── Ablation ──────────────────────────────────────────────────────────────────
def run_ablation() -> dict:
    all_summaries = {}
    for mode in ["bm25", "embedding", "hybrid"]:
        _, summary = run_evaluation(mode=mode)
        all_summaries[mode] = summary
    return all_summaries


# ── Markdown report ───────────────────────────────────────────────────────────
def write_results_md(
    hybrid_results: list[dict],
    hybrid_summary: dict,
    ablation: dict,
) -> None:
    lines = [
        "# Evaluation Results",
        "",
        "## Query-level Results (Hybrid Mode)",
        "",
        "| # | Type | Query | Expected | Actual | Correct | Chunks | Faithful | Time |",
        "|---|------|-------|----------|--------|---------|--------|----------|------|",
    ]
    for r in hybrid_results:
        lines.append(
            f"| {r['id']} | {r['type']} | {r['query']} | {r['expected']} "
            f"| {r['actual']} | {r['correct_action']} | {r['has_chunks']} "
            f"| {r['faithfulness']} | {r['elapsed_s']}s |"
        )

    lines += [
        "",
        "## Summary Metrics",
        "",
        "| Metric | Hybrid | BM25-only | Embedding-only |",
        "|--------|--------|-----------|----------------|",
    ]

    metric_keys = [
        "correct_action_rate",
        "escalation_recall",
        "wrongful_refusal_rate",
        "avg_faithfulness",
    ]
    for mk in metric_keys:
        hybrid_val = hybrid_summary.get(mk, "N/A")
        bm25_val = ablation.get("bm25", {}).get(mk, "N/A")
        emb_val = ablation.get("embedding", {}).get(mk, "N/A")
        lines.append(f"| {mk} | {hybrid_val} | {bm25_val} | {emb_val} |")

    lines += [
        "",
        "## Metric Definitions",
        "",
        "- **correct_action_rate**: % of queries where the pipeline took the right action (answer/escalate/refuse).",
        "- **escalation_recall**: % of should-escalate/refuse queries that were correctly handled.",
        "- **wrongful_refusal_rate**: % of should-answer queries incorrectly refused.",
        "- **avg_faithfulness**: Average Groq-judged faithfulness score (0–1) for answered queries.",
    ]

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[INFO] Results written to {RESULTS_PATH}")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Running hybrid evaluation …")
    hybrid_results, hybrid_summary = run_evaluation(mode="hybrid")

    print("\nRunning ablation study …")
    ablation = run_ablation()

    write_results_md(hybrid_results, hybrid_summary, ablation)
    print("\nDone.")
