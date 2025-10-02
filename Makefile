SHELL := /bin/zsh

.PHONY: setup lint fmt docs api

setup:
	python3 -m pip install -r requirements.txt
	pre-commit install

lint:
	pre-commit run --all-files | cat

fmt:
	black .
	flake8 | cat

docs:
	@echo "Docs located in docs/; update ARCHITECTURE.md and MANIFEST.md when adding files."

api:
	uvicorn src.api.app:app --reload | cat


