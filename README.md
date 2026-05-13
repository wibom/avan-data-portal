# PREDICT — Avan Data Portal

Builds a self-contained **HTML file** and **Excel file** for users to
explore datasets, search variables, and download selections.

The build can also export all portal data as a standalone **`data.json`**
file (see [JSON Export](#json-export)), which can be consumed by a
separate app to recreate the interactive explorer without rebuilding from
source.

The build is **deterministic**: same inputs → identical output
(see [Deterministic Builds](#deterministic-builds)).

---

## Quick Start

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
```

**Windows:** Use `.venv\Scripts\Activate.ps1` (PowerShell) or
`.venv\Scripts\activate.bat` (cmd)

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

### CLI Options

| Flag | Description |
|------|-------------|
| `--output-dir PATH` | Write outputs to *PATH* instead of `./dist` |
| `--export-json` | Also write `data.json` to the output directory (see [JSON Export](#json-export)) |
| `--verbose`, `-v` | Show debug-level log messages |
| `--quiet`, `-q` | Suppress informational messages (warnings only) |

---

## How It Works

**Input:** YAML/Markdown files in `data/`, `config/`, and `content/`
**Process:** `build.py` discovers datasets, normalizes variables,
applies rules, renders HTML/Excel
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

## Project Structure

```text
predict-data-portal/
├── build.py                        # Build script (entry point)
├── requirements.txt                # Python dependencies
├── README.md
├── config/
│   ├── datasets_config.yaml        # Dataset grouping and ordering
│   └── variables_config.yaml       # Variable ignore rules and groups
├── content/
│   ├── intro.md                    # Portal introduction (Markdown)
│   ├── footer.md                   # Portal footer (Markdown)
│   └── logo.png                    # Logo image (embedded as data URI)
├── data/                           # One set of files per dataset:
│   ├── <dataset>_register_meta.yaml      # Dataset metadata
│   ├── <dataset>_register_codebook.yaml  # Variable definitions
│   └── <dataset>_register_meta.md        # Dataset description (optional)
├── static/                         # Files copied verbatim to dist/
├── templates/
│   └── index.html.j2               # Jinja2 HTML template
└── dist/                           # Build output (tracked)
    ├── variables_browser.html
    └── variables_browser.xlsx
```

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

> **Note:** `.venv/` is gitignored. Each developer maintains their own
> environment.

---

## Updating the Portal

### Adding a dataset

A dataset consists of required and optional files in `data/`:

**Required:**

- `<dataset>_register_meta.yaml` — Dataset metadata (title, subtitle, info)
- `<dataset>_register_codebook.yaml` — Variable definitions

**Optional:**

- `<dataset>_register_meta.md` — Markdown description (overrides YAML info
  field)

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

### Static content: `content/` folder

Customize the portal interface:

- **`intro.md`** — Portal introduction and usage instructions (displayed
  before datasets)
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

## Configuration Reference

### `config/datasets_config.yaml`

Controls how datasets are grouped and ordered in the UI.

```yaml
groups:
  - heading: "Display heading"
    datasets:
      - dataset_id_1
      - dataset_id_2
```

| Key | Type | Description |
|-----|------|-------------|
| `heading` | string | Section heading displayed in the UI |
| `datasets` | list[string] | Ordered list of dataset IDs |

Datasets not listed appear under "Other datasets".  If this file is absent,
all discovered datasets are listed alphabetically.

### `config/variables_config.yaml`

Controls variable filtering and synthetic grouping.

#### `ignore` section

```yaml
ignore:
  names:
    - var_to_hide               # Exact variable name
  name_patterns:
    - "^temp_.*"                # Regex pattern
  tags:
    - "internal"                # Remove variables with this tag
  categories:
    - "deprecated"              # Remove variables in this category
```

| Key | Type | Description |
|-----|------|-------------|
| `names` | list[string] | Exact variable names to remove |
| `name_patterns` | list[string] | Regex patterns (glob fallback on parse error) |
| `tags` | list[string] | Variables with any of these tags are removed |
| `categories` | list[string] | Variables in any of these categories are removed |

#### `groups` section

```yaml
groups:
  group_id:
    pattern: "^diagnosis_[0-9]{2}$"
    label: "Diagnosis"
    notes: "ICD-coded diagnosis fields."
    source_variable_name_grouped: "DIA1-DIA30"
    priority: 10
    category_strategy: "union"
    csv_expand: "members"
    categories_override: []
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pattern` | string | *(required)* | Regex to match member variable names |
| `label` | string | group ID | Display label for the group |
| `notes` | string | `""` | Description |
| `source_variable_name_grouped` | string | `""` | Source variable name shown in the UI |
| `priority` | integer | `1000` | Sort order (lower = earlier) |
| `category_strategy` | string | `"union"` | `"union"`, `"intersection"`, or `"override"` |
| `categories_override` | list[string] | `[]` | Fixed categories when strategy is `"override"` |
| `csv_expand` | string | `""` | Client-side CSV expansion mode |

### Codebook YAML fields

Variable definitions in `<dataset>_register_codebook.yaml`:

| YAML Field | Display Column | Purpose |
|------------|----------------|---------|
| `colname_silver` | Source variable name | Original database variable |
| `labels` / `label` | Label | Human-readable name |
| `coltypes` / `dtype` / `class` | Type | Data type |
| `categories` | Categories | String or list of category names |
| `tags` | Tags | String or list (used for filtering) |
| `notes` | Notes | Optional description |

### Meta YAML fields

Dataset metadata in `<dataset>_register_meta.yaml`:

| YAML Field | Purpose |
|------------|---------|
| `title` | Dataset title |
| `subtitle` | Subtitle / source description |
| `info` | List of strings (fallback when no `.md` file exists) |
| `filename` | Source TSV filename |
| `n_individuals` | Number of unique individuals |
| `n_observations` | Number of rows |
| `n_columns` | Number of columns |
| `idcols_individuals` | Individual ID column(s) |
| `idcols_observations` | Observation ID column(s) |
| `observation_descriptions` | What each row represents |
| `tags` | Dataset-level tags |
| `categories` | Dataset categories |
| `ingest_date` | Date data was ingested (YYYY-MM-DD) |

---

## Excel Export

The Excel file (`variables_browser.xlsx`) has one sheet per dataset with
columns:

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

## JSON Export

The `--export-json` flag writes `dist/data.json` (or
`<output-dir>/data.json`) alongside the normal HTML and Excel outputs.
The file contains everything a separate app needs to recreate the
interactive explorer — rendered HTML fragments, all dataset and variable
data, and build metadata — with no dependency on this repo's source files
or the Python build toolchain.

```bash
python build.py --export-json
```

The variable lists for individual datasets (`.docx` and `.xlsx` files)
are available in the `static/` directory of this repo and can be linked
to from a consumer app.

### JSON structure

```json
{
  "meta": {
    "build_date": "2026-05-13T12:00:00",
    "git_sha": "abc1234...",
    "provenance": "file sha256\n..."
  },
  "intro_html": "<p>...</p>",
  "footer_html": "<p>...</p>",
  "datasets": [
    {
      "heading": "National board of health and welfare",
      "datasets": [
        {
          "id": "ps_cancer",
          "title": "National Cancer Register",
          "subtitle": "...",
          "info_html": "<p>...</p>",
          "variables": [ ... ],
          "var_map": { ... },
          "var_map_all": { ... }
        }
      ]
    }
  ]
}
```

| Key | Description |
|-----|-------------|
| `meta` | Build timestamp, git commit SHA, and file provenance hashes |
| `intro_html` | Rendered HTML from `content/intro.md` |
| `footer_html` | Rendered HTML from `content/footer.md` (logo embedded as data URI) |
| `datasets` | Array of display groups, each with a `heading` and `datasets` list |
| `variables` | Ordered list of variables/groups for each dataset |
| `var_map` | Name → variable metadata (non-grouped variables) |
| `var_map_all` | Name → variable metadata (all variables including group members) |

---

## Selection Persistence

Variable selections are saved to the browser's `sessionStorage`, so they
survive page reloads within the same tab.  Selections are automatically
cleared when the tab is closed.  Clicking **Clear** also removes the
stored selection.

No data leaves the browser — `sessionStorage` is local and not sent to
any server.

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

The build pipeline is designed for reproducibility:

- Input files are always processed in **sorted order**.
- No random values are embedded.
- The **build timestamp** is derived deterministically (see below)
  rather than using the current wall-clock time.

### Timestamp resolution order

1. **`SOURCE_DATE_EPOCH`** environment variable (integer Unix timestamp).
   This is the [reproducible-builds.org standard](https://reproducible-builds.org/docs/source-date-epoch/)
   and is the recommended mechanism for CI and release builds:

   ```bash
   SOURCE_DATE_EPOCH=$(date +%s) python build.py
   ```

2. **Newest input-file mtime** — if `SOURCE_DATE_EPOCH` is not set, the
   build date is derived from the most recently modified input file.
   This means that when no input files change, repeated builds produce
   the same timestamp.

3. **Current wall-clock time** — as a last resort (e.g. when file
   modification times are unreliable), the current time is used.

### Verifying reproducibility

```bash
# Two consecutive builds should produce byte-identical output:
SOURCE_DATE_EPOCH=1700000000 python build.py
cp dist/variables_browser.html /tmp/a.html
SOURCE_DATE_EPOCH=1700000000 python build.py
diff /tmp/a.html dist/variables_browser.html  # No output = identical
```

---

## Build Information

The generated HTML includes an expandable footer section with:

- **Build date** — ISO timestamp (see Deterministic Builds above)
- **Git SHA** — Current commit hash (if in a git repo)

Check out the exact version used:

```bash
git checkout <full-sha-hash>
```

---

## Development

### Requirements

- Python ≥ 3.10

### Dev tooling

Install dev dependencies (ruff, mypy, pytest):

```bash
pip install -e ".[dev]"
```

### Linting & formatting

```bash
ruff check .          # lint
ruff format --check . # format check
```

### Type checking

```bash
mypy build.py
```

### Tests

```bash
pytest
```

---

## Clean Rebuild

Force a full rebuild:

```bash
rm -rf dist/
python build.py
```

---

## Troubleshooting

### "Dataset 'X' listed in datasets_config.yaml not found"

The dataset ID in `config/datasets_config.yaml` does not match any file
in `data/`.  Ensure that `data/<id>_register_meta.yaml` exists and that
the ID matches exactly (case-sensitive, hyphens vs underscores matter).

### "Regex compilation failed for '…'"

A pattern in `variables_config.yaml` is not valid Python regex.  The build
falls back to treating it as a glob pattern, which may not match as
intended.  Fix the regex syntax or use a glob (e.g. `*.tmp`).

### "Unrecognised key(s) in group '…'"

A group entry in `variables_config.yaml` contains a key that the build
script does not recognise.  This is usually a typo (e.g. `patern` instead
of `pattern`).  Recognised keys: `pattern`, `label`, `notes`,
`source_variable_name_grouped`, `priority`, `category_strategy`,
`categories_override`, `csv_expand`.

### Build output differs between runs

If you are not setting `SOURCE_DATE_EPOCH` and your input files have not
changed, the build timestamp should still be stable (derived from file
mtimes).  If builds still differ, check whether any tool is modifying file
timestamps (e.g. `git checkout` resets mtimes).  Set `SOURCE_DATE_EPOCH`
explicitly for guaranteed reproducibility.

---

## Dependencies

Managed via `requirements.txt`:

```text
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

---

## Deploy

Requires SSH key authentication configured for the target host (see
`~/.ssh/config`), such as:

```shell
Host predict
  HostName cpanel-new.its.umu.se
  User predict
  IdentityFile ~/.ssh/id_ed25519_cPanel
```

Deploy using:
```bash
rsync -av --exclude='variables_browser.html' predict-data-portal/dist/ predict:www/ && \
  rsync -av predict-data-portal/dist/variables_browser.html predict:www/index.html
```
