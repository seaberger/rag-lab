#!/usr/bin/env python3
"""
Loads and inspects a pickle file expected to contain a list of
LlamaIndex Node objects (e.g., TextNode).
Prints metadata and text content for each node.
"""

import pickle
import argparse
from pathlib import Path

# Optional: Import LlamaIndex types for more specific checking
try:
    from llama_index.core.schema import TextNode, BaseNode

    LLAMAINDEX_INSTALLED = True
except ImportError:
    print(
        "Warning: llama-index-core not installed. Cannot perform detailed Node inspection."
    )
    TextNode = None
    BaseNode = None
    LLAMAINDEX_INSTALLED = False


def display_nodes(file_path: str, limit: int = None, show_full_text: bool = False):
    """Loads nodes from a pickle file and displays their details."""
    path = Path(file_path)
    if not path.is_file():
        print(f"Error: File not found at {path}")
        return

    print(f"Loading nodes from: {path}...")
    try:
        with open(path, "rb") as f:
            nodes = pickle.load(f)
    except pickle.UnpicklingError:
        print(
            f"Error: Failed to unpickle file. It might be corrupted or not a pickle file."
        )
        return
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    if not isinstance(nodes, list):
        print(
            f"Error: Expected a list in the pickle file, but found type {type(nodes).__name__}."
        )
        return

    if not nodes:
        print("Pickle file loaded successfully, but the list is empty.")
        return

    print(f"Successfully loaded {len(nodes)} potential node objects.")

    # Determine how many nodes to display
    nodes_to_display = nodes[:limit] if limit is not None and limit > 0 else nodes
    displayed_count = len(nodes_to_display)
    total_count = len(nodes)

    print(f"\n--- Displaying {displayed_count} out of {total_count} Nodes ---")

    for i, node in enumerate(nodes_to_display):
        print(f"\n--- Node {i + 1}/{displayed_count} | ", end="")

        node_id = getattr(node, "node_id", "N/A")
        node_type = type(node).__name__

        # Try to determine type more specifically if possible
        if LLAMAINDEX_INSTALLED:
            if isinstance(node, TextNode):
                node_type = "TextNode"
            elif isinstance(node, BaseNode):
                node_type = f"BaseNode (Subclass: {type(node).__name__})"
            else:
                node_type = f"Unknown LlamaIndex Object ({type(node).__name__})"
        else:
            node_type = f"Object (Type: {type(node).__name__})"

        print(f"Type: {node_type} | ID: {node_id} ---")

        # Display Metadata
        if hasattr(node, "metadata") and isinstance(node.metadata, dict):
            print("Metadata:")
            if node.metadata:
                for key, value in node.metadata.items():
                    # Simple formatting for lists/dicts within metadata
                    if isinstance(value, list) and len(value) > 5:
                        print(f"  - {key}: List[{len(value)} items]")
                    elif isinstance(value, dict) and len(value) > 5:
                        print(f"  - {key}: Dict[{len(value)} keys]")
                    else:
                        print(
                            f"  - {key}:\n{value}"
                        )  # Print value directly, handles multiline lists well
            else:
                print("  (empty)")
        else:
            print("Metadata: N/A or invalid format")

        # Display Relationships (if they exist)
        if hasattr(node, "relationships") and node.relationships:
            print("\nRelationships:")
            print(f"  {node.relationships}")  # Print the relationship dictionary/list

        # Display Text Content
        print("\nText Content:")
        if hasattr(node, "text") and isinstance(node.text, str):
            text_content = node.text
            text_length = len(text_content)
            print(f"Text Length: {text_length}")
            print(
                "Full Content:"
                if show_full_text
                else "Sample Content (first 500 chars):"
            )
            if show_full_text or text_length <= 500:
                print(text_content)
            else:
                print(text_content[:500] + "...")
        else:
            print("Text: N/A or not a string")
        print("-" * 60)

    if limit is not None and limit < total_count:
        print(f"\nNote: Display limited to the first {limit} nodes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="View contents of a pickle file containing LlamaIndex Nodes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-f",
        "--file",
        required=True,
        help="Path to the input .pkl file containing the list of nodes.",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=None,  # Show all by default
        help="Limit the number of nodes displayed (shows first N nodes).",
    )
    parser.add_argument(
        "--full-text",
        action="store_true",
        help="Show the full text content of each node instead of truncating.",
    )

    args = parser.parse_args()
    display_nodes(args.file, args.limit, args.full_text)
