#!/bin/bash
# Complete Database Setup Script for RAG Lab Pipeline v3
# This script sets up PostgreSQL and Qdrant from scratch

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# Check if we're in the correct directory
if [ ! -f "config.yaml" ] || [ ! -d "src/pipeline_v3" ]; then
    log_error "Please run this script from the rag_lab project root directory"
    exit 1
fi

log_info "🚀 Starting RAG Lab Database Setup"
echo "=============================================="

# Check environment file
if [ ! -f ".env" ]; then
    log_warning ".env file not found"
    echo "Creating template .env file..."
    cat > .env << 'EOF'
# OpenAI API Key (required)
OPENAI_API_KEY=your_openai_api_key_here

# PostgreSQL Configuration
POSTGRES_PASSWORD=rag_lab_secure_password
POSTGRES_USER=rag_user
POSTGRES_DB=rag_lab
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
EOF
    log_warning "Please edit .env file with your actual API key and database password"
    log_info "Then re-run this script"
    exit 1
fi

# Load environment variables
source .env
log_success "Environment variables loaded"

# Check required environment variables
if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key_here" ]; then
    log_error "Please set OPENAI_API_KEY in .env file"
    exit 1
fi

if [ -z "$POSTGRES_PASSWORD" ] || [ "$POSTGRES_PASSWORD" = "rag_lab_secure_password" ]; then
    log_warning "Using default PostgreSQL password. Consider changing it in .env"
fi

# Function to check if PostgreSQL is installed and running
check_postgresql() {
    log_info "Checking PostgreSQL installation..."

    if command -v psql &> /dev/null; then
        log_success "PostgreSQL client found"
    else
        log_error "PostgreSQL client (psql) not found"
        log_info "Install PostgreSQL:"
        log_info "  macOS: brew install postgresql@15"
        log_info "  Ubuntu: sudo apt install postgresql-15 postgresql-contrib-15"
        exit 1
    fi

    # Check if PostgreSQL server is running
    if pg_isready -h ${POSTGRES_HOST:-localhost} -p ${POSTGRES_PORT:-5432} &> /dev/null; then
        log_success "PostgreSQL server is running"
    else
        log_error "PostgreSQL server is not running or not accessible"
        log_info "Start PostgreSQL server:"
        log_info "  macOS: brew services start postgresql@15"
        log_info "  Ubuntu: sudo systemctl start postgresql"
        log_info "  Docker: docker run -d -e POSTGRES_USER=$POSTGRES_USER -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD -e POSTGRES_DB=$POSTGRES_DB -p 5432:5432 postgres:15-alpine"
        exit 1
    fi
}

# Function to setup PostgreSQL database
setup_postgresql() {
    log_info "Setting up PostgreSQL database..."

    # Check if database exists
    if PGPASSWORD=$POSTGRES_PASSWORD psql -h ${POSTGRES_HOST:-localhost} -p ${POSTGRES_PORT:-5432} -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1;" &> /dev/null; then
        log_success "Database $POSTGRES_DB already exists and is accessible"
    else
        log_info "Creating database and user..."

        # Try to create database as postgres user (if available)
        if sudo -u postgres psql -c "SELECT 1;" &> /dev/null; then
            log_info "Creating database using postgres superuser..."
            sudo -u postgres psql << EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$POSTGRES_USER') THEN
        CREATE USER $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';
    END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$POSTGRES_DB')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER;
EOF
        else
            log_error "Cannot create database. Please create manually:"
            log_info "sudo -u postgres psql"
            log_info "CREATE USER $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';"
            log_info "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;"
            exit 1
        fi
    fi

    # Enable required extensions
    log_info "Enabling PostgreSQL extensions..."
    PGPASSWORD=$POSTGRES_PASSWORD psql -h ${POSTGRES_HOST:-localhost} -U $POSTGRES_USER -d $POSTGRES_DB << EOF
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";
EOF

    log_success "PostgreSQL database setup complete"
}

