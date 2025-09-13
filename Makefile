.PHONY: default
default:
	@echo "Specify the target"
	@exit 1

.PHONY: lint
lint:
	uv run ruff check . --fix
	uv run ruff format .
