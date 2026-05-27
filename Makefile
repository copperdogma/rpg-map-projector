PYTHON ?= python3

.PHONY: methodology-compile methodology-check skills-sync skills-check triage-facts triage-facts-check

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
