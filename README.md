# Research Ethics Guidance Assistant

## Setup & Usage Guide

### 1. Install dependencies

```bash
cd research-ethics-assistant
pip install -r requirements.txt
```

### 2. Download official ethics documents

```bash
python download_docs.py
```

> **Note:** Some PDFs may have access restrictions. If download fails, download them manually and save to `data/raw/` using the filenames in `data/manifest.json`.

### 3. Ingest and chunk documents

```bash
python src/ingest.py
```

This reads PDFs from `data/raw/`, cleans and chunks the text, tags topics, and saves `data/processed/chunks.json`.

### 4. Build search indices

```bash
python src/index.py
```

Builds `data/processed/bm25.pkl` and `data/processed/faiss.index`.

### 5. Run the Streamlit UI

```bash
streamlit run app.py
```

### 6. Run evaluation

```bash
python eval/run_eval.py
```

Results are written to `eval/results.md`.

---

## Project Structure

```
research-ethics-assistant/
├── data/
│   ├── raw/                 # official PDFs (download_docs.py)
│   ├── processed/           # chunks.json, bm25.pkl, faiss.index
│   └── manifest.json        # document list with versions and authority
├── src/
│   ├── ingest.py            # parse → clean → chunk → tag
│   ├── index.py             # build BM25 + FAISS index
│   ├── retrieve.py          # hybrid search + RRF
│   ├── safety.py            # escalation and refusal rules
│   ├── generate.py          # Groq client + grounded prompt
│   └── pipeline.py          # ties everything together
├── eval/
│   ├── test_queries.json    # 12 test queries
│   ├── run_eval.py          # evaluation + ablation
│   └── results.md           # generated results table
├── app.py                   # Streamlit UI
├── download_docs.py         # PDF downloader utility
├── .env                     # GROQ_API_KEY (do not commit)
└── requirements.txt
```

---

## Architecture

```
User question
     |
     v
[1] Safety / Scope check  → REFUSE / ESCALATE / CLARIFY
     |
     v
[2] Hybrid retrieval
     |-- BM25 (keyword)  --\
     |                      > RRF merge → top-k chunks
     |-- Embeddings (meaning) --/
     v
[3] Confidence check  → "Not found in approved sources"
     v
[4] Groq LLM (llama-3.3-70b-versatile) → grounded answer + citations (JSON)
     v
[5] Output: General Guidance + "Needs your ethics committee" note
     v
[6] UI: answer + highlighted source excerpts side by side
```

---

## Safety Rules

| Condition | Action |
|---|---|
| Prompt injection | Refuse |
| Off-topic question | Refuse |
| Suspected misconduct | Escalate |
| Vulnerable groups | Escalate (give general principle) |
| Case-specific decision | Escalate |
| Vague question | Ask for clarification |
| Low retrieval confidence | "Not found in approved sources" |

---

## Evaluation Metrics

| Metric | Definition |
|---|---|
| **Correct action rate** | % queries where pipeline took the right action |
| **Escalation recall** | % should-escalate queries correctly escalated |
| **Wrongful refusal rate** | % should-answer queries wrongly refused |
| **Avg faithfulness** | Groq-judged faithfulness score (0–1) |
