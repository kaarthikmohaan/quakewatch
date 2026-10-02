# QuakeWatch commands. Run from the repository root.
#
# Targets marked [EXECUTE=1] only preview by default; add EXECUTE=1 to run them
# for real. Snowflake runs use warehouse credits. `make extract` has no preview:
# it fetches the one bounded window you ask for, like quakewatch-extract.
#   make load-history CUTOFF=2026-09-29T00:00:00Z            # preview
#   make load-history CUTOFF=2026-09-29T00:00:00Z EXECUTE=1  # run

PY := PYTHONPATH=src:. .venv/bin/python
RUN_FLAG := $(if $(EXECUTE),--execute,)
CUTOFF ?= 2026-09-29T00:00:00Z
MAX ?= 50

.DEFAULT_GOAL := help
.PHONY: help setup lint typecheck fixtures test check extract plan-history capture-history \
	load-preview load load-history bootstrap process quality uniqueness metrics postrun \
	release-parser-v2

help:  ## List targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

# ----- Local development (no network or Snowflake) -----

setup:  ## Install locked dependencies
	uv sync --locked --no-editable

lint:  ## Run ruff
	.venv/bin/ruff check src scripts tests

typecheck:  ## Run mypy on src/quakewatch
	.venv/bin/mypy

fixtures:  ## Build the synthetic test fixtures CI uses
	$(PY) scripts/fixtures/build_phase2_fixture_bundle.py
	$(PY) scripts/fixtures/build_phase2_fixture_attempts.py
	$(PY) scripts/fixtures/build_phase2_old_origin_attempts.py

test: fixtures  ## Run the secret-free test suite
	$(PY) -m unittest discover -s tests

check: lint typecheck test  ## Everything CI runs

# ----- Source extraction (USGS) -----

extract:  ## Fetch one batch: make extract SITE=seattle START=... END=...
	@test -n "$(SITE)" -a -n "$(START)" -a -n "$(END)" || \
		(echo "Usage: make extract SITE=seattle START=2026-09-28T00:00:00Z END=2026-09-29T00:00:00Z"; exit 2)
	uv run quakewatch-extract --site $(SITE) --start $(START) --end $(END)

plan-history:  ## Print the 180 planned history windows
	$(PY) -m quakewatch.history_plan --cutoff $(CUTOFF)

capture-history:  ## Capture up to MAX missing history windows [EXECUTE=1]
	$(PY) -m quakewatch.history_plan --cutoff $(CUTOFF) --resume --max-windows $(MAX) $(RUN_FLAG)

# ----- Snowflake (uses warehouse credits with EXECUTE=1) -----

bootstrap:  ## Create project tables and the procedure [EXECUTE=1]
	$(PY) scripts/pipeline/bootstrap.py $(RUN_FLAG)

load-preview:  ## Check one saved batch: make load-preview MANIFEST=data/raw/<id>/manifest.json
	@test -n "$(MANIFEST)" || (echo "Usage: make load-preview MANIFEST=data/raw/<id>/manifest.json"; exit 2)
	$(PY) -m quakewatch.raw_load $(MANIFEST)

load:  ## Load one saved batch into RAW [EXECUTE=1]
	@test -n "$(MANIFEST)" || (echo "Usage: make load MANIFEST=data/raw/<id>/manifest.json EXECUTE=1"; exit 2)
	$(PY) -m quakewatch.raw_load $(MANIFEST) $(RUN_FLAG)

load-history:  ## Load up to MAX ready history windows into RAW [EXECUTE=1]
	$(PY) -m quakewatch.history_raw_load --cutoff $(CUTOFF) --max-windows $(MAX) $(RUN_FLAG)

process:  ## Process up to MAX loaded attempts with the procedure [EXECUTE=1]
	$(PY) scripts/pipeline/process_history.py --max-attempts $(MAX) $(RUN_FLAG)

quality:  ## Create health views if absent and run reconciliation [EXECUTE=1]
	$(PY) scripts/checks/quality.py $(RUN_FLAG)

uniqueness:  ## Check for duplicate revision and bridge keys [EXECUTE=1]
	$(PY) scripts/checks/uniqueness.py $(RUN_FLAG)

postrun:  ## Aggregate quality and reject-reason check [EXECUTE=1]
	$(PY) scripts/checks/postrun.py $(RUN_FLAG)

metrics:  ## Measure fetch-to-curated latency [EXECUTE=1]
	$(PY) scripts/checks/latency_metrics.py $(RUN_FLAG)

release-parser-v2:  ## Relabel stub rejects and deploy parser version 2 [EXECUTE=1]
	$(PY) scripts/migrations/parser_v2.py $(RUN_FLAG)
