#!/usr/bin/env python3
"""
Processes PDF documents using LlamaParse. Uses a user prompt to instruct
LlamaParse to include model/part number pairs in a 'Metadata' block within
the text. Runs parsing jobs in parallel, performs post-processing to extract
these pairs into the metadata field *if found and safe to do so*, adds
standardized metadata, and saves results as a list of LlamaIndex Document
objects in a pickle file.

Requires:
- LLAMA_CLOUD_API_KEY or OPENAI_API_KEY in environment variables.
- `pip install llama-cloud llama-index`

Usage:
    python parse.py --input_dir <dir>
    python parse.py --input_file <file>
    python parse.py --help for more options
"""

import os
import time
import argparse
import asyncio
import pickle
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
import ast
import re

# Make sure llama-cloud is installed and import LlamaParse
try:
    from llama_cloud_services import LlamaParse
except ImportError:
    raise ImportError(
        "llama_cloud_services not found. Please install with: pip install llama-cloud"
    )

from llama_index.core import Document

# Custom parsing prompt for technical documents (Same as baseline)
DATASHEET_PARSE_PROMPT = """# CRITICAL PARSING INSTRUCTIONS - FOLLOW EXACTLY

These documents contain technical information about laser power meters, laser energy meters, and laser beam diagnostics products.

When you are parsing a technical product datasheet, always:
1. Follow table formatting rules
2. Extract pairs of model names and part numbers

## TABLE FORMATTING RULES:

1. FILL ALL EMPTY CELLS: Every cell in specification tables must be filled. No cell should be empty.
   - When a value spans multiple columns, copy that value to each individual cell it applies to.
   - Example: If "0.19 to 12" appears once but applies to all models, it must be repeated in each model's column.

2. TABLE STRUCTURE: Include model names in the first row of each column above specifications.
   - Example: |Model|PM2|PM10|PM30|

3. PART NUMBERS:
   - Keep part numbers within specification tables
   - Remove any footnote symbols/superscripts from part numbers
   - Most part numbers have seven digits unless they start with 33 and include dashes

## EXAMPLES OF CORRECT TABLE FORMATTING:

INCORRECT (with empty cells):
|Wavelength Range (µm)| |0.19 to 12| | |
|Active Area Diameter (mm)|50| |25|10|

CORRECT (all cells filled):
|Wavelength Range (µm)|0.19 to 12|0.19 to 12|0.19 to 12|0.19 to 12|
|Active Area Diameter (mm)|50|50|25|10|

## PAIR EXTRACTION RULES:

4.  **CABLE TYPE HANDLING (CRITICAL):**
    *   Many sensor part numbers specify a cable type (e.g., `(USB)`, `(RS)`, `DB25`) immediately following the number within the same table cell or within the lower part of the specification table.
    *   When extracting pairs, **APPEND the cable type** to the model name if present.
    *   Use the format: `[Model Name] [Cable Type]` (e.g., "PM10 USB", "PM30 RS-232", "J-10MB-LE DB25").
    *   Common cable types to look for: USB, RS (treat as RS-232), DB25. Use the abbreviation found in the table cell (e.g., use "RS" if the table says "(RS)").
    *   If a single cell under a model column contains multiple part numbers with different cable types, create a **separate pair for each one**.
    *   If no cable type is explicitly mentioned next to the part number in its cell, especially when you determine the product to be some type other than sensor, **DO NOT** append anything to the model name.

## EXAMPLES OF CORRECT PAIR EXTRACTION (incorporating cable types):

Consider this table cell under the 'PM30' column: `1174257 (USB)² \\n 1174258 (RS)`

CORRECT PAIRS EXTRACTED:
('PM30 USB', '1174257')
('PM30 RS', '1174258')

Consider this cell under the 'PM10' column: `1174262 (USB)²`

CORRECT PAIR EXTRACTED:
('PM10 USB', '1174262')

Consider this cell under the 'PM2' column: `1174264` (no cable type mentioned)

CORRECT PAIR EXTRACTED:
('PM2', '1174264')


## FINAL OUTPUT FORMAT within the text:

Ensure the final output in the text strictly follows this format if pairs are found:

Metadata: {
    'pairs': [
        ('Sensor Model Name with Cable Type', 'PartNumber'),
        ('Another Sensor Model with Cable Type', 'AnotherPartNumber'),
        ('Meter Model Name', 'MeterPartNumber')
    ]
}
"""


