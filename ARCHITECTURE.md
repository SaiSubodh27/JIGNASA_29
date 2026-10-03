# Architecture Design — Research Ethics Guidance Assistant

> **Project:** JIG26_29 · Track C: Ethics Compliance & AI Safety  
> **Stack:** Python · Groq API (qwen/qwen3.8-27b) · BM25 · TF-IDF/LSA · FAISS · Streamlit  
> **Pattern:** Retrieval-Augmented Generation (RAG) with Safety Gating

---

## 1. High-Level System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER (Browser / CLI)                           │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │  Natural-language ethics question
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         app.py  (Streamlit UI)                          │
│  • Question input box          • Status badge (Answered / Escalated)    │
│  • Left: Answer + citations     • Right: Source excerpts + authority    │
│  • Sidebar: Document list, retrieval-mode toggle                        │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      src/pipeline.py  (Orchestrator)                    │
│                                                                         │
│   Question ──► [1] Safety Gate ──►  REFUSE / ESCALATE / CLARIFY        │
│                      │                                                  │
│                      │  (safe to answer)                                │
│                      ▼                                                  │
│               [2] Hybrid Retrieval                                      │
│                  BM25 ──────────────┐                                   │
│                                     ├──► RRF Merge ──► top-k chunks    │
│                  TF-IDF/LSA+FAISS ──┘                                   │
│                      │                                                  │
│                      ▼                                                  │
│               [3] Confidence Check ──► NOT_FOUND (score < threshold)   │
│                      │                                                  │
│                      ▼                                                  │
│               [4] Groq LLM Generation                                   │
│                  (grounded answer + JSON citations)                     │
│                      │                                                  │
│                      ▼                                                  │
│               [5] PipelineResponse                                      │
│                  { status, guidance, needs_committee, sources }         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Breakdown

### 2.1 Data Layer

```
data/
├── manifest.json          ← Document registry (title, publisher, version, authority)
├── raw/                   ← Official PDF files
│   ├── helsinki_2013.pdf
│   ├── icmje_2023.pdf
│   ├── cope_guidelines.pdf
│   └── icmr_2017.pdf
└── processed/             ← Generated artefacts (never commit)
    ├── chunks.json        ← Chunked text with rich metadata
    ├── bm25.pkl           ← BM25Okapi index (rank_bm25)
    ├── tfidf.pkl          ← TF-IDF vectorizer (scikit-learn)
    ├── svd.pkl            ← TruncatedSVD / LSA model (scikit-learn)
    ├── faiss.index        ← FAISS inner-product index (faiss-cpu)
    └── chunk_meta.json    ← Ordered chunk IDs (FAISS row -> chunk ID)
```

**Chunk metadata schema:**

```json
{
  "chunk_id":   "helsinki_2013_c0001",
  "doc_id":     "helsinki_2013",
  "doc_title":  "Declaration of Helsinki",
  "publisher":  "World Medical Association",
  "version":    "2013",
  "section":    "Informed Consent",
  "page":       -1,
  "topic":      "consent",
  "all_topics": ["consent", "data_handling"],
  "authority":  2,
  "text":       "..."
}
```

**Authority scale** (lower = more authoritative):

| Level | Meaning |
|---|---|
| 1 | Law / Regulation |
| 2 | International / National Guideline |
| 3 | Professional Standard (ICMJE, COPE) |
| 4 | Institute Policy |
| 5 | Background Reading |

---

### 2.2 Ingestion Pipeline (`src/ingest.py`)

```
PDF files (data/raw/)
      │
      ▼
  PDF Text Extraction  <-- pypdf
      │
      ▼
  Text Cleaning
  • Strip page numbers (regex)
  • Collapse blank lines
  • Normalise whitespace
      │
      ▼
  Chunking  (200-300 words, 50-word overlap)
  • Split on paragraph boundaries
  • Fallback to word-count window
      │
      ▼
  Topic Tagging  (keyword rules)
  • consent | data_handling | authorship | publication_ethics | general
      │
      ▼
  Section Heuristic  (first UPPERCASE line = section title)
      │
      ▼
  chunks.json
```

---

### 2.3 Indexing Pipeline (`src/index.py`)

