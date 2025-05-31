# #!/usr/bin/env python3
# """
# Processes PDF and Markdown documents for ingestion into a RAG system.

# - PDFs: Parsed via LlamaParse using a custom prompt to extract text, tables,
#   and model/part number pairs. Post-processing moves pairs to metadata.
# - Markdown: Content is read directly.

# Adds standardized metadata to all documents and saves the combined results
# as a list of LlamaIndex Document objects in a pickle file.

# Requires:
# - LLAMA_CLOUD_API_KEY or OPENAI_API_KEY in environment variables (for PDF parsing).
# - `pip install llama-cloud llama-index python-dotenv` (dotenv is optional)

# Usage:
#     # Process all .pdf and .md/.markdown files in a directory
#     python md_pdf_parse.py --input_dir <dir> [--output <outfile.pkl>]

#     # Process a single .pdf or .md file
#     python md_pdf_parse.py --input_file <file.pdf_or_md> [--output <outfile.pkl>]

#     python md_pdf_parse.py --help for more options
# """

# import os
# import time
# import argparse
# import asyncio
# import pickle
# from pathlib import Path
# from typing import Dict, List, Any, Optional
# import logging
# import ast
# import re

# # Make sure llama-cloud is installed and import LlamaParse
# # Make it optional so the script can run for Markdown only
# try:
#     from llama_cloud_services import LlamaParse

#     LLAMA_PARSE_INSTALLED = True
# except ImportError:
#     LlamaParse = None  # Define as None if not installed
#     LLAMA_PARSE_INSTALLED = False
#     logging.warning("llama_cloud_services not found. PDF parsing will be disabled.")

# # Make sure llama-index is installed
# try:
#     from llama_index.core import Document
# except ImportError:
#     raise ImportError(
#         "llama-index-core not found. Please install with: pip install llama-index-core"
#     )


# # Custom parsing prompt for technical documents (Same as baseline)
# DATASHEET_PARSE_PROMPT = """# CRITICAL PARSING INSTRUCTIONS - FOLLOW EXACTLY

# These documents contain technical information about laser power meters, laser energy meters, and laser beam diagnostics products.

# When you are parsing a technical product datasheet, always:
# 1. Follow table formatting rules
# 2. Extract pairs of model names and part numbers

# ## TABLE FORMATTING RULES:

# 1. FILL ALL EMPTY CELLS: Every cell in specification tables must be filled. No cell should be empty.
#    - When a value spans multiple columns, copy that value to each individual cell it applies to.
#    - Example: If "0.19 to 12" appears once but applies to all models, it must be repeated in each model's column.

# 2. TABLE STRUCTURE: Include model names in the first row of each column above specifications.
#    - Example: |Model|PM2|PM10|PM30|

# 3. PART NUMBERS:
#    - Keep part numbers within specification tables
#    - Remove any footnote symbols/superscripts from part numbers
#    - Most part numbers have seven digits unless they start with 33 and include dashes

# ## EXAMPLES OF CORRECT TABLE FORMATTING:

# INCORRECT (with empty cells):
# |Wavelength Range (µm)| |0.19 to 12| | |
# |Active Area Diameter (mm)|50| |25|10|

# CORRECT (all cells filled):
# |Wavelength Range (µm)|0.19 to 12|0.19 to 12|0.19 to 12|0.19 to 12|
# |Active Area Diameter (mm)|50|50|25|10|

# ## PAIR EXTRACTION RULES:

# 4.  **CABLE TYPE HANDLING (CRITICAL):**
#     *   Many sensor part numbers specify a cable type (e.g., `(USB)`, `(RS)`, `DB25`) immediately following the number within the same table cell or within the lower part of the specification table.
#     *   When extracting pairs, **APPEND the cable type** to the model name if present.
#     *   Use the format: `[Model Name] [Cable Type]` (e.g., "PM10 USB", "PM30 RS-232", "J-10MB-LE DB25").
#     *   Common cable types to look for: USB, RS (treat as RS-232), DB25. Use the abbreviation found in the table cell (e.g., use "RS" if the table says "(RS)").
#     *   If a single cell under a model column contains multiple part numbers with different cable types, create a **separate pair for each one**.
#     *   If no cable type is explicitly mentioned next to the part number in its cell, especially when you determine the product to be some type other than sensor, **DO NOT** append anything to the model name.

# ## EXAMPLES OF CORRECT PAIR EXTRACTION (incorporating cable types):

# Consider this table cell under the 'PM30' column: `1174257 (USB)² \\n 1174258 (RS)`

# CORRECT PAIRS EXTRACTED:
# ('PM30 USB', '1174257')
# ('PM30 RS', '1174258')

# Consider this cell under the 'PM10' column: `1174262 (USB)²`

# CORRECT PAIR EXTRACTED:
# ('PM10 USB', '1174262')

# Consider this cell under the 'PM2' column: `1174264` (no cable type mentioned)

# CORRECT PAIR EXTRACTED:
# ('PM2', '1174264')


# ## FINAL OUTPUT FORMAT within the text:

# Ensure the final output in the text strictly follows this format if pairs are found:

# Metadata: {
#     'pairs': [
#         ('Sensor Model Name with Cable Type', 'PartNumber'),
#         ('Another Sensor Model with Cable Type', 'AnotherPartNumber'),
#         ('Meter Model Name', 'MeterPartNumber')
#     ]
# }
# """


# # --- Parser Creation (Returns Optional Parser) ---
# def create_parser() -> Optional[LlamaParse]:
#     """Create and configure the LlamaParse instance using user_prompt and auto_mode."""
#     if not LLAMA_PARSE_INSTALLED:
#         logging.warning("LlamaParse library not installed. PDF parsing disabled.")
#         return None

