#!/usr/bin/env python3
"""
Merges multiple pickle files containing lists of LlamaIndex objects, separating
them by type (Document vs. Node).

Searches recursively within a specified input directory for `.pkl` files.
Verifies that each file contains a list of either Document objects or
BaseNode objects (like TextNode). Merges objects of the same type into
separate lists.

Saves the merged lists to output files based on the provided base output
filename, appending '_documents.pkl' or '_nodes.pkl' accordingly.

Requires:
- Input pickle files containing lists of LlamaIndex Document or Node objects.
- Installation of `llama-index-core` for type verification (recommended).
  `pip install llama-index-core`

Usage:
------
For detailed options run:
    python merge_pickles.py --help

Basic Example:

1. Merge all .pkl files found in './pickle_outputs/' and save results to
   './merged_data_documents.pkl' and/or './merged_data_nodes.pkl':

   python merge_pickles.py --input_dir ./pickle_outputs --output_base_filename ./merged_data.pkl

Command Line Arguments:
-----------------------
--input_dir (-i) : Input directory containing .pkl files (searches recursively).
                   (Required)
--output_base_filename (-o): Base path and filename for the merged output files.
                             Suffixes '_documents.pkl' and '_nodes.pkl' will be
                             appended automatically based on the data found.
                             (Required)
"""

import os
import pickle
import argparse
from pathlib import Path
from typing import List, Any, Optional, Tuple, Type

# Import Document and Node types for verification
# Make it optional
try:
    from llama_index.core.schema import Document, TextNode, BaseNode

    VALID_OBJECT_TYPES: Tuple[Type, ...] = (
        Document,
        BaseNode,
    )  # Types we expect lists OF
    DOCUMENT_TYPE = Document
    NODE_TYPE = BaseNode  # Base class for TextNode etc.
    LLAMAINDEX_INSTALLED = True
except ImportError:
    print(
        "WARNING: llama-index-core not installed. Cannot perform strict type verification."
    )
    print("         Will only check if loaded data is a list.")
    VALID_OBJECT_TYPES = None
    DOCUMENT_TYPE = None
    NODE_TYPE = None
    LLAMAINDEX_INSTALLED = False


def find_pickle_files(input_dir: str) -> List[Path]:
    """Finds all .pkl files recursively within the input directory."""
    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_path}")

    print(f"Searching for .pkl files recursively in: {input_path.resolve()}")
    pickle_files = sorted(list(input_path.rglob("*.pkl")))

    if not pickle_files:
        print("No .pkl files found in the specified directory.")
    else:
        print(f"Found {len(pickle_files)} potential pickle files:")
        for f in pickle_files:
            # Use relative path for cleaner display if possible
            try:
                display_path = f.relative_to(Path.cwd())
            except ValueError:
                display_path = f  # Show absolute path if not relative
            print(f"  - {display_path}")
    return pickle_files


def load_and_verify_pickle(file_path: Path) -> Optional[Tuple[List[Any], Type]]:
    """
    Loads a pickle file, verifies it contains a list of a consistent
    LlamaIndex object type (Document or Node), and returns the list
    along with the detected type.
    """
    print(f"Attempting to load and verify: {file_path.name} ... ", end="")
    try:
        with open(file_path, "rb") as f:
            loaded_data = pickle.load(f)

        # --- Verification 1: Is it a list? ---
        if not isinstance(loaded_data, list):
            print(f"FAILED (Expected a list, found {type(loaded_data).__name__})")
            return None

        # --- Verification 2: Is the list empty? ---
        if not loaded_data:
            print("OK (Empty list)")  # Allow merging empty lists, type is undetermined
            # Return empty list and signal undetermined type with None
            return loaded_data, None

        # --- Verification 3: Item Type (if possible) ---
        first_item = loaded_data[0]
        detected_type = type(first_item)

        if LLAMAINDEX_INSTALLED and VALID_OBJECT_TYPES:
            # Check if the first item is an instance of Document or BaseNode
            if not isinstance(first_item, VALID_OBJECT_TYPES):
                print(
                    f"FAILED (Expected list items of type {VALID_OBJECT_TYPES}, found {detected_type.__name__})"
                )
                return None

            # Optional: Check all items for consistency (more robust but slower)
            # if not all(isinstance(item, detected_type) for item in loaded_data):
            #     print(f"FAILED (List contains mixed types, first was {detected_type.__name__})")
            #     return None

            # Determine primary type (Document or Node)
            if isinstance(first_item, DOCUMENT_TYPE):
                primary_type = DOCUMENT_TYPE
            elif isinstance(first_item, NODE_TYPE):
                primary_type = NODE_TYPE
            else:
                # Should not happen if VALID_OBJECT_TYPES check passed
                print(f"FAILED (Unexpected type {detected_type.__name__})")
                return None

            print(f"OK ({len(loaded_data)} items, type: {primary_type.__name__})")
            return loaded_data, primary_type

        # If only list check is possible (llama-index not installed)
        elif not LLAMAINDEX_INSTALLED:
            print("OK (Verified as list, type check skipped)")
            # Return list, but signal type couldn't be verified
            return loaded_data, Any  # Or another placeholder type

        else:  # Should not be reached
            print("FAILED (Internal verification logic error)")
            return None

    except FileNotFoundError:
        print("FAILED (File not found - was it moved/deleted?)")
        return None
    except pickle.UnpicklingError as e:
        print(f"FAILED (Pickle error: {e})")
        return None
    except Exception as e:
        print(f"FAILED (Unexpected error: {e})")
        return None


