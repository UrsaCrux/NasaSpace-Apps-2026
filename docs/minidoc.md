# Documenting the code with minidoc

The project uses [minidoc](https://gitlab.com/matsuori/minidoc): a tiny,
comment-based documentation convention. A doc is a normal comment that ends
on the line **directly above** a declaration. Its optional first line, in
parentheses, lists the arguments; the rest is free text.

## C / C++ (`cpp/`)

```cpp
// (double nir, double red)
// normalised difference vegetation index, in [-1, 1]; returns 0 when nir + red is 0
FS_API double fs_ndvi(double nir, double red);
```

In Emacs, minidoc shows this doc above any line that uses `fs_ndvi`. Setup
(see the minidoc README for more):

```elisp
(add-to-list 'load-path "/path/to/NasaSpace-Apps-2026/.tools/minidoc")
(require 'minidoc)
(global-minidoc-mode 1)
```

`cpp/.minidoc` marks `cpp/` as the minidoc project root.

## Python (`fieldshift/`)

minidoc itself only reads C/C++, so the Python code — including the whole
map abstraction layer — follows the **same convention** with `#` comments,
and `tools/minidoc_py.py` exports it in the same Markdown layout:

```python
# (float lon, float lat, float scale = None)
# centres the map on a point; keeps the current scale when none is given
@abstractmethod
def set_center(self, lon, lat, scale=None):
```

Rules (same as minidoc):

- No blank line between the comment and the declaration (decorators may sit
  between them).
- Module- and class-level functions, classes and variables are indexed, and
  `self.x = ...` attributes in `__init__`.
- Names starting with `_` are private and not exported (except `__init__`).
- Separator lines like `# -----` are ignored.

## Generating `docs/api/`

```bash
make docs
```

- `docs/api/CPP_API.md` — `emacs --batch -l .tools/minidoc/minidoc.el -f minidoc-batch-export`
  (minidoc is cloned into `.tools/minidoc` the first time).
- `docs/api/PYTHON_API.md` — `python3 tools/minidoc_py.py fieldshift`.

Regenerate and commit these files whenever you change a documented
declaration.

## Known gotcha

minidoc decides that a `{` opens a function body when there is a `)` in the
text before it (up to the previous `;`, `{` or `}`). Parentheses in a comment
or a macro right above `extern "C" {` therefore hide every declaration of the
block. That is why `FS_API` lives in `export.h` and the top comment of
`fieldshift.h` has no parentheses.
