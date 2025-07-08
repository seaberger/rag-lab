#!/usr/bin/env python3
"""
Simple database setup verification script
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent))


def test_basic_imports():
    """Test that basic imports work."""
    print("🔍 Testing Basic Imports")
    print("=" * 50)

    try:
        from src.pipeline_v3.utils.config import PipelineConfig

        config = PipelineConfig()
        print("✅ Configuration loaded")
        print(f"   Backend: {config.database.backend}")
        print(f"   Qdrant mode: {config.qdrant.mode}")
        return True
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False


def test_postgresql_connection():
    """Test PostgreSQL connection using psycopg."""
    print("\n🔍 Testing PostgreSQL Connection")
    print("=" * 50)

    try:
        # Try to use asyncpg if available
        import asyncpg

        async def test_connection():
            # Get config
            from src.pipeline_v3.utils.config import PipelineConfig

            config = PipelineConfig()

            connection_string = (
                f"postgresql://{config.database.postgresql.user}:"
                f"{os.getenv('POSTGRES_PASSWORD', '')}@"
                f"{config.database.postgresql.host}:"
                f"{config.database.postgresql.port}/"
                f"{config.database.postgresql.database}"
            )

            try:
                conn = await asyncpg.connect(connection_string)

                # Test basic queries
                version = await conn.fetchval("SELECT version()")
                print(f"✅ PostgreSQL connected: {version.split()[1]}")

                # Check schemas
                schemas = await conn.fetch("""
                    SELECT schema_name FROM information_schema.schemata
                    WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                    ORDER BY schema_name
                """)

                print(f"✅ Found {len(schemas)} custom schemas:")
                for schema in schemas:
                    print(f"   • {schema['schema_name']}")

                # Check migration status
                try:
                    migrations = await conn.fetch(
                        "SELECT version, description FROM migrations.schema_versions ORDER BY version"
                    )
                    print(f"✅ Found {len(migrations)} migrations:")
                    for migration in migrations:
                        print(f"   • v{migration['version']}: {migration['description']}")
                except:
                    print("⚠️  No migration tracking table found")

                # Check tenants
                try:
                    tenants = await conn.fetch(
                        "SELECT tenant_id, name FROM tenants.tenants ORDER BY name"
                    )
                    print(f"✅ Found {len(tenants)} tenants:")
                    for tenant in tenants[:5]:  # Show first 5
                        print(f"   • {tenant['name']} ({tenant['tenant_id']})")
                except:
                    print("⚠️  No tenants table found")

                await conn.close()
                return True

            except Exception as e:
                print(f"❌ PostgreSQL connection failed: {e}")
                return False

        return asyncio.run(test_connection())

    except ImportError:
        print("⚠️ asyncpg not available, trying psycopg2...")

        try:
            import psycopg2

            from src.pipeline_v3.utils.config import PipelineConfig

            config = PipelineConfig()

            conn = psycopg2.connect(
                host=config.database.postgresql.host,
                port=config.database.postgresql.port,
                database=config.database.postgresql.database,
                user=config.database.postgresql.user,
                password=os.getenv("POSTGRES_PASSWORD", ""),
            )

            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"✅ PostgreSQL connected: {version.split()[1]}")

            cursor.close()
            conn.close()
            return True

        except Exception as e:
            print(f"❌ PostgreSQL connection failed: {e}")
            return False


def test_qdrant_connection():
    """Test Qdrant connection."""
    print("\n🔍 Testing Qdrant Connection")
    print("=" * 50)

    try:
        import qdrant_client

        from src.pipeline_v3.utils.config import PipelineConfig

        config = PipelineConfig()

        if config.qdrant.mode == "server":
            print(
                f"🔄 Testing Qdrant server at {config.qdrant.server.host}:{config.qdrant.server.port}"
            )
            client = qdrant_client.QdrantClient(
                host=config.qdrant.server.host, port=config.qdrant.server.port
            )
        else:
            print(f"🔄 Testing Qdrant local mode at {config.qdrant.path}")
            Path(config.qdrant.path).mkdir(parents=True, exist_ok=True)
            client = qdrant_client.QdrantClient(path=config.qdrant.path)

        # Test connection
        collections = client.get_collections()
        print(f"✅ Qdrant accessible with {len(collections.collections)} collections")

        for collection in collections.collections:
            try:
                info = client.get_collection(collection.name)
                print(f"   • {collection.name}: {info.points_count} points")
            except:
                print(f"   • {collection.name}: (info unavailable)")

        # Test creating target collection if needed
        target_collection = config.qdrant.collection_name
        if target_collection not in [c.name for c in collections.collections]:
            print(f"🔄 Creating collection '{target_collection}'...")
            client.create_collection(
                collection_name=target_collection,
                vectors_config=qdrant_client.models.VectorParams(
                    size=config.openai.dimensions,
                    distance=qdrant_client.models.Distance.COSINE,
                ),
            )
            print(f"✅ Collection '{target_collection}' created")

        return True

    except Exception as e:
        print(f"❌ Qdrant connection failed: {e}")
        return False


def test_cli_functionality():
    """Test basic CLI functionality."""
    print("\n🔍 Testing CLI Functionality")
    print("=" * 50)

    try:
        # Test basic CLI import and status
        import subprocess

        result = subprocess.run(
            ["uv", "run", "python", "-m", "src.pipeline_v3.cli_main", "status", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            print("✅ CLI status command works")
            # Try to parse the JSON output
            try:
                import json

                status = json.loads(result.stdout)
                print(f"   Pipeline state: {status.get('state', 'unknown')}")
                if "components" in status:
                    components = status["components"]
                    print(f"   Embedding model: {components.get('embedding_model', 'unknown')}")
                    print(f"   Vision model: {components.get('vision_model', 'unknown')}")
            except:
                print("   (could not parse status JSON)")
        else:
            print(f"❌ CLI status failed: {result.stderr}")
            return False

        # Test search (should work even with no documents)
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "src.pipeline_v3.cli_main",
                "search",
                "test",
                "--type",
                "hybrid",
                "--top-k",
                "1",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            print("✅ CLI search command works")
        else:
            print(f"⚠️ CLI search failed (expected if no documents): {result.stderr}")

        return True

    except Exception as e:
        print(f"❌ CLI test failed: {e}")
        return False


def main():
    """Run all verification tests."""
    print("🧪 Database Setup Verification")
    print("=" * 60)
    print(f"Working directory: {os.getcwd()}")
    print(f"Environment file: {os.path.exists('.env')}")

    # Check environment
    if os.getenv("OPENAI_API_KEY"):
        print("✅ OPENAI_API_KEY is set")
    else:
        print("⚠️ OPENAI_API_KEY not set")

    if os.getenv("POSTGRES_PASSWORD"):
        print("✅ POSTGRES_PASSWORD is set")
    else:
        print("⚠️ POSTGRES_PASSWORD not set")

    print("")

    # Run tests
    results = []

    # Test basic imports
    import_result = test_basic_imports()
    results.append(("Basic Imports", import_result))

    if import_result:
        # Test PostgreSQL
        pg_result = test_postgresql_connection()
        results.append(("PostgreSQL", pg_result))

        # Test Qdrant
        qdrant_result = test_qdrant_connection()
        results.append(("Qdrant", qdrant_result))

        # Test CLI (regardless of direct connection test, since CLI uses its own auth)
        cli_result = test_cli_functionality()
        results.append(("CLI", cli_result))

    # Summary
    print("\n📊 Verification Results")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:15} {status}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 Database setup verification passed!")
        print("\nDatabase is ready for use. Next steps:")
        print(
            "1. Load documents: uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf"
        )
        print("2. Test search: uv run python -m src.pipeline_v3.cli_main search 'laser power'")
        print(
            "3. Test tenant isolation: uv run python -m src.pipeline_v3.cli_main search 'power' --tenant-id [tenant-id]"
        )
    else:
        print("❌ Some verification tests failed.")
        print("Please check DATABASE_SETUP_GUIDE.md for setup instructions.")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
