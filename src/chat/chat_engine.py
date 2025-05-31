# --- START OF FILE chat_engine.py ---
# --- Imports for LlamaIndex components ---
import json
import re
import pickle
import sqlite3
import logging
import os
import uuid
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, AsyncGenerator
from dotenv import load_dotenv

# Langfuse/LlamaIndex Integration
from llama_index.core.callbacks import CallbackManager

# from langfuse.llama_index import LlamaIndexCallbackHandler  # Removed as not used
from langfuse.llama_index import LlamaIndexInstrumentor

# Global client reference
# Global reference to Langfuse instrumentor for direct access
LANGFUSE_INSTRUMENTOR = None

from llama_index.core import (
    Settings,
    VectorStoreIndex,
)
from llama_index.core.schema import NodeWithScore, TextNode, QueryBundle
from llama_index.core.chat_engine.types import (
    BaseChatEngine,
    StreamingAgentChatResponse,
)
from llama_index.core.chat_engine import ContextChatEngine
from llama_index.llms.openai import OpenAI
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.postprocessor.cohere_rerank import CohereRerank
from llama_index.core.retrievers import BaseRetriever
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)
load_dotenv()

# --- Explicit Langfuse Initialization --- -> Switch to Callback Handler
# langfuse_client = None  # Initialize as None
langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
langfuse_host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

# --- Constants ---
# General
APP_NAME = "Matrix Chatbot"
APP_VERSION = "1.0.1"
MAX_TOKENS = 4096
TEMPERATURE = 0.1
DEFAULT_PROMPT = (
    "You are a helpful AI assistant knowledgeable about Matrix Laser products."
)

# Models
LLM_MODEL = "gpt-4.1"
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072
RERANK_MODEL = "rerank-v3.5"

# Database Paths (Now using Qdrant and SQLite)
NODE_PICKLE_FILE = "matrix_nodes.pkl"
SQLITE_DB_NAME_LOCAL = "matrix_nodes.db"
SQLITE_DB_NAME_PROD = "/app/matrix_nodes.db"
QDRANT_COLLECTION_NAME = "matrix_docs"
QDRANT_PATH_LOCAL = "./qdrant_db"
QDRANT_PATH_PROD = "/app/qdrant_db"

# Retriever Settings
VECTOR_SIMILARITY_TOP_K = 10
KEYWORD_SIMILARITY_TOP_K = 5
RERANK_TOP_N = 5
HYBRID_RETRIEVER_MODE = "relative_score"

# --- Helper Classes ---


class HybridRetrieverModeA(BaseRetriever):
    """Hybrid retriever that combines vector and keyword results using relative scoring."""

    def __init__(self, vector_retriever, keyword_retriever, mode="relative_score"):
        self.vector_retriever = vector_retriever
        self.keyword_retriever = keyword_retriever
        self.mode = mode
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Retrieve nodes using both vector and keyword search, then combine."""
        # Extract query string for potential logging or future use
        # query_str = query_bundle.query_str

        vector_nodes = self.vector_retriever.retrieve(query_bundle)
        keyword_nodes = self.keyword_retriever.retrieve(query_bundle)

        vector_ids = {n.node.node_id for n in vector_nodes}
        keyword_ids = {n.node.node_id for n in keyword_nodes}

        combined_dict = {n.node.node_id: n for n in vector_nodes}
        combined_dict.update({n.node.node_id: n for n in keyword_nodes})

        if self.mode == "relative_score":
            self._normalize_scores(vector_nodes)
            self._normalize_scores(keyword_nodes)
            for node_id, node in combined_dict.items():
                node.score = node.score or 0.0
                if node_id in vector_ids and node_id in keyword_ids:
                    v_node = next(n for n in vector_nodes if n.node.node_id == node_id)
                    k_node = next(n for n in keyword_nodes if n.node.node_id == node_id)
                    node.score = (v_node.score + k_node.score) / 2
                elif node_id in vector_ids:
                    v_node = next(n for n in vector_nodes if n.node.node_id == node_id)
                    node.score = v_node.score
                elif node_id in keyword_ids:
                    k_node = next(n for n in keyword_nodes if n.node.node_id == node_id)
                    node.score = k_node.score

        sorted_results = sorted(
            combined_dict.values(), key=lambda x: x.score or 0.0, reverse=True
        )
        logger.info(f"Hybrid retrieval found {len(sorted_results)} unique nodes.")
        return sorted_results

    def _normalize_scores(self, nodes: List[NodeWithScore]):
        """Normalize scores to be between 0 and 1."""
        scores = [node.score for node in nodes if node.score is not None]
        if not scores:
            return
        max_score = max(scores) if scores else 1.0
        min_score = min(scores) if scores else 0.0
        for node in nodes:
            if node.score is not None:
                if max_score == min_score:
                    node.score = 1.0 if max_score > 0 else 0.0
                else:
                    node.score = (node.score - min_score) / (max_score - min_score)
            else:
                node.score = 0.0


# --- Add SQLiteFTSRetriever from working file ---
class SQLiteFTSRetriever(BaseRetriever):
    """SQLite FTS (Full-Text-Search) retriever that inherits from BaseRetriever for tracing."""

    def __init__(self, db_path=None, top_k=5, callback_manager=None):
        # Initialize the BaseRetriever first to enable tracing
        super().__init__(callback_manager=callback_manager)

        # Standard initialization
        if db_path is None:
            if os.environ.get("PLASH_PRODUCTION") == "1":
                self.db_path = SQLITE_DB_NAME_PROD
            else:
                self.db_path = SQLITE_DB_NAME_LOCAL
        else:
            self.db_path = db_path
        self.top_k = top_k
        logging.info(f"SQLiteFTSRetriever initialized with DB path: {self.db_path}")

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Implementation of the abstract _retrieve method required by BaseRetriever.
        This method is the INTERNAL implementation that will be called by retrieve().
        The BaseRetriever's retrieve() method adds instrumentation around this method.
        """
        query_str = query_bundle.query_str  # <-- Extract the string here

        # --- Restore DB connection logic ---
        if not os.path.exists(self.db_path):
            logging.error(f"Error: SQLite database not found at {self.db_path}")
            return []
        conn = None  # Initialize conn
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            # ---------------------------------

            # Perform query analysis
            fts_query = f'"""*{query_str}*"""'  # Use FTS5 phrase query syntax

            # --- Fix syntax in query execution and logging ---
            # Corrected logging format string
            logging.debug(f"Executing FTS query: {query_str}")

            # FIXED QUERY: Join nodes_fts with nodes table to get node_id
            c.execute(
                """
                SELECT nodes.node_id, nodes.content, nodes.metadata, nodes_fts.rank
                FROM nodes_fts
                JOIN nodes ON nodes_fts.rowid = nodes.rowid
                WHERE nodes_fts MATCH ?
                ORDER BY nodes_fts.rank
                LIMIT ?
                """,
                (fts_query, self.top_k),
            )
            results = c.fetchall()

            nodes = []
            if results:
                # No need for a second query - we already have all the data
                for node_id, content, metadata_str, rank_score in results:
                    try:
                        # Parse the metadata JSON string
                        metadata = json.loads(metadata_str)

                        # Create the TextNode
                        node = TextNode(
                            id_=node_id,
                            text=content,
                            metadata=metadata,
                        )

                        # Use a score based on rank (lower rank -> higher score)
                        score = 1.0 / (rank_score + 1)  # Simple inverse rank score
                        nodes.append(NodeWithScore(node=node, score=score))
                    except json.JSONDecodeError:
                        logging.error(
                            f"Failed to decode metadata JSON for node_id: {node_id}"
                        )
            return nodes

        except sqlite3.Error as e:
            logging.error(f"SQLite error during FTS query: {e}")
            return []
        finally:
            if conn:
                conn.close()

    # NOTE: We DO NOT override retrieve() here.
    # BaseRetriever.retrieve() from the parent class will call our _retrieve() method.
    # The parent's retrieve() method has all the necessary instrumentation built in.


