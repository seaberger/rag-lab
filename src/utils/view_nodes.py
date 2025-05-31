#!/usr/bin/env python3
import pickle
import argparse
import sys
import json
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any, Optional

# Attempt to import LlamaIndex types, handle if not installed
try:
    from llama_index.core.schema import BaseNode, TextNode, NodeRelationship

    NODE_CLASSES = (BaseNode,)  # Check against BaseNode
except ImportError:
    print(
        "Warning: llama_index.core not found. Assuming loaded objects have 'text', 'metadata', and 'node_id' attributes."
    )

    # Define a dummy class if llama_index is not critical for inspection itself
    class BasicNode:
        def __init__(self, text=None, metadata=None, node_id=None, relationships=None):
            self.text = text
            self.metadata = metadata or {}
            self.node_id = node_id
            self.relationships = relationships or {}

    NODE_CLASSES = (BasicNode,)
    NodeRelationship = None  # No enum available


def display_nodes(
    nodes_to_display: List[Any],  # Expecting list of BaseNode or similar
    show_full_view: bool,
    node_limit_applied: int,
):
    """Displays the details of the provided list of nodes."""

    print(
        f"\n--- Displaying {len(nodes_to_display)} out of {node_limit_applied} Nodes ---"
    )

    for i, node in enumerate(nodes_to_display, start=1):
        node_type = type(node).__name__
        node_id = getattr(node, "node_id", "N/A")

        print(
            f"\n--- Node {i}/{len(nodes_to_display)} | Type: {node_type} | ID: {node_id} ---"
        )

        # Display Metadata
        print("Metadata:")
        metadata = getattr(node, "metadata", {})
        if metadata and isinstance(metadata, dict):
            # Sort keys for consistent display, put 'file_name' first if exists
            sorted_keys = sorted(metadata.keys())
            if "file_name" in sorted_keys:
                sorted_keys.insert(0, sorted_keys.pop(sorted_keys.index("file_name")))

            for key in sorted_keys:
                value = metadata[key]
                # Pretty print if value is list/dict (like 'pairs')
                if isinstance(value, (list, dict)):
                    try:
                        value_str = json.dumps(value, indent=2)
                        print(f"  - {key}:\n{value_str}")
                    except TypeError:  # Handle non-serializable types if any
                        print(f"  - {key}: {value} (Could not JSON serialize)")
                else:
                    print(f"  - {key}: {value}")
        elif metadata:
            print(f"  Metadata present but not a dictionary: {metadata}")
        else:
            print("  Metadata missing or empty.")

        # Display Relationships (Optional but useful)
        print("\nRelationships:")
        relationships = getattr(node, "relationships", {})
        if relationships and isinstance(relationships, dict):
            for rel_key, related_node_info in relationships.items():
                # Use enum name if possible, otherwise raw key
                rel_name = (
                    rel_key.name
                    if NodeRelationship and isinstance(rel_key, NodeRelationship)
                    else str(rel_key)
                )
                # Handle single or list of related nodes
                if isinstance(related_node_info, list):
                    ids = [getattr(n, "node_id", "?") for n in related_node_info]
                    print(f"  - {rel_name}: {ids}")
                else:
                    rel_id = getattr(related_node_info, "node_id", "?")
                    print(f"  - {rel_name}: {rel_id}")
        else:
            print("  No relationships found.")

        # Display Text Content
        print("\nText Content:")
        text_content = getattr(node, "text", None)
        if text_content is not None:
            print(f"Text Length: {len(text_content)}")
            if show_full_view:
                print("Full Content:")
                print(text_content)
            else:
                preview_len = 500
                print(f"Content Preview (first {preview_len} chars):")
                print(
                    text_content[:preview_len]
                    + ("..." if len(text_content) > preview_len else "")
                )
        else:
            print("Text Length: 0 or Text attribute missing!")
            print("Content: N/A")

        print("-" * 60)


