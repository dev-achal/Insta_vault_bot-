.PHONY: install run test lint format clean

# Install dependencies in editable mode
install:
	pip install -e .

# Run the telegram bot (clears stuck port first)
run:
	@echo "🚀 Starting InstaVault Bot..."
	@fuser -k 8099/tcp 2>/dev/null || true
	PYTHONPATH=src python -m instavault

# Run tests
test:
	pytest tests/

# Run linters (flake8/black)
lint:
	flake8 src/ tests/ scripts/
	black --check src/ tests/ scripts/

# Format code with black
format:
	black src/ tests/ scripts/

# Clean cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