#     # Get API key from environment variable
#     api_key = os.environ.get("LLAMA_CLOUD_API_KEY")
#     if not api_key:
#         api_key = os.environ.get("OPENAI_API_KEY")
#         if not api_key:
#             logging.warning(
#                 "API key (LLAMA_CLOUD_API_KEY or OPENAI_API_KEY) not found. PDF parsing disabled."
#             )
#             return None
#         else:
#             logging.info("Using OPENAI_API_KEY as fallback for LlamaParse.")

#     logging.info("Initializing LlamaParse with user_prompt and auto_mode=True...")
#     try:
#         return LlamaParse(
#             api_key=api_key,
#             result_type="markdown",
#             auto_mode=True,
#             auto_mode_trigger_on_image_in_page=True,
#             auto_mode_trigger_on_table_in_page=True,
#             invalidate_cache=True,
#             do_not_cache=True,
#             verbose=True,
#             user_prompt=DATASHEET_PARSE_PROMPT,
#         )
#     except Exception as e:
#         logging.error(f"Failed to initialize LlamaParse instance: {e}")
#         return None


# # --- Post-processing Function (Dictionary Format - only applied to PDF docs) ---
# def postprocess_extract_pairs(doc: Document) -> Document:
#     """
#     Finds "Metadata: {'pairs': ...}" block using line-anchored regex, parses it,
#     converts pairs to a list of dictionaries [{'model_name': ..., 'part_number': ...}],
#     adds this list to metadata, and conditionally removes the block using set_content
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
#                 raw_extracted_pairs = ast.literal_eval(pairs_string)
#                 if isinstance(raw_extracted_pairs, list):
#                     structured_pairs = []
#                     all_tuples_valid = True
#                     if not raw_extracted_pairs:
#                         pass
#                     else:
#                         for p in raw_extracted_pairs:
#                             if (
#                                 isinstance(p, tuple)
#                                 and len(p) == 2
#                                 and isinstance(p[0], str)
#                                 and isinstance(p[1], str)
#                             ):
#                                 structured_pairs.append(
#                                     {"model_name": p[0], "part_number": p[1]}
#                                 )
#                             else:
#                                 all_tuples_valid = False
#                                 logging.warning(
#                                     f"Invalid tuple format within pairs list for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Item: {p}. Keeping block in text."
#                                 )
#                                 break
#                     if all_tuples_valid:
#                         doc.metadata["pairs"] = structured_pairs
#                         logging.info(
#                             f"Extracted {len(structured_pairs)} pairs to metadata (dict format) for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}"
#                         )
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
#                             if hasattr(doc, "set_content"):
#                                 doc.set_content(new_text)
#                             else:
#                                 logging.error(
#                                     "Document object missing 'set_content' method. Cannot remove metadata block from text."
#                                 )
#                 else:
#                     logging.warning(
#                         f"Extracted pairs structure not a list for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Keeping block in text."
#                     )
#             except (ValueError, SyntaxError) as e:
#                 logging.warning(
#                     f"Could not parse pairs string for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}: {e}. Snippet: '{pairs_string[:100]}...'. Keeping block in text."
#                 )
#     return doc


# # --- Parallel Processing Core (Only for PDFs) ---
# async def process_pdf_documents_parallel(  # Renamed for clarity
#     pdf_file_list: List[Path],
#     parser_template: LlamaParse,
#     max_workers: int = 4,
#     max_retries: int = 3,
#     timeout_seconds: int = 180,
# ) -> List[Document]:
#     """
#     Process PDF documents in parallel using LlamaParse.
#     Applies post-processing to extract pairs metadata.
#     Returns a flat list of processed Document objects (sections from all PDFs).
#     """
#     all_processed_pdf_docs = []  # Collect processed PDF docs here

#     async def process_single_pdf(fname: Path):
#         # Re-initialize parser instance
#         try:
#             parser = LlamaParse(
#                 api_key=parser_template.api_key,
#                 result_type=parser_template.result_type,
#                 auto_mode=parser_template.auto_mode,
#                 auto_mode_trigger_on_image_in_page=parser_template.auto_mode_trigger_on_image_in_page,
#                 auto_mode_trigger_on_table_in_page=parser_template.auto_mode_trigger_on_table_in_page,
#                 user_prompt=parser_template.user_prompt,
#                 invalidate_cache=parser_template.invalidate_cache,
#                 do_not_cache=parser_template.do_not_cache,
#                 verbose=parser_template.verbose,
#             )
#         except Exception as init_e:
#             logging.error(
#                 f"Failed to re-initialize parser for PDF {fname.name}: {init_e}"
#             )
#             return None

#         for attempt in range(max_retries):
#             try:
#                 logging.info(
#                     f"Attempt {attempt + 1}/{max_retries} parsing PDF {fname.name} (Timeout: {timeout_seconds}s)..."
#                 )
#                 start_time = time.time()
#                 parsed_doc_list = await asyncio.wait_for(
#                     parser.aload_data(str(fname)), timeout=timeout_seconds
#                 )
#                 elapsed = time.time() - start_time
#                 if (
#                     parsed_doc_list
#                     and isinstance(parsed_doc_list, list)
#                     and len(parsed_doc_list) > 0
#                 ):
#                     logging.info(
#                         f"Successfully parsed PDF {fname.name} into {len(parsed_doc_list)} sections in {elapsed:.2f} seconds."
#                     )
#                     return parsed_doc_list  # Return list of document sections
#                 else:
#                     logging.warning(
#                         f"No content returned for PDF {fname.name} on attempt {attempt + 1}"
#                     )
#             except asyncio.TimeoutError:
#                 logging.error(
#                     f"Timeout error ({timeout_seconds}s) on attempt {attempt + 1} for PDF {fname.name}"
#                 )
#             except Exception as e:
#                 logging.error(
#                     f"Error on attempt {attempt + 1} for PDF {fname.name}: {str(e)}",
#                     exc_info=True,
#                 )
#             if attempt < max_retries - 1:
#                 backoff_time = 2**attempt
#                 logging.info(f"Retrying {fname.name} in {backoff_time} seconds...")
#                 await asyncio.sleep(backoff_time)
#         logging.error(f"Failed to parse PDF {fname.name} after {max_retries} attempts")
#         return None  # Return None on failure