def filter_nodes(nodes: List[Any], filter_dict: Optional[Dict[str, str]]) -> List[Any]:
    """Filters nodes based on metadata key-value pairs."""
    if not filter_dict:
        return nodes

    filtered_list = []
    print(f"\nApplying metadata filters: {filter_dict}")
    filter_items = filter_dict.items()

    for node in nodes:
        metadata = getattr(node, "metadata", {})
        if isinstance(metadata, dict):
            match = True
            for key, expected_value in filter_items:
                actual_value = str(metadata.get(key, ""))  # Compare as strings
                if actual_value != expected_value:
                    match = False
                    break  # No need to check other keys for this node
            if match:
                filtered_list.append(node)
        # else: Node doesn't have dict metadata, cannot match filter

    print(f"Found {len(filtered_list)} nodes matching filters.")
    return filtered_list


def parse_filter_string(filter_str: Optional[str]) -> Optional[Dict[str, str]]:
    """Parses 'key1=value1,key2=value2' into a dictionary."""
    if not filter_str:
        return None

    filter_dict = {}
    try:
        pairs = filter_str.split(",")
        for pair in pairs:
            if "=" not in pair:
                raise ValueError(
                    f"Invalid filter format in part: '{pair}'. Use 'key=value'."
                )
            key, value = pair.split("=", 1)
            filter_dict[key.strip()] = value.strip()
        if not filter_dict:  # Handle empty string case after splits
            return None
        return filter_dict
    except Exception as e:
        print(f"Error parsing filter string '{filter_str}': {e}", file=sys.stderr)
        print("Expected format: 'key1=value1,key2=value2,...'", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Inspect LlamaIndex Node objects stored in a pickle file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        default=Path("enhanced_laser_nodes.pkl"),
        help="Path to the input pickle file containing a list of Node objects.",
    )
    parser.add_argument(
        "-n",
        "--num-nodes",
        type=int,
        default=None,
        help="Maximum number of nodes to display. Shows all if not specified.",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter nodes by metadata. Format: 'key1=value1,key2=value2,...' (e.g., 'file_name=doc.pdf,element_type=table'). Values are compared as strings.",
    )
    parser.add_argument(
        "--full-view",
        action="store_true",
        default=False,
        help="Display the full text content of each node instead of a preview.",
    )

    args = parser.parse_args()

    # --- File Loading ---
    pickle_file: Path = args.file
    if not pickle_file.is_file():
        print(f"Error: Pickle file not found at '{pickle_file}'", file=sys.stderr)
        sys.exit(1)

    print(f"Loading nodes from: {pickle_file}...")
    try:
        with open(pickle_file, "rb") as f:
            loaded_data = pickle.load(f)
    except Exception as e:
        print(f"Error loading pickle file: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Data Validation ---
    if not isinstance(loaded_data, list):
        print(
            f"Error: Expected a list of Node objects in the pickle file, but found type '{type(loaded_data).__name__}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not loaded_data:
        print("Pickle file loaded successfully, but the list of nodes is empty.")
        sys.exit(0)

    # Basic check if items look like nodes
    if not all(isinstance(item, NODE_CLASSES) for item in loaded_data):
        print(
            f"Warning: Loaded a list, but not all items appear to be Nodes (based on type check against {NODE_CLASSES}). Proceeding cautiously."
        )

    print(f"Successfully loaded {len(loaded_data)} potential node objects.")

    # --- Filtering ---
    filter_dict = parse_filter_string(args.filter)
    nodes_after_filter = filter_nodes(loaded_data, filter_dict)

    if not nodes_after_filter:
        print("No nodes remaining after applying filters.")
        sys.exit(0)

    total_nodes_after_filter = len(nodes_after_filter)

    # --- Limiting ---
    nodes_to_display = nodes_after_filter
    limit_applied = total_nodes_after_filter  # Store total before potentially limiting
    if args.num_nodes is not None and args.num_nodes < total_nodes_after_filter:
        nodes_to_display = nodes_after_filter[: args.num_nodes]
        print(
            f"\nLimiting display to first {args.num_nodes} out of {total_nodes_after_filter} nodes."
        )

    # --- Display ---
    display_nodes(nodes_to_display, args.full_view, limit_applied)


if __name__ == "__main__":
    main()
