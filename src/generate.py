"""
generate.py - Groq LLM client for grounded, cited answer generation.
Also provides a faithfulness judge prompt for evaluation.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from dotenv import load_dotenv
from groq import Groq, RateLimitError

load_dotenv()

# Model selection — use models available on this Groq account
PRIMARY_MODEL = "qwen/qwen3.8-27b"       # Good TPM limit, strong reasoning
FALLBACK_MODEL = "openai/gpt-oss-20b"    # Smaller fallback

# Max chars per source chunk to keep prompts within token limits
MAX_SOURCE_CHARS = 600

# ── Initialise client ─────────────────────────────────────────────────────────
_api_key = os.getenv("GROQ_API_KEY")
if not _api_key:
    raise EnvironmentError(
        "GROQ_API_KEY not found. Add it to your .env file or export it as an "
        "environment variable."
    )
client = Groq(api_key=_api_key)

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a Research Ethics Guidance Assistant.

Rules:
1. Answer ONLY using the numbered SOURCES provided below. Never use outside knowledge.
2. Cite every factual claim with the source number in brackets, e.g. [1], [2]. The number MUST exactly match the source number provided.
3. If the sources do not contain a clear answer, you MUST set "general_guidance" to EXACTLY the string "NOT_FOUND", and set "needs_committee" to "Topic not covered in approved documents."
4. Never decide whether a specific study, person, or situation is ethical or approved.
5. Give GENERAL guidance only. Always note that case-specific decisions belong to the
   researcher's own institution's ethics committee / IRB, NOT this tool.
6. Return your answer strictly as a JSON object with this exact schema:
   {
     "general_guidance": "<answer with inline citations, OR the exact string NOT_FOUND>",
     "needs_committee": "<what this tool cannot decide and why, OR default message if NOT_FOUND>",
     "citations": [<list of source numbers used, as integers>]
   }
"""

FAITHFULNESS_JUDGE_PROMPT = """You are a faithfulness judge.

Given an ANSWER and a set of SOURCES, split the answer into individual factual claims.
For each claim, check whether it is directly supported by the sources.

Return a JSON object:
{
  "claims": [
    {"claim": "...", "supported": true/false, "source_number": <int or null>}
  ],
  "faithfulness_score": <float 0-1, supported_claims / total_claims>
}
"""


# ── Helper: build source block ────────────────────────────────────────────────
def _build_sources(chunks: list[dict]) -> str:
    def trunc(text: str) -> str:
        return text[:MAX_SOURCE_CHARS] + ("…" if len(text) > MAX_SOURCE_CHARS else "")

    return "\n\n".join(
        f"[{i + 1}] {c['doc_title']} (v{c['version']}), "
        f"Section: {c.get('section', 'N/A')}, "
        f"Authority level: {c['authority']}:\n{trunc(c['text'])}"
        for i, c in enumerate(chunks)
    )


# ── Core generation ───────────────────────────────────────────────────────────
def generate_answer(
    question: str,
    chunks: list[dict],
    model: str = PRIMARY_MODEL,
    max_retries: int = 3,
) -> dict:
    """
    Call the Groq LLM to produce a grounded, cited answer.
    Returns a dict with keys: general_guidance, needs_committee, citations.
    Falls back to FALLBACK_MODEL on RateLimitError.
    """
    sources = _build_sources(chunks)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"SOURCES:\n{sources}\n\nQUESTION: {question}",
        },
    ]

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
            content = resp.choices[0].message.content
            result = json.loads(content)
            # Normalise keys
            return {
                "general_guidance": result.get("general_guidance", "NOT_FOUND"),
                "needs_committee": result.get(
                    "needs_committee",
                    "All case-specific decisions should be directed to your "
                    "institution's ethics committee / IRB.",
                ),
                "citations": result.get("citations", []),
            }
        except RateLimitError:
            if model != FALLBACK_MODEL:
                print(f"[WARN] Rate limit on {model}; switching to {FALLBACK_MODEL}")
                model = FALLBACK_MODEL
            else:
                wait = 2 ** attempt
                print(f"[WARN] Rate limit. Retrying in {wait}s …")
                time.sleep(wait)
        except json.JSONDecodeError:
            # Model didn't return valid JSON — try to extract it
            raw = resp.choices[0].message.content
            try:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                return json.loads(raw[start:end])
            except Exception:
                return {
                    "general_guidance": raw,
                    "needs_committee": "Unable to parse structured response.",
                    "citations": [],
                }

    return {
        "general_guidance": "NOT_FOUND",
        "needs_committee": "Service temporarily unavailable. Please try again.",
        "citations": [],
    }


