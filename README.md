# PREDICT — Avan data portal (static build)

This project builds a **single, self-contained HTML file** that lets users **search, browse, and select variables** per dataset and **download the selection as CSV**.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python build.py
open dist/variables_browser.html  # or double-click the file
```

## Source data
Place your YAML files in the `data/` directory. The builder pairs files named like:

- `*_register_codebook.yaml` (variables)
- `*_register_meta.yaml`     (dataset descriptors)

The meta YAML should provide at least: `title`, `subtitle`, `info`. The codebook YAML contains variables as top-level mapping keys.

## Display rules
- Each **variable** shows **Label** (from `label` or `labels`), **Variable name** (YAML key), **Source variable name** (`colname_silver`), and **Notes** (`notes`).
- We **exclude** any variables whose `tags` contain `internal` or `identifier` (case-insensitive). `tags` may be a string or an array; both are supported.
- The page is organized by dataset (`title`, `subtitle`, `info`).

## Determinism
Builds are deterministic: datasets and variables are sorted, and no timestamps are embedded. Repeated builds with unchanged inputs yield byte-identical output.

## Provenance
The footer lists input files and a SHA-256 of their concatenated contents for traceability.

## Customization
Edit `templates/index.html.j2` to adjust layout, colors, and behaviors. Re-run `python build.py` to regenerate.