# --- Parser Creation (Based on Baseline Success) ---
def create_parser() -> LlamaParse:
    """Create and configure the LlamaParse instance using user_prompt."""
    # Get API key from environment variable
    # Prefer LLAMA_CLOUD_API_KEY if available
    api_key = os.environ.get("LLAMA_CLOUD_API_KEY")
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")  # Fallback
        if not api_key:
            raise ValueError(
                "LLAMA_CLOUD_API_KEY or OPENAI_API_KEY environment variable must be set"
            )
        else:
            logging.info("Using OPENAI_API_KEY as fallback.")

    logging.info("Initializing LlamaParse with user_prompt...")
    # Use settings that worked in the baseline `parse_backup2.py`
    return LlamaParse(
        api_key=api_key,  # Explicitly pass key
        result_type="markdown",
        auto_mode=True,
        auto_mode_trigger_on_image_in_page=True,  # if using auto_mode
        auto_mode_trigger_on_table_in_page=True,  # if using auto_mode
        invalidate_cache=True,  # Keep for development
        do_not_cache=True,  # Keep for development
        verbose=True,  # Keep verbose logging
        user_prompt=DATASHEET_PARSE_PROMPT,
    )


# --- Post-processing Function (Final Robust Version) ---
# def postprocess_extract_pairs(doc: Document) -> Document:
#     """
#     Finds "Metadata: {'pairs': ...}" block using line-anchored regex, parses it,
#     adds to metadata, and conditionally removes the block using set_content
#     ONLY if the block doesn't constitute the entire text content.
#     Returns the modified document.
#     """
#     # Use ORIGINAL REGEX with ^ and $ anchors
#     metadata_pairs_regex = re.compile(
#         r"^\s*Metadata:\s*\{\s*['\"]pairs['\"]\s*:\s*(\[.*?\])\s*\}\s*$",  # Original ^...$
#         re.MULTILINE | re.DOTALL | re.IGNORECASE,
#     )

#     if not hasattr(doc, "metadata") or doc.metadata is None:
#         doc.metadata = {}

#     if hasattr(doc, "text") and doc.text and doc.text.strip():
#         original_text = doc.text
#         match = metadata_pairs_regex.search(original_text)

#         if match:
#             pairs_string = match.group(1)
#             matched_block = match.group(0)
#             logging.debug(
#                 f"Found potential pairs string snippet: {pairs_string[:100]}..."
#             )

#             try:
#                 extracted_pairs = ast.literal_eval(pairs_string)

#                 if isinstance(extracted_pairs, list):
#                     all_valid = True
#                     if not extracted_pairs:
#                         pass
#                     elif not all(
#                         isinstance(p, tuple)
#                         and len(p) == 2
#                         and isinstance(p[0], str)
#                         and isinstance(p[1], str)
#                         for p in extracted_pairs
#                     ):
#                         all_valid = False
#                         logging.warning(
#                             f"Extracted pairs format invalid for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Keeping block in text."
#                         )

#                     if all_valid:
#                         doc.metadata["pairs"] = extracted_pairs
#                         logging.info(
#                             f"Extracted {len(extracted_pairs)} pairs to metadata for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}"
#                         )

#                         # --- Conditional Removal Logic ---
#                         if matched_block.strip() == original_text.strip():
#                             logging.warning(
#                                 f"Metadata block is entire content for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Leaving block in text."
#                             )
#                         else:
#                             logging.debug(
#                                 f"Removing metadata block from text for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}"
#                             )
#                             new_text = metadata_pairs_regex.sub(
#                                 "", original_text
#                             ).strip()
#                             # Ensure set_content exists before calling
#                             if hasattr(doc, "set_content"):
#                                 doc.set_content(new_text)
#                             else:
#                                 logging.error(
#                                     "Document object missing 'set_content' method. Cannot remove metadata block from text."
#                                 )

#                 else:  # Not a list
#                     logging.warning(
#                         f"Extracted pairs structure not a list for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Keeping block in text."
#                     )

#             except (ValueError, SyntaxError) as e:  # ast parse error
#                 logging.warning(
#                     f"Could not parse pairs string for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}: {e}. Snippet: '{pairs_string[:100]}...'. Keeping block in text."
#                 )
#         # else: No metadata block found
#     # else: Document has no text or only whitespace
#     return doc


