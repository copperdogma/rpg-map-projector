PYTHON ?= python3

.PHONY: methodology-compile methodology-check skills-sync skills-check triage-facts triage-facts-check local-app local-status local-stop app-test app-build app-e2e app-check

methodology-compile:
	$(PYTHON) scripts/methodology_graph.py build

methodology-check:
	$(PYTHON) scripts/methodology_graph.py check

skills-sync:
	./scripts/sync-agent-skills.sh

skills-check:
	./scripts/sync-agent-skills.sh --check

triage-facts:
	$(PYTHON) scripts/triage_facts.py

triage-facts-check:
	$(PYTHON) scripts/triage_facts.py --json >/dev/null

local-app:
	npm run local:app

local-status:
	npm run local:status

local-stop:
	npm run local:stop

app-test:
	npm run test

app-build:
	npm run build

app-e2e:
	npm run test:e2e

app-check:
	npm run check