# --- Add analyze_query from working file ---
def analyze_query(query: str) -> dict:
    part_number_pattern = r"\d{7}|\d{2}-\d{3}-\d{3}"  # Example
    model_keywords = ["matrix", "model", "laser", "series"]  # Example
    analysis = {
        "has_part_number": bool(re.search(part_number_pattern, query, re.IGNORECASE)),
        "has_model_reference": any(
            keyword in query.lower() for keyword in model_keywords
        ),
        "detected_part_numbers": re.findall(part_number_pattern, query),
        "query_type": "general",
    }
    if analysis["has_part_number"]:
        analysis["query_type"] = "part_number"
    elif analysis["has_model_reference"]:
        analysis["query_type"] = "model"
    return analysis


# --- Add HybridRetrieverWithReranking from working file ---
class HybridRetrieverWithReranking(BaseRetriever):
    def __init__(
        self,
        vector_retriever,
        keyword_retriever,
        reranker,
        vector_weight=0.7,
        keyword_weight=0.3,
        initial_top_k=20,
    ):
        self.vector_retriever = vector_retriever
        self.keyword_retriever = keyword_retriever
        self.reranker = reranker
        self.base_vector_weight = vector_weight
        self.base_keyword_weight = keyword_weight
        self.initial_top_k = initial_top_k
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Retrieve nodes using both vector and keyword search, then combine the results.
        With LlamaIndexInstrumentor, this method is automatically traced, so we no longer
        need manual Langfuse instrumentation.
        """
        logger.info(
            f"Starting hybrid retrieval for query: {query_bundle.query_str[:50]}..."
        )

        try:
            # Vector retrieval - will be automatically traced by Langfuse instrumentation
            vector_nodes = self.vector_retriever.retrieve(query_bundle)
            logger.info(f"Vector retrieval returned {len(vector_nodes)} nodes")

            # Keyword retrieval - will be automatically traced by Langfuse instrumentation
            keyword_nodes = self.keyword_retriever.retrieve(query_bundle)
            logger.info(f"Keyword retrieval returned {len(keyword_nodes)} nodes")

            # Process results
            node_scores = {}
            max_score = 0.0

            # Process vector results
            for result in vector_nodes:
                node_id = result.node.node_id
                score = result.score * self.base_vector_weight
                if node_id not in node_scores:
                    node_scores[node_id] = {"node": result.node, "score": 0.0}
                node_scores[node_id]["score"] += score
                max_score = max(max_score, node_scores[node_id]["score"])

            # Process keyword results (rank-based scoring)
            keyword_max_rank_score = self.base_keyword_weight
            for i, result in enumerate(keyword_nodes):
                node_id = result.node.node_id
                keyword_score = keyword_max_rank_score * (1.0 / (i + 1))
                # Add boosting logic here if needed based on metadata
                if node_id not in node_scores:
                    node_scores[node_id] = {"node": result.node, "score": 0.0}
                node_scores[node_id]["score"] += keyword_score
                max_score = max(max_score, node_scores[node_id]["score"])

            # --- Normalize scores ---
            if max_score > 0:
                for node_id in node_scores:
                    node_scores[node_id]["score"] /= max_score

            logger.info(
                f"Completed score computation with {len(node_scores)} nodes and max score {max_score}"
            )

            # --- Sort combined results ---
            sorted_results = sorted(
                node_scores.values(), key=lambda x: x["score"], reverse=True
            )

            # --- Prepare for Reranking ---
            initial_results_for_rerank = [
                NodeWithScore(node=item["node"], score=item["score"])
                for item in sorted_results[: self.initial_top_k]
            ]

            # --- Rerank (if applicable) ---
            final_top_n = self.reranker.top_n if self.reranker else 5
            if self.reranker is not None and initial_results_for_rerank:
                try:
                    logger.info(
                        f"Applying reranker: {self.reranker.__class__.__name__}"
                    )
                    reranked_nodes = self.reranker.postprocess_nodes(
                        initial_results_for_rerank, query_bundle
                    )
                    logger.info(
                        f"Reranking complete, returning {min(len(reranked_nodes), final_top_n)} nodes"
                    )
                    return reranked_nodes[:final_top_n]
                except Exception as e:
                    logger.error(
                        f"Error during reranking: {e}. Returning initial sorted results."
                    )
                    return initial_results_for_rerank[:final_top_n]

            # --- Return top N if no reranker or reranking failed ---
            logger.info(
                f"No reranking needed, returning {min(len(initial_results_for_rerank), final_top_n)} nodes"
            )
            return initial_results_for_rerank[:final_top_n]

        except Exception as e:
            logger.error(f"Error in hybrid retrieval: {e}", exc_info=True)
            raise


# --- Add create_or_load_sqlite_db from working file ---
def create_or_load_sqlite_db(nodes_path, db_path):
    if os.path.exists(db_path):
        logging.info(f"Using existing SQLite database at {db_path}")
        conn_check = sqlite3.connect(db_path)
        try:
            cursor = conn_check.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes_fts'"
            )
            if not cursor.fetchone():
                logging.warning(
                    f"DB file {db_path} exists but FTS table is missing. Recreating."
                )
                conn_check.close()
                os.remove(db_path)  # Remove bad file
            else:
                conn_check.close()
                return  # DB looks okay
        except Exception as e:
            logging.warning(f"Error checking existing DB {db_path}: {e}. Recreating.")
            try:
                conn_check.close()
            except Exception:
                pass
            if os.path.exists(db_path):
                os.remove(db_path)

    logging.info(f"Creating new SQLite FTS database at {db_path}")
    if not os.path.exists(nodes_path):
        logging.error(
            f"Error: Node pickle file not found at {nodes_path}. Cannot create SQLite DB."
        )
        raise FileNotFoundError(f"Required node file not found: {nodes_path}")
    with open(nodes_path, "rb") as f:
        nodes = pickle.load(f)
    if not nodes:
        logging.warning("No nodes found in pickle file. SQLite DB will be empty.")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Create nodes table
    c.execute(
        "CREATE TABLE IF NOT EXISTS nodes (rowid INTEGER PRIMARY KEY, node_id TEXT UNIQUE, content TEXT, metadata TEXT)"
    )
    conn.commit()
    # Create FTS table
    c.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(content, content='nodes', content_rowid='rowid', tokenize='porter unicode61')"
    )
    conn.commit()
    # Insert nodes
    inserted_count = 0
    skipped_count = 0
    for node in nodes:
        try:
            metadata_json = json.dumps(node.metadata or {})
            c.execute(
                "INSERT OR IGNORE INTO nodes (node_id, content, metadata) VALUES (?, ?, ?)",
                (node.node_id, node.text, metadata_json),
            )
            if c.rowcount > 0:
                inserted_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            logging.error(
                f"Error inserting node {getattr(node, 'node_id', 'UNKNOWN')}: {e}"
            )
            skipped_count += 1
    if skipped_count > 0:
        logging.info(f"Skipped {skipped_count} nodes (likely duplicates).")
    # Populate FTS index
    if inserted_count > 0:
        logging.info(f"Populating FTS index for {inserted_count} new nodes...")
        try:
            c.execute(
                "INSERT INTO nodes_fts(rowid, content) SELECT rowid, content FROM nodes WHERE rowid NOT IN (SELECT rowid FROM nodes_fts);"
            )
            conn.commit()
            logging.info("FTS index population complete.")
        except Exception as e:
            logging.error(f"Error populating FTS index: {e}")
            conn.rollback()
    elif skipped_count == len(nodes) and skipped_count > 0:
        logging.info("No new nodes inserted, FTS index assumed up-to-date.")
    else:
        logging.info("No nodes to insert into FTS index.")
    conn.close()
    logging.info(f"Finished SQLite DB setup at {db_path}.")


# --- Global Variables ---
global_retriever_async: Optional[BaseRetriever] = (
    None  # Keep for potential direct use/debug
)


# --- Settings Initialization (NOW includes Callback Manager) ---
def _init_settings():
    """Loads API keys and initializes LLM, Embedding model, and Langfuse Callback Handler globally."""
    logger.info("Initializing settings...")
    try:
        llm = OpenAI(model=LLM_MODEL, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
        embed_model = OpenAIEmbedding(model=EMBED_MODEL, dimensions=EMBED_DIM)
        Settings.llm = llm
        Settings.embed_model = embed_model
        logger.info(f"Using LLM: {LLM_MODEL}, Embed Model: {EMBED_MODEL}")

        # Ensure callback_manager exists but is empty initially if needed elsewhere
        # This is needed to prevent LlamaIndex from complaining about Settings.callback_manager being None
        if (
            not hasattr(Settings, "callback_manager")
            or Settings.callback_manager is None
        ):
            logger.info("Initializing empty Settings.callback_manager")
            Settings.callback_manager = CallbackManager([])  # Initialize empty manager

        logger.info("Settings initialized (LLM & Embed Model only).")
    except Exception as e:
        logger.error(f"Error initializing OpenAI models: {e}", exc_info=True)
        raise


def _init_langfuse() -> Optional[LlamaIndexInstrumentor]:
    """Initializes Langfuse LlamaIndexInstrumentor cleanly.

    This function creates and configures a single LlamaIndexInstrumentor instance
    according to best practices, with proper trace isolation.
    """
    global LANGFUSE_INSTRUMENTOR  # Declare intent to modify global

    # Skip if already initialized
    if LANGFUSE_INSTRUMENTOR is not None:
        logger.info(
            "Langfuse instrumentor already initialized, returning existing instance"
        )
        return LANGFUSE_INSTRUMENTOR

    # Get credentials
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")

    # Skip if keys are missing
    if not (langfuse_secret_key and langfuse_public_key):
        logger.warning("Langfuse keys not configured, skipping tracing setup.")
        LANGFUSE_INSTRUMENTOR = None  # Ensure it's None if keys are missing
        return None

    try:
        # Reset LlamaIndex Settings callbacks if they exist
        if hasattr(Settings, "callback_manager") and Settings.callback_manager:
            logger.info(
                "Resetting Settings.callback_manager before instrumentor setup."
            )
            if hasattr(Settings.callback_manager, "handlers"):
                Settings.callback_manager.handlers.clear()

        # Create the instrumentor - use default client settings for simplicity
        logger.info("Creating LlamaIndexInstrumentor with default settings.")
        instrumentor = LlamaIndexInstrumentor(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host,
            # Removing custom client config to prevent conflicts
        )

        # Start the instrumentor - this patches LlamaIndex classes
        logger.info("Starting Langfuse instrumentor patching...")
        instrumentor.start()
        logger.info("Langfuse instrumentor started.")

        # Keep a global reference
        LANGFUSE_INSTRUMENTOR = instrumentor

        # Register a simpler flush on exit with duplicate protection
        import atexit

        def flush_on_exit():
            if LANGFUSE_INSTRUMENTOR:
                logger.info("atexit: Flushing Langfuse instrumentor...")
                try:
                    LANGFUSE_INSTRUMENTOR.flush()
                    logger.info("atexit: Langfuse flush complete.")
                except Exception as e:
                    logger.error(f"atexit: Error flushing Langfuse: {e}")

        # Ensure only one atexit handler is registered
        exit_handlers = getattr(atexit, "_exithandlers", [])
        handler_exists = any(
            h[0].__name__ == "flush_on_exit" for h in exit_handlers if callable(h[0])
        )
        if not handler_exists:
            atexit.register(flush_on_exit)
            logger.info("Registered Langfuse flush on exit.")

        logger.info("Langfuse setup complete using LlamaIndexInstrumentor.")
        return instrumentor

    except ImportError as ie:
        logger.error(
            f"Langfuse package not found: {ie}. Please install with 'pip install langfuse'"
        )
    except Exception as e:
        logger.error(f"Error initializing Langfuse Instrumentor: {e}", exc_info=True)

    LANGFUSE_INSTRUMENTOR = None  # Ensure it's None on error
    return None


# --- ADD _create_sync_retriever (based on working create_retriever) ---
def _create_sync_retriever(cohere_api_key: str) -> HybridRetrieverWithReranking:
    """Creates the synchronous hybrid retriever using SQLite FTS and Qdrant."""
    # No need to explicitly get callback_manager - the instrumentor's start() method already
    # patches LlamaIndex components to use the global Settings.callback_manager
    logger.info("Creating retriever components - using automatic instrumentation")

    # Determine paths
    if os.environ.get("PLASH_PRODUCTION") == "1":
        sqlite_db_path = SQLITE_DB_NAME_PROD
        qdrant_db_path = QDRANT_PATH_PROD
        logging.info("Using PRODUCTION paths for SQLite and Qdrant.")
    else:
        sqlite_db_path = SQLITE_DB_NAME_LOCAL
        qdrant_db_path = QDRANT_PATH_LOCAL
        logging.info("Using LOCAL paths for SQLite and Qdrant.")

    # --- SQLite Retriever Setup ---
    # DB creation/check happens in init_chat_engine
    sqlite_retriever = SQLiteFTSRetriever(
        db_path=sqlite_db_path,
        top_k=KEYWORD_SIMILARITY_TOP_K,
        # Let instrumentor patching handle callback_manager automatically
    )

    # --- Vector Retriever Setup (LOAD from persistent Qdrant) ---
    try:
        qdrant_path_obj = Path(qdrant_db_path)
        if not qdrant_path_obj.exists() or not any(qdrant_path_obj.iterdir()):
            logging.error(
                f"Qdrant database path {qdrant_db_path} not found or is empty."
            )
            logging.error(
                "Please run 'create_vector_db.py' locally and ensure the 'qdrant_db' folder is deployed."
            )
            raise FileNotFoundError(f"Qdrant database not found at {qdrant_db_path}")

        logging.info(
            f"Connecting to persistent Qdrant client at path: {qdrant_db_path}"
        )
        # Use the imported QdrantClient class
        qdrant_client_instance = QdrantClient(path=qdrant_db_path)

        # Check if collection exists
        try:
            qdrant_client_instance.get_collection(
                collection_name=QDRANT_COLLECTION_NAME
            )
            logging.info(f"Found Qdrant collection '{QDRANT_COLLECTION_NAME}'.")
        except Exception as e:
            # Be more specific if possible, e.g., qdrant_client.http.exceptions.UnexpectedResponse
            logging.error(
                f"Qdrant collection '{QDRANT_COLLECTION_NAME}' not found in DB at {qdrant_db_path}. Error: {e}"
            )
            raise ValueError(
                f"Collection '{QDRANT_COLLECTION_NAME}' not found. Ensure DB was created correctly."
            )

        vector_store = QdrantVectorStore(
            client=qdrant_client_instance,
            collection_name=QDRANT_COLLECTION_NAME,
            # Let instrumentor patching handle callbacks automatically
        )

        logging.info("Loading VectorStoreIndex FROM existing vector store...")
        # Ensure Settings.embed_model is initialized before this call
        if Settings.embed_model is None:
            raise RuntimeError(
                "Settings.embed_model not initialized before creating vector index."
            )
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=Settings.embed_model,
            # Let instrumentor patching handle callbacks automatically
        )
        logging.info("VectorStoreIndex loaded successfully.")

        # Create vector retriever (callback_manager is already passed through the index)
        vector_retriever = index.as_retriever(
            similarity_top_k=VECTOR_SIMILARITY_TOP_K
            # Don't pass callback_manager again - it's already in the index
        )

    except Exception as e:
        logging.error(f"Error creating vector retriever from persistent Qdrant: {e}")
        import traceback

        traceback.print_exc()
        raise

    # --- Reranker and Hybrid Retriever Setup ---
    logging.info("Initializing Cohere Reranker...")
    try:
        # Ensure RERANK_MODEL constant is defined or use string directly
        reranker = CohereRerank(
            api_key=cohere_api_key,
            model=RERANK_MODEL,
            top_n=RERANK_TOP_N,
            # CohereRerank doesn't accept callback_manager
        )
    except Exception as e:
        logging.error(
            f"Error initializing Cohere Reranker: {e}. Reranking will be disabled."
        )
        reranker = None

    logging.info("Initializing Hybrid Retriever...")

    # Attempt to get Langfuse client from global callback manager for direct access
    langfuse_client = None
    if hasattr(Settings, "callback_manager") and Settings.callback_manager:
        for handler in Settings.callback_manager.handlers:
            if hasattr(handler, "langfuse"):
                langfuse_client = handler.langfuse
                logger.info(
                    "Obtained direct reference to Langfuse client from global callback handler"
                )
                break

    hybrid_retriever = HybridRetrieverWithReranking(
        vector_retriever=vector_retriever,
        keyword_retriever=sqlite_retriever,
        reranker=reranker,
        # Using relative score mode, weights are not directly used but kept for potential future use
        vector_weight=0.7,
        keyword_weight=0.3,
        # HybridRetrieverWithReranking doesn't accept callback_manager
    )

    # Directly attach the Langfuse client to the retriever for direct tracing
    if langfuse_client:
        hybrid_retriever.langfuse_client = langfuse_client
        logger.info(
            "Set Langfuse client directly on the hybrid retriever for explicit tracing"
        )

        # Also set on child retrievers for maximum coverage
        if hasattr(sqlite_retriever, "langfuse_client"):
            sqlite_retriever.langfuse_client = langfuse_client
            logger.info("Set Langfuse client on SQLite retriever")

        if hasattr(vector_retriever, "langfuse_client"):
            vector_retriever.langfuse_client = langfuse_client
            logger.info("Set Langfuse client on Vector retriever")

    return hybrid_retriever


# --- Main initialization function MODIFIED ---
def init_chat_engine() -> Dict:
    """Initializes the chat engine components with SYNC retrieval and returns them in a dict."""
    logger.info("--- Initializing Chat Engine (Sync Retrieval) --- ")

    # 1. Initialize Settings (LLM, Embed Model, Callback Handler)
    _init_settings()  # This now includes setting Settings.callback_manager

    # --- Initialize and Start Langfuse Instrumentor EARLY ---
    langfuse_instrumentor = _init_langfuse()
    # ------------------------------------------------------

    # 2. Get Cohere API Key (needed for retriever)
    cohere_api_key = os.environ.get("COHERE_API_KEY")
    if not cohere_api_key:
        raise ValueError("COHERE_API_KEY environment variable is not set")

    # 3. Create/Load SQLite DB *before* creating retriever
    nodes_pickle_path = NODE_PICKLE_FILE
    if os.environ.get("PLASH_PRODUCTION") == "1":
        sqlite_db_path = SQLITE_DB_NAME_PROD
        logger.info("Running in PLASH_PRODUCTION mode.")
    else:
        sqlite_db_path = SQLITE_DB_NAME_LOCAL
        logger.info("Running in local mode.")
    try:
        if not os.path.exists(nodes_pickle_path):
            logging.warning(
                f"Node pickle file '{nodes_pickle_path}' not found. Skipping SQLite DB creation/check."
            )
            # If SQLite is essential, could raise error here instead.
            # raise FileNotFoundError(f"Required node file '{nodes_pickle_path}' not found for SQLite DB.")
        else:
            create_or_load_sqlite_db(nodes_pickle_path, sqlite_db_path)
    except FileNotFoundError as e:
        logging.error(f"Fatal Error during SQLite setup: {e}.")
        raise
    except sqlite3.Error as e:  # More specific exception
        logging.error(f"Error during SQLite DB creation/check: {e}")
        raise  # Stop execution if DB fails
    except Exception as e:  # Catch other potential errors like pickle load
        logging.error(f"Unexpected error during SQLite setup: {e}")
        raise

    # 4. Create the SYNC retriever
    try:
        retriever = _create_sync_retriever(cohere_api_key)
    except Exception as e:
        logging.error(f"Fatal Error: Could not create retriever: {e}")
        raise

    # 6. Create the Chat Engine (using sync retriever)
    try:
        memory = ChatMemoryBuffer.from_defaults(token_limit=3900)
        chat_engine = ContextChatEngine.from_defaults(
            retriever=retriever,
            memory=memory,
            llm=Settings.llm,
            system_prompt="""Core Objective: Act as a knowledgeable Coherent/Matrix technical support agent. Your primary goal is to provide accurate technical answers based only on the information given to you for the current query, while maintaining strict confidentiality about the information's origins.