#     semaphore = asyncio.Semaphore(max_workers)

#     async def process_with_semaphore(fname):
#         async with semaphore:
#             # Returns list of docs or None
#             return fname, await process_single_pdf(fname)

#     tasks = [process_with_semaphore(fname) for fname in pdf_file_list]
#     results_list = await asyncio.gather(*tasks)

#     # Process results: Add metadata and apply post-processing for pairs
#     for fname, doc_list_result in results_list:
#         if doc_list_result:
#             file_name = fname.name
#             total_docs_in_file = len(doc_list_result)
#             logging.info(
#                 f"Post-processing {total_docs_in_file} sections from PDF {file_name}"
#             )
#             for i, doc in enumerate(doc_list_result, 1):
#                 # 1. Ensure metadata exists
#                 if not hasattr(doc, "metadata") or doc.metadata is None:
#                     doc.metadata = {}
#                 # 2. Add standard metadata
#                 doc.metadata["source"] = str(fname.resolve())
#                 doc.metadata["file_name"] = file_name
#                 doc.metadata["doc_num"] = i
#                 doc.metadata["total_docs_in_file"] = total_docs_in_file

#                 # 3. --- APPLY POST-PROCESSING for pairs ---
#                 processed_doc = postprocess_extract_pairs(doc)
#                 # ----------------------------------------

#                 all_processed_pdf_docs.append(processed_doc)
#             logging.info(f"✅ Finished post-processing PDF {file_name}")
#         else:
#             logging.warning(
#                 f"❌ PDF {fname.name}: Failed to parse or returned empty result."
#             )

#     return all_processed_pdf_docs


# # --- NEW Function to process Markdown files ---
# def process_markdown_file(file_path: Path) -> List[Document]:
#     """Reads a Markdown file and returns it as a single Document object."""
#     logging.info(f"Processing Markdown file: {file_path.name}")
#     try:
#         # Determine encoding, try common ones
#         encodings_to_try = ["utf-8", "latin-1", "cp1252"]
#         content = None
#         for enc in encodings_to_try:
#             try:
#                 with open(file_path, "r", encoding=enc) as f:
#                     content = f.read()
#                 logging.debug(f"Successfully read {file_path.name} with encoding {enc}")
#                 break  # Stop trying encodings once successful
#             except UnicodeDecodeError:
#                 logging.debug(f"Failed to read {file_path.name} with encoding {enc}")
#                 continue  # Try next encoding
#             except Exception as e_read:  # Catch other potential file read errors
#                 logging.error(
#                     f"Error reading {file_path.name} even after trying encodings: {e_read}"
#                 )
#                 return []  # Return empty if read fails completely

#         if content is None:
#             logging.error(
#                 f"Could not decode Markdown file {file_path.name} with any attempted encoding."
#             )
#             return []

#         if not content.strip():
#             logging.warning(
#                 f"Markdown file {file_path.name} is empty or contains only whitespace."
#             )
#             # Still return a document object, but maybe log it specially downstream
#             # Or decide to return [] based on requirements
#             # Let's return it for now, downstream can filter empty nodes if needed
#             pass

#         # Create a single Document object for the whole file
#         # LlamaIndex Document expects text content
#         doc = Document(text=content if content else "")  # Ensure text is not None

#         # Add standard metadata
#         doc.metadata = {
#             "source": str(file_path.resolve()),
#             "file_name": file_path.name,
#             "doc_num": 1,  # Markdown files are treated as a single document section
#             "total_docs_in_file": 1,
#             # Add 'pairs': [] explicitly for consistency downstream? Optional.
#             # 'pairs': []
#         }
#         logging.info(f"✅ Successfully processed Markdown file {file_path.name}")
#         return [doc]  # Return as a list containing one document
#     except Exception as e:
#         logging.error(
#             f"❌ Error processing Markdown file {file_path.name}: {e}", exc_info=True
#         )
#         return []


# # --- Saving Function remains the same ---
# def save_docs_to_pickle(docs: List[Document], file_path: str):
#     """Save parsed documents to a pickle file."""
#     output_path = Path(file_path)
#     output_path.parent.mkdir(parents=True, exist_ok=True)
#     try:
#         with open(output_path, "wb") as f:
#             pickle.dump(docs, f)
#         print(f"\nSaved {len(docs)} processed document sections to {output_path}")
#     except Exception as e:
#         print(f"Error saving documents to {output_path}: {e}")


# # --- Main Execution Logic (Handles both PDF and MD) ---
# async def main(
#     input_dir: Optional[str],
#     input_file: Optional[str],
#     output_file: str,
#     max_workers: int,
#     timeout: int,
#     max_retries: int = 3,
# ):
#     """
#     Main async function to orchestrate the parsing of PDF and Markdown files.
#     """
#     all_docs = []  # Combined list for results from all file types
#     pdf_files_to_process = []
#     md_files_to_process = []

