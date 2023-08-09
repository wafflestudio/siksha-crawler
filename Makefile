.PHONY: default
default:
	@echo "Specify the target"
	@exit 1

.PHONY: lint
lint:
	black --check .
	pylint --recursive=yes .

.PHONY: crawl
crawl:
	python3 handler.py \
		--restaurant $(RESTAURANT) \
		--date $(DATE)
