#!/usr/bin/env python3
"""
Script to examine the current PostgreSQL database structure
"""

import os
import sys
from pathlib import Path

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent))

import psycopg2

from src.pipeline_v3.utils.config import PipelineConfig


def examine_database_structure():
    """Examine the current database structure."""
    config = PipelineConfig()

    # Connect to PostgreSQL
    connection_params = {
        "host": config.database.postgresql.host,
        "port": config.database.postgresql.port,
        "database": config.database.postgresql.database,
        "user": config.database.postgresql.user,
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }

    print("🔍 Examining PostgreSQL Database Structure")
    print("=" * 60)

    try:
        conn = psycopg2.connect(**connection_params)
        cursor = conn.cursor()

        # List all schemas
        print("\n📁 SCHEMAS:")
        cursor.execute("""
            SELECT schema_name, schema_owner
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            ORDER BY schema_name;
        """)
        schemas = cursor.fetchall()
        for schema, owner in schemas:
            print(f"  • {schema} (owner: {owner})")

        # For each schema, list tables
        for schema, _ in schemas:
            print(f"\n📊 TABLES IN SCHEMA '{schema}':")
            cursor.execute(
                """
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = %s
                ORDER BY table_name;
            """,
                (schema,),
            )
            tables = cursor.fetchall()

            if not tables:
                print("  (no tables)")
            else:
                for table, table_type in tables:
                    print(f"  • {table} ({table_type})")

                    # Get column info for each table
                    cursor.execute(
                        """
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position;
                    """,
                        (schema, table),
                    )
                    columns = cursor.fetchall()

                    for col_name, data_type, nullable, default in columns:
                        null_str = "NULL" if nullable == "YES" else "NOT NULL"
                        default_str = f" DEFAULT {default}" if default else ""
                        print(f"    - {col_name}: {data_type} {null_str}{default_str}")

        # Check for any functions/procedures
        print("\n🔧 FUNCTIONS:")
        cursor.execute("""
            SELECT routine_schema, routine_name, routine_type
            FROM information_schema.routines
            WHERE routine_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY routine_schema, routine_name;
        """)
        functions = cursor.fetchall()

        if not functions:
            print("  (no custom functions)")
        else:
            for schema, name, ftype in functions:
                print(f"  • {schema}.{name} ({ftype})")

        # Check for row-level security policies
        print("\n🔒 ROW LEVEL SECURITY POLICIES:")
        cursor.execute("""
            SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
            FROM pg_policies
            ORDER BY schemaname, tablename, policyname;
        """)
        policies = cursor.fetchall()

        if not policies:
            print("  (no RLS policies)")
        else:
            for schema, table, policy, permissive, roles, cmd, qual, with_check in policies:
                print(f"  • {schema}.{table}.{policy}")
                print(f"    - Command: {cmd}, Permissive: {permissive}")
                print(f"    - Roles: {roles}")
                if qual:
                    print(f"    - Qualifier: {qual}")
                if with_check:
                    print(f"    - With Check: {with_check}")

        cursor.close()
        conn.close()

        print("\n✅ Database structure examination complete")

    except Exception as e:
        print(f"❌ Error examining database: {e}")
        return False

    return True


if __name__ == "__main__":
    examine_database_structure()
