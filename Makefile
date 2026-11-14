# Field Shift - common tasks.  Run `make help`.

PYTHON      ?= python3
EMACS       ?= emacs

# --- QGIS environment ------------------------------------------------------
# If a micromamba environment with QGIS exists, `make run` / `make test` use
# it automatically; otherwise the system Python is used.
#   make env              create it (conda-forge QGIS 4, no compiling)
#   make run CONDA=0      force the system Python
MAMBA       ?= $(firstword $(shell command -v micromamba 2>/dev/null) \
                           $(wildcard $(HOME)/.local/bin/micromamba))
MAMBA_ROOT  ?= $(HOME)/micromamba
ENV_NAME    ?= fieldshift
CONDA       ?= 1
ENV_DIR     := $(MAMBA_ROOT)/envs/$(ENV_NAME)

ifeq ($(CONDA)$(if $(MAMBA),y)$(if $(wildcard $(ENV_DIR)/bin/python),y),1yy)
  RUN := $(MAMBA) run -r $(MAMBA_ROOT) -n $(ENV_NAME) python
else
  RUN := $(PYTHON)
endif
BUILD_DIR   := cpp/build
MINIDOC_DIR := .tools/minidoc
MINIDOC_URL := https://gitlab.com/matsuori/minidoc.git

# language of the texts: make run LANG_UI=es  (see docs/i18n.md). Not LANG,
# which the operating system already uses.
LANG_UI     ?=

.PHONY: help run env which cpp test docs docs-cpp docs-python clean

help:
	@echo "make env          create the micromamba environment with QGIS 4"
	@echo "make run          start the application (uses the env if present)"
	@echo "make run LANG_UI=es   same, with the texts in Spanish (en, es)"
	@echo "make which        show which Python make run will use"
	@echo "make cpp          build the C++ library in cpp/build"
	@echo "make test         run the tests"
	@echo "make docs         regenerate docs/api/ with minidoc"
	@echo "make clean        remove build outputs"

run:
	$(RUN) -m fieldshift $(if $(LANG_UI),--lang $(LANG_UI))

which:
	@echo "make run uses: $(RUN)"
	@$(RUN) -c "import sys; print(sys.executable, sys.version.split()[0])"
	@$(RUN) -c "import qgis.core as q; print('QGIS', q.Qgis.version())" 2>/dev/null \
	  || echo "QGIS: not importable (run 'make env', see docs/README.md)"

env:
	@test -n "$(MAMBA)" || { echo "micromamba not found: see docs/README.md"; exit 1; }
	$(MAMBA) create -y -r $(MAMBA_ROOT) -n $(ENV_NAME) -c conda-forge "qgis>=4" python=3.12

cpp:
	cmake -S cpp -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=Release
	cmake --build $(BUILD_DIR) --config Release

test:
	$(RUN) -m unittest discover -s tests -v

docs: docs-cpp docs-python

$(MINIDOC_DIR)/minidoc.el:
	git clone --depth 1 $(MINIDOC_URL) $(MINIDOC_DIR)

# C/C++ declarations: exported by minidoc itself (needs Emacs >= 27.1)
docs-cpp: $(MINIDOC_DIR)/minidoc.el
	@mkdir -p docs/api
	$(EMACS) --batch -l $(MINIDOC_DIR)/minidoc.el -f minidoc-batch-export \
	  $(CURDIR)/cpp ../docs/api/CPP_API.md

# Python abstraction layer: same comment convention, same Markdown layout
docs-python:
	@mkdir -p docs/api
	$(RUN) tools/minidoc_py.py fieldshift docs/api/PYTHON_API.md

clean:
	rm -rf $(BUILD_DIR)
