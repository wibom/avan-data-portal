# PREDICT — Avan Data Portal (static build)

This project builds a **single, self-contained HTML file** that lets users
**search, browse, and select variables** per dataset and **download selections as CSV**.

The build system is deterministic: repeated builds with the same inputs produce
byte-identical output.

---

## Quick start

### 1. Clone the repository

```bash
git clone <repo-url>
cd <repo-name>
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

Activate it:

**macOS / Linux**
```bash
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
.venv\Scripts\Activate.ps1
```

> Note:
> The `.venv/` directory is intentionally **not** tracked in Git.
> Each developer creates their own local virtual environment.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Build the static HTML

```bash
python build.py
```

### 5. Open the result

Open the generated file in your browser:

```text
dist/variables_browser.html
```

You can double-click the file or open it from the command line.

---

## Requirements

- Python 3.x
- Dependencies are defined in `requirements.txt`

---

## Repository hygiene

The following files and directories are intentionally excluded from version control:

- `.venv/` (local Python virtual environment)
- `__pycache__/`
- `.pyc` files

Only source code, configuration, and input data are tracked.

---

## Source data

Place dataset files in the `data/` folder, using the following naming scheme.

### Required files (must be present)

| Purpose                   | File pattern                   | Required |
|---------------------------|--------------------------------|----------|
| Dataset metadata          | `*_register_meta.yaml`         | Yes      |
| Dataset variable codebook | `*_register_codebook.yaml`     | Yes      |

### Optional files

| Purpose                         | File pattern               | Required |
|--------------------------------|----------------------------|----------|
| Dataset description (Markdown) | `*_register_meta.md`       | No (recommended) |

---

## Dataset discovery rules

A dataset **exists only if** the file:

```text
data/<dataset>_register_meta.yaml
```

exists.

Given dataset ID `<dataset>`, the builder then looks for:

```text
data/<dataset>_register_codebook.yaml   # required: variables
data/<dataset>_register_meta.md         # optional: markdown description
```

Dataset descriptions are resolved in this order:

1. `<dataset>_register_meta.md` (Markdown)
2. `info:` list inside `<dataset>_register_meta.yaml`
3. (none)

---

## Codebook format

Codebook YAML files must contain a **top-level mapping**, where each key is a
variable name.

Example:

```yaml
birthdate:
  colname_silver: "birthdate"
  labels: "Date of birth"
  coltypes: "date"

sex:
  colname_silver: "sex"
  labels: "Sex"
  coltypes: "character"
  categories:
    - "demography"
```

Common supported fields:

- `colname_silver` → displayed as “Source variable name”
- `labels` / `label` → used as the human-readable label
- `coltypes` / `dtype` / `class` → displayed as “Type”
- `categories` → list or single string
- `tags` → string or list
- `notes` → optional

All fields are normalized automatically.

---

## How to add a new dataset

To introduce a dataset named `foo`, add **at least two files**:

### 1. Required: metadata YAML

```text
data/foo_register_meta.yaml
```

Minimal example:

```yaml
title: Foo dataset
subtitle: Demonstration dataset
```

### 2. Required: codebook YAML

```text
data/foo_register_codebook.yaml
```

Minimal example:

```yaml
foo_var:
  colname_silver: "foo_var"
  labels: "Example variable"
  coltypes: "character"
```

### 3. Optional: Markdown description

```text
data/foo_register_meta.md
```

Example:

```markdown
# Foo dataset

This is an example dataset added to the portal.
```

> Important:
> A dataset will **not** be discovered unless
> `foo_register_meta.yaml` exists.
> The Markdown file alone is insufficient.

### After adding files

```bash
python build.py
```

You should see output like:

```text
Assembled dataset: foo variables: 1
```

…and the dataset will appear in the UI.

---

## Display rules

- Variables show:
  - Label
  - Variable name (YAML key)
  - Source variable name (`colname_silver`)
  - Notes

- Dataset descriptions support:
  - Markdown formatting
  - Inline code
  - Links
  - Light HTML tags

- Search matches:
  - Label
  - Variable name
  - Notes
  - Group member names

- Groups are created via patterns in `config/variables_config.yaml`.

---

## Determinism

The build is deterministic:

- Input files processed in sorted order
- No timestamps embedded
- Identical inputs produce identical output HTML

---

## Provenance

The footer of the generated HTML lists:

- All input YAML files
- Dataset Markdown files (if present)
- The config file
- The `intro.md` file
- A combined SHA-256 digest

This supports traceability and reproducibility.

---

## Customization

To adjust UI layout, styling, or behavior, edit:

```text
templates/index.html.j2
```

To create grouped variables or ignore variables, edit:

```text
config/variables_config.yaml
```

Rebuild afterwards:

```bash
python build.py
```

---

## Clean rebuild

If you want to force a clean rebuild:

```bash
rm -rf dist/
python build.py
```
