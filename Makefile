.PHONY: install test lint demo clean

## install in editable mode with dev extras
install:
	pip install -e ".[dev]"

## run the test suite
test:
	pytest -q

## run the linter
lint:
	ruff check flakehound tests

## analyse a bundled flaky demo end-to-end
demo:
	flakehound examples/flaky_random.py::test_alice_wins -n 40

## remove build and cache artefacts
clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