Key Instructions:

Answer from Provided Information ONLY: Base your answers strictly and solely on the information provided to you in the context for this specific query. Synthesize this information into a natural, helpful response.
Acknowledge Limits: If the answer is not present in the provided information, explicitly state that you do not have that specific detail available. Do not invent answers, speculate, or use any external knowledge.
ABSOLUTE CONFIDENTIALITY - CRITICAL:
NO Sourcing or Referencing: Under NO circumstances add any kind of reference, citation, source mention, footnote, link, or any indication whatsoever that your answer comes from specific documents or data sources. Do not even hint that documents were consulted.
NO Internal Details: Never mention internal file names (e.g., 'regulatory_certifications.md'), internal data structures (nodes, metadata), the retrieval process, or the existence of source documents.
Seamless Persona: Frame your answers naturally as if this knowledge is part of your technical expertise. The user must interact with you as a support agent, completely unaware of the underlying documentation or retrieval system.
Professional & Positive Tone: Maintain a helpful, professional, and positive tone regarding Coherent and Matrix laser products. Never speak negatively about the company, its products, or technology.
Pricing/Sales Off-Limits: REFUSE TO ANSWER any questions related to product pricing, costs, discounts, special offers, availability, lead times, or sales inquiries. Politely state that you cannot provide information on these topics and can only assist with technical questions about the products based on the available technical information.
Accuracy is Paramount: Ensure all technical details, product names, and specifications mentioned are accurate according to the provided information. Do not make assumptions or generalize beyond what is stated.
Handling "How Do You Know?" Questions: If the user asks about the source of your information or how you know something, politely state that your knowledge comes from the authorized technical documentation and resources for Coherent/Matrix products. Reassure them the information is accurate based on these official materials, but state clearly that you cannot provide specific internal document names or references.
Example Response: "My responses are based on the official technical information and documentation for Coherent and Matrix products. While I don't have access to specific internal document titles or references to share, I can assure you the details I provide are drawn from those authorized resources."
""",
            # Let instrumentor patching handle callbacks automatically
            # system_prompt="""You are a helpful technical support assistant specializing in Matrix laser products and technology.
            # Use the provided context to answer questions accurately and concisely.
            # If the context doesn't contain the answer, state that the information is not available in the provided documents.
            # Do not make up information. Be specific when referring to product names or technical details found in the context.""",
        )
        logger.info("Chat Engine Initialized Successfully.")
    except Exception as e:
        logger.error(f"Fatal Error: Could not create chat engine: {e}")
        raise

    # 7. Return components
    return {
        "chat_engine": chat_engine,
        "retriever": retriever,
        "langfuse_instrumentor": langfuse_instrumentor,  # Add instrumentor back
    }


