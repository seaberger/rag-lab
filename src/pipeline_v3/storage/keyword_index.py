"""
BM25 keyword index for hybrid search.
"""

import json
import math
import pickle
import re  # Moved re import higher for consistency
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

# import numpy as np # numpy seems unused in this file, commenting out.
from llama_index.core.schema import TextNode  # Added TextNode

from utils.common_utils import logger
from utils.config import PipelineConfig


class BM25Index:
    """BM25 keyword index with SQLite FTS5 backend."""

    def __init__(self, db_path: str | None = None, config: PipelineConfig = None):
        # Use config if provided, otherwise use parameter or default
        if config and hasattr(config, "storage"):
            self.db_path = config.storage.keyword_db_path
        else:
            self.db_path = db_path or "./keyword_index.db"
        self.conn = sqlite3.connect(self.db_path)
        self._init_db()

    def _init_db(self):
        """Initialize FTS5 table for full-text search."""
        self.conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(
                doc_id,
                chunk_id,
                text,
                keywords,
                metadata,
                tokenize='porter unicode61'
            )
        """
        )

        # Create metadata table for document info
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_metadata (
                doc_id TEXT PRIMARY KEY,
                source TEXT,
                pairs TEXT,  -- JSON array
                chunk_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        self.conn.commit()

    def index_nodes(
        self,
        nodes: list[TextNode],
        doc_id: str,
        source: str,
        pairs: list[tuple[str, str]],
    ):
        """Index nodes for BM25 search."""
        # Extract document metadata
        self.conn.execute(
            """
            INSERT OR REPLACE INTO doc_metadata (doc_id, source, pairs, chunk_count)
            VALUES (?, ?, ?, ?)
        """,
            (doc_id, source, json.dumps(pairs), len(nodes)),
        )

        # Index each chunk
        for node in nodes:
            # Extract keywords if present
            keywords = ""
            if "Context:" in node.text:
                # Extract keyword line
                parts = node.text.split("Context:", 1)
                if len(parts) > 1:
                    keywords = parts[1].strip().split("\n")[0]

            # Prepare text for indexing (remove special characters)
            clean_text = self._clean_text(node.text)

            self.conn.execute(
                """
                INSERT INTO documents (doc_id, chunk_id, text, keywords, metadata)
                VALUES (?, ?, ?, ?, ?)
            """,
                (doc_id, node.id_, clean_text, keywords, json.dumps(node.metadata)),
            )

        self.conn.commit()

    def _clean_text(self, text: str) -> str:
        """Clean text for better indexing."""
        # Remove markdown formatting
        text = re.sub(r"[#*`\[\]()]", " ", text)
        # Normalize whitespace
        return " ".join(text.split())

    def _escape_fts5_query(self, query: str) -> str:
        """Escape FTS5 special characters to prevent syntax errors and injection."""
        if not query or not query.strip():
            return ""

        # Remove/escape FTS5 special characters that can cause syntax errors
        # FTS5 special chars: " (quotes), ' (single quotes), () (parentheses), * (wildcards), - (NOT operator)

        # First, remove any existing quotes to prevent quote injection
        query = query.replace('"', " ").replace("'", " ")

        # Remove other FTS5 operators and SQL special characters that could be injection attempts
        query = re.sub(r"[(){}[\]<>|&^~`;,=]", " ", query)

        # Remove SQL injection patterns
        query = re.sub(r"[-]{2,}.*$", " ", query)  # Remove SQL comments (-- )
        query = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)  # Remove /* */ comments

        # Remove common SQL keywords that shouldn't appear in search
        sql_keywords = [
            "DROP",
            "DELETE",
            "INSERT",
            "UPDATE",
            "CREATE",
            "ALTER",
            "UNION",
            "SELECT",
            "FROM",
            "WHERE",
            "TABLE",
            "DATABASE",
            "SCHEMA",
        ]
        for keyword in sql_keywords:
            query = re.sub(rf"\b{keyword}\b", " ", query, flags=re.IGNORECASE)

        # Clean up whitespace and normalize
        query = " ".join(query.split())

        # If query is empty after cleaning, return a safe default
        if not query.strip():
            return "placeholder_safe_query"

        return query

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """BM25 search using SQLite FTS5."""
        # Escape query for FTS5 safety
        clean_query = self._escape_fts5_query(query)

        # Search with BM25 ranking with error handling
        try:
            results = self.conn.execute(
                """
                SELECT
                    doc_id,
                    chunk_id,
                    text,
                    keywords,
                    metadata,
                    bm25(documents) as score
                FROM documents
                WHERE documents MATCH ?
                ORDER BY score
                LIMIT ?
            """,
                (clean_query, limit),
            ).fetchall()
        except sqlite3.OperationalError as e:
            # If FTS5 query still fails, return empty results instead of crashing
            logger.warning(f"FTS5 search failed for query '{query}': {e}")
            return []

        return [
            {
                "doc_id": r[0],
                "chunk_id": r[1],
                "text": r[2],
                "keywords": r[3],
                "metadata": json.loads(r[4]),
                "score": r[5],
            }
            for r in results
        ]

    def search_by_part_number(self, part_number: str) -> list[dict]:
        """Search specifically by part number."""
        results = self.conn.execute(
            """
            SELECT DISTINCT
                dm.doc_id,
                dm.source,
                dm.pairs
            FROM doc_metadata dm
            WHERE dm.pairs LIKE ?
        """,
            (f"%{part_number}%",),
        ).fetchall()

        return [{"doc_id": r[0], "source": r[1], "pairs": json.loads(r[2])} for r in results]

    def get_stats(self) -> dict:
        """Get index statistics."""
        stats = {
            "total_documents": self.conn.execute(
                "SELECT COUNT(DISTINCT doc_id) FROM documents"
            ).fetchone()[0],
            "total_chunks": self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "documents_with_keywords": self.conn.execute(
                "SELECT COUNT(*) FROM documents WHERE keywords != ''"
            ).fetchone()[0],
        }

        # Get top terms
        # Note: FTS5 doesn't expose term frequencies directly, so this is approximate
        stats["index_size_mb"] = Path(self.db_path).stat().st_size / 1024 / 1024

        return stats


class SimpleBM25Index:
    """Alternative pure Python BM25 implementation for flexibility."""

    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_freq = defaultdict(int)  # term -> doc count
        self.doc_len = {}  # doc_id -> length
        self.doc_term_freqs = {}  # doc_id -> Counter
        self.documents = {}  # doc_id -> document data
        self.N = 0  # total documents
        self.avgdl = 0  # average document length

    def index_nodes(self, nodes: list[TextNode], doc_id: str):
        """Index nodes for BM25."""
        for node in nodes:
            chunk_id = f"{doc_id}_{node.metadata.get('chunk_index', 0)}"

            # Tokenize
            tokens = self._tokenize(node.text)

            # Update statistics
            self.doc_len[chunk_id] = len(tokens)
            self.doc_term_freqs[chunk_id] = Counter(tokens)
            self.documents[chunk_id] = {
                "text": node.text,
                "metadata": node.metadata,
                "node_id": node.id_,
            }

            # Update document frequencies
            for term in set(tokens):
                self.doc_freq[term] += 1

            self.N += 1

        # Update average document length
        self.avgdl = sum(self.doc_len.values()) / len(self.doc_len) if self.doc_len else 0

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization."""
        # Convert to lowercase and split on non-alphanumeric
        tokens = re.findall(r"\b\w+\b", text.lower())
        # Remove stopwords (simplified)
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
        }
        return [t for t in tokens if t not in stopwords and len(t) > 2]

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float, dict]]:
        """BM25 search."""
        query_tokens = self._tokenize(query)
        scores = {}

        for doc_id in self.documents:
            score = 0
            doc_len = self.doc_len[doc_id]

            for term in query_tokens:
                if term in self.doc_term_freqs[doc_id]:
                    # BM25 formula
                    tf = self.doc_term_freqs[doc_id][term]
                    doc_freq = self.doc_freq[term]
                    idf = math.log((self.N - doc_freq + 0.5) / (doc_freq + 0.5) + 1)

                    numerator = idf * tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)

                    score += numerator / denominator

            if score > 0:
                scores[doc_id] = score

        # Sort by score
        results = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        return [(doc_id, score, self.documents[doc_id]) for doc_id, score in results]

    def save(self, path: str):
        """Save index to disk."""
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "doc_freq": dict(self.doc_freq),
                    "doc_len": self.doc_len,
                    "doc_term_freqs": {k: dict(v) for k, v in self.doc_term_freqs.items()},
                    "documents": self.documents,
                    "N": self.N,
                    "avgdl": self.avgdl,
                    "k1": self.k1,
                    "b": self.b,
                },
                f,
            )

    def load(self, path: str):
        """Load index from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
            self.doc_freq = defaultdict(int, data["doc_freq"])
            self.doc_len = data["doc_len"]
            self.doc_term_freqs = {k: Counter(v) for k, v in data["doc_term_freqs"].items()}
            self.documents = data["documents"]
            self.N = data["N"]
            self.avgdl = data["avgdl"]
            self.k1 = data["k1"]
            self.b = data["b"]
