#!/usr/bin/env python3
"""
Update tests to remove SQLite dependencies and add proper markers.

This script:
1. Adds pytest markers to categorize tests
2. Updates SQLite imports to use database adapters
3. Ensures tests use the test_databases fixture for real DB access
"""

import re
import sys
from pathlib import Path
from typing import Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestUpdater:
    """Update tests for PostgreSQL/Qdrant usage."""

    def __init__(self):
        self.test_root = Path(__file__).parent.parent / "tests"
        self.updates_made = 0
        self.files_updated = []

    def should_use_real_db(self, file_path: Path, content: str) -> bool:
        """Determine if a test should use real databases."""
        # Integration and e2e tests should use real DBs
        if "integration" in str(file_path) or "e2e" in str(file_path):
            return True

        # Tests that explicitly test database functionality
        return any(
            term in content
            for term in [
                "test_isolation",
                "test_tenant",
                "test_migration",
                "test_registry",
                "test_keyword",
                "test_fingerprint",
            ]
        )

    def update_sqlite_imports(self, content: str) -> Tuple[str, bool]:
        """Replace direct SQLite imports with adapter usage."""
        updated = False
        lines = content.splitlines()
        new_lines = []

        for line in lines:
            # Skip SQLite imports
            if "import sqlite3" in line:
                updated = True
                continue

            # Replace SQLite connection creation
            if "sqlite3.connect" in line:
                # Replace with adapter usage
                new_line = line.replace(
                    "sqlite3.connect(", "# TODO: Use database adapter instead of direct SQLite\n# "
                )
                new_lines.append(new_line)
                updated = True
            else:
                new_lines.append(line)

        return "\n".join(new_lines), updated

    def add_test_database_fixture(self, content: str, use_real_db: bool) -> Tuple[str, bool]:
        """Add test_databases fixture to tests that need it."""
        if not use_real_db:
            return content, False

        # Check if fixture already exists
        if "test_databases" in content or "test_tenant_config" in content:
            return content, False

        updated = False
        lines = content.splitlines()

        # Find test functions that might need the fixture
        for i, line in enumerate(lines):
            if line.strip().startswith("def test_") or line.strip().startswith("async def test_"):
                # Check if it's a database-related test
                func_name = line.split("(")[0].split()[-1]
                if any(
                    term in func_name.lower()
                    for term in ["registry", "keyword", "fingerprint", "job", "tenant"]
                ):
                    # Add fixture if not present
                    if "test_config" in line and "test_tenant_config" not in line:
                        lines[i] = line.replace("test_config", "test_tenant_config")
                        updated = True

        if updated:
            # Ensure import exists
            import_line = "from src.pipeline_v3.tests.fixtures.test_database_setup import test_databases, test_tenant_config"
            if import_line not in content:
                # Find import section
                import_end = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith("import ") or line.strip().startswith("from "):
                        import_end = i + 1
                    elif import_end > 0 and line.strip() and not line.strip().startswith("#"):
                        break

                lines.insert(import_end, import_line)

        return "\n".join(lines), updated

    def add_pytest_markers(self, content: str, file_path: Path) -> Tuple[str, bool]:
        """Add appropriate pytest markers to test file."""
        markers_to_add = set()

        # Determine markers based on path and content
        rel_path = file_path.relative_to(self.test_root)
        path_parts = rel_path.parts

        if "unit" in path_parts:
            markers_to_add.add("unit")
        elif "integration" in path_parts:
            markers_to_add.add("integration")
        elif "security" in path_parts:
            markers_to_add.add("security")
        elif "e2e" in path_parts:
            markers_to_add.add("e2e")

        # Check content for database usage
        if "PostgreSQL" in content or "postgres" in content.lower():
            markers_to_add.add("requires_postgres")
        if "Qdrant" in content or "vector" in content:
            markers_to_add.add("requires_qdrant")

        if not markers_to_add:
            return content, False

        # Check for existing markers
        existing_markers = set(re.findall(r"@pytest\.mark\.(\w+)", content))
        markers_to_add -= existing_markers

        if not markers_to_add:
            return content, False

        # Add markers
        lines = content.splitlines()
        updated = False

        # Ensure pytest import
        if "import pytest" not in content:
            import_end = 0
            for i, line in enumerate(lines):
                if line.strip().startswith("import ") or line.strip().startswith("from "):
                    import_end = i + 1
            lines.insert(import_end, "import pytest")
            lines.insert(import_end + 1, "")

        # Add markers to test classes and functions
        i = 0
        while i < len(lines):
            line = lines[i]

            if (
                line.strip().startswith("class Test")
                or line.strip().startswith("def test_")
                or line.strip().startswith("async def test_")
            ):
                # Check if already has markers
                has_markers = False
                j = i - 1
                while j >= 0 and (lines[j].strip().startswith("@") or not lines[j].strip()):
                    if "@pytest.mark" in lines[j]:
                        has_markers = True
                        break
                    j -= 1

                if not has_markers:
                    indent = len(line) - len(line.lstrip())
                    insert_pos = i

                    # Add markers
                    for marker in sorted(markers_to_add):
                        lines.insert(insert_pos, " " * indent + f"@pytest.mark.{marker}")
                        insert_pos += 1
                        i += 1

                    updated = True

            i += 1

        return "\n".join(lines), updated

    def process_file(self, file_path: Path):
        """Process a single test file."""
        try:
            content = file_path.read_text()

            # Skip if it's a fixture file
            if "fixtures" in str(file_path) or "conftest" in file_path.name:
                return

            # Determine if should use real DB
            use_real_db = self.should_use_real_db(file_path, content)

            # Update SQLite imports
            content, updated1 = self.update_sqlite_imports(content)

            # Add test database fixture if needed
            content, updated2 = self.add_test_database_fixture(content, use_real_db)

            # Add pytest markers
            content, updated3 = self.add_pytest_markers(content, file_path)

            # Write back if changed
            if updated1 or updated2 or updated3:
                file_path.write_text(content)
                self.updates_made += 1
                self.files_updated.append(file_path.relative_to(self.test_root))

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    def run(self):
        """Process all test files."""
        test_files = list(self.test_root.rglob("test_*.py"))

        print(f"Processing {len(test_files)} test files...")

        for test_file in test_files:
            self.process_file(test_file)

        print(f"\nUpdated {self.updates_made} files")
        if self.files_updated:
            print("\nFiles updated:")
            for f in self.files_updated[:10]:  # Show first 10
                print(f"  - {f}")
            if len(self.files_updated) > 10:
                print(f"  ... and {len(self.files_updated) - 10} more")


def main():
    """Main entry point."""
    updater = TestUpdater()
    updater.run()


if __name__ == "__main__":
    main()