# --- Post-processing Function (Final Robust Version - Dictionary Format) ---
def postprocess_extract_pairs(doc: Document) -> Document:
    """
    Finds "Metadata: {'pairs': ...}" block using line-anchored regex, parses it,
    converts pairs to a list of dictionaries [{'model_name': ..., 'part_number': ...}],
    adds this list to metadata, and conditionally removes the block using set_content
    ONLY if the block doesn't constitute the entire text content.
    Returns the modified document.
    """
    # Use ORIGINAL REGEX with ^ and $ anchors
    metadata_pairs_regex = re.compile(
        r"^\s*Metadata:\s*\{\s*['\"]pairs['\"]\s*:\s*(\[.*?\])\s*\}\s*$",  # Original ^...$
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )

    # Ensure metadata dict exists if we need to add to it later
    if not hasattr(doc, "metadata") or doc.metadata is None:
        doc.metadata = {}

    # Check if text exists and is not empty/whitespace before proceeding
    if hasattr(doc, "text") and doc.text and doc.text.strip():
        original_text = doc.text
        match = metadata_pairs_regex.search(original_text)

        if match:
            pairs_string = match.group(1)  # The list part '[...]'
            matched_block = match.group(0)  # The entire matched block "Metadata: {...}"
            logging.debug(
                f"Found potential pairs string snippet: {pairs_string[:100]}..."
            )

            try:
                # Parse the string representation of the list of tuples
                raw_extracted_pairs = ast.literal_eval(pairs_string)

                # Validate the raw format first (must be a list)
                if isinstance(raw_extracted_pairs, list):
                    # --- Convert to List of Dictionaries ---
                    structured_pairs = []
                    all_tuples_valid = (
                        True  # Flag to track if all items had the correct tuple format
                    )

                    if not raw_extracted_pairs:  # Handle empty list case
                        pass  # Empty list is fine
                    else:
                        # Iterate through the parsed tuples
                        for p in raw_extracted_pairs:
                            # Validate each item as (str, str) tuple
                            if (
                                isinstance(p, tuple)
                                and len(p) == 2
                                and isinstance(p[0], str)
                                and isinstance(p[1], str)
                            ):
                                # Create dictionary for this pair
                                structured_pairs.append(
                                    {"model_name": p[0], "part_number": p[1]}
                                )
                            else:
                                # Encountered an invalid item in the list
                                all_tuples_valid = False
                                logging.warning(
                                    f"Invalid tuple format within pairs list for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Item: {p}. Keeping block in text."
                                )
                                break  # Stop processing this block if one tuple is bad
                    # --- End Conversion ---

                    # Proceed only if all original tuples were valid
                    if all_tuples_valid:
                        # Assign the list of dictionaries to metadata
                        doc.metadata["pairs"] = structured_pairs
                        logging.info(
                            f"Extracted {len(structured_pairs)} pairs to metadata (dict format) for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}"
                        )

                        # --- Conditional Removal Logic (remains the same) ---
                        # Compare stripped versions to see if block was the only non-whitespace content
                        if matched_block.strip() == original_text.strip():
                            logging.warning(
                                f"Metadata block is entire content for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Leaving block in text."
                            )
                            # DO NOT MODIFY TEXT in this case
                        else:
                            # Metadata block is part of larger text content, remove it safely
                            logging.debug(
                                f"Removing metadata block from text for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}"
                            )
                            # Use re.sub on the original text, then strip the result
                            new_text = metadata_pairs_regex.sub(
                                "", original_text
                            ).strip()
                            # Ensure set_content exists before calling
                            if hasattr(doc, "set_content"):
                                doc.set_content(new_text)
                            else:
                                logging.error(
                                    "Document object missing 'set_content' method. Cannot remove metadata block from text."
                                )

                    # else: all_tuples_valid was false, already logged warning, do nothing further to text

                else:  # Original structure wasn't a list
                    logging.warning(
                        f"Extracted pairs structure not a list for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Keeping block in text."
                    )

            except (ValueError, SyntaxError) as e:  # Error during ast.literal_eval
                logging.warning(
                    f"Could not parse pairs string for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}: {e}. Snippet: '{pairs_string[:100]}...'. Keeping block in text."
                )

        # else: No metadata block found in text, do nothing

    # else: Document has no text or only whitespace, do nothing

    return doc  # Return the document, potentially modified or not


