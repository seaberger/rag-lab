# metadata.py
"""
Processes a list of LlamaIndex Document objects (typically output from parse.py)
to generate enhanced TextNode objects suitable for indexing in a RAG system.

This script performs the following main steps:
1. Loads Document objects from an input pickle file.
2. Splits the loaded Documents into smaller TextNode objects using SentenceSplitter.
   (Metadata from the parent Document, including extracted 'pairs', is
   preserved in the resulting Nodes).
3. For each TextNode, generates contextual keywords/phrases using an OpenAI LLM
   (e.g., gpt-4o-mini or gpt-4o) via the OpenAI API.
4. Appends the generated context string to the end of each Node's text content.
5. Saves the final list of enhanced TextNode objects to an output pickle file.

Requires:
- An input pickle file containing a list of LlamaIndex Document objects.
- The OPENAI_API_KEY environment variable to be set.
- Installation of necessary libraries:
  `pip install openai llama-index llama-index-llms-openai llama-index-embeddings-openai tqdm pydantic`

Usage:
------
For detailed options and defaults, run:
    python metadata.py --help

Basic Examples:

1. Process 'parsed_docs.pkl' and save enhanced nodes to 'enhanced_laser_nodes.pkl' (using defaults):
   python metadata.py

2. Process a specific input file and save to a specific output file:
   python metadata.py --input processed_step1.pkl --output final_nodes_for_indexing.pkl

Command Line Arguments:
-----------------------
--input  : Path to the input pickle file containing Document objects
           (default: ./parsed_docs.pkl).
--output : Path to save the output pickle file containing enhanced TextNode objects
           (default: ./enhanced_laser_nodes.pkl).
"""

import os
import re
import time
import json
import pickle
import asyncio
import logging
from pathlib import Path
from tqdm import tqdm
import openai

from llama_index.llms.openai import OpenAI
from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.schema import TextNode
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.ingestion import IngestionPipeline
from pydantic import BaseModel, Field
from typing import List

# Set up OpenAI API key
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")
openai.api_key = OPENAI_API_KEY


def load_docs_from_pickle(file_path):
    logging.info(f"Loading documents from {file_path}")
    with open(file_path, "rb") as f:
        loaded_docs = pickle.load(f)
        logging.info(f"Loaded {len(loaded_docs)} documents from {file_path}")
        for i, doc in enumerate(loaded_docs, start=1):
            logging.info(f"Document {i}: Length = {len(doc.text)}")
    return loaded_docs


def save_nodes_to_pickle(nodes, file_path):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "wb") as f:
        pickle.dump(nodes, f)
    logging.info(f"Successfully saved {len(nodes)} nodes to {file_path}")
    return file_path


