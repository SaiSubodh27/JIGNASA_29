# Project Report: Research Ethics Guidance Assistant

**Project:** JIG26_29 · Track C: Ethics Compliance & AI Safety
**Goal:** Build a robust, grounded RAG assistant for researchers to query institutional ethics guidelines.

## 1. Introduction
The Research Ethics Guidance Assistant is an AI-powered tool designed to help researchers navigate complex ethics guidelines. Unlike general-purpose LLMs which can hallucinate legal or ethical advice, this assistant relies entirely on a strictly curated set of approved documents using a Retrieval-Augmented Generation (RAG) architecture. It is built to answer questions when the information is available, and safely refuse, escalate, or clarify when the query is risky, out of scope, or requires an official Ethics Committee review.

## 2. Methodology
The system architecture implements a gated RAG pipeline:
1. **Safety Gate:** A pre-retrieval layer (implemented in Python via regex logic) intercepts high-risk or off-topic queries before they ever reach the LLM. 
2. **Hybrid Retrieval:** We use a combination of exact keyword matching (BM25) and semantic embedding search (scikit-learn TF-IDF + TruncatedSVD LSA). The results are merged using Reciprocal Rank Fusion (RRF). Note: We explicitly avoided neural embeddings (like PyTorch-based sentence-transformers) to ensure maximum compatibility across all CPU environments.
3. **Grounded Generation:** The top retrieved chunks are injected into the context of the Groq LLM (`qwen/qwen3.8-27b`). The system prompt rigidly enforces that the model must return answers strictly as JSON, citing exact source numbers, and returning `NOT_FOUND` if the answer is missing.

### 2.1 Supported Documents
The system currently indexes four authoritative documents (all chunks tagged with version metadata):
* **Declaration of Helsinki (v2013)** · International Guideline
* **ICMJE Recommendations (v2023)** · Professional Standard
* **COPE Core Practices (v2017)** · Professional Standard
* **ICMR National Ethical Guidelines (v2017)** · National Guideline

### 2.2 Supported Topics & Safety Escalation Rules
To prevent scope creep, the pipeline categorises queries into specific topics:
* **Covered Topics:** `consent`, `data_handling`, `authorship`, `publication_ethics`.
* **Escalation & Refusal Rules:**
  1. *Prompt Injection:* ("ignore rules", "bypass") -> **Refuse**
  2. *Off-Topic:* (food, sports, weather) -> **Refuse**
  3. *Suspected Misconduct:* ("my supervisor added a ghost author") -> **Escalate**
  4. *Vulnerable Groups:* (children, prisoners, pregnant women) -> **Escalate**
  5. *Case-Specific Advice:* ("my study", "can I", "am I allowed") -> **Escalate**
  6. *Vague/Unclear:* (< 4 words) -> **Clarify**

All escalated and answered queries append a mandatory caveat: *"This tool cannot decide whether a specific study is ethical... Case-specific decisions belong to the institution's ethics committee/IRB."*

## 3. Results & Evaluation

The system was evaluated against 12 test queries representing a mix of in-scope, out-of-scope, and high-risk scenarios. 

*The full evaluation results and ablation study comparing Hybrid, BM25-only, and Embedding-only modes are output by our evaluation script to `eval/results.md`.*

**Summary of Performance:**
* **Safe Escalation / Refusal (6/6):** The system successfully intercepted all 6 risky/off-topic queries (prompt injection, misconduct, vulnerable groups, case-specific, out-of-scope, off-topic) without hallucinating advice.
* **Retrieval Robustness:** The Hybrid retrieval mode successfully surfaced the correct document sections for complex questions (e.g., criteria for authorship, consent waiver conditions).
* **LLM Grounding:** Following a prompt fix, the LLM successfully maps its citations perfectly to the retrieved chunks and cleanly outputs `NOT_FOUND` when the retrieved chunks do not contain the answer, avoiding waffling.

## 4. Limitations
1. **Document Coverage:** Only four documents are currently indexed. If a user asks about animal testing ethics (not covered in these human-centric docs), the system correctly returns `NOT_FOUND`, but expanding the document corpus would improve utility.
2. **Deterministic Safety Rules:** The safety gate uses keyword/regex matching. While highly robust and fast (zero latency), advanced adversarial phrasing might bypass it. A secondary small-LLM classifier could be added as a backup.
3. **Not Binding Advice:** The tool's output is exclusively general guidance. It cannot and should not replace an official IRB/Ethics Committee review.