# --- Parallel Processing Core (Re-enable post-processing call) ---
async def process_documents_parallel(
    file_list: List[Path],
    parser_template: LlamaParse,  # Pass the initialized template
    max_workers: int = 4,  # Using updated defaults
    max_retries: int = 3,
    timeout_seconds: int = 180,
) -> List[Document]:  # Return flat list
    """
    Process multiple documents in parallel using async.
    Returns a flat list of all processed Document objects.
    """
    all_processed_docs = []

    async def process_single_doc(fname: Path):
        # Re-initialize parser instance for each job for safety
        try:
            # Ensure re-initialization uses the same core settings (esp. user_prompt)
            parser = LlamaParse(
                api_key=parser_template.api_key,
                result_type=parser_template.result_type,
                auto_mode=parser_template.auto_mode,
                auto_mode_trigger_on_image_in_page=parser_template.auto_mode_trigger_on_image_in_page,
                auto_mode_trigger_on_table_in_page=parser_template.auto_mode_trigger_on_table_in_page,
                user_prompt=parser_template.user_prompt,
                invalidate_cache=parser_template.invalidate_cache,
                do_not_cache=parser_template.do_not_cache,
                verbose=parser_template.verbose,
                # Add other relevant params if needed (like auto_mode if reintroduced)
            )
        except Exception as init_e:
            logging.error(f"Failed to re-initialize parser for {fname.name}: {init_e}")
            return None

        for attempt in range(max_retries):
            try:
                logging.info(
                    f"Attempt {attempt + 1}/{max_retries} parsing {fname.name} (Timeout: {timeout_seconds}s)..."
                )
                start_time = time.time()
                # Use asyncio.wait_for for timeout control
                parsed_doc_list = await asyncio.wait_for(
                    parser.aload_data(str(fname)), timeout=timeout_seconds
                )
                elapsed = time.time() - start_time
                if (
                    parsed_doc_list
                    and isinstance(parsed_doc_list, list)
                    and len(parsed_doc_list) > 0
                ):
                    logging.info(
                        f"Successfully parsed {fname.name} into {len(parsed_doc_list)} sections in {elapsed:.2f} seconds."
                    )
                    return parsed_doc_list
                else:
                    logging.warning(
                        f"No content returned for {fname.name} on attempt {attempt + 1}"
                    )
            except asyncio.TimeoutError:
                logging.error(
                    f"Timeout error ({timeout_seconds}s) on attempt {attempt + 1} for {fname.name}"
                )
            except Exception as e:
                logging.error(
                    f"Error on attempt {attempt + 1} for {fname.name}: {str(e)}",
                    exc_info=True,
                )
            if attempt < max_retries - 1:
                backoff_time = 2**attempt
                logging.info(f"Retrying {fname.name} in {backoff_time} seconds...")
                await asyncio.sleep(backoff_time)
        logging.error(f"Failed to parse {fname.name} after {max_retries} attempts")
        return None

    semaphore = asyncio.Semaphore(max_workers)

    async def process_with_semaphore(fname):
        async with semaphore:
            return fname, await process_single_doc(fname)

    tasks = [process_with_semaphore(fname) for fname in file_list]
    results_list = await asyncio.gather(*tasks)

    # Process results: Combine all documents into a single list and apply post-processing
    for fname, doc_list_result in results_list:
        if doc_list_result:
            file_name = fname.name
            total_docs_in_file = len(doc_list_result)
            logging.info(
                f"Post-processing {total_docs_in_file} sections from {file_name}"
            )
            for i, doc in enumerate(doc_list_result, 1):
                # 1. Ensure metadata exists
                if not hasattr(doc, "metadata") or doc.metadata is None:
                    doc.metadata = {}
                # 2. Add standard metadata
                doc.metadata["source"] = str(fname.resolve())
                doc.metadata["file_name"] = file_name
                doc.metadata["doc_num"] = i
                doc.metadata["total_docs_in_file"] = total_docs_in_file

                # 3. --- RE-ENABLE POST-PROCESSING CALL ---
                processed_doc = postprocess_extract_pairs(doc)
                # ----------------------------------------

                all_processed_docs.append(processed_doc)
            logging.info(f"✅ Finished post-processing {file_name}")
        else:
            logging.warning(
                f"❌ {fname.name}: Failed to parse or returned empty result."
            )
    return all_processed_docs


# --- Saving Function (Unchanged) ---
def save_docs_to_pickle(docs: List[Document], file_path: str):
    """Save parsed documents to a pickle file."""
    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(output_path, "wb") as f:
            pickle.dump(docs, f)
        print(f"\nSaved {len(docs)} processed document sections to {output_path}")
    except Exception as e:
        print(f"Error saving documents to {output_path}: {e}")