```
chunks.json
      │
      ├──► BM25Okapi (rank_bm25)
      │        tokenize(text) -> whitespace split
      │        saved -> bm25.pkl
      │
      └──► TF-IDF + TruncatedSVD (scikit-learn)
               TfidfVectorizer(ngram_range=(1,2), max_features=20000, sublinear_tf=True)
               TruncatedSVD(n_components=64, random_state=42)  <- LSA / semantic embedding
               L2 normalise -> float32
               saved -> tfidf.pkl, svd.pkl
                    │
                    └──► FAISS IndexFlatIP  <- inner-product == cosine on normalised vecs
                         saved -> faiss.index
```

> **Why TF-IDF/LSA instead of sentence-transformers?**  
> The deployment environment crashes PyTorch with a Windows AVX2 SIGILL. TF-IDF + LSA delivers semantic search without any native binary dependencies.

---

### 2.4 Retrieval (`src/retrieve.py`)

```
Query string
      │
      ├──► BM25 path
      │        tokenize(query)
      │        BM25.get_scores() -> ranked chunk IDs (keyword match)
      │
      └──► Embedding path
               TF-IDF transform -> SVD transform -> L2 normalise
               FAISS.search(qvec, top_k) -> ranked chunk IDs + cosine score
      │
      ▼
  Reciprocal Rank Fusion (RRF)
  score(chunk) = SUM( 1 / (k + rank + 1) ),   k = 60
      │
      ▼
  Sort by authority (prefer lower number = more authoritative)
      │
      ▼
  Top-k chunks  +  confidence_ok flag
```

**Three retrieval modes** (toggled in the UI sidebar):

| Mode | Description |
|---|---|
| `hybrid` | BM25 + Embedding merged via RRF **(default)** |
| `bm25` | Keyword-only (exact term match) |
| `embedding` | Semantic-only (TF-IDF/LSA cosine) |

---

### 2.5 Safety Layer (`src/safety.py`)

Runs **before** retrieval — adds zero latency (no LLM call needed).

```
Question
    │
    ├─► Prompt Injection?   ("ignore your rules", "jailbreak", ...)
    │       └──► action = "refuse"
    │
    ├─► Off-Topic?          (food, sport, movie, weather, ...)
    │       └──► action = "refuse"
    │
    ├─► Suspected Misconduct? ("ghost/fake author", "my supervisor added")
    │       └──► action = "escalate"
    │
    ├─► Vulnerable Groups?  (children, prisoners, pregnant, dementia, ...)
    │       └──► action = "escalate"
    │
    ├─► Case-Specific?      ("my study", "can I", "am I allowed", ...)
    │       └──► action = "escalate"
    │
    ├─► Vague?              ("is this ethical?", len < 4 words)
    │       └──► action = "clarify"
    │
    └─► In-Scope            └──► action = "answer"
```

**SafetyDecision dataclass:**

```python
@dataclass
class SafetyDecision:
    action:        Literal["answer", "escalate", "refuse", "clarify"]
    category:      str   # e.g. "case_specific", "off_topic"
    reason:        str   # internal log
    response_hint: str   # pre-canned user-facing message
```

---

### 2.6 Generation (`src/generate.py`)

```
question + top-k chunks
      │
      ▼
  Build source block
  [1] Doc title (vVersion), Section, Authority:
      <truncated text <= 600 chars>
  [2] ...
      │
      ▼
  Groq API  --- model: qwen/qwen3.8-27b
  temperature = 0          (deterministic, faithful)
  response_format = json_object
      │
      ▼
  System prompt enforces:
  • Answer ONLY from provided SOURCES
  • Cite every claim [1][2]
  • Return NOT_FOUND if answer not in sources
  • No case-specific decisions
  • JSON schema:
    {
      "general_guidance": "...",
      "needs_committee":  "...",
      "citations":        [1, 2]
    }
      │
      ▼
  Rate-limit retry (exponential back-off, fallback to openai/gpt-oss-20b)
      │
      ▼
  JSON parse -> dict
```

---

### 2.7 Pipeline Orchestrator (`src/pipeline.py`)

```
run_pipeline(question, top_k=5, retrieval_mode="hybrid")
      │
      ├── [1] check_safety(question)
      │         refuse  ->  PipelineResponse(status="refused")
      │         clarify ->  PipelineResponse(status="clarify")
      │
      ├── [2] retriever.search(question, top_k, mode)
      │         -> (chunks, confidence_ok)
      │
      ├── [3] if not confidence_ok or not chunks:
      │             -> PipelineResponse(status="not_found")
      │
      ├── [4] generate_answer(question, chunks)
      │         -> {general_guidance, needs_committee, citations}
      │
      └── [5] assemble PipelineResponse
                status = "answered" | "escalated" | "not_found"
```