#     # --- Determine file list ---
#     if input_file:
#         path = Path(input_file)
#         if not path.is_file():
#             raise FileNotFoundError(f"Input file {input_file} not found.")
#         suffix = path.suffix.lower()
#         if suffix == ".pdf":
#             pdf_files_to_process = [path]
#         elif suffix in [".md", ".markdown"]:
#             md_files_to_process = [path]
#         else:
#             raise ValueError(
#                 f"Input file {input_file} is not a supported type (.pdf, .md, .markdown)."
#             )
#         logging.info(f"Processing single input file: {path.resolve()}")
#     elif input_dir:
#         input_path = Path(input_dir)
#         if not input_path.is_dir():
#             raise FileNotFoundError(f"Input directory {input_dir} not found.")
#         pdf_files_to_process = sorted(list(input_path.rglob("*.pdf")))
#         md_files_to_process = sorted(list(input_path.rglob("*.md")))
#         md_files_to_process.extend(
#             sorted(list(input_path.rglob("*.markdown")))
#         )  # Also check .markdown
#         if not pdf_files_to_process and not md_files_to_process:
#             print(f"No PDF or Markdown files found in {input_dir} (recursive search).")
#             return
#         logging.info(
#             f"Found {len(pdf_files_to_process)} PDF files and {len(md_files_to_process)} Markdown files in {input_path.resolve()}."
#         )
#     else:
#         raise ValueError("Missing input source: Specify --input_dir or --input_file.")

#     # --- Process Markdown Files Directly (Synchronous) ---
#     if md_files_to_process:
#         logging.info(f"\n--- Processing {len(md_files_to_process)} Markdown files ---")
#         for md_file in md_files_to_process:
#             processed_md_docs = process_markdown_file(md_file)
#             all_docs.extend(processed_md_docs)  # Add results to the main list

#     # --- Process PDF Files using LlamaParse (Asynchronous) ---
#     processed_pdf_docs = []  # Store PDF results separately first
#     if pdf_files_to_process:
#         logging.info(f"\n--- Processing {len(pdf_files_to_process)} PDF files ---")
#         parser_template = create_parser()  # Attempt to create parser
#         if parser_template:  # Check if parser could be initialized
#             start_pdf_time = time.time()
#             logging.info(
#                 f"Starting PDF parallel processing (Max Workers: {max_workers}, Timeout: {timeout}s)..."
#             )
#             # Use the renamed function for clarity
#             processed_pdf_docs = await process_pdf_documents_parallel(
#                 pdf_files_to_process,
#                 parser_template,
#                 max_workers=max_workers,
#                 timeout_seconds=timeout,
#                 max_retries=max_retries,
#             )
#             end_pdf_time = time.time()
#             logging.info(
#                 f"Finished PDF processing in {end_pdf_time - start_pdf_time:.2f} seconds."
#             )
#             all_docs.extend(processed_pdf_docs)  # Add PDF results to the main list
#         else:
#             logging.warning(
#                 "PDF processing skipped because LlamaParse parser could not be initialized (check API key and installation)."
#             )

#     # --- Final Summary and Saving ---
#     total_files_attempted = len(pdf_files_to_process) + len(md_files_to_process)
#     # Count successful files by checking the final combined list
#     successful_md_files = sum(
#         1
#         for doc in all_docs
#         if doc.metadata.get("file_name", "").lower().endswith((".md", ".markdown"))
#     )
#     successful_pdf_files = sum(
#         1
#         for doc in all_docs
#         if doc.metadata.get("file_name", "").lower().endswith(".pdf")
#     )
#     # Note: Failed PDFs won't be in all_docs, count failures based on initial list vs successful
#     failed_pdf_files = len(pdf_files_to_process) - successful_pdf_files
#     # Failed MD files are harder to track precisely here unless process_markdown_file returns None/signals failure

#     print(f"\n--- Run Summary ---")
#     print(f"Output File: {output_file}")
#     print(
#         f"Attempted {len(md_files_to_process)} Markdown files, successfully processed {successful_md_files}."
#     )
#     print(f"Attempted {len(pdf_files_to_process)} PDF files.")
#     if (
#         LLAMA_PARSE_INSTALLED and pdf_files_to_process
#     ):  # Only mention PDF specifics if attempted
#         print(f"Successfully parsed and processed {successful_pdf_files} PDF file(s).")
#         if failed_pdf_files > 0:
#             print(f"Failed to parse {failed_pdf_files} PDF file(s) after retries.")
#     elif pdf_files_to_process:
#         print("PDF processing was skipped (LlamaParse not initialized).")
#     print(f"Generated {len(all_docs)} total document sections.")

#     # Save combined list to pickle file
#     if all_docs:
#         save_docs_to_pickle(all_docs, output_file)
#     else:
#         print("\nNo documents were successfully processed or generated.")


# # --- __main__ block ---
# # --- __main__ block ---
# if __name__ == "__main__":
#     # Setup logging
#     logging.basicConfig(
#         level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
#     )

#     # Load .env file if present
#     try:
#         from dotenv import load_dotenv

#         # --- CHANGE HERE: Remove find_dotenv=True ---
#         if load_dotenv():  # Call without arguments
#             logging.info("Loaded environment variables from .env file.")
#         else:
#             logging.info("No .env file found or failed to load.")
#         # --- End Change ---
#     except ImportError:
#         logging.info(
#             ".env file handling skipped (python-dotenv not installed). Relying on environment variables."
#         )
#     except Exception as e_dotenv:  # Catch potential errors during load_dotenv itself
#         logging.warning(f"Error occurred during load_dotenv: {e_dotenv}")

