.PHONY: default
default:
	@echo "Specify the target"
	@exit 1

.PHONY: lint
lint:
	black --check .
	pylint --recursive=yes .
