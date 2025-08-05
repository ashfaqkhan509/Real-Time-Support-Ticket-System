PROJECT_NAME=Real Time Customer Support API

# Build containers without starting them
build:
	docker compose build

# Start services without rebuilding
start:
	docker compose up

# Build and start
up:
	docker compose up --build

# Stop all services
down:
	docker compose down

# Restart services (rebuild)
restart:
	docker compose down
	docker compose up --build

# View logs
logs:
	docker compose logs -f

# Open a shell inside FastAPI container
web-shell:
	docker compose exec web sh

# Run Alembic migration (if using Alembic)
migrate:
	docker compose exec web alembic upgrade head

# Create a new Alembic revision (provide msg="your message")
makemigration:
	docker compose exec web alembic revision --autogenerate -m "$(msg)"

# Show container status
ps:
	docker compose ps

# Remove everything and prune
clean:
	docker compose down -v
	docker system prune -af --volumes
