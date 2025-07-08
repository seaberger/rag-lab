"""Initial PostgreSQL schema

Revision ID: 001
Revises:
Create Date: 2025-01-06

"""

from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply initial schema from SQL file."""
    # Get the SQL file path
    migrations_dir = Path(__file__).parent.parent.parent
    sql_file = migrations_dir / "postgres" / "001_initial_schema.sql"

    # Read and execute the SQL
    with open(sql_file) as f:
        sql_content = f.read()

    # Execute the SQL commands
    # Note: We need to handle multiple statements
    connection = op.get_bind()

    # Split by semicolon but be careful with functions/triggers
    statements = []
    current_statement = []
    in_function = False

    for line in sql_content.split("\n"):
        # Check if we're entering or leaving a function definition
        if "$$" in line:
            in_function = not in_function

        current_statement.append(line)

        # If we hit a semicolon and we're not in a function, it's the end of a statement
        if line.strip().endswith(";") and not in_function:
            statements.append("\n".join(current_statement))
            current_statement = []

    # Execute each statement
    for statement in statements:
        statement = statement.strip()
        if statement and not statement.startswith("--"):
            connection.execute(sa.text(statement))


def downgrade() -> None:
    """Drop all schemas and tables."""
    # Drop schemas in reverse order of dependencies
    op.execute("DROP SCHEMA IF EXISTS tenants CASCADE")
    op.execute("DROP SCHEMA IF EXISTS migrations CASCADE")
    op.execute("DROP SCHEMA IF EXISTS fingerprints CASCADE")
    op.execute("DROP SCHEMA IF EXISTS jobs CASCADE")
    op.execute("DROP SCHEMA IF EXISTS search CASCADE")
    op.execute("DROP SCHEMA IF EXISTS registry CASCADE")

    # Drop extensions
    op.execute("DROP EXTENSION IF EXISTS unaccent")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
