############################################################
# datasheet_ingest_pipeline.py  (v2 – keyword & markdown)
#
# A reproducible ETL pipeline that ingests **both PDF datasheets and raw
# Markdown files** into a LlamaIndex ➜ Qdrant retrieval stack.
#
# Main stages (async, CLI-driven or schedulable):
#   1. Fetch (HTTP or local) and SHA-256 hash for doc_id dedup.
#   2. Parse → Markdown text:
#        • PDF  → Poppler → PNG → OpenAI Vision/Responses API → Markdown.
#        • MD   → read file bytes (no model call needed).
#   3. Artefact persistence  (JSONL one-per-doc).
#   4. Chunk with MarkdownNodeParser.
#   5. **Optional Keyword Augmentation** (Anthropic RAG best-practice):
#        • Generates comma-separated keywords for each chunk via OpenAI
#        • Appends to node.text so both BM25 and vector search benefit.
#   6. Embed & upsert to Qdrant (vector + metadata filters).
#
# ---------------------------------------------------------------------------
# USAGE EXAMPLES
# ---------------------------------------------------------------------------
#   python datasheet_ingest_pipeline.py --src urls.txt *.pdf docs/*.md \
#          --with_keywords --keyword_model gpt-4o-mini
#
#   python datasheet_ingest_pipeline.py --src specs/               # generic
#   python datasheet_ingest_pipeline.py --src ds1.pdf --prompt alt.txt
# ---------------------------------------------------------------------------
#   pip install openai pdf2image pillow llama-index qdrant-client tqdm aiohttp
#   brew install poppler   # or apt-get install poppler-utils
############################################################
from __future__ import annotations

import asyncio, aiohttp, base64, hashlib, io, json, os, shutil, tempfile, textwrap
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Tuple, Union