def save_merged_list(data_list: List[Any], output_base_path: Path, suffix: str):
    """Saves a list to a pickle file with a specific suffix."""
    if not data_list:
        print(f"Skipping save for '{suffix}' (no data).")
        return

    # Construct the final output path
    output_path = output_base_path.with_name(f"{output_base_path.stem}_{suffix}.pkl")

    print(
        f"\nAttempting to save {suffix} data ({len(data_list)} items) to: {output_path.resolve()}"
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            pickle.dump(data_list, f)
        print(f"Successfully saved {len(data_list)} {suffix} items to {output_path}")
    except Exception as e:
        print(f"ERROR: Failed to save output file '{output_path}': {e}")


def main(input_dir: str, output_base_filename: str):
    """
    Main function to find, load, verify, merge by type, and save pickle files.
    """

    pickle_files = find_pickle_files(input_dir)
    if not pickle_files:
        print("Exiting.")
        return

    # Separate lists for different types
    combined_documents: List[Document] = []
    combined_nodes: List[BaseNode] = []
    # Store files we couldn't determine type for (e.g., empty lists, or if LlamaIndex not installed)
    other_data_sources = []

    successfully_loaded_count = 0
    skipped_count = 0

    print("\n--- Starting Merge Process ---")
    for file_path in pickle_files:
        load_result = load_and_verify_pickle(file_path)

        if load_result is not None:
            loaded_data, detected_type = load_result
            successfully_loaded_count += 1

            if not loaded_data:  # Skip empty lists for categorization
                continue

            # Categorize based on detected type
            if LLAMAINDEX_INSTALLED:
                if detected_type == DOCUMENT_TYPE:
                    combined_documents.extend(loaded_data)
                elif detected_type == NODE_TYPE:
                    combined_nodes.extend(loaded_data)
                elif detected_type is None:  # Empty list case from verification
                    other_data_sources.append(file_path.name + " (empty)")
                elif detected_type == Any:  # Type check skipped case
                    print(
                        f"  -> WARNING: Type not verified for {file_path.name}. Adding to 'other' for review."
                    )
                    other_data_sources.append(file_path.name + " (type unchecked)")
                else:  # Should not happen
                    print(
                        f"  -> WARNING: Unknown type {detected_type} detected for {file_path.name}. Skipping merge."
                    )
                    other_data_sources.append(file_path.name + " (unknown type)")
            else:
                # If llama-index not installed, we can't separate. Add to 'other'.
                print(
                    f"  -> WARNING: Cannot determine type for {file_path.name} (llama-index not installed)."
                )
                other_data_sources.append(
                    file_path.name + " (type unknown - lib missing)"
                )

        else:
            # Loading or verification failed
            skipped_count += 1
            print(
                f"  -> Skipping file due to load/verification failure: {file_path.name}"
            )

    print("\n--- Merge Summary ---")
    print(f"Attempted to process {len(pickle_files)} files.")
    print(f"Successfully loaded and verified {successfully_loaded_count} files.")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} files due to errors.")
    if other_data_sources:
        print(
            "Sources for files with undetermined/unchecked types (not merged by type):"
        )
        for src in other_data_sources:
            print(f"  - {src}")

    # --- Save the combined lists ---
    output_base_path = Path(output_base_filename)

    save_merged_list(combined_documents, output_base_path, "documents")
    save_merged_list(combined_nodes, output_base_path, "nodes")

    if not combined_documents and not combined_nodes:
        print("\nNo valid Document or Node data found to save.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge multiple pickle files containing lists of LlamaIndex Documents and/or Nodes into separate outputs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        type=str,
        help="Input directory containing .pkl files (searches recursively).",
    )
    parser.add_argument(
        "-o",
        "--output_base_filename",
        required=True,
        type=str,
        help="Base path and filename for the merged output files. Suffixes '_documents.pkl' and '_nodes.pkl' will be added.",
    )

    args = parser.parse_args()

    # Basic check on output filename format
    if not args.output_base_filename.endswith(".pkl"):
        print(
            "Warning: Output base filename does not end with .pkl. Suffixes will be added anyway."
        )
        # Optionally, force .pkl or modify the suffix addition logic

    main(args.input_dir, args.output_base_filename)
