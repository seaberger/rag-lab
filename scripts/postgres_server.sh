#!/bin/bash
# Script to manage PostgreSQL server for development and testing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default action
ACTION=${1:-status}

cd "$PROJECT_ROOT"

# Load environment if available
if [ -f ".env.postgres" ]; then
    source .env.postgres
fi

case $ACTION in
    start)
        echo -e "${GREEN}Starting PostgreSQL server...${NC}"
        docker compose up -d postgres 2>/dev/null || docker-compose up -d postgres
        echo -e "${YELLOW}Waiting for PostgreSQL to be ready...${NC}"

        # Wait for health check
        for i in {1..30}; do
            if docker compose exec -T postgres pg_isready -U rag_user -d rag_lab > /dev/null 2>&1; then
                echo -e "${GREEN}✓ PostgreSQL server is ready!${NC}"
                echo -e "Connection: postgres://rag_user:${POSTGRES_PASSWORD:-rag_dev_password}@localhost:5432/rag_lab"
                exit 0
            fi
            echo -n "."
            sleep 1
        done

        echo -e "\n${RED}✗ PostgreSQL server failed to start${NC}"
        docker-compose logs postgres
        exit 1
        ;;

    stop)
        echo -e "${YELLOW}Stopping PostgreSQL server...${NC}"
        docker compose down postgres 2>/dev/null || docker-compose down postgres
        echo -e "${GREEN}✓ PostgreSQL server stopped${NC}"
        ;;

    restart)
        $0 stop
        sleep 2
        $0 start
        ;;

    status)
        if docker compose exec -T postgres pg_isready -U rag_user -d rag_lab > /dev/null 2>&1; then
            echo -e "${GREEN}✓ PostgreSQL server is running${NC}"
            echo -e "Connection: postgres://rag_user:${POSTGRES_PASSWORD:-rag_dev_password}@localhost:5432/rag_lab"

            # Show table counts
            echo -e "\n${YELLOW}Database Tables:${NC}"
            docker compose exec -T postgres psql -U rag_user -d rag_lab -c "
                SELECT table_name,
                       (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = t.table_name) as exists
                FROM (VALUES
                    ('documents'),
                    ('index_entries'),
                    ('keyword_search'),
                    ('fingerprints'),
                    ('jobs')
                ) AS t(table_name)
                ORDER BY table_name;
            " 2>/dev/null || echo "Database not initialized yet"
        else
            echo -e "${RED}✗ PostgreSQL server is not running${NC}"
            echo -e "Run: $0 start"
        fi
        ;;

    logs)
        docker compose logs -f postgres 2>/dev/null || docker-compose logs -f postgres
        ;;

    psql)
        if docker compose exec -T postgres pg_isready -U rag_user -d rag_lab > /dev/null 2>&1; then
            docker compose exec postgres psql -U rag_user -d rag_lab
        else
            echo -e "${RED}✗ PostgreSQL server is not running${NC}"
            exit 1
        fi
        ;;

    reset)
        echo -e "${RED}WARNING: This will delete all PostgreSQL data!${NC}"
        read -p "Are you sure? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            $0 stop
            rm -rf "$PROJECT_ROOT/postgres_data"
            echo -e "${GREEN}✓ PostgreSQL data cleared${NC}"
        fi
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs|psql|reset}"
        echo
        echo "Commands:"
        echo "  start    - Start PostgreSQL server in Docker"
        echo "  stop     - Stop PostgreSQL server"
        echo "  restart  - Restart PostgreSQL server"
        echo "  status   - Check server status and show tables"
        echo "  logs     - Show server logs (follow mode)"
        echo "  psql     - Connect to PostgreSQL with psql client"
        echo "  reset    - Stop server and delete all data"
        exit 1
        ;;
esac