from tqdm import tqdm
from pdf2image import convert_from_path
from openai import OpenAI
from llama_index.core import (
    Document,
    MarkdownNodeParser,
    ServiceContext,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.ingestion import IngestionPipeline, BaseTransformation
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

# ---------------------------------------------------------------------------
# CONFIG & CONSTANTS
# ---------------------------------------------------------------------------
OPENAI_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
VECTOR_DB_PATH = os.getenv("QDRANT_LOCAL", "./qdrant_data")
ARTEFACT_DIR = Path(os.getenv("ARTEFACT_DIR", "./artefacts"))
ARTEFACT_DIR.mkdir(parents=True, exist_ok=True)
POPPLER_PATH = (
    os.getenv("POPPLER_PATH")
    or (
        lambda: Path(shutil.which("pdfinfo")).parent
        if shutil.which("pdfinfo")
        else None
    )()
)
INLINE_PROMPT = """"""
DEFAULT_GENERIC_PROMPT = "Extract all text as GitHub-flavoured Markdown."


# ---------------------------------------------------------------------------
@dataclass
class DatasheetArtefact:
    doc_id: str
    source: str
    pairs: List[Tuple[str, str]]
    markdown: str
    parse_version: int = 2
    page_map: dict | None = None

    def to_jsonl(self):
        return json.dumps(asdict(self), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Prompt resolution hierarchy
# ---------------------------------------------------------------------------


def _resolve_prompt(cli_path: str | None) -> str:
    if cli_path:  # 1 CLI file
        return Path(cli_path).read_text(encoding="utf-8").strip()
    env_p = os.getenv("DATASHEET_PARSE_PROMPT")  # 2 ENV var
    if env_p:
        return env_p.strip()
    sib = Path(__file__).with_name("datasheet_parse_prompt.txt")  # 3 sibling
    if sib.exists():
        return sib.read_text(encoding="utf-8").strip()
    return INLINE_PROMPT.strip() or DEFAULT_GENERIC_PROMPT  # 4 fallback


# ---------------------------------------------------------------------------
# === Vision-based PDF ➜ Markdown parser ===
# ---------------------------------------------------------------------------


def _pdf_to_data_uris(pdf: Path, dpi: int = 300) -> List[str]:
    imgs = convert_from_path(
        str(pdf), dpi=dpi, poppler_path=str(POPPLER_PATH) if POPPLER_PATH else None
    )
    uris = []
    for im in imgs:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        uris.append(
            "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        )
    return uris


def vision_parse(pdf: Path, parsing_prompt: str) -> Tuple[str, List[Tuple[str, str]]]:
    client = OpenAI()
    parts = [
        {
            "type": "input_text",
            "text": textwrap.dedent(f"""
        {parsing_prompt}

        Return one Markdown document that begins with a line:
        Metadata: {{ 'pairs': [...] }}
        followed by the full datasheet body.  Use GitHub-flavoured tables.
        """),
        }
    ]
    parts += [
        {"type": "input_image", "image_url": uri} for uri in _pdf_to_data_uris(pdf)
    ]
    resp = client.responses.create(
        model=OPENAI_MODEL, input=[{"role": "user", "content": parts}], temperature=0.0
    )
    md = resp.output[0].content[0].text
    first_line, *_ = md.split("\n", 1)
    try:
        meta = json.loads(first_line.replace("Metadata:", "").strip())
        pairs = [tuple(p) for p in meta.get("pairs", [])]
    except Exception:
        pairs = []
    return md, pairs


# ---------------------------------------------------------------------------
# Keyword-augmentation transformer (optional)
# ---------------------------------------------------------------------------
class KeywordGenerator(BaseTransformation):
    """Appends LLM-generated keyword line to each node.text."""

    def __init__(self, model="gpt-4o-mini", max_tokens=64):
        self.client = OpenAI()
        self.model = model
        self.max_tokens = max_tokens

    async def _kw(self, text: str):
        prompt = (
            "Generate concise, comma-separated keywords describing the main concepts."
            " Replace pronouns with referents."
        )  # ~Anthropic guide
        r = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": f"{prompt}\n\n{text[:800]}"}],
            max_tokens=self.max_tokens,
            temperature=0.2,
        )
        return r.choices[0].message.content.strip()

    async def atransform(self, nodes, **kwargs):
        async def enrich(n):
            n.text += f"\n\nContext: {await self._kw(n.text)}"
            return n

        return [await enrich(n) for n in nodes]


# ---------------------------------------------------------------------------
# Fetch / hashing helpers
# ---------------------------------------------------------------------------
async def _download(url: str) -> bytes:
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            r.raise_for_status()
            return await r.read()


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def fetch_document(src: str | Path) -> Tuple[Path, str, bytes]:
    if isinstance(src, Path) or not str(src).startswith("http"):
        data = Path(src).read_bytes()
        return Path(src), _sha256(data), data
    data = await _download(str(src))
    temp = Path(tempfile.gettempdir()) / f"{_sha256(data)}.pdf"
    temp.write_bytes(data)
    return temp, _sha256(data), data


# ---------------------------------------------------------------------------
# Main ingestion routine
# ---------------------------------------------------------------------------
async def ingest_sources(
    sources: Iterable[str | Path],
    *,
    prompt_file: str | None = None,
    with_keywords: bool = False,
    keyword_model: str = "gpt-4o-mini",
):
    prompt_text = _resolve_prompt(prompt_file)
    print(
        "Prompt preview:",
        prompt_text[:100].replace("\n", " ") + ("…" if len(prompt_text) > 100 else ""),
    )

    qclient = QdrantClient(path=VECTOR_DB_PATH)
    vstore = QdrantVectorStore(client=qclient, collection_name="datasheets")
    storage = StorageContext.from_defaults(vector_store=vstore)
    svc_ctx = ServiceContext.from_defaults()
    md_parser = MarkdownNodeParser()
    kw_trans = KeywordGenerator(model=keyword_model) if with_keywords else None

    # Progress bar
    for src in tqdm(list(sources), desc="Docs"):
        pdf_path, doc_id, raw_bytes = await fetch_document(src)
        artefact_path = ARTEFACT_DIR / f"{doc_id}.jsonl"
        if artefact_path.exists():
            continue  # skip dedup
        # choose branch
        if pdf_path.suffix.lower() == ".pdf":
            markdown, pairs = vision_parse(pdf_path, prompt_text)
        else:  # Markdown file path
            markdown = Path(pdf_path).read_text(encoding="utf-8", errors="ignore")
            pairs = []
        # save artefact
        DatasheetArtefact(doc_id, str(src), pairs, markdown).to_jsonl()
        artefact_path.write_text(
            DatasheetArtefact(doc_id, str(src), pairs, markdown).to_jsonl(),
            encoding="utf-8",
        )
        # build Document
        doc = Document(
            text=markdown,
            metadata={"doc_id": doc_id, "source": str(src), "pairs": pairs},
        )
        pipeline = IngestionPipeline(
            transformations=[md_parser] + ([kw_trans] if kw_trans else [])
        )
        nodes = await pipeline.arun(documents=[doc])
        for n in nodes:
            n.metadata.update({"doc_id": doc_id, "pairs": pairs})
        VectorStoreIndex.from_nodes(
            nodes, storage_context=storage, service_context=svc_ctx
        )
    print(
        "Ingestion complete –",
        len(list(ARTEFACT_DIR.glob("*.jsonl"))),
        "artefacts total.",
    )


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse, sys

    p = argparse.ArgumentParser(
        description="Bulk ingest datasheets & Markdown into LlamaIndex/Qdrant"
    )
    p.add_argument(
        "--src",
        nargs="+",
        required=True,
        help="File paths or URLs (supports @filelist.txt)",
    )
    p.add_argument("--prompt", help="Path to custom prompt file")
    p.add_argument(
        "--with_keywords",
        action="store_true",
        help="Enable keyword augmentation per chunk",
    )
    p.add_argument(
        "--keyword_model", default="gpt-4o-mini", help="Model for keyword generation"
    )
    args = p.parse_args()

    # flatten @filelist.txt syntax
    expanded = []
    for s in args.src:
        if s.startswith("@"):
            expanded += [
                l.strip() for l in Path(s[1:]).read_text().splitlines() if l.strip()
            ]
        else:
            expanded.append(s)
    try:
        asyncio.run(
            ingest_sources(
                expanded,
                prompt_file=args.prompt,
                with_keywords=args.with_keywords,
                keyword_model=args.keyword_model,
            )
        )
    except KeyboardInterrupt:
        sys.exit(130)