async def generate_context(node_text, max_retries=3):
    """
    Generate context for a node using direct OpenAI API.

    Args:
        node_text: Text content of the node
        max_retries: Number of retries in case of API errors

    Returns:
        Generated context string
    """
    prompt = f"""
    Generate keywords and brief phrases describing the main topics, entities, and actions in this text.
    Replace any pronouns with their specific referents.
    Format as comma-separated phrases.
    
    TEXT:
    {node_text[:1000]}  # Limit text length to avoid token issues
    """

    for attempt in range(max_retries):
        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that generates concise context for document chunks.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.2,
            )

            # Extract the content from the response
            context = response.choices[0].message.content.strip()
            return context

        except Exception as e:
            logging.error(f"Error on attempt {attempt + 1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retrying

    return "Failed to generate context after multiple attempts"


async def enhance_all_nodes(nodes, batch_size=5, sleep_time=1):
    """
    Enhance all nodes by appending context to the content.

    Args:
        nodes: List of nodes to process
        batch_size: Number of nodes to process before sleeping
        sleep_time: Time to sleep between batches to avoid rate limits

    Returns:
        The enhanced nodes list
    """
    logging.info(f"Enhancing {len(nodes)} nodes with context...")

    # Create a progress bar with standard tqdm
    for i, node in enumerate(tqdm(nodes)):
        try:
            # Check if context already exists in metadata
            if "context" in node.metadata:
                # Use existing context from metadata
                context = node.metadata["context"]
                # Remove it from metadata
                del node.metadata["context"]
            else:
                # Generate new context
                context = await generate_context(node.text)

            # Append context to the content with a separator
            node.text = f"{node.text}\n\nContext: {context}"

            # Sleep after each batch to avoid rate limits
            if (i + 1) % batch_size == 0:
                time.sleep(sleep_time)

        except Exception as e:
            logging.error(f"Error processing node {i}: {str(e)}")
            # Add a placeholder context
            node.text = f"{node.text}\n\nContext: Error generating context: {str(e)}"
            # Make sure we don't have context in metadata
            if "context" in node.metadata:
                del node.metadata["context"]
            time.sleep(sleep_time)  # Sleep after an error

    # Count successful enhancements
    successful = sum(
        1
        for node in nodes
        if "\n\nContext: " in node.text and not "Error generating context" in node.text
    )
    logging.info(f"Successfully enhanced {successful}/{len(nodes)} nodes")

    return nodes


async def create_origin_nodes(input_file_path):
    """
    Create origin nodes from the input pickle file using the ingestion pipeline.

    Args:
        input_file_path: Path to the input pickle file

    Returns:
        List of processed nodes
    """

    logging.info(f"Loading documents from {input_file_path}")
    loaded_docs = load_docs_from_pickle(input_file_path)

    logging.info("Initializing MarkdownElementNodeParser...")

    # Load documents
    loaded_docs = load_docs_from_pickle(input_file_path)

    node_parser = SentenceSplitter(chunk_size=2048, chunk_overlap=128)
    # Create ingestion pipeline (without program_extractor since pairs are now handled by LlamaParse)
    pipeline = IngestionPipeline(transformations=[node_parser])

    # Run the pipeline with error handling
    logging.info("Running ingestion pipeline to create origin nodes...")
    try:
        # Print document info for debugging
        if loaded_docs:
            logging.info(f"\nProcessing {len(loaded_docs)} documents")
            for i, doc in enumerate(loaded_docs[:2]):  # Show first 2 docs
                logging.info(f"\nDocument {i + 1}:")
                logging.info("-" * 40)
                logging.info(f"Text length: {len(doc.text)}")
                logging.info("Sample content:")
                logging.info(doc.text[:500] + "...")
                logging.info("-" * 40)

        logging.info("\nStarting pipeline run...")
        origin_nodes = await pipeline.arun(documents=loaded_docs)
        logging.info("Pipeline run completed")

        # --- TEMPORARY DEBUGGING ---
        # Save the direct output of the parser BEFORE enhancement
        temp_output_path = "./raw_parser_output.pkl"
        logging.info(
            f"Saving raw parser output to {temp_output_path} for inspection..."
        )
        save_nodes_to_pickle(origin_nodes, temp_output_path)
        # --- END TEMPORARY DEBUGGING ---

        if origin_nodes:
            logging.info(f"Created {len(origin_nodes)} origin nodes")
            # Print sample nodes
            for i, node in enumerate(origin_nodes[:2]):  # Show first 2 nodes
                logging.info(f"\nNode {i + 1}:")
                logging.info("-" * 40)
                logging.info(f"Text length: {len(node.text)}")
                logging.info(f"Metadata: {node.metadata}")
                logging.info("Sample content:")
                logging.info(node.text[:500] + "...")
                logging.info("-" * 40)
            return origin_nodes
        else:
            logging.info(
                "No valid nodes were created. Check the extraction rules and validation."
            )
            return []
    except Exception as e:
        logging.error(f"Error during node creation: {str(e)}")
        logging.info("Stack trace:")
        import traceback

        traceback.print_exc()
        logging.info("\nReturning empty node list to allow pipeline to continue")
        return []


async def main(
    input_file="./parsed_lmc_docs.pkl",
    output_file="./enhanced_laser_nodes.pkl",
):
    """
    Main function to process the metadata pipeline.

    Args:
        input_file: Path to the input pickle file
        output_file: Path to the output pickle file
    """
    logging.info(f"Starting metadata processing pipeline...")
    logging.info(f"Input file: {input_file}")
    logging.info(f"Output file: {output_file}")

    # Step 1: Create origin nodes
    origin_nodes = await create_origin_nodes(input_file)

    # Step 2: Enhance nodes with context (pairs metadata now handled by LlamaParse)
    enhanced_nodes = await enhance_all_nodes(origin_nodes)

    # Step 4: Save the enhanced nodes
    save_nodes_to_pickle(enhanced_nodes, output_file)

    logging.info(f"Metadata processing pipeline completed successfully!")
    return enhanced_nodes


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process metadata for document nodes")
    parser.add_argument(
        "--input",
        default="./parsed_docs.pkl",
        help="Path to the input pickle file",
    )
    parser.add_argument(
        "--output",
        default="./enhanced_laser_nodes.pkl",
        help="Path to the output pickle file",
    )

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Run the async main function
    asyncio.run(main(input_file=args.input, output_file=args.output))
