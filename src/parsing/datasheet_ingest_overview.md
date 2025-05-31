
# Datasheet & Markdown Ingestion Pipeline – Overview

This document explains the purpose, architecture, and operation of **`datasheet_ingest_pipeline.py` (v2)**.  
The script ingests PDF laser‑meter datasheets **and** raw Markdown files, normalises them to Markdown, augments each chunk with optional keyword context, and indexes everything into LlamaIndex + Qdrant for Retrieval‑Augmented Generation (RAG).

---

## 1  Purpose

* **Unified ETL** for mixed PDF/MD corpora.  
* Extracts `(model name, part number)` pairs from datasheets.  
* Optional **keyword augmentation** (Anthropic “Contextual Retrieval”) boosts recall.  
* Creates a durable JSONL artefact per source and vector‑embeds chunks for search.

---

## 2  Processing Flow

```text
fetch (HTTP / disk) ──► SHA‑256 hash
                       │
                       ├─► PDF?  yes ──► Poppler → PNG → OpenAI Vision → Markdown
                       │
                       └─► Markdown? read file
        ↓
write artefact JSONL
        ↓
MarkdownNodeParser
        ↓
(optional) KeywordGenerator (OpenAI chat → comma keywords)
        ↓
embed & upsert into Qdrant through LlamaIndex
```

---

## 3  Prompt Resolution

Priority | Source
---------|--------
1 | `--prompt FILE` CLI flag
2 | `DATASHEET_PARSE_PROMPT` ENV
3 | `datasheet_parse_prompt.txt` next to script
4 | `INLINE_PROMPT` constant inside script
5 | Fallback generic: *“Extract all text as GitHub‑flavoured Markdown.”*

---

## 4  Key Modules & Choices

| Component | Library | Reason |
|-----------|---------|--------|
| Vision OCR | OpenAI `responses.create` | Native PDF+image input, no manual OCR |
| Rasterisation | `pdf2image` + Poppler | High‑fidelity, CLI‑free |
| Chunker | `MarkdownNodeParser` | Preserves tables & headings |
| Keyword step | Custom `KeywordGenerator` transformer | Implements Anthropic best‑practice |
| Vector DB | Qdrant | Fast hybrid search & metadata filters |
| Docstore | JSONL artefact per doc | Audit & easy re‑processing |

---

## 5  Running the Pipeline

```bash
# Datasheets + Markdown with keyword context
python datasheet_ingest_pipeline.py \
       --src @urls.txt local/*.md specs/*.pdf \
       --with_keywords

# Generic parsing (no keywords, alternate prompt)
python datasheet_ingest_pipeline.py --src manual.pdf --prompt plain.txt
```

Special syntax: `@filelist.txt` expands to a list of newline‑separated paths/URLs.

---

## 6  Artefact Schema (`artefacts/<doc_id>.jsonl`)

```jsonc
{
  "doc_id": "f1c2…",
  "source": "https://…/PM10K+.pdf",
  "pairs": [["PM10K+ USB", "2293937"]],
  "markdown": "## PM10K+ LASER POWER SENSOR …",
  "parse_version": 2,
  "page_map": null
}
```

---

## 7  Extending

* **Page linking** – add bbox via PyMuPDF, store in `page_map`.
* **Different DB** – swap `QdrantVectorStore` for LanceDB/Weaviate.
* **Schedule** – wrap `ingest_sources()` in Prefect/Airflow for nightly sync.
* **Richer metadata** – plug additional `BaseTransformation`s (e.g., entity extractor).

---

## 8  Requirements

```bash
pip install openai pdf2image pillow llama-index qdrant-client tqdm aiohttp
brew install poppler   # or apt-get install poppler-utils
export OPENAI_API_KEY=...
```

---

## 9  References

* **Anthropic Contextual Retrieval paper** – keyword lines technique  
* **OpenAI multimodal Responses API** – PDF+image input  
* **LlamaIndex IngestionPipeline docs** – custom transformers  
* **Qdrant filtering guide** – metadata queries  
* **Poppler utilities** – `pdfinfo`, `pdftoppm` for rasterisation