# --- Main Execution Logic (Using refined structure) ---
async def main(
    input_dir: Optional[str],
    input_file: Optional[str],
    output_file: str,
    max_workers: int,
    timeout: int,
    max_retries: int = 3,  # Make retries consistent or add arg
):
    """
    Main async function to orchestrate the parsing process.
    """
    # Determine file list based on input args
    file_list: List[Path] = []
    if input_file:
        path = Path(input_file)
        if not path.is_file():
            raise FileNotFoundError(f"Input file {input_file} not found.")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file {input_file} is not a PDF.")
        file_list = [path]
        logging.info(f"Processing single input file: {path.resolve()}")
    elif input_dir:
        input_path = Path(input_dir)
        if not input_path.is_dir():
            raise FileNotFoundError(f"Input directory {input_dir} not found.")
        pdf_files = sorted(list(input_path.rglob("*.pdf")))
        if not pdf_files:
            print(f"No PDF files found in {input_dir} (recursive search).")
            return
        file_list = pdf_files
        logging.info(
            f"Found {len(pdf_files)} PDF files in {input_path.resolve()} (recursive search)."
        )
    else:
        raise ValueError("Missing input source: Specify --input_dir or --input_file.")

    # Create the parser template
    try:
        parser_template = create_parser()
    except Exception as e:
        logging.error(f"Failed to create LlamaParse instance: {e}", exc_info=True)
        return

    # Process documents in parallel
    start_run_time = time.time()
    logging.info(
        f"Starting parallel processing (Max Workers: {max_workers}, Timeout: {timeout}s)..."
    )
    processed_docs = await process_documents_parallel(
        file_list,
        parser_template,
        max_workers=max_workers,
        timeout_seconds=timeout,
        max_retries=max_retries,
    )
    end_run_time = time.time()

    # Print summary
    total_files_attempted = len(file_list)
    total_docs_generated = len(processed_docs)
    successful_files_sources = set()
    if processed_docs:
        successful_files_sources = set(
            doc.metadata.get("source")
            for doc in processed_docs
            if doc.metadata.get("source")
        )
    successful_files = len(successful_files_sources)
    failed_files = total_files_attempted - successful_files

    print(f"\n--- Run Summary ---")
    print(f"Output File: {output_file}")
    print(f"Attempted to process {total_files_attempted} input file(s).")
    print(f"Successfully parsed {successful_files} file(s).")
    if failed_files > 0:
        print(f"Failed to parse {failed_files} file(s) after retries.")
    print(f"Generated {total_docs_generated} total document sections.")
    print(f"Total processing time: {end_run_time - start_run_time:.2f} seconds.")

    # Save to pickle file
    if processed_docs:
        save_docs_to_pickle(processed_docs, output_file)
    else:
        print("\nNo documents were successfully processed or generated.")


if __name__ == "__main__":
    # Set up basic logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Load .env file if present (optional, for API keys)
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logging.info("Attempted to load .env file.")
    except ImportError:
        logging.info(
            ".env file handling skipped (dotenv not installed). Relying on environment variables."
        )

    # Argument Parsing (Using refined structure)
    parser = argparse.ArgumentParser(
        description="Parse PDF documents using LlamaParse, extract metadata pairs, and save results.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input_dir",
        "-i",
        type=str,
        help="Directory containing PDF files to parse (recursive).",
    )
    input_group.add_argument(
        "--input_file", type=str, help="Path to a single PDF file to parse."
    )
    parser.add_argument(
        "--output_file",
        "-o",
        type=str,
        default="parsed_docs.pkl",
        help="Path to save the processed documents list.",
    )
    parser.add_argument(
        "--max_workers",
        "-w",
        type=int,
        default=4,
        help="Maximum number of concurrent parsing workers.",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=180,
        help="Timeout in seconds for parsing each file.",
    )
    # Consider adding --max_retries if needed

    args = parser.parse_args()

    # Run the async main function
    try:
        asyncio.run(
            main(
                input_dir=args.input_dir,
                input_file=args.input_file,
                output_file=args.output_file,
                max_workers=args.max_workers,
                timeout=args.timeout,
            )
        )
    except (FileNotFoundError, ValueError) as e:
        logging.error(f"Execution failed due to file or value error: {e}")
        print(f"Error: {e}")
    except Exception as e:
        logging.error(
            f"An unexpected error occurred during execution: {e}", exc_info=True
        )
        print(f"An unexpected error occurred: {e}")
