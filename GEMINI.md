# RAG Lab Repository - GEMINI.md

This file provides a summary of the RAG Lab repository for developers.

## 🎯 Project Overview

The RAG Lab project is a document processing pipeline designed for enterprise use. It uses a Retrieval Augmented Generation (RAG) architecture to process and analyze documents, with a focus on technical datasheets. The current development effort is focused on "Pipeline v3," a production-ready system that uses the OpenAI Vision API for document processing.

### Key Features:

*   **Pipeline v3:** A robust document processing pipeline.
*   **Storage:** Document artifacts are stored as JSONL files.
*   **Search:** The system uses a hybrid search approach, combining vector and keyword search.
*   **Queue Management:** The pipeline supports scalable and concurrent processing of documents.

## 🗂️ Repository Structure

The repository is organized as follows:

*   `src/pipeline_v3/`: The current development focus, containing the production-ready document processing system.
*   `src/parsing/refactored_2_1/`: A reference implementation of a previous version of the pipeline (v2.1).
*   `data/`: Contains sample and production documents for testing and development.
*   `storage_data_v3/`: The output directory for processed document artifacts.

## 🚀 Getting Started

To get started with the project, follow these steps:

1.  **Navigate to the project root directory:**
    ```bash
    cd /Users/seanbergman/Repositories/rag_lab
    ```
2.  **Install dependencies using `uv`:**
    ```bash
    uv sync
    ```
3.  **Set up your environment:**
    *   Create a `.env` file in the project root.
    *   Add your `OPENAI_API_KEY` to the `.env` file.
4.  **Run the main CLI:**
    ```bash
    uv run python -m src.pipeline_v3.cli_main --help
    ```

## 🎯 GitHub Issues

This list of open issues was retrieved from the project's GitHub repository.

*   **#23:** Implement Enhanced Search Filtering System
*   **#21:** Data Consistency: doc_id mismatch between keyword and vector indexes
*   **#15:** Implement proper table extraction and LlamaIndex node handling
*   **#14:** Implement document-type aware chunking strategies
*   **#13:** Implement hybrid PDF parsing: VLM for datasheets, Docling for regular documents
*   **#12:** Implement page-level content classification for mixed document types
*   **#10:** Create top-level CLAUDE.md for repository navigation and context
*   **#8:** Enhanced Pipeline missing get_status() method for CLI status command
*   **#5:** Upgrade to Qdrant server for concurrent access and better performance
