#!/usr/bin/env python3
"""
Categorize tests by adding pytest markers based on their content and location.

This script analyzes test files and adds appropriate markers like:
- @pytest.mark.unit
- @pytest.mark.integration
- @pytest.mark.requires_postgres
- @pytest.mark.requires_qdrant
"""

import re
import sys
from pathlib import Path
from typing import Set, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestCategorizer:
    """Categorize tests based on their content and dependencies."""

    def __init__(self):
        self.test_root = Path(__file__).parent.parent / "tests"
        self.stats = {
            "total_files": 0,
            "modified_files": 0,
            "unit_tests": 0,
            "integration_tests": 0,
            "e2e_tests": 0,
            "postgres_tests": 0,
            "qdrant_tests": 0,
        }

    def categorize_file(self, file_path: Path) -> Tuple[Set[str], bool]:
        """
        Categorize a test file based on its content.

        Returns:
            Tuple of (markers_to_add, needs_modification)
        """
        content = file_path.read_text()
        markers = set()

        # Check file location
        rel_path = file_path.relative_to(self.test_root)
        path_parts = rel_path.parts

        # Directory-based categorization
        if "unit" in path_parts:
            markers.add("unit")
        elif "integration" in path_parts:
            markers.add("integration")
        elif "security" in path_parts:
            markers.add("security")
        elif "regression" in path_parts:
            markers.add("regression")
        elif "e2e" in path_parts or "end_to_end" in path_parts:
            markers.add("e2e")

        # Content-based categorization
        content_lower = content.lower()

        # Check for database usage
        if any(
            term in content_lower
            for term in [
                "postgresql",
                "psycopg",
                "postgres",
                "pg_",
                "row level security",
                "rls",
                "tenant_id",
            ]
        ):
            markers.add("requires_postgres")
            if "unit" not in markers:
                markers.add("integration")

        if any(term in content_lower for term in ["qdrant", "vector", "embedding", "collection"]):
            markers.add("requires_qdrant")
            if "unit" not in markers:
                markers.add("integration")

        # Check for SQLite usage (these might need conversion)
        if "sqlite" in content_lower or "sqlite3" in content_lower:
            # SQLite in unit tests is OK, but integration tests should use real DB
            if "integration" in markers or "e2e" in markers:
                markers.add("requires_postgres")

        # Check for OpenAI API usage
        if any(term in content for term in ["OPENAI_API_KEY", "openai", "gpt-4", "embedding"]):
            markers.add("requires_api")

        # Check for slow operations
        if any(
            term in content_lower
            for term in [
                "sleep",
                "time.sleep",
                "large file",
                "many documents",
                "stress test",
                "performance test",
            ]
        ):
            markers.add("slow")

        # E2E test patterns
        if any(
            pattern in content
            for pattern in [
                "test_full_pipeline",
                "test_end_to_end",
                "test_complete_workflow",
                "EnhancedPipeline",
                "add.*search.*verify",
            ]
        ):
            markers.add("e2e")
            markers.add("integration")

        # Smoke test patterns
        if "smoke" in file_path.name or "test_basic_" in content:
            markers.add("smoke")

        # Check if markers already exist
        existing_markers = set()
        marker_pattern = r"@pytest\.mark\.(\w+)"
        for match in re.finditer(marker_pattern, content):
            existing_markers.add(match.group(1))

        # Only add markers that don't already exist
        markers_to_add = markers - existing_markers

        return markers_to_add, len(markers_to_add) > 0

    def add_markers_to_file(self, file_path: Path, markers: Set[str]) -> bool:
        """Add pytest markers to a test file."""
        if not markers:
            return False

        content = file_path.read_text()
        lines = content.splitlines()

        # Find the import section
        import_end = 0
        has_pytest_import = False
        for i, line in enumerate(lines):
            if line.strip().startswith("import ") or line.strip().startswith("from "):
                import_end = i + 1
                if "pytest" in line:
                    has_pytest_import = True
            elif import_end > 0 and line.strip() and not line.strip().startswith("#"):
                break

        # Add pytest import if needed
        if not has_pytest_import:
            lines.insert(import_end, "import pytest")
            import_end += 1
            lines.insert(import_end, "")
            import_end += 1

        # Process each test function/class
        modified = False
        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for test class or function
            if (
                line.strip().startswith("class Test")
                or line.strip().startswith("def test_")
                or (line.strip().startswith("async def test_"))
            ):
                # Check if it already has markers
                has_markers = False
                j = i - 1
                while j >= 0 and (lines[j].strip().startswith("@") or not lines[j].strip()):
                    if "@pytest.mark" in lines[j]:
                        has_markers = True
                        break
                    j -= 1

                if not has_markers:
                    # Add markers before the test
                    indent = len(line) - len(line.lstrip())
                    insert_pos = i

                    # Add blank line if needed
                    if i > 0 and lines[i - 1].strip():
                        lines.insert(insert_pos, "")
                        insert_pos += 1
                        i += 1

                    # Add markers
                    for marker in sorted(markers):
                        lines.insert(insert_pos, " " * indent + f"@pytest.mark.{marker}")
                        insert_pos += 1
                        i += 1

                    modified = True

            i += 1

        if modified:
            # Write back the modified content
            file_path.write_text("\n".join(lines) + "\n")

        return modified

    def process_directory(self, directory: Path):
        """Process all test files in a directory."""
        test_files = list(directory.rglob("test_*.py"))

        print(f"Found {len(test_files)} test files in {directory}")

        for test_file in test_files:
            self.stats["total_files"] += 1

            try:
                markers, needs_modification = self.categorize_file(test_file)

                if needs_modification:
                    print(f"\n{test_file.relative_to(self.test_root)}:")
                    print(f"  Adding markers: {', '.join(sorted(markers))}")

                    if self.add_markers_to_file(test_file, markers):
                        self.stats["modified_files"] += 1

                        # Update stats
                        if "unit" in markers:
                            self.stats["unit_tests"] += 1
                        if "integration" in markers:
                            self.stats["integration_tests"] += 1
                        if "e2e" in markers:
                            self.stats["e2e_tests"] += 1
                        if "requires_postgres" in markers:
                            self.stats["postgres_tests"] += 1
                        if "requires_qdrant" in markers:
                            self.stats["qdrant_tests"] += 1

            except Exception as e:
                print(f"  ERROR processing {test_file}: {e}")

    def print_summary(self):
        """Print categorization summary."""
        print("\n" + "=" * 60)
        print("TEST CATEGORIZATION SUMMARY")
        print("=" * 60)
        print(f"Total test files processed: {self.stats['total_files']}")
        print(f"Files modified: {self.stats['modified_files']}")
        print("\nTest categories added:")
        print(f"  Unit tests: {self.stats['unit_tests']}")
        print(f"  Integration tests: {self.stats['integration_tests']}")
        print(f"  E2E tests: {self.stats['e2e_tests']}")
        print(f"  Tests requiring PostgreSQL: {self.stats['postgres_tests']}")
        print(f"  Tests requiring Qdrant: {self.stats['qdrant_tests']}")
        print("=" * 60)

        # Print example commands
        print("\nExample test commands:")
        print("  # Run only unit tests (fast)")
        print("  pytest -m unit")
        print("\n  # Run integration tests without databases")
        print("  pytest -m 'integration and not (requires_postgres or requires_qdrant)'")
        print("\n  # Run all tests except slow ones")
        print("  pytest -m 'not slow'")
        print("\n  # Run PostgreSQL tests")
        print("  pytest -m requires_postgres")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Categorize tests with pytest markers")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without modifying files"
    )
    parser.add_argument(
        "--directory", type=Path, help="Specific directory to process (default: all tests)"
    )

    args = parser.parse_args()

    categorizer = TestCategorizer()

    if args.directory:
        categorizer.process_directory(args.directory)
    else:
        categorizer.process_directory(categorizer.test_root)

    categorizer.print_summary()


if __name__ == "__main__":
    main()
