#!/bin/bash
# Development helper script

case "$1" in
  up)
    docker-compose -f docker-compose.dev.yml up
    ;;
  down)
    docker-compose -f docker-compose.dev.yml down
    ;;
  build)
    docker-compose -f docker-compose.dev.yml up --build
    ;;
  logs)
    docker-compose -f docker-compose.dev.yml logs -f "${@:2}"
    ;;
  shell)
    docker-compose -f docker-compose.dev.yml exec app python manage.py shell
    ;;
  migrate)
    docker-compose -f docker-compose.dev.yml exec app python manage.py migrate
    ;;
  test)
    docker-compose -f docker-compose.dev.yml exec app python manage.py test "${@:2}"
    ;;
  *)
    echo "Usage: $0 {up|down|build|logs|shell|migrate|test}"
    exit 1
esac