**PipelineResponse status machine:**

```
                   safety=refuse
                 ┌──────────────► "refused"
                 │
question ──► safety check
                 │
                 │  safety=clarify
                 ├──────────────► "clarify"
                 │
                 │  safety=answer OR escalate
                 │
                 ▼
            retrieval ──── no chunks / low confidence ──► "not_found"
                 │
                 ▼
            Groq LLM
                 │
                 ├── safety=answer   ──────────────────► "answered"
                 ├── safety=escalate ────────────────► "escalated"
                 └── LLM returns NOT_FOUND ──────────► "not_found"
```

---

### 2.8 User Interface (`app.py`)

```
┌───────────── SIDEBAR ─────────────────────────────────────────────────┐
│  Retrieval Mode: (o) hybrid  ( ) bm25  ( ) embedding                  │
│  Source chunks:  [====slider 2-8====]                                  │
│  Approved Documents:                                                   │
│    Declaration of Helsinki (v2013)  · International Guideline          │
│    ICMJE Recommendations   (v2023)  · Professional Standard            │
│    COPE Core Practices     (v2017)  · Professional Standard            │
│    ICMR Guidelines         (v2017)  · National Guideline               │
└───────────────────────────────────────────────────────────────────────┘

┌── LEFT COLUMN (3/5) ────────────────┐  ┌── RIGHT COLUMN (2/5) ────────┐
│  [Question text area]               │  │  Source Excerpts             │
│  [Get Guidance]                     │  │                              │
│                                     │  │  ⭐[1] Declaration of        │
│  [badge: Answered / Escalated / ..] │  │  Helsinki (v2013)            │
│                                     │  │  International Guideline     │
│  GENERAL GUIDANCE                   │  │  consent, data_handling      │
│  <cited answer [1][2]>              │  │  "Physicians must protect..." │
│                                     │  │                              │
│  NEEDS YOUR ETHICS COMMITTEE        │  │  [2] ICMJE Recommendations   │
│  <what cannot be decided>           │  │  Professional Standard       │
│                                     │  │  authorship                  │
│  CITATIONS USED                     │  │  "Authorship should be..."   │
│  [1] Helsinki · Informed Consent    │  │                              │
└─────────────────────────────────────┘  └──────────────────────────────┘
```

**Source box left-border colours (authority level):**

| Colour | Authority |
|---|---|
| Red | Law / Regulation |
| Orange | International / National Guideline |
| Blue | Professional Standard |
| Grey | Institute Policy |

---

## 3. Full Data Flow Diagram

```
                      OFFLINE (one-time setup)
┌──────────┐    ┌──────────────┐    ┌──────────────┐
│PDF files │───►│  ingest.py   │───►│ chunks.json  │
│(data/raw)│    │ parse+chunk  │    │ (w/ metadata)│
└──────────┘    │ tag+clean    │    └──────┬───────┘
                └──────────────┘           │
                                           ▼
                                  ┌──────────────────┐
                                  │    index.py      │
                                  │ BM25+TF-IDF/LSA  │
                                  │ + FAISS          │
                                  └──┬───────────────┘
                       saves:        │
               ┌─────────────────────┼────────────────┐
               ▼                     ▼                 ▼
           bm25.pkl          tfidf.pkl + svd.pkl  faiss.index


                      ONLINE (every query)
┌──────────┐    ┌──────────────┐    ┌─────────────────────┐
│  User    │───►│  safety.py   │───►│    retrieve.py      │
│  Query   │    │  (gate)      │    │  BM25 + LSA + RRF   │
└──────────┘    └──────────────┘    └──────────┬──────────┘
                                               │ top-k chunks
                                               ▼
                                    ┌─────────────────────┐
                                    │   generate.py       │
                                    │   Groq API          │
                                    │   qwen/qwen3.8-27b  │
                                    └──────────┬──────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │  PipelineResponse   │
                                    │  status + guidance  │
                                    │  + source excerpts  │
                                    └──────────┬──────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │  app.py (Streamlit) │
                                    │  http://localhost   │
                                    │  :8501              │
                                    └─────────────────────┘
```

---

## 4. Technology Choices & Rationale