# --- generate_streaming_response (Keep as is for async inference) ---
def generate_sync_response(query: str, chat_engine, instrumentor=None) -> str:
    """Generate a completely synchronous response without streaming.

    This function uses the simple synchronous chat() method for tracing instead
    of the streaming approach. This should provide the most reliable tracing.

    Important: This implementation uses the `observe` context manager to ensure
    each query gets its own isolated trace, preventing multiple queries from
    being stacked onto the same trace.

    Args:
        query (str): The user query
        chat_engine: The LlamaIndex chat engine instance

    Returns:
        str: The complete response text
    """
    logger.info("Using fully synchronous approach with proper trace isolation")
    try:
        # Verify callback manager is properly set up
        if hasattr(Settings, "callback_manager") and Settings.callback_manager:
            handlers = [type(h).__name__ for h in Settings.callback_manager.handlers]
            logger.info(f"Using callback handlers: {', '.join(handlers)}")
        else:
            logger.warning("No callback manager found in Settings")

        # Generate a unique trace ID for this query to prevent stacking
        trace_id = f"query-{uuid.uuid4()}"
        logger.info(f"Generated unique trace ID: {trace_id}")

        # Log whether we received an instrumentor from the app state
        if instrumentor:
            logger.info(
                f"Using instrumentor passed from app state: {type(instrumentor).__name__}"
            )
        else:
            # Fallback to global search only if not provided explicitly
            logger.warning("No instrumentor provided from app state, checking globals")
            for item in globals().values():
                if (
                    hasattr(item, "__class__")
                    and item.__class__.__name__ == "LlamaIndexInstrumentor"
                ):
                    instrumentor = item
                    logger.info("Found fallback instrumentor in globals")
                    break

        # If we found an instrumentor, use it with the observe context manager
        if instrumentor:
            logger.info(f"Using observe context with trace_id={trace_id}")
            # Using observe with update_parent=False to prevent trace stacking
            with instrumentor.observe(
                trace_id=trace_id, metadata={"query": query[:100]}, update_parent=False
            ) as trace:
                # Execute the query in this isolated trace context
                logger.info(
                    f"Executing query in isolated trace context: '{query[:30]}...'"
                )
                response = chat_engine.chat(query)

                # Add metadata to the trace
                trace.update(metadata={"response_length": len(response.response)})

                # Force a flush to immediately send the trace
                instrumentor.flush()

                logger.info(
                    f"Generated response of length {len(response.response)} with isolated trace"
                )
                return response.response
        else:
            # Fallback if no instrumentor is found
            logger.warning(
                "No instrumentor found for observe context, using standard approach"
            )
            response = chat_engine.chat(query)
            logger.info(f"Generated response of length {len(response.response)}")
            return response.response
    except Exception as e:
        logger.error(f"Error generating synchronous response: {e}", exc_info=True)
        return f"Error: {str(e)}"


