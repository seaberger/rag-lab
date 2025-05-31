import pickle
from llama_index.core import (
    Document,
)  # Import Document to help type hinting/checking if needed

# Load the parsed document from the pickle file
pickle_file = "test_parsed_doc.pkl"
try:
    with open(pickle_file, "rb") as f:
        # Explicitly state we expect a List of Document objects
        parsed_docs: list[Document] = pickle.load(f)
except FileNotFoundError:
    print(f"Error: Pickle file not found at {pickle_file}")
    exit()
except Exception as e:
    print(f"Error loading pickle file: {e}")
    exit()

# Inspect the structure of the parsed document list
if parsed_docs and isinstance(parsed_docs, list):
    print(f"Found {len(parsed_docs)} Document objects in the list.\n")

    # Iterate directly over the list of Document objects
    for i, doc in enumerate(parsed_docs, start=1):
        # Get the original filename from the metadata we added in parse.py
        file_name = doc.metadata.get("file_name", "Unknown File")
        doc_num = doc.metadata.get("doc_num", "?")  # Get the doc num within that file
        total_docs_in_file = doc.metadata.get(
            "total_docs_in_file", "?"
        )  # Get total for that file

        print(
            f"--- Document {i} (Section {doc_num}/{total_docs_in_file} from {file_name}) ---"
        )

        # Check if text exists and print length
        if hasattr(doc, "text") and doc.text is not None:
            print(f"Text Length: {len(doc.text)}")
            print("Content Preview (first 500 chars):")
            print(doc.text[:500] + ("..." if len(doc.text) > 500 else ""))
        else:
            print("Text Length: 0 or Text attribute missing!")
            print("Content Preview: N/A")

        print("\nMetadata:")
        # Print metadata nicely
        if hasattr(doc, "metadata") and doc.metadata:
            for key, value in doc.metadata.items():
                print(f"  - {key}: {value}")
        else:
            print("  Metadata missing or empty.")

        print("-" * 50 + "\n")

elif isinstance(parsed_docs, dict):
    print("Error: Loaded data is a dictionary. Expected a list.")
    print("Did you run the script using the *old* pickle file format?")
    print(
        "Please re-run parse.py with the refactored code to generate a list format pickle."
    )
else:
    print(
        f"No documents found or unexpected data type ({type(parsed_docs).__name__}) in the pickle file."
    )
