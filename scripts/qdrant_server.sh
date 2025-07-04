#!/bin/bash
# Script to manage Qdrant server for development and testing

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

case $ACTION in
    start)
        echo -e "${GREEN}Starting Qdrant server...${NC}"
        docker compose up -d qdrant 2>/dev/null || docker-compose up -d qdrant
        echo -e "${YELLOW}Waiting for Qdrant to be ready...${NC}"

        # Wait for health check
        for i in {1..30}; do
            if curl -s http://localhost:6333/readyz > /dev/null; then
                echo -e "${GREEN}✓ Qdrant server is ready!${NC}"
                echo -e "Dashboard: http://localhost:6333/dashboard"
                exit 0
            fi
            echo -n "."
            sleep 1
        done

        echo -e "\n${RED}✗ Qdrant server failed to start${NC}"
        docker-compose logs qdrant
        exit 1
        ;;

    stop)
        echo -e "${YELLOW}Stopping Qdrant server...${NC}"
        docker compose down 2>/dev/null || docker-compose down
        echo -e "${GREEN}✓ Qdrant server stopped${NC}"
        ;;

    restart)
        $0 stop
        sleep 2
        $0 start
        ;;

    status)
        if curl -s http://localhost:6333/readyz > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Qdrant server is running${NC}"
            echo -e "Dashboard: http://localhost:6333/dashboard"

            # Show collections
            echo -e "\n${YELLOW}Collections:${NC}"
            curl -s http://localhost:6333/collections | jq -r '.result.collections[].name' 2>/dev/null || echo "No collections found"
        else
            echo -e "${RED}✗ Qdrant server is not running${NC}"
            echo -e "Run: $0 start"
        fi
        ;;

    logs)
        docker compose logs -f qdrant 2>/dev/null || docker-compose logs -f qdrant
        ;;

    reset)
        echo -e "${RED}WARNING: This will delete all Qdrant data!${NC}"
        read -p "Are you sure? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            $0 stop
            rm -rf "$PROJECT_ROOT/qdrant_server_data"
            echo -e "${GREEN}✓ Qdrant data cleared${NC}"
        fi
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs|reset}"
        echo
        echo "Commands:"
        echo "  start    - Start Qdrant server in Docker"
        echo "  stop     - Stop Qdrant server"
        echo "  restart  - Restart Qdrant server"
        echo "  status   - Check server status and show collections"
        echo "  logs     - Show server logs (follow mode)"
        echo "  reset    - Stop server and delete all data"
        exit 1
        ;;
esac
