# Field Shift - common tasks.  Run `make help`.

PYTHON      ?= python3
EMACS       ?= emacs
BUILD_DIR   := cpp/build
MINIDOC_DIR := .tools/minidoc
MINIDOC_URL := https://gitlab.com/matsuori/minidoc.git

.PHONY: help run cpp test docs docs-cpp docs-python clean

help:
	@echo "make run          start the application"
	@echo "make cpp          build the C++ library in cpp/build"
	@echo "make test         run the tests"
	@echo "make docs         regenerate docs/api/ with minidoc"
	@echo "make clean        remove build outputs"

run:
	$(PYTHON) -m fieldshift

cpp:
	cmake -S cpp -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=Release
	cmake --build $(BUILD_DIR) --config Release

test:
	$(PYTHON) -m unittest discover -s tests -v

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
	$(PYTHON) tools/minidoc_py.py fieldshift docs/api/PYTHON_API.md

clean:
	rm -rf $(BUILD_DIR)