async def generate_response(
    query: str,
    chat_engine: BaseChatEngine,
    instrumentor=None,
    chat_history: Optional[List] = None,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a complete response with proper trace isolation, returning structured data in one block.

    Args:
        query: The user query to process
        chat_engine: The chat engine instance to use
        instrumentor: Optional Langfuse instrumentor (will use app state or global)
        chat_history: Optional chat history to set before generating response
        system_prompt: Optional system prompt to apply

    Returns:
        Dict with 'response', 'sources', and error status if applicable
    """
    if not chat_engine:
        logger.error("generate_response: Received None for chat_engine.")
        return {"error": True, "response": "Chat engine not available."}

    # Set chat history if provided
    if chat_history:
        if hasattr(chat_engine, "chat_history"):
            chat_engine.chat_history = chat_history
        else:
            logger.warning(
                "Chat engine instance does not have 'chat_history' attribute."
            )

    # Unique ID for this specific request/query
    trace_id = f"query-{uuid.uuid4()}"
    full_response_text = ""
    response_metadata = {}  # To store source nodes etc. if needed

    # Ensure instrumentor is available
    if instrumentor is None:
        # Attempt to get from global as a last resort, but prefer passed state
        instrumentor = globals().get("LANGFUSE_INSTRUMENTOR")
        if instrumentor:
            logger.warning(
                "generate_streaming_response: Using global instrumentor fallback."
            )
        else:
            logger.warning(
                "generate_streaming_response: No instrumentor available for tracing."
            )

    try:
        logger.info(
            f"Starting generation for trace_id: {trace_id}, Query: '{query[:50]}...'"
        )

        if instrumentor:
            # Use observe context with update_parent=False
            # CRITICAL: Ensures this trace doesn't attach to any previous ones
            # Prepare structured input for better visibility in Langfuse UI
            trace_input = {"query": query}

            with instrumentor.observe(
                trace_id=trace_id,
                metadata={"query_preview": query[:100]},
                update_parent=False,
            ) as trace:
                # Update trace with input immediately after getting trace object
                try:
                    trace.update(input=trace_input)
                    logger.info(f"Updated trace with input for {trace_id}")
                except Exception as input_err:
                    logger.error(
                        f"Failed to update trace with input for {trace_id}: {input_err}"
                    )

                # --- Execute Synchronous Chat ---
                logger.info(f"Executing chat_engine.chat() within trace {trace_id}")
                response = chat_engine.chat(query)  # Simple synchronous call

                # Get the full response text
                full_response_text = response.response

                # Capture source nodes if available
                if hasattr(response, "source_nodes"):
                    response_metadata["source_nodes"] = [
                        {
                            "id": node.node.node_id,
                            "score": node.score,
                            "text": node.node.text[:100],
                        }
                        for node in response.source_nodes
                    ]

                logger.info(
                    f"Chat completed for trace {trace_id}. Response length: {len(full_response_text)}"
                )

                # --- Update Trace Metadata ---
                # This happens *before* the observe block exits
                from llama_index.core import Settings

                trace_meta = {
                    "response_length": len(full_response_text),
                    "response_type": "sync_chat",
                    "num_source_nodes": len(response_metadata.get("source_nodes", [])),
                }

                # Add LLM model if available
                if (
                    hasattr(Settings, "llm")
                    and Settings.llm
                    and hasattr(Settings.llm, "metadata")
                ):
                    trace_meta["llm_model"] = getattr(
                        Settings.llm.metadata, "model_name", "unknown"
                    )

                # Prepare structured output for better visibility in Langfuse UI
                trace_output = {"response": full_response_text}

                try:
                    # Update the trace with both output and metadata before exiting the block
                    trace.update(
                        output=trace_output,  # Add the final output
                        metadata=trace_meta,
                    )
                    logger.info(
                        f"Updated trace with output and metadata for {trace_id}"
                    )
                except Exception as meta_err:
                    logger.error(
                        f"Failed to update trace output/metadata for {trace_id}: {meta_err}"
                    )

            # --- Flush AFTER the observe block ---
            # This ensures the trace (including metadata) is complete before sending
            logger.info(f"Flushing instrumentor for trace_id: {trace_id}")
            instrumentor.flush()
            logger.info(f"Flush called for trace_id: {trace_id}")

        else:
            # --- No Instrumentor: Execute directly ---
            logger.info(
                f"Executing chat_engine.chat() WITHOUT tracing. Query: '{query[:50]}...'"
            )
            response = chat_engine.chat(query)  # Simple synchronous call

            # Get the full response text
            full_response_text = response.response

            # Capture source nodes if available
            if hasattr(response, "source_nodes"):
                response_metadata["source_nodes"] = [
                    {
                        "id": node.node.node_id,
                        "score": node.score,
                        "text": node.node.text[:100],
                    }
                    for node in response.source_nodes
                ]

            logger.info(
                f"Chat completed (no tracing). Response length: {len(full_response_text)}"
            )

        # --- Prepare and return the complete response ---
        result = {
            "error": False,
            "response": full_response_text or "(No response generated)",
        }

        # Add sources if available
        if response_metadata.get("source_nodes"):
            result["sources"] = response_metadata["source_nodes"]

        return result

    except Exception as e:
        logger.error(f"Error during chat (Trace ID: {trace_id}): {e}", exc_info=True)
        return {"error": True, "response": f"An error occurred: {str(e)}"}

    finally:
        # We no longer need a redundant flush here
        # The flush after the observe block is sufficient and prevents timing issues
        logger.debug(f"generate_response completed for trace_id: {trace_id}")


# --- ADD ASYNC STREAMING FUNCTION ---
async def generate_streaming_response(
    query: str,
    chat_engine: BaseChatEngine,
    instrumentor=None,
    # chat_history: Optional[List] = None, # Add if needed later
    # system_prompt: Optional[str] = None, # Add if needed later
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generates a streaming response using astream_chat with Langfuse tracing."""

    if not chat_engine:
        logger.error("generate_streaming_response: Received None for chat_engine.")
        yield {"type": "error", "content": "Chat engine not available."}
        yield {"type": "done", "content": ""}
        return

    # Ensure instrumentor is available
    if instrumentor is None:
        instrumentor = globals().get("LANGFUSE_INSTRUMENTOR")
        # ... (Add logging warnings if needed) ...

    trace_id = f"stream-query-{uuid.uuid4()}"
    trace_input = {"query": query}
    full_response_text = ""
    source_nodes_data = []

    try:
        logger.info(
            f"Starting ASYNC generation for trace_id: {trace_id}, Query: '{query[:50]}...'"
        )

        if instrumentor:
            with instrumentor.observe(
                trace_id=trace_id,
                metadata={"query_preview": query[:100], "streamed": True},
                update_parent=False,
            ) as trace:
                try:
                    trace.update(input=trace_input)
                    logger.info(f"Updated trace with input for {trace_id}")
                except Exception as input_update_err:
                    logger.error(
                        f"Failed to update trace with input for {trace_id}: {input_update_err}"
                    )

                logger.info(
                    f"Calling chat_engine.astream_chat() within trace {trace_id}"
                )
                try:
                    response_stream: StreamingAgentChatResponse = (
                        await chat_engine.astream_chat(query)
                    )
                    logger.info(f"Got response stream object for trace {trace_id}")

                    async for chunk in response_stream.async_response_gen():
                        yield {"type": "content", "content": chunk}
                        full_response_text += chunk
                        await asyncio.sleep(
                            0.005
                        )  # Prevent blocking event loop entirely

                    logger.info(
                        f"Finished iterating stream for trace {trace_id}. Full length: {len(full_response_text)}"
                    )

                    # Get source nodes after stream
                    if hasattr(response_stream, "source_nodes"):
                        source_nodes_data = [
                            {
                                "id": node.node.node_id,
                                "score": node.score,
                                "text_preview": node.node.get_content()[:100],
                            }
                            for node in response_stream.source_nodes
                        ]
                        logger.info(
                            f"Captured {len(source_nodes_data)} source nodes for trace {trace_id}"
                        )
                        yield {"type": "sources", "content": source_nodes_data}

                except Exception as stream_err:
                    logger.error(
                        f"Error *during* astream_chat or iteration: {stream_err}",
                        exc_info=True,
                    )
                    yield {
                        "type": "error",
                        "content": f"Error during streaming: {stream_err}",
                    }
                    # Still attempt to update trace below

                # Update Trace with Output and Final Metadata
                trace_output = {"response": full_response_text}
                trace_meta = {
                    "query_preview": query[:100],
                    "response_length": len(full_response_text),
                    "llm_model": Settings.llm.metadata.model_name
                    if Settings.llm
                    else "unknown",
                    "num_source_nodes": len(source_nodes_data),
                    "streamed": True,
                }
                try:
                    trace.update(output=trace_output, metadata=trace_meta)
                    logger.info(f"Updated trace with output/metadata for {trace_id}")
                except Exception as final_update_err:
                    logger.error(
                        f"Failed to update trace output/metadata for {trace_id}: {final_update_err}"
                    )

            # Flush AFTER observe block
            logger.info(f"Flushing instrumentor for trace_id: {trace_id}")
            instrumentor.flush()
            logger.info(f"Flush called for trace_id: {trace_id}")

        else:
            # --- No Instrumentor case (Streaming) ---
            logger.warning(
                f"Executing astream_chat WITHOUT tracing for Query: '{query[:50]}...'"
            )
            try:
                response_stream = await chat_engine.astream_chat(query)
                async for chunk in response_stream.async_response_gen():
                    yield {"type": "content", "content": chunk}
                    await asyncio.sleep(0.005)
                # Handle sources if needed for non-traced version
                if hasattr(response_stream, "source_nodes"):
                    # ... yield sources ...
                    pass

            except Exception as e:
                logger.error(f"Error during non-traced streaming: {e}", exc_info=True)
                yield {"type": "error", "content": f"Error processing stream: {e}"}

        # Signal completion
        yield {"type": "done", "content": ""}

    except Exception as e:
        logger.error(
            f"Outer error during async streaming (Trace ID: {trace_id}): {e}",
            exc_info=True,
        )
        yield {"type": "error", "content": f"An unexpected error occurred: {str(e)}"}
        yield {"type": "done", "content": ""}  # Ensure done signal


# --- END OF FILE chat_engine.py ---
