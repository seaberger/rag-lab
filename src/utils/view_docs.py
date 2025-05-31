import pickle
import argparse
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Dict

# Attempt to import Document, handle if llama_index is not installed
try:
    from llama_index.core import Document

    BaseNodeType = Document  # Use Document as the base type we expect
except ImportError:
    print(
        "Warning: llama_index.core not found. Assuming loaded objects have 'text' and 'metadata' attributes."
    )

    # Define a dummy class or use 'object' if llama_index is not critical for inspection itself
    class BasicNode:
        def __init__(self, text=None, metadata=None):
            self.text = text
            self.metadata = metadata

    BaseNodeType = BasicNode


def display_documents(
    parsed_docs: List[BaseNodeType],
    num_files_limit: int | None,
    num_sections_limit: int | None,
    show_full_view: bool,
):
    """Groups documents by file and displays them according to limits."""

    if not parsed_docs or not isinstance(parsed_docs, list):
        print(
            f"Input is not a valid list of documents (Type: {type(parsed_docs).__name__}). Cannot display."
        )
        return

    docs_by_file: Dict[str, List[BaseNodeType]] = defaultdict(list)
    for doc in parsed_docs:
        if not hasattr(doc, "metadata") or not isinstance(doc.metadata, dict):
            print(f"Warning: Skipping document without valid 'metadata' dictionary.")
            continue
        file_name = doc.metadata.get("file_name", "Unknown_File")
        docs_by_file[file_name].append(doc)

    total_files = len(docs_by_file)
    file_names_to_process = list(docs_by_file.keys())

    if num_files_limit is not None and num_files_limit < total_files:
        print(
            f"Limiting display to first {num_files_limit} out of {total_files} source files.\n"
        )
        file_names_to_process = file_names_to_process[:num_files_limit]
    else:
        print(f"Displaying details for all {total_files} source files found.\n")
        num_files_limit = total_files  # For accurate progress display

    global_doc_index = 0
    for file_idx, file_name in enumerate(file_names_to_process, start=1):
        sections_in_file = docs_by_file[file_name]
        total_sections_in_file = len(sections_in_file)

        sections_to_display = sections_in_file
        limit_msg = ""
        if (
            num_sections_limit is not None
            and num_sections_limit < total_sections_in_file
        ):
            sections_to_display = sections_in_file[:num_sections_limit]
            limit_msg = f" (showing first {num_sections_limit})"

        print(
            f"--- File {file_idx}/{num_files_limit}: {file_name} ({total_sections_in_file} sections total{limit_msg}) ---"
        )

        for section_idx, doc in enumerate(sections_to_display, start=1):
            global_doc_index += 1

            # Get metadata safely
            doc_num_md = doc.metadata.get("doc_num", "?")
            total_docs_md = doc.metadata.get("total_docs_in_file", "?")

            print(
                f"--- Document {global_doc_index} (Section {doc_num_md}/{total_docs_md} from {file_name}) ---"
            )

            # Display Text Content
            if hasattr(doc, "text") and doc.text is not None:
                text_content = doc.text
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

            # Display Metadata
            print("\nMetadata:")
            if hasattr(doc, "metadata") and doc.metadata:
                # Sort metadata keys for consistent display
                for key in sorted(doc.metadata.keys()):
                    value = doc.metadata[key]
                    print(f"  - {key}: {value}")
            else:
                print("  Metadata missing or empty.")

            print("-" * 50 + "\n")

        # Add extra newline between files for readability
        print("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect LlamaIndex Document objects stored in a pickle file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,  # Show defaults in help
    )

    parser.add_argument(
        "-f",
        "--file",
        type=Path,  # Use pathlib for better path handling
        default=Path("test_parsed_doc.pkl"),
        help="Path to the input pickle file containing a list of Document objects.",
    )
    parser.add_argument(
        "-nf",
        "--num-files",
        type=int,
        default=None,  # Default to showing all files
        help="Maximum number of source files to display sections from. Shows all if not specified.",
    )
    parser.add_argument(
        "-ns",
        "--num-sections",
        type=int,
        default=None,  # Default to showing all sections per file
        help="Maximum number of sections (Document objects) to display per source file. Shows all if not specified.",
    )
    parser.add_argument(
        "--full-view",
        action="store_true",  # Creates a boolean flag, True if present
        default=False,
        help="Display the full text content of each section instead of a preview.",
    )

    args = parser.parse_args()

    # --- File Loading ---
    pickle_file: Path = args.file
    if not pickle_file.is_file():
        print(f"Error: Pickle file not found at '{pickle_file}'")
        sys.exit(1)  # Exit with an error code

    print(f"Loading documents from: {pickle_file}...")
    try:
        with open(pickle_file, "rb") as f:
            # Load the data
            loaded_data = pickle.load(f)
    except Exception as e:
        print(f"Error loading pickle file: {e}")
        sys.exit(1)

    # --- Data Validation and Display ---
    # Check if the loaded data is a list (basic check)
    if isinstance(loaded_data, list):
        # Check if the list is not empty and items seem like documents (have metadata)
        if loaded_data and hasattr(loaded_data[0], "metadata"):
            print(f"Successfully loaded {len(loaded_data)} document objects.")
            display_documents(
                loaded_data, args.num_files, args.num_sections, args.full_view
            )
        elif not loaded_data:
            print("Pickle file loaded successfully, but the list is empty.")
        else:
            print(
                "Warning: Loaded a list, but items might not be Document objects (missing metadata attribute on first item)."
            )
            # Optionally, you could still try to display if items have 'text'
            # display_documents(loaded_data, args.num_files, args.num_sections, args.full_view)
    else:
        print(
            f"Error: Expected a list of documents in the pickle file, but found type '{type(loaded_data).__name__}'."
        )
        print(
            "Please ensure the pickle file was created correctly by the updated parse.py script."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
