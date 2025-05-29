#!/bin/bash
# Production helper script

case "$1" in
  up)
    docker-compose -f docker-compose.prod.yml up -d
    ;;
  down)
    docker-compose -f docker-compose.prod.yml down
    ;;
  build)
    docker-compose -f docker-compose.prod.yml up --build -d
    ;;
  logs)
    docker-compose -f docker-compose.prod.yml logs -f "${@:2}"
    ;;
  test-db)
    docker-compose -f docker-compose.prod.yml exec app python manage.py test_aiven
    ;;
  *)
    echo "Usage: $0 {up|down|build|logs|test-db}"
    exit 1
esac