#     # Argument Parsing (remains the same)
#     parser = argparse.ArgumentParser(
#         description="Parse PDF (via LlamaParse) and Markdown files, extract metadata pairs from PDFs, and save results.",
#         formatter_class=argparse.ArgumentDefaultsHelpFormatter,
#     )
#     input_group = parser.add_mutually_exclusive_group(required=True)
#     input_group.add_argument(
#         "--input_dir",
#         "-i",
#         type=str,
#         help="Directory containing PDF and/or Markdown files (recursive).",
#     )
#     input_group.add_argument(
#         "--input_file", type=str, help="Path to a single PDF or Markdown file."
#     )
#     parser.add_argument(
#         "--output_file",
#         "-o",
#         type=str,
#         default="parsed_docs.pkl",
#         help="Path to save the processed LlamaIndex Document objects list.",
#     )
#     parser.add_argument(
#         "--max_workers",
#         "-w",
#         type=int,
#         default=4,
#         help="Maximum number of concurrent PDF parsing workers.",
#     )
#     parser.add_argument(
#         "--timeout",
#         "-t",
#         type=int,
#         default=180,
#         help="Timeout in seconds for parsing each PDF file.",
#     )

#     args = parser.parse_args()

#     # Run the async main function (remains the same)
#     try:
#         asyncio.run(
#             main(
#                 input_dir=args.input_dir,
#                 input_file=args.input_file,
#                 output_file=args.output_file,
#                 max_workers=args.max_workers,
#                 timeout=args.timeout,
#             )
#         )
#     # Error handling remains the same
#     except (FileNotFoundError, ValueError) as e:
#         logging.error(f"Execution failed due to file or value error: {e}")
#         print(f"Error: {e}")
#     except ImportError as e:
#         logging.error(f"Execution failed due to missing library: {e}")
#         print(f"Error: Missing required library - {e}")
#     except Exception as e:
#         logging.error(
#             f"An unexpected error occurred during execution: {e}", exc_info=True
#         )
#         print(f"An unexpected error occurred: {e}")
#!/usr/bin/env python3
"""
Processes PDF and Markdown documents for ingestion into a RAG system.

- PDFs: Parsed via LlamaParse. By default, uses a custom prompt for datasheets
  to extract text, tables, and model/part number pairs, with post-processing
  to move pairs to metadata. This custom handling can be disabled via a flag
  for general PDF documents (e.g., manuals).
- Markdown: Content is read directly.

Adds standardized metadata to all documents and saves the combined results
as a list of LlamaIndex Document objects in a pickle file.

Requires:
- LLAMA_CLOUD_API_KEY or OPENAI_API_KEY in environment variables (for PDF parsing).
- `pip install llama-cloud llama-index-core python-dotenv` (dotenv is optional)

Usage:
    # Process PDF datasheets and MD files (default, custom prompt + pair extraction)
    python parse_pdf_md.py --input_dir <dir>

    # Process general PDFs (like manuals) and MD files (disable custom prompt/pairs)
    python parse_pdf_md.py --input_dir <dir> --disable-pair-extraction

    # Process a single file (auto-detects PDF/MD)
    python parse_pdf_md.py --input_file <file.pdf_or_md> [--disable-pair-extraction]

    python parse_pdf_md.py --help for more options
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

# Optional LlamaParse import
try:
    from llama_cloud_services import LlamaParse

    LLAMA_PARSE_INSTALLED = True
except ImportError:
    LlamaParse = None  # Define as None if not installed
    LLAMA_PARSE_INSTALLED = False
    logging.warning("llama_cloud_services not found. PDF parsing will be disabled.")

# Required LlamaIndex import
try:
    from llama_index.core import Document
except ImportError:
    raise ImportError(
        "llama-index-core not found. Please install with: pip install llama-index-core"
    )


# Custom parsing prompt (only used if --disable-pair-extraction is NOT set)
# --- FULL PROMPT INCLUDED HERE ---
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
# --- END OF FULL PROMPT ---


# --- Parser Creation (Now conditional based on flag) ---
def create_parser(disable_pair_extraction: bool) -> Optional[LlamaParse]:
    """
    Create and configure the LlamaParse instance.
    Optionally skips the custom user_prompt if disable_pair_extraction is True.
    """
    if not LLAMA_PARSE_INSTALLED:
        logging.warning("LlamaParse library not installed. PDF parsing disabled.")
        return None

    api_key = os.environ.get("LLAMA_CLOUD_API_KEY")
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logging.warning(
                "API key (LLAMA_CLOUD_API_KEY or OPENAI_API_KEY) not found. PDF parsing disabled."
            )
            return None
        else:
            logging.info("Using OPENAI_API_KEY as fallback for LlamaParse.")

    # --- Core LlamaParse arguments ---
    init_args = {
        "api_key": api_key,
        "result_type": "markdown",
        "auto_mode": True,  # Keep auto_mode generally useful
        "auto_mode_trigger_on_image_in_page": True,
        "auto_mode_trigger_on_table_in_page": True,
        "invalidate_cache": True,
        "do_not_cache": True,
        "verbose": True,
    }

    # --- Conditionally add user_prompt ---
    if not disable_pair_extraction:
        logging.info("Initializing LlamaParse WITH custom datasheet prompt...")
        init_args["user_prompt"] = DATASHEET_PARSE_PROMPT
    else:
        logging.info(
            "Initializing LlamaParse WITHOUT custom datasheet prompt (using default behavior)..."
        )
        # Do not add 'user_prompt' key to init_args

    try:
        parser = LlamaParse(**init_args)
        # Store the flag setting within the template object for worker reference
        # Use a non-standard attribute name to avoid potential conflicts
        parser._internal_disable_pair_extraction = disable_pair_extraction
        return parser
    except Exception as e:
        logging.error(f"Failed to initialize LlamaParse instance: {e}")
        return None


# --- Post-processing Function (remains the same, but called conditionally) ---
def postprocess_extract_pairs(doc: Document) -> Document:
    """
    Finds "Metadata: {'pairs': ...}" block using line-anchored regex, parses it,
    converts pairs to a list of dictionaries [{'model_name': ..., 'part_number': ...}],
    adds this list to metadata, and conditionally removes the block using set_content
    ONLY if the block doesn't constitute the entire text content.
    Returns the modified document.
    """
    metadata_pairs_regex = re.compile(
        r"^\s*Metadata:\s*\{\s*['\"]pairs['\"]\s*:\s*(\[.*?\])\s*\}\s*$",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not hasattr(doc, "metadata") or doc.metadata is None:
        doc.metadata = {}
    if hasattr(doc, "text") and doc.text and doc.text.strip():
        original_text = doc.text
        match = metadata_pairs_regex.search(original_text)
        if match:
            pairs_string = match.group(1)
            matched_block = match.group(0)
            logging.debug(
                f"Found potential pairs string snippet: {pairs_string[:100]}..."
            )
            try:
                raw_extracted_pairs = ast.literal_eval(pairs_string)
                if isinstance(raw_extracted_pairs, list):
                    structured_pairs = []
                    all_tuples_valid = True
                    if not raw_extracted_pairs:
                        pass
                    else:
                        for p in raw_extracted_pairs:
                            if (
                                isinstance(p, tuple)
                                and len(p) == 2
                                and isinstance(p[0], str)
                                and isinstance(p[1], str)
                            ):
                                structured_pairs.append(
                                    {"model_name": p[0], "part_number": p[1]}
                                )
                            else:
                                all_tuples_valid = False
                                logging.warning(
                                    f"Invalid tuple format within pairs list for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Item: {p}. Keeping block in text."
                                )
                                break
                    if all_tuples_valid:
                        doc.metadata["pairs"] = structured_pairs
                        logging.info(
                            f"Extracted {len(structured_pairs)} pairs to metadata (dict format) for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}"
                        )
                        if matched_block.strip() == original_text.strip():
                            logging.warning(
                                f"Metadata block is entire content for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Leaving block in text."
                            )
                        else:
                            logging.debug(
                                f"Removing metadata block from text for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}"
                            )
                            new_text = metadata_pairs_regex.sub(
                                "", original_text
                            ).strip()
                            if hasattr(doc, "set_content"):
                                doc.set_content(new_text)
                            else:
                                logging.error(
                                    "Document object missing 'set_content' method."
                                )
                else:
                    logging.warning(
                        f"Extracted pairs structure not a list for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}. Keeping block in text."
                    )
            except (ValueError, SyntaxError) as e:
                logging.warning(
                    f"Could not parse pairs string for doc {doc.metadata.get('file_name', '?')} sec {doc.metadata.get('doc_num', '?')}: {e}. Snippet: '{pairs_string[:100]}...'. Keeping block in text."
                )
    return doc


# --- Parallel Processing Core (Conditional prompt in worker, conditional post-processing) ---
async def process_pdf_documents_parallel(
    pdf_file_list: List[Path],
    parser_template: LlamaParse,  # Template created by create_parser
    max_workers: int = 4,
    max_retries: int = 3,
    timeout_seconds: int = 180,
) -> List[Document]:
    """
    Process PDF documents in parallel using LlamaParse.
    Applies post-processing ONLY if the parser template was created with the custom prompt.
    Returns a flat list of processed Document objects.
    """
    all_processed_pdf_docs = []
    # Retrieve the setting from the template using the internal attribute name
    disable_pair_extraction = getattr(
        parser_template, "_internal_disable_pair_extraction", True
    )  # Default to disabled if attribute missing

    async def process_single_pdf(fname: Path):
        # Define arguments for re-initialization
        worker_init_args = {
            "api_key": parser_template.api_key,
            "result_type": parser_template.result_type,
            "auto_mode": parser_template.auto_mode,
            "auto_mode_trigger_on_image_in_page": getattr(
                parser_template, "auto_mode_trigger_on_image_in_page", False
            ),  # Use getattr for safety
            "auto_mode_trigger_on_table_in_page": getattr(
                parser_template, "auto_mode_trigger_on_table_in_page", False
            ),
            "invalidate_cache": parser_template.invalidate_cache,
            "do_not_cache": parser_template.do_not_cache,
            "verbose": parser_template.verbose,
        }
        # Conditionally add user_prompt based on template setting
        if not disable_pair_extraction:
            # Check if user_prompt actually exists on template before accessing
            if hasattr(parser_template, "user_prompt") and parser_template.user_prompt:
                worker_init_args["user_prompt"] = parser_template.user_prompt
            else:
                # This case should ideally not happen if disable_pair_extraction is False, but good to handle
                logging.warning(
                    f"Pair extraction enabled but user_prompt missing on template for {fname.name}. Proceeding without custom prompt."
                )

        try:
            parser = LlamaParse(**worker_init_args)
        except Exception as init_e:
            logging.error(
                f"Failed to re-initialize worker parser for PDF {fname.name}: {init_e}"
            )
            return None

        # Parsing Loop
        for attempt in range(max_retries):
            try:
                log_prefix = (
                    "(Custom Prompt)"
                    if not disable_pair_extraction
                    else "(Default Prompt)"
                )
                logging.info(
                    f"Attempt {attempt + 1}/{max_retries} parsing PDF {log_prefix} {fname.name} (Timeout: {timeout_seconds}s)..."
                )
                start_time = time.time()
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
                        f"Successfully parsed PDF {fname.name} into {len(parsed_doc_list)} sections in {elapsed:.2f} seconds."
                    )
                    return parsed_doc_list
                else:
                    logging.warning(
                        f"No content returned for PDF {fname.name} on attempt {attempt + 1}"
                    )
            except asyncio.TimeoutError:
                logging.error(
                    f"Timeout error ({timeout_seconds}s) on attempt {attempt + 1} for PDF {fname.name}"
                )
            except Exception as e:
                logging.error(
                    f"Error on attempt {attempt + 1} for PDF {fname.name}: {str(e)}",
                    exc_info=True,
                )
            if attempt < max_retries - 1:
                backoff_time = 2**attempt
                logging.info(f"Retrying {fname.name} in {backoff_time} seconds...")
                await asyncio.sleep(backoff_time)
        logging.error(f"Failed to parse PDF {fname.name} after {max_retries} attempts")
        return None

    # Semaphore and Task Gathering
    semaphore = asyncio.Semaphore(max_workers)

    async def process_with_semaphore(fname):
        async with semaphore:
            return fname, await process_single_pdf(fname)

    tasks = [process_with_semaphore(fname) for fname in pdf_file_list]
    results_list = await asyncio.gather(*tasks)

    # Process results: Add metadata and CONDITIONALLY apply post-processing
    for fname, doc_list_result in results_list:
        if doc_list_result:
            file_name = fname.name
            total_docs_in_file = len(doc_list_result)
            post_processing_status = (
                "Applying" if not disable_pair_extraction else "Skipping"
            )
            logging.info(
                f"{post_processing_status} pairs post-processing for {total_docs_in_file} sections from PDF {file_name}"
            )

            for i, doc in enumerate(doc_list_result, 1):
                if not hasattr(doc, "metadata") or doc.metadata is None:
                    doc.metadata = {}
                doc.metadata["source"] = str(fname.resolve())
                doc.metadata["file_name"] = file_name
                doc.metadata["doc_num"] = i
                doc.metadata["total_docs_in_file"] = total_docs_in_file

                if not disable_pair_extraction:
                    processed_doc = postprocess_extract_pairs(doc)
                else:
                    processed_doc = doc
                    # Add empty 'pairs' if consistency is desired when skipping post-processing
                    # if 'pairs' not in processed_doc.metadata:
                    #     processed_doc.metadata['pairs'] = []

                all_processed_pdf_docs.append(processed_doc)
        else:
            logging.warning(
                f"❌ PDF {fname.name}: Failed to parse or returned empty result."
            )

    return all_processed_pdf_docs


# --- process_markdown_file remains the same ---
def process_markdown_file(file_path: Path) -> List[Document]:
    """Reads a Markdown file and returns it as a single Document object."""
    logging.info(f"Processing Markdown file: {file_path.name}")
    try:
        encodings_to_try = ["utf-8", "latin-1", "cp1252"]
        content = None
        for enc in encodings_to_try:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    content = f.read()
                logging.debug(f"Successfully read {file_path.name} with encoding {enc}")
                break
            except UnicodeDecodeError:
                logging.debug(f"Failed to read {file_path.name} with encoding {enc}")
                continue
            except Exception as e_read:
                logging.error(f"Error reading {file_path.name}: {e_read}")
                return []

        if content is None:
            logging.error(f"Could not decode Markdown file {file_path.name}")
            return []
        if not content.strip():
            logging.warning(
                f"Markdown file {file_path.name} is empty or contains only whitespace."
            )

        doc = Document(text=content if content else "")
        doc.metadata = {
            "source": str(file_path.resolve()),
            "file_name": file_path.name,
            "doc_num": 1,
            "total_docs_in_file": 1,
            # Consider adding 'pairs': [] here for absolute consistency if needed downstream
            # 'pairs': []
        }
        logging.info(f"✅ Successfully processed Markdown file {file_path.name}")
        return [doc]
    except Exception as e:
        logging.error(
            f"❌ Error processing Markdown file {file_path.name}: {e}", exc_info=True
        )
        return []


# --- Saving Function remains the same ---
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


# --- Main Execution Logic (Passes flag down) ---
async def main(
    input_dir: Optional[str],
    input_file: Optional[str],
    output_file: str,
    max_workers: int,
    timeout: int,
    disable_pair_extraction: bool,  # Accept the flag here
    max_retries: int = 3,
):
    """
    Main async function to orchestrate the parsing of PDF and Markdown files.
    """
    all_docs = []
    pdf_files_to_process = []
    md_files_to_process = []

    # Determine file list
    if input_file:
        path = Path(input_file)
        if not path.is_file():
            raise FileNotFoundError(f"Input file {input_file} not found.")
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pdf_files_to_process = [path]
        elif suffix in [".md", ".markdown"]:
            md_files_to_process = [path]
        else:
            raise ValueError(
                f"Input file {input_file} is not a supported type (.pdf, .md, .markdown)."
            )
        logging.info(f"Processing single input file: {path.resolve()}")
    elif input_dir:
        input_path = Path(input_dir)
        if not input_path.is_dir():
            raise FileNotFoundError(f"Input directory {input_dir} not found.")
        pdf_files_to_process = sorted(list(input_path.rglob("*.pdf")))
        md_files_to_process = sorted(list(input_path.rglob("*.md")))
        md_files_to_process.extend(sorted(list(input_path.rglob("*.markdown"))))
        if not pdf_files_to_process and not md_files_to_process:
            print(f"No PDF or Markdown files found in {input_dir} (recursive search).")
            return
        logging.info(
            f"Found {len(pdf_files_to_process)} PDF files and {len(md_files_to_process)} Markdown files in {input_path.resolve()}."
        )
    else:
        raise ValueError("Missing input source: Specify --input_dir or --input_file.")

    # Process Markdown Files
    if md_files_to_process:
        logging.info(f"\n--- Processing {len(md_files_to_process)} Markdown files ---")
        for md_file in md_files_to_process:
            processed_md_docs = process_markdown_file(md_file)
            all_docs.extend(processed_md_docs)

    # Process PDF Files
    processed_pdf_docs = []
    if pdf_files_to_process:
        logging.info(f"\n--- Processing {len(pdf_files_to_process)} PDF files ---")
        # Pass the flag to create_parser
        parser_template = create_parser(disable_pair_extraction=disable_pair_extraction)
        if parser_template:
            start_pdf_time = time.time()
            logging.info(
                f"Starting PDF parallel processing (Max Workers: {max_workers}, Timeout: {timeout}s)..."
            )
            processed_pdf_docs = await process_pdf_documents_parallel(
                pdf_files_to_process,
                parser_template,  # Pass the template
                max_workers=max_workers,
                timeout_seconds=timeout,
                max_retries=max_retries,
            )
            end_pdf_time = time.time()
            logging.info(
                f"Finished PDF processing in {end_pdf_time - start_pdf_time:.2f} seconds."
            )
            all_docs.extend(processed_pdf_docs)  # Add PDF results
        else:
            logging.warning(
                "PDF processing skipped because LlamaParse parser could not be initialized."
            )

    # Final Summary and Saving
    successful_md_files = sum(
        1
        for doc in all_docs
        if doc.metadata.get("file_name", "").lower().endswith((".md", ".markdown"))
    )
    successful_pdf_files = sum(
        1
        for doc in all_docs
        if doc.metadata.get("file_name", "").lower().endswith(".pdf")
    )
    failed_pdf_files = len(pdf_files_to_process) - successful_pdf_files

    print(f"\n--- Run Summary ---")
    print(f"Output File: {output_file}")
    print(f"Processed {successful_md_files}/{len(md_files_to_process)} Markdown files.")
    print(f"Attempted {len(pdf_files_to_process)} PDF files.")
    if LLAMA_PARSE_INSTALLED and pdf_files_to_process:
        pdf_mode = (
            "Default Parsing"
            if disable_pair_extraction
            else "Custom Prompt/Pair Extraction"
        )
        print(f"PDF Processing Mode: {pdf_mode}")
        print(f"Successfully parsed and processed {successful_pdf_files} PDF file(s).")
        if failed_pdf_files > 0:
            print(f"Failed to parse {failed_pdf_files} PDF file(s) after retries.")
    elif pdf_files_to_process:
        print("PDF processing was skipped (LlamaParse not initialized).")
    print(f"Generated {len(all_docs)} total document sections.")

    if all_docs:
        save_docs_to_pickle(all_docs, output_file)
    else:
        print("\nNo documents were successfully processed or generated.")


# --- __main__ block (Adds the new flag) ---
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        from dotenv import load_dotenv

        # Call without find_dotenv for compatibility with older versions
        if load_dotenv():
            logging.info("Loaded environment variables from .env file.")
        else:
            logging.info("No .env file found or failed to load.")
    except ImportError:
        logging.info(".env file handling skipped (python-dotenv not installed).")
    except Exception as e_dotenv:
        logging.warning(f"Error occurred during load_dotenv: {e_dotenv}")

    parser = argparse.ArgumentParser(
        description="Parse PDF (via LlamaParse) and Markdown files. Optionally disable custom PDF processing for pairs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input_dir",
        "-i",
        type=str,
        help="Directory containing PDF/Markdown files (recursive).",
    )
    input_group.add_argument(
        "--input_file", type=str, help="Path to a single PDF or Markdown file."
    )
    parser.add_argument(
        "--output_file",
        "-o",
        type=str,
        default="parsed_docs.pkl",
        help="Path to save the processed Document objects list.",
    )
    parser.add_argument(
        "--max_workers",
        "-w",
        type=int,
        default=4,
        help="Maximum concurrent PDF parsing workers.",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=180,
        help="Timeout in seconds for parsing each PDF file.",
    )
    # --- Add the new flag ---
    parser.add_argument(
        "--disable-pair-extraction",
        action="store_true",  # Makes it a boolean flag
        default=False,  # Default is to perform extraction
        help="Disable custom datasheet prompt and pair extraction post-processing for PDFs (use default LlamaParse behavior).",
    )
    # ---
    # Optional: Add --max_retries argument
    # parser.add_argument("--max_retries", type=int, default=3, help="Max retries for PDF parsing.")

    args = parser.parse_args()

    try:
        asyncio.run(
            main(
                input_dir=args.input_dir,
                input_file=args.input_file,
                output_file=args.output_file,
                max_workers=args.max_workers,
                timeout=args.timeout,
                disable_pair_extraction=args.disable_pair_extraction,  # Pass the flag value to main
                # max_retries=args.max_retries # Pass if added as arg
            )
        )
    except (FileNotFoundError, ValueError) as e:
        logging.error(f"Execution failed due to file or value error: {e}")
        print(f"Error: {e}")
    except ImportError as e:
        logging.error(f"Execution failed due to missing library: {e}")
        print(f"Error: Missing required library - {e}")
    except Exception as e:
        logging.error(
            f"An unexpected error occurred during execution: {e}", exc_info=True
        )
        print(f"An unexpected error occurred: {e}")
