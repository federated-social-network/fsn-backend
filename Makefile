.PHONY: help install dev run test clean migrate docker-build docker-run lint format

# Default target
help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make dev          - Install development dependencies"
	@echo "  make run          - Run the development server"
	@echo "  make test         - Run tests with pytest"
	@echo "  make clean        - Remove Python cache files"
	@echo "  make migrate      - Create database tables"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run   - Run Docker container"
	@echo "  make lint         - Run code linting"
	@echo "  make format       - Format code with black"

# Install production dependencies
install:
	pip install -r requirements.txt

# Install development dependencies (includes testing tools)
dev:
	pip install -r requirements.txt
	pip install black flake8 isort

# Run development server
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
test:
	pytest -v

# Run tests with coverage
test-coverage:
	pytest --cov=app --cov-report=html --cov-report=term

# Clean Python cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage

# Create database tables (run migrations)
migrate:
	python -c "from app.database import Base, engine; Base.metadata.create_all(bind=engine); print('Database tables created successfully')"

# Build Docker image
docker-build:
	docker build -t fsn-backend .

# Run Docker container
docker-run:
	docker run -p 8080:8080 --env-file .env fsn-backend

# Run with docker-compose (if you have docker-compose.yml)
docker-compose-up:
	docker-compose up -d

docker-compose-down:
	docker-compose down

# Lint code
lint:
	flake8 app/ tests/ --max-line-length=120 --exclude=__pycache__

# Format code
format:
	black app/ tests/ --line-length=120
	isort app/ tests/

# Create Gmail OAuth refresh token
create-token:
	python create_refresh_token.py

# Run specific instance (A or B)
run-instance-a:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env.InstanceA

run-instance-b:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8001 --env-file .env.InstanceB

# Database shell (PostgreSQL)
db-shell:
	@echo "Connect to your PostgreSQL database using the DATABASE_URL from .env"

# Show project structure
tree:
	tree -I '__pycache__|*.pyc|.git|.pytest_cache' -L 3