| Component | Choice | Why |
|---|---|---|
| **LLM** | Groq `qwen/qwen3.8-27b` | Fast inference, good TPM limit, strong instruction following |
| **Keyword retrieval** | BM25 (`rank_bm25`) | Exact term match; essential for precise ethics terminology |
| **Semantic retrieval** | TF-IDF + TruncatedSVD (LSA) | No PyTorch / AVX2 deps; runs on any CPU |
| **Vector store** | FAISS `IndexFlatIP` | Exact cosine search; simple, no server needed |
| **Rank merging** | Reciprocal Rank Fusion | Proven, parameter-robust, no score normalisation needed |
| **PDF parsing** | pypdf | Pure-Python, lightweight |
| **UI** | Streamlit | Rapid prototyping, Python-native |
| **Safety** | Rule-based regex | Deterministic, auditable, zero latency |

---

## 5. Evaluation Design

### 5.1 Test Query Set (12 queries)

| # | Type | Expected Action |
|---|---|---|
| 1–4 | Covered (in-scope) | `answered` + citation |
| 5 | Case-specific | `escalated` |
| 6 | Vulnerable group | `escalated` |
| 7 | Misconduct | `escalated` |
| 8 | Not covered | `not_found` |
| 9 | Off-topic | `refused` |
| 10 | Prompt injection | `refused` |
| 11–12 | COI + consent waiver | `answered` + citation |

### 5.2 Metrics

| Metric | Formula | Target |
|---|---|---|
| **Correct Action Rate** | correct actions / total | > 90% |
| **Escalation Recall** | correctly escalated / should-escalate | > 95% |
| **Wrongful Refusal Rate** | wrongly refused / should-answer | < 5% |
| **Avg Faithfulness** | supported claims / total claims | > 0.80 |

### 5.3 Ablation Study

`eval/run_eval.py` runs all three retrieval modes and writes `eval/results.md`:

```
Hybrid (BM25 + LSA)  <-- primary
BM25 only            <-- ablation A
Embedding only       <-- ablation B
```

---

## 6. Security & Limitations

### Security Controls

| Threat | Mitigation |
|---|---|
| Prompt injection | Regex rules block before LLM call |
| API key leakage | `.env` in `.gitignore`; never committed |
| Hallucination | System prompt: "answer ONLY from SOURCES" |
| Scope creep | Safety gate refuses off-topic before retrieval |

### Known Limitations

1. **Coverage is bounded** — only 4 curated documents; topics not in these docs return `NOT_FOUND`.
2. **TF-IDF/LSA embeddings** — less powerful than neural embeddings for paraphrase queries.
3. **Regex-based safety** — adversarial phrasing may bypass; an LLM classifier can be added as Layer 2.
4. **Not legal advice** — citations enable user verification of any LLM output.
5. **Final authority** — always rests with the institution's ethics committee / IRB.

---

## 7. File Map

```
research-ethics-assistant/
│
├── app.py                  <- Streamlit UI (entry point)
├── download_docs.py        <- One-time PDF downloader
├── requirements.txt        <- Python dependencies
├── .env                    <- GROQ_API_KEY (gitignored)
├── .gitignore
├── README.md
├── ARCHITECTURE.md         <- This document
│
├── data/
│   ├── manifest.json       <- Document registry
│   ├── raw/                <- Source PDFs (gitignored)
│   └── processed/          <- Generated indices (gitignored)
│
├── src/
│   ├── ingest.py           <- Step 1: PDF -> chunks.json
│   ├── index.py            <- Step 2: chunks -> BM25 + FAISS
│   ├── retrieve.py         <- Step 3: hybrid search + RRF
│   ├── safety.py           <- Step 4: safety gate
│   ├── generate.py         <- Step 5: Groq LLM + prompt
│   └── pipeline.py         <- Step 6: orchestration
│
└── eval/
    ├── test_queries.json   <- 12 test queries
    ├── run_eval.py         <- Evaluation + ablation runner
    └── results.md          <- Generated results table
```

---

## 8. Setup Sequence

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download official ethics PDFs
python download_docs.py

# 3. Parse, clean, chunk, and tag documents
python src/ingest.py

# 4. Build BM25 + TF-IDF/LSA + FAISS indices
python src/index.py

# 5. Launch the Streamlit UI
streamlit run app.py         # -> http://localhost:8501

# 6. (Optional) Run evaluation and ablation
python eval/run_eval.py      # -> eval/results.md
```
