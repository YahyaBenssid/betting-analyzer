.PHONY: install install-dev run scan arbitrage dashboard test lint clean

# Installation
install:
	pip install -r requirements.txt
	playwright install chromium

install-dev:
	pip install -r requirements-dev.txt
	playwright install chromium

# Lancement
run:
	python main.py scan --sport football --min-ev 3 --min-confidence 60

scan:
	python main.py scan --sport football --min-ev $(EV) --min-confidence $(CONF) --bankroll $(BR)
EV ?= 3
CONF ?= 60
BR ?= 1000

arbitrage:
	python main.py arbitrage --sport all

dashboard:
	python main.py dashboard

# Tests
test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --cov=. --cov-report=html --cov-report=term-missing

# Qualité
lint:
	ruff check . --fix
	mypy . --ignore-missing-imports

# Nettoyage
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .cache/ htmlcov/ .mypy_cache/ .ruff_cache/
