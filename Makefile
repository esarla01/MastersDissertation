# Entry points for reproducing and checking the results.
#
#   make verify      everything below, offline, non-zero exit on any mismatch
#   make harness     the regression gates
#   make setup       create .venv from the lockfile
#
# PYTHONDONTWRITEBYTECODE is not tidiness. CONFIRM_SPEND = None and = 1836 are
# both four characters, so editing one for the other leaves the file the same
# SIZE and, within a second, the same MTIME -- the exact pair Python's bytecode
# cache validates on. A stale .pyc then serves the armed version from a clean
# source file, which cost an hour of this repository's life.
PY := PYTHONDONTWRITEBYTECODE=1 python3 -B
# Absolute: the notebook recipes cd into fourarm/ first, and a relative
# path would then resolve to fourarm/.venv, which does not exist.
VENV := $(CURDIR)/.venv/bin/python
NBEXEC := $(VENV) -m jupyter nbconvert --to notebook --execute \
          --ExecutePreprocessor.timeout=900

.PHONY: all verify verify-ex1 verify-ex2 appendix harness manifest probes spend-check setup clean help

all: verify

help:
	@sed -n '2,8p' Makefile

# ---------------------------------------------------------------------------

verify: spend-check manifest probes verify-ex1 verify-ex2 appendix harness
	@echo
	@echo "all checks passed"

# No cell may carry a filled-in CONFIRM_SPEND. Committing one turns Run All on
# a fresh clone into a paid sweep; six cells reached git that way.
spend-check:
	@echo "== spend gates =="
	@if grep -rnE '^[[:space:]]*"?[[:space:]]*CONFIRM_SPEND[[:space:]]*=[[:space:]]*[0-9]' \
	     --include='*.ipynb' --include='*.py' fourarm attic 2>/dev/null \
	     | grep -v 'set CONFIRM_SPEND'; then \
	  echo "ARMED SPEND GATE -- set it back to None"; exit 1; \
	else echo "  no cell arms the spend gate"; fi

# Every published run file present and holding what it claims, and nothing on
# disk that no list accounts for.
manifest:
	@echo "== run-file manifest =="
	@cd fourarm && $(PY) run_files.py

# The frozen probe sets: content hashes, the 278 -> 185 -> 162 derivation
# Appendix D describes, and the six per-source counts in Table D.1.
probes:
	@echo "== probe sets =="
	@cd fourarm && $(PY) harvest/probe_audit.py | tail -1

# The notebook's table checks read the thesis LaTeX. Without it they report
# SKIPPED, print "0 of 13", and still exit 0 -- so the count is extracted and
# required to be 13, rather than printed as a constant. A green verify that
# checked nothing is worse than a red one.
verify-ex1:
	@echo "== Experiment 1 =="
	@cd fourarm && $(PY) analysis/ex1/ex1_verify_tables.py --quiet
	@cd fourarm && cp notebooks/ex1/ex1_reproduce_tables.ipynb analysis/ex1/.verify.ipynb; \
	  if $(NBEXEC) --inplace analysis/ex1/.verify.ipynb >/dev/null 2>&1; then \
	    got=$$($(PY) -c "import json,sys,re; nb=json.load(open('analysis/ex1/.verify.ipynb')); \
t=[''.join(o.get('text',[])) for c in nb['cells'] for o in c.get('outputs',[]) if 'text' in o]; \
m=[re.search(r'(\d+) of (\d+) tables regenerated', x) for x in t]; \
m=[x for x in m if x][-1:]; print(m[0].group(0) if m else 'no audit line')"); \
	    rm -f analysis/ex1/.verify.ipynb; \
	    echo "  ex1_reproduce_tables.ipynb: $$got"; \
	    case "$$got" in "13 of 13"*) ;; *) \
	      echo "  EXPECTED 13 of 13. Tables are checked against the thesis LaTeX;"; \
	      echo "  set THESIS_REPO to it (default ~/Desktop/msc-paper) or they SKIP."; \
	      exit 1;; esac; \
	  else rm -f analysis/ex1/.verify.ipynb; echo "  ex1_reproduce_tables.ipynb FAILED"; exit 1; fi

# The paid cells are inert with CONFIRM_SPEND unset, so this is offline. It
# executes copies: the tracked notebooks keep the outputs of the runs that were
# actually bought.
verify-ex2:
	@echo "== Experiment 2 =="
	@cd fourarm && for nb in notebooks/ex2/ex2_q1_derivation notebooks/ex2/ex2_q2_precedence \
	    notebooks/ex2/ex2_q3_remediation notebooks/ex2/ex2_q3_repair; do \
	  cp $$nb.ipynb $$nb.verify.ipynb; \
	  if $(NBEXEC) --inplace $$nb.verify.ipynb >/dev/null 2>&1; then \
	    echo "  $$(basename $$nb) ok"; else echo "  $$(basename $$nb) FAILED"; \
	    rm -f $$nb.verify.ipynb; exit 1; fi; \
	  rm -f $$nb.verify.ipynb; \
	done

# The appendix and Chapter 3 tables, rebuilt from the modules that define
# them and checked against the thesis.
appendix:
	@echo "== appendix tables =="
	@cd fourarm && cp notebooks/appendix/appendix_tables.ipynb notebooks/appendix/.verify.ipynb; \
	  if $(NBEXEC) --inplace notebooks/appendix/.verify.ipynb >/dev/null 2>&1; then \
	    got=$$($(PY) -c "import json,re; nb=json.load(open('notebooks/appendix/.verify.ipynb')); \
t=[''.join(o.get('text',[])) for c in nb['cells'] for o in c.get('outputs',[]) if 'text' in o]; \
m=[x for x in (re.search(r'(\d+) of (\d+) appendix tables', y) for y in t) if x][-1:]; \
print(m[0].group(0) if m else 'no audit line')"); \
	    rm -f notebooks/appendix/.verify.ipynb; \
	    echo "  appendix_tables.ipynb: $$got"; \
	    case "$$got" in "13 of 13"*) ;; *) echo "  EXPECTED 13 of 13."; exit 1;; esac; \
	  else rm -f notebooks/appendix/.verify.ipynb; echo "  appendix_tables.ipynb FAILED"; exit 1; fi

harness:
	@echo "== harness =="
	@pass=0; fail=0; failed=""; \
	for f in harness/h_*.py harness/check_columns.py; do \
	  if $(PY) $$f >/dev/null 2>&1; then pass=$$((pass+1)); \
	  else fail=$$((fail+1)); failed="$$failed $$(basename $$f .py)"; fi; \
	done; \
	echo "  $$pass passed, $$fail failed$${failed:+ ($$failed)}"; \
	test $$fail -eq 0

# ---------------------------------------------------------------------------

setup:
	python3 -m venv .venv
	$(VENV) -m pip install --quiet --upgrade pip
	$(VENV) -m pip install --quiet -r requirements.lock
	@echo "environment ready; run 'make verify'"

clean:
	find . -name '__pycache__' -type d -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.verify.ipynb' -delete
	rm -f fourarm/analysis/ex1/.verify.ipynb