# Function to run migrations
run_migrations() {
    log_info "Running database migrations..."

    local migration_dir="src/pipeline_v3/migrations/postgres"

    # List of migrations in order
    local migrations=(
        "001_initial_schema.sql"
        "002_row_level_security.sql"
        "003_add_index_entries.sql"
        "005_fix_tenant_functions.sql"
    )

    for migration in "${migrations[@]}"; do
        local migration_file="$migration_dir/$migration"

        if [ -f "$migration_file" ]; then
            log_info "Running migration: $migration"
            if PGPASSWORD=$POSTGRES_PASSWORD psql -h ${POSTGRES_HOST:-localhost} -U $POSTGRES_USER -d $POSTGRES_DB -f "$migration_file"; then
                log_success "Migration $migration completed"
            else
                log_error "Migration $migration failed"
                exit 1
            fi
        else
            log_warning "Migration file not found: $migration_file"
        fi
    done

    # Run enhanced tenant management (optional)
    local tenant_migration="src/pipeline_v3/migrations/003_tenant_management.sql"
    if [ -f "$tenant_migration" ]; then
        log_info "Running enhanced tenant management migration..."
        if PGPASSWORD=$POSTGRES_PASSWORD psql -h ${POSTGRES_HOST:-localhost} -U $POSTGRES_USER -d $POSTGRES_DB -f "$tenant_migration" 2>/dev/null; then
            log_success "Enhanced tenant management migration completed"
        else
            log_warning "Enhanced tenant management migration failed (this is optional)"
        fi
    fi

    log_success "Database migrations complete"
}

# Function to create test tenants
create_test_tenants() {
    log_info "Creating test tenants..."

    PGPASSWORD=$POSTGRES_PASSWORD psql -h ${POSTGRES_HOST:-localhost} -U $POSTGRES_USER -d $POSTGRES_DB << 'EOF'
-- Create test tenants for development
DO $$
BEGIN
    -- Check if create_tenant function exists
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'create_tenant' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'tenants')) THEN
        -- Create LMC tenant
        PERFORM tenants.create_tenant('lmc-dev', 'LMC Development', 50000, 500);

        -- Create Matrix tenant
        PERFORM tenants.create_tenant('matrix', 'Matrix Technologies', 25000, 250);

        -- Create CellX tenant
        PERFORM tenants.create_tenant('cellx', 'CellX Innovation', 15000, 150);

        RAISE NOTICE 'Test tenants created successfully';
    ELSE
        RAISE NOTICE 'Tenant creation function not available - using basic setup';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Tenant creation failed (this is optional): %', SQLERRM;
END $$;

-- Show all tenants
SELECT tenant_id, name, display_name FROM tenants.tenants ORDER BY name;
EOF

    log_success "Test tenants setup complete"
}

# Function to check Qdrant setup
setup_qdrant() {
    log_info "Setting up Qdrant vector database..."

    # Check if Qdrant server is configured
    if grep -q "mode: server" config.yaml; then
        log_info "Qdrant server mode detected"

        # Check if Qdrant server is running
        if curl -s http://localhost:6333/collections > /dev/null 2>&1; then
            log_success "Qdrant server is running on localhost:6333"
        else
            log_warning "Qdrant server not accessible on localhost:6333"
            log_info "Start Qdrant server:"
            log_info "  Docker: docker run -d --name rag-lab-qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest"
            log_info "  Or switch to local mode in config.yaml"

            # Ask user what to do
            read -p "Would you like to switch to local file mode? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                log_info "Switching to local file mode..."
                sed -i.bak 's/mode: server/mode: local/' config.yaml
                log_success "Config updated to use local file mode"
            else
                log_info "Please start Qdrant server and re-run this script"
                exit 1
            fi
        fi
    else
        log_info "Qdrant local file mode detected"
        local qdrant_path=$(grep -A5 "qdrant:" config.yaml | grep "path:" | cut -d: -f2 | xargs)
        if [ -z "$qdrant_path" ]; then
            qdrant_path="./qdrant_data_v3"
        fi

        log_info "Creating Qdrant data directory: $qdrant_path"
        mkdir -p "$qdrant_path"
        log_success "Qdrant local setup complete"
    fi
}

# Function to test the setup
test_setup() {
    log_info "Testing database setup..."

    if python3 test_database_setup.py; then
        log_success "Database setup test passed!"
    else
        log_error "Database setup test failed"
        log_info "Check the error messages above and refer to DATABASE_SETUP_GUIDE.md"
        exit 1
    fi
}

# Main execution
main() {
    check_postgresql
    setup_postgresql
    run_migrations
    create_test_tenants
    setup_qdrant

    log_success "🎉 Database setup complete!"
    echo ""
    log_info "Next steps:"
    echo "1. Test the setup: uv run python test_database_setup.py"
    echo "2. Load test documents: uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf"
    echo "3. Test search: uv run python -m src.pipeline_v3.cli_main search 'laser power' --type hybrid"
    echo "4. Test tenant isolation: uv run python -m src.pipeline_v3.cli_main search 'power' --tenant-id 081f2c7d-20be-4fc6-b8e2-113b9629db8e"
    echo ""
    log_info "For detailed information, see DATABASE_SETUP_GUIDE.md"

    # Ask if user wants to run the test
    read -p "Would you like to run the setup test now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_setup
    fi
}

# Run main function
main "$@"