# ── Faithfulness judge ────────────────────────────────────────────────────────
def judge_faithfulness(answer: str, chunks: list[dict]) -> dict:
    """
    Use Groq as a faithfulness judge for evaluation purposes.
    Returns {"claims": [...], "faithfulness_score": float}.
    """
    sources = _build_sources(chunks)
    messages = [
        {"role": "system", "content": FAITHFULNESS_JUDGE_PROMPT},
        {
            "role": "user",
            "content": f"ANSWER:\n{answer}\n\nSOURCES:\n{sources}",
        },
    ]
    resp = client.chat.completions.create(
        model=FALLBACK_MODEL,  # cheaper model for judging
        temperature=0,
        response_format={"type": "json_object"},
        messages=messages,
    )
    return json.loads(resp.choices[0].message.content)

# ── Audit Prompt ──────────────────────────────────────────────────────────────
AUDIT_PROMPT = """You are a Research Ethics Auditor.

You will be provided with an excerpt from a research paper's methodology or abstract (the "USER PAPER"), followed by official ethics guidelines (the "SOURCES").

Your job is to cross-reference the user's paper against the official rules and output a compliance audit in JSON format.

Rules:
1. ONLY use the provided SOURCES. Do not use outside knowledge.
2. Identify areas where the paper aligns with the rules (Compliant).
3. Identify areas where the paper violates or risks violating the rules (Red Flags).
4. Identify missing ethical information (Missing Info).
5. Always cite the source number in brackets, e.g. [1].
6. You cannot officially approve or reject a study. Add a disclaimer.

Output JSON format:
{
  "compliant": ["<point 1 with citation>"],
  "red_flags": ["<point 1 with citation>"],
  "missing_info": ["<point 1>"],
  "disclaimer": "This is an automated audit. Final approval requires your IRB."
}
"""

def generate_audit(paper_text: str, base_paper_text: str, chunks: list[dict]) -> dict:
    sources_text = _build_sources(chunks)
    safe_paper = paper_text[:2000] + ("..." if len(paper_text) > 2000 else "")
    safe_base = base_paper_text[:2000] + ("..." if len(base_paper_text) > 2000 else "") if base_paper_text else "None provided."
    user_content = f"MAIN PAPER:\n{safe_paper}\n\nBASE PAPER:\n{safe_base}\n\nSOURCES:\n{sources_text}"
    
    try:
        import json
        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": AUDIT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as e:
        print(f"[ERROR] Audit generation failed: {e}")
        return {
            "compliant": [],
            "red_flags": ["Error generating audit."],
            "missing_info": [],
            "disclaimer": "Pipeline Error."
        }


def generate_audit_chat(question: str, paper_text: str, base_paper_text: str, chunks: list[dict]) -> str:
    """Follow-up chat for the audit mode, bypassing case-specific blocks."""
    sources_text = _build_sources(chunks)
    safe_paper = paper_text[:2000]
    safe_base = base_paper_text[:2000] if base_paper_text else "None" 
    
    sys_prompt = (
        "You are a Research Ethics Auditor answering a follow-up question.\n"
        "1. Apply the principles from the OFFICIAL GUIDELINES to the specific situation described in the MAIN PAPER and BASE PAPER.\n"
        "2. It is completely OK if the guidelines do not explicitly mention the user's specific dataset or algorithm names. You MUST apply the general rules (like plagiarism, consent, or citation) to their specific scenario.\n"
        "3. Cite the guidelines using [1].\n"
        "4. Only say NOT_FOUND if the guidelines are entirely irrelevant to the core ethical question."
    )
    
    user_msg = f"MAIN PAPER:\n{safe_paper}\n\nBASE PAPER:\n{safe_base}\n\nOFFICIAL GUIDELINES:\n{sources_text}\n\nUSER QUESTION:\n{question}"
    
    try:
        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content or "No response."
    except Exception as e:
        return f"Error connecting to LLM: {e}"
