# PREDICT — Avan Data Portal

Builds a self-contained **HTML file** and **Excel file** for users to explore datasets, search variables, and download selections.

The build is **deterministic**: same inputs → identical output (supports reproducibility).

---

## Quick Start

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
```

**Windows:** Use `.venv\Scripts\Activate.ps1` (PowerShell) or `.venv\Scripts\activate.bat` (cmd)

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Build

```bash
python build.py
```

**Outputs:**
- `dist/variables_browser.html` — Web interface
- `dist/variables_browser.xlsx` — Excel file for offline selection

---

## How It Works

**Input:** YAML/Markdown files in `data/`, `config/`, and `content/`  
**Process:** `build.py` discovers datasets, normalizes variables, applies rules, renders HTML/Excel  
**Output:** Self-contained HTML + formatted Excel file in `dist/`

### Build Pipeline

1. Discover datasets from `data/*_register_meta.yaml` files
2. Load codebooks from `data/*_register_codebook.yaml`
3. Normalize variables (standardize field names and types)
4. Apply ignore/filter rules from `config/variables_config.yaml`
5. Build synthetic groups from regex patterns
6. Load dataset descriptions from Markdown or YAML
7. Render HTML via Jinja2 template
8. Export Excel workbook with formatted sheets per dataset
9. Write outputs to `dist/`

---

## Virtual Environment

### Create

```bash
python3 -m venv .venv
```

### Activate

**macOS / Linux:**
```bash
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows (cmd):**
```cmd
.venv\Scripts\activate.bat
```

### Update dependencies

After editing `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Deactivate

```bash
deactivate
```

> **Note:** `.venv/` is gitignored. Each developer maintains their own environment.

---

## File Structure

| Folder/File | Purpose |
|-------------|---------|
| `data/` | Dataset metadata (YAML) and variable codebooks |
| `config/` | Rules for filtering, grouping, and dataset ordering |
| `content/` | Static content: intro, footer, logo |
| `templates/` | Jinja2 HTML template |
| `build.py` | Build script |
| `dist/` | Output directory (gitignored; auto-created) |

---

## Updating the Portal

### Adding a dataset

A dataset consists of required and optional files in `data/`:

**Required:**
- `<dataset>_register_meta.yaml` — Dataset metadata (title, subtitle, info)
- `<dataset>_register_codebook.yaml` — Variable definitions

**Optional:**
- `<dataset>_register_meta.md` — Markdown description (overrides YAML info field)

**Example: Add dataset `foo`**

1. Create `data/foo_register_meta.yaml`:
```yaml
title: Foo dataset
subtitle: Example
```

2. Create `data/foo_register_codebook.yaml`:
```yaml
foo_var:
  colname_silver: "foo_var"
  labels: "Example variable"
  coltypes: "character"
  categories: ["example"]
  notes: "Optional description"
```

3. Optionally, add `data/foo_register_meta.md`:
```markdown
# Foo Dataset

Markdown description with **formatting**, links, and admonitions.

!!! note
    Important info here.
```

4. Rebuild:
```bash
python build.py
```

### Variable fields (codebook)

Common YAML fields are normalized automatically:

| YAML Field | Display Column | Purpose |
|-----------|---|---|
| `colname_silver` | Source variable name | Original database variable |
| `labels`/`label` | Label | Human-readable name |
| `coltypes`/`dtype`/`class` | Type | Data type |
| `categories` | Categories | String or list of category names |
| `tags` | Tags | String or list (for filtering) |
| `notes` | Notes | Optional description |

### Filtering variables: `config/variables_config.yaml`

Hide unwanted variables or create synthetic groups:

```yaml
ignore:
  names:
    - var_to_hide
  name_patterns:
    - "^temp_.*"           # Hide variables starting with temp_
  tags:
    - "internal"           # Hide variables tagged "internal"
  categories:
    - "deprecated"         # Hide variables in "deprecated" category

groups:
  demographics:
    pattern: "^(age|sex|birth).*"
    label: "Demographics"
    notes: "Demographic variables"
    priority: 10
    category_strategy: "union"  # "union" | "intersection" | "override"
```

### Ordering datasets: `config/datasets_config.yaml`

Control dataset grouping and order in the UI:

```yaml
groups:
  - heading: "Cancer & Health"
    datasets:
      - ps_cancer
      - ps_cause-of-death
  - heading: "Patient Data"
    datasets:
      - ps_patient-in
      - ps_patient-out
```

Datasets listed here appear in order. Datasets not listed go to "Other datasets" section.  
If this file is absent, all discovered datasets are listed alphabetically.

### Static content: `content/` folder

Customize the portal interface:

- **`intro.md`** — Portal introduction and usage instructions (displayed before datasets)
- **`footer.md`** — Footer text, links, and legal info (supports Markdown)
- **`logo.png`** — Optional logo (embedded as data URI in footer if present)

Rebuild after changes:
```bash
python build.py
```

#### Supported Markdown

In all Markdown files:
- **Bold**, *italic*, `code` formatting
- Links: `[text](url)`
- Lists, tables
- Admonitions (see below)

#### Admonitions

Highlighted callout boxes. Available types:

```markdown
!!! note
    General information

!!! warning
    Cautions and important notices

!!! danger
    Critical warnings

!!! tip
    Helpful suggestions

!!! info / success / bug / example / quote
    Other admonition types
```

Custom titles:
```markdown
!!! warning "Custom Title"
    Content here
```

---

## Excel Export

The Excel file (`variables_browser.xlsx`) has one sheet per dataset with columns:

| Column | Purpose |
|--------|---------|
| Selection | Empty; users mark chosen variables with "x" |
| Label | Human-readable variable name |
| Notes | Variable description |
| Variable name | YAML key (unique identifier) |
| Source variable name | Original database variable name |
| Categories | Variable categories |
| Grouped | Yes/No (synthetic group variable) |
| Members | For groups: member variable names |

---

## Template Customization

Edit the HTML template to change layout, styling, or behavior:

```text
templates/index.html.j2
```

Rebuild:
```bash
python build.py
```

---

## Deterministic Builds

Reproducibility is guaranteed:
- Input files are always processed in sorted order
- No timestamps or random values embedded
- Same inputs produce byte-identical output

---

## Build Information

The generated HTML includes an expandable footer section with:
- **Build date** — ISO timestamp when the portal was built
- **Git SHA** — Current commit hash (if in a git repo)

Check out the exact version used:
```bash
git checkout <full-sha-hash>
```

---

## Clean Rebuild

Force a full rebuild:

```bash
rm -rf dist/
python build.py
```

---

## Dependencies

Managed via `requirements.txt`:
```
pyyaml==6.0.1
jinja2==3.1.4
markdown==3.6
pymdown-extensions==10.5
openpyxl==3.1.2
```

Update with:
```bash
pip install -r requirements.txt
```
