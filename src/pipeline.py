"""
pipeline.py - Full end-to-end pipeline: safety → retrieval → generation → output.
Can be used by both the Streamlit UI and the evaluation script.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

# Make src importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

from safety import check_safety, SafetyDecision
from retrieve import HybridRetriever
from generate import generate_answer

# Lazy-load the retriever (expensive: loads models and indices)
_retriever: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever


# ── Response data model ───────────────────────────────────────────────────────
@dataclass
class PipelineResponse:
    status: Literal["answered", "escalated", "refused", "clarify", "not_found"]
    question: str
    safety_decision: SafetyDecision
    general_guidance: str = ""
    needs_committee: str = ""
    sources: list[dict] = field(default_factory=list)
    citations: list[int] = field(default_factory=list)
    retrieval_mode: str = "hybrid"
    confidence_ok: bool = True

    def format_text(self) -> str:
        """Return a plain-text formatted answer."""
        lines = []

        if self.status == "refused":
            lines.append(self.safety_decision.response_hint)
            return "\n".join(lines)

        if self.status == "escalated":
            lines.append(self.safety_decision.response_hint)
            if self.general_guidance and self.general_guidance != "NOT_FOUND":
                lines.append("\n─────────────────────────────────────────")
                lines.append("GENERAL GUIDANCE (from approved documents)")
                lines.append("─────────────────────────────────────────")
                lines.append(self.general_guidance)
            if self.sources:
                lines.append("\nSOURCES")
                for i, src in enumerate(self.sources):
                    lines.append(
                        f"[{i+1}] {src['doc_title']} (v{src['version']}), "
                        f"{src.get('section', 'N/A')}"
                    )
            return "\n".join(lines)

        if self.status == "not_found":
            return (
                "❌ **Not found in approved sources.**\n\n"
                "The approved ethics documents do not contain specific guidance "
                "on this topic. Please consult your institution's ethics committee."
            )

        if self.status == "clarify":
            return self.safety_decision.response_hint

        # answered
        lines.append("GENERAL GUIDANCE")
        lines.append("─" * 40)
        lines.append(self.general_guidance)
        lines.append("")
        lines.append("NEEDS YOUR ETHICS COMMITTEE")
        lines.append("─" * 40)
        lines.append(self.needs_committee)
        lines.append("")
        lines.append("SOURCES")
        lines.append("─" * 40)
        for i, src in enumerate(self.sources):
            lines.append(
                f"[{i+1}] {src['doc_title']} (v{src['version']}), "
                f"Section: {src.get('section', 'N/A')}, "
                f"Authority: {src['authority']}"
            )
        return "\n".join(lines)


# ── Main pipeline function ────────────────────────────────────────────────────
def run_pipeline(
    question: str,
    top_k: int = 5,
    retrieval_mode: str = "hybrid",
) -> PipelineResponse:
    """
    Full RAG pipeline.
    1. Safety check
    2. Retrieve chunks
    3. Confidence check
    4. Generate answer
    5. Return structured response
    """
    # Step 1: Safety / scope check
    safety = check_safety(question)

    if safety.action == "refuse":
        return PipelineResponse(
            status="refused",
            question=question,
            safety_decision=safety,
        )

    if safety.action == "clarify":
        return PipelineResponse(
            status="clarify",
            question=question,
            safety_decision=safety,
        )

    # Step 2: Retrieval
    retriever = get_retriever()
    chunks, confidence_ok = retriever.search(
        question, top_k=top_k, mode=retrieval_mode
    )

    # Step 3: Confidence check
    if not confidence_ok or not chunks:
        base_response = PipelineResponse(
            status="not_found",
            question=question,
            safety_decision=safety,
            confidence_ok=False,
        )
        # Escalation queries still get the not-found + escalation message
        if safety.action == "escalate":
            base_response.status = "escalated"
            base_response.general_guidance = "NOT_FOUND"
        return base_response

    # Step 4: Generate answer
    result = generate_answer(question, chunks)

    if safety.action == "escalate":
        status = "escalated"
    elif result["general_guidance"] == "NOT_FOUND":
        status = "not_found"
    else:
        status = "answered"

    return PipelineResponse(
        status=status,
        question=question,
        safety_decision=safety,
        general_guidance=result["general_guidance"],
        needs_committee=result["needs_committee"],
        sources=chunks,
        citations=result["citations"],
        retrieval_mode=retrieval_mode,
        confidence_ok=confidence_ok,
    )


# ── CLI usage ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not question:
        question = input("Enter your ethics question: ").strip()
    response = run_pipeline(question)
    print(response.format_text())


def run_audit_pipeline(paper_text: str, base_paper_text: str = "", top_k: int = 5, retrieval_mode: str = "hybrid") -> dict:
    """
    RAG pipeline for Auditing a paper excerpt against a base paper.
    """
    retriever = get_retriever()
    search_query = paper_text[:500]
    chunks, confidence_ok = retriever.search(search_query, top_k=top_k, mode=retrieval_mode)
    
    if not chunks:
        return {
            "compliant": [],
            "red_flags": [],
            "missing_info": ["No relevant ethics guidelines found for this text."],
            "disclaimer": "Pipeline Error."
        }
        
    from generate import generate_audit
    return generate_audit(paper_text, base_paper_text, chunks)


def run_audit_chat(question: str, paper_text: str, base_paper_text: str = "", top_k: int = 5, retrieval_mode: str = "hybrid") -> str:
    """Retrieves new chunks for a follow-up question and generates an answer."""
    retriever = get_retriever()
    chunks, _ = retriever.search(question, top_k=top_k, mode=retrieval_mode)
    from generate import generate_audit_chat
    return generate_audit_chat(question, paper_text, base_paper_text, chunks)
