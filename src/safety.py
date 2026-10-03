"""
safety.py - Safety, refusal, and escalation rules.
Run before retrieval (scope check) and optionally again after generation.
Returns a structured decision dict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass
class SafetyDecision:
    action: Literal["answer", "escalate", "refuse", "clarify"]
    category: str
    reason: str
    response_hint: str  # pre-canned message to show the user


# ── Keyword/regex rule tables ─────────────────────────────────────────────────
_OFF_TOPIC_PATTERNS = [
    r"\bfood\b", r"\brecipe\b", r"\bbiryani\b", r"\brestaurant\b",
    r"\bsport\b", r"\bmovie\b", r"\bfilm\b", r"\bmusic\b",
    r"\bweather\b", r"\bstock\b", r"\bcrypto\b",
]

_INJECTION_PATTERNS = [
    r"ignore\s+(your|all|previous)\s+(rules?|instructions?|guidelines?)",
    r"you are now",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if",
    r"disregard\s+your",
    r"jailbreak",
    r"(approve|confirm|certify)\s+my\s+study",
    r"override\s+(the|your)\s+(rules?|system)",
]

_MISCONDUCT_PATTERNS = [
    r"\b(ghost|fake|fabricat|fraud|forger|plagi)\w*\b",
    r"my\s+(supervisor|advisor|pi|professor)\s+.{0,60}(author|credit|data)",
    r"forced\s+me\s+to",
    r"steal(ing)?\s+(my|the)\s+(work|data|credit)",
    r"putting\s+(his|her|their)\s+name\s+on",
    r"(add|added|adding)\s+(him|her|them)sel(f|ves)\s+as\s+author",
    r"name\s+on\s+my\s+paper\s+without\s+contribut",
    r"without\s+contribut\w+.{0,40}(author|paper|manuscript)",
]

_VULNERABLE_PATTERNS = [
    r"\bchildren\b", r"\bminors?\b", r"\bprisoners?\b", r"\binmates?\b",
    r"\bdetainee\b",
    r"\bpregnant\b", r"\bfetus\b", r"\bembryo\b",
    r"\bdement\w+\b", r"\bcognitive\s+impair\w+\b",
    r"\bincapacitated\b", r"\black\s+(of\s+)?capacity\b",
    r"\bmental\s+(health|illness|disorder)\b",
]

_CASE_SPECIFIC_PATTERNS = [
    r"\bmy\s+study\b", r"\bmy\s+research\b", r"\bour\s+study\b",
    r"\bcan\s+i\b", r"\bis\s+it\s+ok\s+(for\s+me|if\s+i)\b",
    r"\bam\s+i\s+allowed\b", r"\bshould\s+i\b",
    r"\bmy\s+participants?\b", r"\bmy\s+data\b",
    r"\bmy\s+institution\b", r"\bmy\s+hospital\b",
    r"approved\s+(by\s+the)?\s*(irb|ethics\s+committee)",
    r"do\s+i\s+need\s+(to\s+get\s+)?approval",
]

_VAGUE_PATTERNS = [
    r"^is\s+this\s+ethical\??$",
    r"^is\s+this\s+ok\??$",
    r"^what\s+do\s+you\s+think\??$",
    r"^help\s+me\s+with\s+ethics\.?$",
]


def _match_any(patterns: list[str], text: str) -> bool:
    tl = text.lower()
    return any(re.search(p, tl) for p in patterns)


# ── Main function ─────────────────────────────────────────────────────────────
def check_safety(question: str) -> SafetyDecision:
    """
    Run rule-based safety checks on the raw user question.
    Returns a SafetyDecision that says whether to answer, escalate, refuse, or clarify.
    """
    q = question.strip()

    # 1. Prompt injection
    if _match_any(_INJECTION_PATTERNS, q):
        return SafetyDecision(
            action="refuse",
            category="prompt_injection",
            reason="The question appears to contain a prompt-injection attempt.",
            response_hint=(
                "⚠️ **Request refused.** I detected an attempt to override my "
                "guidelines. I cannot approve studies, bypass rules, or act outside "
                "my defined role as a Research Ethics Guidance Assistant."
            ),
        )

    # 2. Off-topic
    if _match_any(_OFF_TOPIC_PATTERNS, q):
        return SafetyDecision(
            action="refuse",
            category="off_topic",
            reason="The question is outside the scope of research ethics.",
            response_hint=(
                "🚫 **Out of scope.** I can only assist with research ethics topics "
                "such as informed consent, data handling, authorship, and publication "
                "ethics. Please ask a question in one of those areas."
            ),
        )

    # 3. Suspected misconduct
    if _match_any(_MISCONDUCT_PATTERNS, q):
        return SafetyDecision(
            action="escalate",
            category="suspected_misconduct",
            reason="The question suggests a possible misconduct situation.",
            response_hint=(
                "⚠️ **This question may involve research misconduct.** I can share "
                "general guidance on publication integrity and authorship standards, "
                "but I cannot adjudicate individual cases. Please contact your "
                "institution's Research Integrity Officer or ethics committee."
            ),
        )

    # 4. Vulnerable groups — give general principle then escalate
    if _match_any(_VULNERABLE_PATTERNS, q):
        return SafetyDecision(
            action="escalate",
            category="vulnerable_group",
            reason="The question involves research with a vulnerable population.",
            response_hint=(
                "⚠️ **Vulnerable participants involved.** I will provide general "
                "ethical principles from approved guidance, but any specific study "
                "design decisions must be reviewed by your ethics committee / IRB."
            ),
        )

    # 5. Case-specific
    if _match_any(_CASE_SPECIFIC_PATTERNS, q):
        return SafetyDecision(
            action="escalate",
            category="case_specific",
            reason="The question asks for a decision about a specific study or situation.",
            response_hint=(
                "⚠️ **Case-specific question detected.** I can only provide general "
                "guidance from approved ethics documents. For decisions about your "
                "specific study, please consult your Institutional Review Board (IRB) "
                "or ethics committee."
            ),
        )

    # 6. Vague question
    if _match_any(_VAGUE_PATTERNS, q) or len(q.split()) < 4:
        return SafetyDecision(
            action="clarify",
            category="vague",
            reason="The question is too vague to retrieve meaningful guidance.",
            response_hint=(
                "❓ **Please clarify your question.** Could you describe the specific "
                "ethics topic you are asking about? For example: informed consent, "
                "data privacy, authorship criteria, or duplicate publication."
            ),
        )

    # 7. Otherwise: safe to answer
    return SafetyDecision(
        action="answer",
        category="in_scope",
        reason="Question appears to be a general ethics inquiry.",
        response_hint="",
    )


# ── Convenience for pipeline use ─────────────────────────────────────────────
def is_answerable(question: str) -> tuple[bool, SafetyDecision]:
    decision = check_safety(question)
    return decision.action == "answer", decision
