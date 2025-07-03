"""
Page Range Parsing and Processing Utilities

Provides functionality to parse page range specifications (e.g., "1-5", "1,3,7", "10-20")
and manage page-by-page document processing with progress monitoring.
"""

import logging

logger = logging.getLogger(__name__)


class PageRangeError(Exception):
    """Raised when page range specification is invalid."""


class PageRangeParser:
    """Parse and validate page range specifications."""

    @staticmethod
    def parse(page_spec: str, total_pages: int | None = None) -> list[int]:
        """
        Parse a page range specification into a list of page numbers.

        Args:
            page_spec: Page specification (e.g., "1-5", "1,3,7", "10-20", "1-10,15-20")
            total_pages: Optional total page count for validation

        Returns:
            List of page numbers (1-indexed)

        Raises:
            PageRangeError: If the specification is invalid

        Examples:
            parse("1-5") -> [1, 2, 3, 4, 5]
            parse("1,3,7") -> [1, 3, 7]
            parse("1-3,7-9") -> [1, 2, 3, 7, 8, 9]
            parse("5-") -> [5, 6, 7, ...] (requires total_pages)
        """
        if not page_spec or not page_spec.strip():
            raise PageRangeError("Page specification cannot be empty")

        page_spec = page_spec.strip()
        page_numbers = set()

        # Split by commas for multiple ranges/individual pages
        parts = [part.strip() for part in page_spec.split(",")]

        for part in parts:
            if not part:
                continue

            if "-" in part:
                # Range specification
                page_numbers.update(PageRangeParser._parse_range(part, total_pages))
            else:
                # Individual page number
                try:
                    page_num = int(part)
                    if page_num < 1:
                        raise PageRangeError(f"Page numbers must be positive, got: {page_num}")
                    page_numbers.add(page_num)
                except ValueError:
                    raise PageRangeError(f"Invalid page number: {part}")

        # Validate against total pages if provided
        if total_pages is not None:
            invalid_pages = [p for p in page_numbers if p > total_pages]
            if invalid_pages:
                raise PageRangeError(
                    f"Page numbers {invalid_pages} exceed document length ({total_pages} pages)"
                )

        # Return sorted list
        return sorted(page_numbers)

    @staticmethod
    def _parse_range(range_spec: str, total_pages: int | None = None) -> list[int]:
        """Parse a range specification like '1-5' or '10-'."""
        if range_spec.count("-") != 1:
            raise PageRangeError(f"Invalid range format: {range_spec}")

        start_str, end_str = range_spec.split("-")

        # Parse start page
        try:
            start = int(start_str) if start_str else 1
        except ValueError:
            raise PageRangeError(f"Invalid start page in range: {start_str}")

        if start < 1:
            raise PageRangeError(f"Start page must be positive: {start}")

        # Parse end page
        if not end_str:
            # Open-ended range like "5-"
            if total_pages is None:
                raise PageRangeError("Open-ended ranges require total page count")
            end = total_pages
        else:
            try:
                end = int(end_str)
            except ValueError:
                raise PageRangeError(f"Invalid end page in range: {end_str}")

        if end < start:
            raise PageRangeError(f"End page ({end}) must be >= start page ({start})")

        return list(range(start, end + 1))

    @staticmethod
    def validate_page_spec(page_spec: str) -> bool:
        """
        Validate a page specification without requiring total page count.

        Args:
            page_spec: Page specification to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Parse without total pages (this will catch format errors)
            PageRangeParser.parse(page_spec)
            return True
        except PageRangeError:
            return False

    @staticmethod
    def format_page_summary(pages: list[int]) -> str:
        """
        Format a list of page numbers into a human-readable summary.

        Args:
            pages: List of page numbers

        Returns:
            Formatted string (e.g., "pages 1-5, 7, 10-12")
        """
        if not pages:
            return "no pages"

        pages = sorted(set(pages))  # Remove duplicates and sort

        if len(pages) == 1:
            return f"page {pages[0]}"

        # Group consecutive pages into ranges
        ranges = []
        start = pages[0]
        end = pages[0]

        for i in range(1, len(pages)):
            if pages[i] == end + 1:
                # Consecutive page
                end = pages[i]
            else:
                # Gap found, close current range
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{end}")
                start = end = pages[i]

        # Close final range
        if start == end:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{end}")

        return f"pages {', '.join(ranges)}"


class PageProgressMonitor:
    """Monitor progress of page-by-page document processing."""

    def __init__(self, total_pages: int, page_numbers: list[int] | None = None):
        """
        Initialize progress monitor.

        Args:
            total_pages: Total number of pages in document
            page_numbers: Specific pages being processed (if None, assumes all pages)
        """
        self.total_pages = total_pages
        self.page_numbers = page_numbers or list(range(1, total_pages + 1))
        self.processed_pages = []
        self.current_page = None
        self.start_time = None

    def start_processing(self, page_num: int) -> None:
        """Mark the start of processing for a specific page."""
        import time

        self.current_page = page_num
        self.start_time = time.time()

        progress = len(self.processed_pages) + 1
        total = len(self.page_numbers)

        logger.info(f"📄 Processing page {page_num} ({progress}/{total})...")

    def finish_processing(self, page_num: int, success: bool = True) -> None:
        """Mark the completion of processing for a specific page."""
        import time

        if page_num != self.current_page:
            logger.warning(f"Page number mismatch: expected {self.current_page}, got {page_num}")

        if self.start_time:
            duration = time.time() - self.start_time
            status = "✅" if success else "❌"
            logger.info(f"{status} Page {page_num} processed in {duration:.2f}s")

        if success:
            self.processed_pages.append(page_num)

        self.current_page = None
        self.start_time = None

    def get_progress_summary(self) -> dict:
        """Get current progress summary."""
        total = len(self.page_numbers)
        completed = len(self.processed_pages)

        return {
            "total_pages_in_document": self.total_pages,
            "pages_to_process": self.page_numbers,
            "pages_completed": completed,
            "pages_total": total,
            "progress_percentage": (completed / total * 100) if total > 0 else 0,
            "current_page": self.current_page,
            "remaining_pages": [p for p in self.page_numbers if p not in self.processed_pages],
        }

    def is_complete(self) -> bool:
        """Check if all pages have been processed."""
        return len(self.processed_pages) == len(self.page_numbers)


# Utility functions for common operations


def extract_pages_from_pdf_data_uris(
    all_data_uris: list[str], page_numbers: list[int]
) -> list[str]:
    """
    Extract specific pages from a list of PDF data URIs.

    Args:
        all_data_uris: List of data URIs for all pages (1-indexed by position)
        page_numbers: List of page numbers to extract (1-indexed)

    Returns:
        List of data URIs for the specified pages
    """
    total_pages = len(all_data_uris)

    # Validate page numbers
    invalid_pages = [p for p in page_numbers if p < 1 or p > total_pages]
    if invalid_pages:
        raise PageRangeError(
            f"Page numbers {invalid_pages} are out of range (document has {total_pages} pages)"
        )

    # Extract specified pages (convert to 0-indexed for list access)
    selected_uris = []
    for page_num in page_numbers:
        index = page_num - 1  # Convert to 0-indexed
        selected_uris.append(all_data_uris[index])

    return selected_uris


def get_page_count_from_pdf(pdf_path) -> int:
    """
    Get the total number of pages in a PDF file.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Total number of pages
    """
    try:
        # Quick way to get page count without converting all pages
        import fitz  # PyMuPDF for faster page counting
        from pdf2image import convert_from_path

        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()
        return page_count
    except ImportError:
        # Fallback to pdf2image if PyMuPDF not available
        from pdf2image import convert_from_path

        images = convert_from_path(str(pdf_path), dpi=72, first_page=1, last_page=1)
        # This is inefficient but works as fallback
        logger.warning("PyMuPDF not available, using pdf2image for page counting (slower)")
        # We need a different approach - let's use a subprocess call to pdfinfo
        import subprocess

        try:
            result = subprocess.run(
                ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
            )
            for line in result.stdout.split("\n"):
                if line.startswith("Pages:"):
                    return int(line.split(":")[1].strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Final fallback - convert all pages (slow but reliable)
            images = convert_from_path(str(pdf_path), dpi=72)
            return len(images)

    raise RuntimeError(f"Could not determine page count for {pdf_path}")


# Export main classes and functions
__all__ = [
    "PageProgressMonitor",
    "PageRangeError",
    "PageRangeParser",
    "extract_pages_from_pdf_data_uris",
    "get_page_count_from_pdf",
]
