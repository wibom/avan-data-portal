#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Builds a self-contained variables browser HTML.

What this script does:
- Scans ./data for <dataset>_register_codebook.yaml and <dataset>_register_meta.yaml
- For each dataset:
    * Loads variable codebook and meta YAML
    * Prefers dataset description from a Markdown file located in ./data,
      named exactly like the meta YAML but with .md extension:
          <dataset>_register_meta.md
      (e.g., 'ps_cancer_register_meta.md')
      If the Markdown file is missing, falls back to YAML 'info:' list (if present)
    * Applies groups and ignore rules from ./config/variables_config.yaml
    * Outputs a compact JSON structure that the template consumes
- Renders ./templates/index.html.j2 to ./dist/variables_browser.html
- Embeds per-file provenance (SHA-256) and a combined digest
"""

from __future__ import annotations

import json
import re
import fnmatch
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

import yaml  # PyYAML
import markdown  # Markdown processing
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# -------- Paths --------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
CONTENT_DIR = ROOT_DIR / "content"
CONFIG_DIR = ROOT_DIR / "config"
TEMPLATES_DIR = ROOT_DIR / "templates"
DIST_DIR = ROOT_DIR / "dist"

DATASETS_CONFIG = CONFIG_DIR / "datasets_config.yaml"

TEMPLATE_NAME = "index.html.j2"
OUTPUT_HTML = DIST_DIR / "variables_browser.html"

VARIABLES_CONFIG = CONFIG_DIR / "variables_config.yaml"
INTRO_MD = CONTENT_DIR / "intro.md"
FOOTER_MD = CONTENT_DIR / "footer.md"
LOGO_PATH = CONTENT_DIR / "logo.png"

# -------- Utilities --------

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())

def dataset_id_from_filename(file: Path) -> str:
    """
    'ps_cancer_register_codebook.yaml' -> 'ps_cancer'
    'ps_cause-of-death_register_meta.yaml' -> 'ps_cause-of-death'
    """
    name = file.name
    if name.endswith("_register_codebook.yaml"):
        return name[: -len("_register_codebook.yaml")]
    if name.endswith("_register_meta.yaml"):
        return name[: -len("_register_meta.yaml")]
    # Fallback
    stem = file.stem
    stem = stem.replace("_register_codebook", "").replace("_register_meta", "")
    return stem

def read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# --- Minimal Markdown -> HTML for intro.md (dataset Markdown rendered client-side) ---

def md_to_html_intro(text: str) -> str:
    """
    Convert intro.md to simple HTML using markdown with admonitions support.
    """
    if not text:
        return ""
    try:
        # extra includes tables, code fences, footnotes, abbr, attr_list
        # admonition provides !!! callout syntax
        return markdown.markdown(text, extensions=["extra", "admonition"])
    except Exception as e:
        print(f"Warning: Failed to process markdown: {e}")
        parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
        return "".join(f"<p>{escape_html(p)}</p>" for p in parts)

def md_to_html_dataset(text: str) -> str:
    """
    Convert dataset description markdown to HTML.
    Uses the markdown library with support for lists, tables, code blocks, and admonitions.
    """
    if not text:
        return ""
    try:
        # extra includes tables, code fences, footnotes, abbr, attr_list
        # nl2br preserves line breaks
        # admonition provides !!! callout syntax
        return markdown.markdown(text, extensions=["extra", "nl2br", "admonition"])
    except Exception as e:
        print(f"Warning: Failed to process markdown: {e}")
        # Fallback: simple conversion
        parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
        return "".join(f"<p>{escape_html(p)}</p>" for p in parts)

def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#39;")
    )

# -------- variables_config.yaml handling --------

def _compile_ignore_patterns(patterns: List[str]) -> List[re.Pattern]:
    """
    Compile ignore patterns. First try as regex; on failure fallback to glob->regex.
    This makes it robust if an editor provides a glob (e.g., *.tmp).
    """
    compiled: List[re.Pattern] = []
    for raw in patterns or []:
        p = (raw or "").strip()
        if not p:
            continue
        try:
            compiled.append(re.compile(p))
        except re.error:
            compiled.append(re.compile(fnmatch.translate(p)))
    return compiled

def load_variables_config() -> Tuple[Dict[str, Any], List[str], List[re.Pattern], List[str], List[str]]:
    """
    Returns:
      groups_cfg: dict keyed by group_id with fields like pattern, label, notes, etc.
      ignore_names: exact variable names to remove
      ignore_name_patterns: compiled regex patterns for variable names to remove
      ignore_tags: tags from variables that should be ignored
      ignore_categories: category names from variables that should be ignored
    """
    if not VARIABLES_CONFIG.exists():
        return {}, [], [], [], []

    cfg = read_yaml(VARIABLES_CONFIG) or {}
    groups_cfg = (cfg.get("groups") or {})
    ignore_cfg = (cfg.get("ignore") or {})
    ignore_names: List[str] = (ignore_cfg.get("names", []) or [])
    ignore_name_patterns = _compile_ignore_patterns(ignore_cfg.get("name_patterns", []) or [])
    ignore_tags: List[str] = (ignore_cfg.get("tags", []) or [])
    ignore_categories: List[str] = (ignore_cfg.get("categories", []) or [])
    return groups_cfg, ignore_names, ignore_name_patterns, ignore_tags, ignore_categories

# -------- Codebook/meta ingestion --------

def discover_datasets() -> Dict[str, Dict[str, Optional[Path]]]:
    """
    Returns map: dataset_id -> {'codebook': Path|None, 'meta': Path|None}
    """
    out: Dict[str, Dict[str, Optional[Path]]] = {}
    for yml in DATA_DIR.glob("*_register_*.yaml"):
        ds_id = dataset_id_from_filename(yml)
        bucket = out.setdefault(ds_id, {"codebook": None, "meta": None})
        if yml.name.endswith("_register_codebook.yaml"):
            bucket["codebook"] = yml
        elif yml.name.endswith("_register_meta.yaml"):
            bucket["meta"] = yml
    return out

def dataset_md_path_for(ds_id: str, meta_path: Optional[Path]) -> Path:
    """
    Dataset description markdown is stored in ./data alongside YAML,
    named exactly like the meta YAML but with '.md' extension:
        <dataset>_register_meta.md
    If meta_path is None, derive the path from ds_id.
    """
    if meta_path:
        return meta_path.with_suffix(".md")  # ..._register_meta.md
    # meta missing; still support <id>_register_meta.md
    return DATA_DIR / f"{ds_id}_register_meta.md"

def load_dataset_markdown(ds_id: str, meta_path: Optional[Path]) -> Tuple[str, Optional[Path]]:
    """
    Returns (markdown_text, md_path_if_exists) else ("", None)
    """
    md_path = dataset_md_path_for(ds_id, meta_path)
    if md_path.exists() and md_path.is_file():
        return md_path.read_text(encoding="utf-8"), md_path
    return "", None

def extract_var_map_from_codebook(cb_data: Any) -> Dict[str, Dict[str, Any]]:
    """
    Accept multiple codebook YAML shapes:
      - {'variables': [ {name:.., ...}, ... ]}
      - {'variables': { varname: {...}, ... }}
      - {'var_map': { varname: {...}, ... }}
      - Or a mapping {name: {...}} directly
    """
    if not cb_data:
        return {}

    if isinstance(cb_data, dict):
        if "var_map" in cb_data and isinstance(cb_data["var_map"], dict):
            return _normalize_var_map(cb_data["var_map"])

        if "variables" in cb_data:
            vars_obj = cb_data["variables"]
            if isinstance(vars_obj, list):
                return {v.get("name"): _normalize_var(v) for v in vars_obj if v and v.get("name")}
            if isinstance(vars_obj, dict):
                return _normalize_var_map(vars_obj)

        if all(isinstance(v, dict) for v in cb_data.values()):
            return _normalize_var_map(cb_data)

    return {}

def _normalize_var_map(m: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for name, v in m.items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("name", name)
        out[name] = _normalize_var(v)
    return out

def _normalize_var(v: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(v)

    # Standardize name
    if "name" not in out:
        out["name"] = out.get("colname_silver") or out.get("colname") or None

    # Normalize label
    out["label"] = (
        out.get("labels")
        or out.get("label")
        or out.get("name")
        or ""
    )

    # Normalize type
    out["type"] = (
        out.get("coltypes")
        or out.get("dtype")
        or out.get("class")
        or ""
    )

    # Normalize categories — always list
    cats = out.get("categories")
    if isinstance(cats, str):
        cats = [cats]
    out["categories"] = cats or []

    # Normalize tags — always list
    tags = out.get("tags")
    if isinstance(tags, str):
        tags = [tags]
    out["tags"] = tags or []

    # Other fields
    out["notes"] = out.get("notes") or ""
    # source = the source variable name (typically from colname_silver)
    out["source"] = out.get("colname_silver") or out.get("source") or ""
    out["is_group"] = bool(out.get("is_group", False))

    return out

def apply_ignore(var_map: Dict[str, Dict[str, Any]], ignore_names: List[str], ignore_name_patterns: List[re.Pattern], ignore_tags: List[str] = None, ignore_categories: List[str] = None) -> Dict[str, Dict[str, Any]]:
    if ignore_tags is None:
        ignore_tags = []
    if ignore_categories is None:
        ignore_categories = []
    out = {}
    for name, v in var_map.items():
        # Check exact name match
        if name in ignore_names:
            continue
        # Check name pattern match
        if any(p.search(name) for p in ignore_name_patterns):
            continue
        # Check if variable has any tags in the ignore list
        var_tags = v.get("tags", []) or []
        if any(tag in ignore_tags for tag in var_tags):
            continue
        # Check if variable has any categories in the ignore list
        var_categories = v.get("categories", []) or []
        if any(cat in ignore_categories for cat in var_categories):
            continue
        out[name] = v
    return out

# -------- Grouping --------

def build_groups_for_dataset(
    groups_cfg: Dict[str, Any],
    var_map: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Creates synthetic group variables from config patterns.
    Returns list of:
      { name, label, is_group=True, members:[...], notes, source, type:"", categories:[...], tags:[], _priority:int }
    """
    groups: List[Dict[str, Any]] = []
    for gid, cfg in (groups_cfg or {}).items():
        pattern = cfg.get("pattern")
        if not pattern:
            continue
        try:
            rx = re.compile(pattern)
        except re.error:
            continue

        members = sorted([name for name in var_map.keys() if rx.search(name)])
        if not members:
            continue

        strategy = (cfg.get("category_strategy") or "union").lower()
        cats_override = cfg.get("categories_override") or []
        if strategy == "override":
            cats = list(cats_override)
        else:
            member_cats = [set((var_map[m].get("categories") or [])) for m in members]
            if not member_cats:
                cats = []
            elif strategy == "intersection":
                s = set.intersection(*member_cats) if member_cats else set()
                cats = sorted(s)
            else:
                s = set().union(*member_cats) if member_cats else set()
                cats = sorted(s)

        group_var = {
            "name": gid,
            "label": cfg.get("label") or gid,
            "is_group": True,
            "members": members,
            "notes": cfg.get("notes") or "",
            "source": cfg.get("source_variable_name_grouped") or "",
            "type": "",
            "categories": cats,
            "tags": [],
            # preserve group-level settings for client-side behavior
            "csv_expand": cfg.get("csv_expand") or "",
            "category_strategy": cfg.get("category_strategy") or "",
            "categories_override": cfg.get("categories_override") or [],
            "_priority": int(cfg.get("priority")) if "priority" in cfg else 1000
        }
        groups.append(group_var)

    groups.sort(key=lambda g: (g.get("_priority", 1000), g.get("label", g["name"]).lower()))
    return groups

# -------- Dataset assembly --------

def assemble_dataset(
    ds_id: str,
    codebook_path: Optional[Path],
    meta_path: Optional[Path],
    groups_cfg: Dict[str, Any],
    ignore_names: List[str],
    ignore_name_patterns: List[re.Pattern],
    ignore_tags: List[str],
    ignore_categories: List[str],
) -> Tuple[Dict[str, Any], List[Tuple[str, str]]]:
    """
    Returns (dataset_dict, provenance_entries)
    provenance_entries: list[(filename, sha256)]
    """
    provenance: List[Tuple[str, str]] = []

    # Load meta YAML (optional)
    meta = {}
    if meta_path and meta_path.exists():
        meta = read_yaml(meta_path) or {}
        provenance.append((meta_path.name, sha256_file(meta_path)))

    # Load codebook YAML (optional)
    var_map: Dict[str, Dict[str, Any]] = {}
    if codebook_path and codebook_path.exists():
        cb_data = read_yaml(codebook_path)
        var_map = extract_var_map_from_codebook(cb_data)
        # Attach source filename to each variable
        for v in var_map.values():
            v['_source_yaml'] = codebook_path.name
        provenance.append((codebook_path.name, sha256_file(codebook_path)))

    # Ignore rules
    var_map = apply_ignore(var_map, ignore_names, ignore_name_patterns, ignore_tags, ignore_categories)

    # Preserve a full copy of the var_map (after applying ignore rules).
    # We may hide member variables from the visible `var_map` when groups are
    # synthesized, but need the full mapping for CSV export when groups expand
    # into individual members on the client side.
    var_map_all = dict(var_map)

    # Group variables
    groups = build_groups_for_dataset(groups_cfg, var_map)

    # If a variable is represented by a synthetic group, do not show the
    # individual member variables in the UI. Groups are shown instead.
    # This keeps the listing concise and avoids duplicated rows.
    grouped_members = set()
    for g in groups:
        for m in g.get("members", []):
            grouped_members.add(m)
    for m in grouped_members:
        if m in var_map:
            del var_map[m]

    # Variables list: place each synthetic group at the position of its first
    # member according to the original codebook order (var_map_all). This keeps
    # the listing intuitive: groups appear where their members would have been.
    variables: List[Dict[str, Any]] = []

    # Build mapping from member -> group (respect group priority order)
    member_to_group: Dict[str, Dict[str, Any]] = {}
    for g in groups:
        for m in g.get("members", []):
            if m not in member_to_group:
                member_to_group[m] = g

    inserted_groups = set()
    # Iterate original ordering from var_map_all (preserves YAML mapping order)
    for name in (list(var_map_all.keys()) if isinstance(var_map_all, dict) else []):
        # If this name belongs to a group, insert the group at first occurrence
        if name in member_to_group:
            g = member_to_group[name]
            if g["name"] not in inserted_groups:
                variables.append(g)
                inserted_groups.add(g["name"])
            # skip the member (we removed members from var_map earlier)
            continue

        # Otherwise, if the variable still exists (was not grouped), append it
        if name in var_map:
            variables.append(var_map[name])

    # Append any groups not yet inserted (no members present in var_map_all)
    for g in groups:
        if g["name"] not in inserted_groups:
            variables.append(g)

    # Append any remaining variables (defensive)
    for vname, v in var_map.items():
        if v not in variables:
            variables.append(v)

    # Heuristic to determine whether a notes field is "long" enough
    # to require a client-side expand/collapse. This avoids unreliable
    # visual measurements in the browser (line-clamp) by computing a
    # simple boolean at build time. Criteria:
    # - >= 3 explicit newlines -> long
    # - OR length > 240 characters -> long
    def _notes_is_long(text: Optional[str]) -> bool:
        if not text:
            return False
        # Consider shorter notes as "long" to enable expand/collapse
        if isinstance(text, str) and text.count('\n') >= 2:
            return True
        if isinstance(text, str) and len(text) > 120:
            return True
        return False

    # Annotate all variables we expose in var_map_all and synthetic groups
    for name, info in var_map_all.items():
        info['notes_is_long'] = _notes_is_long(info.get('notes'))

    for g in groups:
        # groups may have a notes field
        if isinstance(g, dict):
            g['notes_is_long'] = _notes_is_long(g.get('notes'))

    # Also annotate the visible var_map entries (after ignore/group removal)
    for name, info in var_map.items():
        info['notes_is_long'] = _notes_is_long(info.get('notes'))

    # Ensure each variable entry in `variables` inherits the flag when possible
    for idx, v in enumerate(variables):
        if isinstance(v, dict):
            # groups already annotated; for variables, prefer var_map_all metadata
            name = v.get('name')
            if name and name in var_map_all:
                v['notes_is_long'] = var_map_all[name].get('notes_is_long', False)
            else:
                # fallback to any notes_is_long present on the dict
                v['notes_is_long'] = v.get('notes_is_long', False)

    # Prefer Markdown description in ./data/<dataset>_register_meta.md
    info_md, md_path = load_dataset_markdown(ds_id, meta_path)
    if md_path:
        provenance.append((md_path.name, sha256_file(md_path)))

    # If no Markdown, fall back to YAML 'info' (list of strings) if present
    info_block: Dict[str, Any]
    if info_md.strip():
        # Convert markdown to HTML server-side
        info_html = md_to_html_dataset(info_md)
        info_block = {"info_html": info_html}
    else:
        yaml_info = meta.get("info") if isinstance(meta.get("info"), list) else []
        info_block = {"info": yaml_info}

    ds = {
        "id": ds_id,
        "title": meta.get("title") or readable_title_from_id(ds_id),
        "subtitle": meta.get("subtitle") or "",
        **info_block,
        "var_map": var_map,
        "var_map_all": var_map_all,
        "variables": variables
    }
    return ds, provenance

def readable_title_from_id(ds_id: str) -> str:
    return ds_id.replace("_", " ").replace("-", " ").title()

# -------- Intro.md --------

def load_intro_html() -> str:
    if INTRO_MD.exists():
        return md_to_html_intro(INTRO_MD.read_text(encoding="utf-8"))
    return ""


def load_footer_html() -> str:
    if FOOTER_MD.exists():
        html = md_to_html_intro(FOOTER_MD.read_text(encoding="utf-8"))
        # Inject logo if it exists and footer references it as [LOGO]
        logo_uri = load_logo_data_uri()
        if logo_uri and "[LOGO]" in html:
            logo_html = f'<img src="{logo_uri}" alt="Logo" style="height:64px;width:auto;display:block;margin-bottom:1rem;" />'
            html = html.replace("[LOGO]", logo_html)
        return html
    return ""

# -------- Provenance --------

def format_provenance(prov_per_dataset: Dict[str, List[Tuple[str, str]]]) -> str:
    """
    Returns a multi-line string:
      <file> <sha256>
      ...
      Combined SHA-256: <digest-of-digests>
    Combined digest is SHA-256 of the concatenated individual hex digests
    in stable order.
    """
    lines: List[str] = []
    all_hexes: List[str] = []

    # Also include variables_config.yaml and intro.md if present
    supplemental_files: List[Path] = []
    if VARIABLES_CONFIG.exists():
        supplemental_files.append(VARIABLES_CONFIG)
    if INTRO_MD.exists():
        supplemental_files.append(INTRO_MD)
    if FOOTER_MD.exists():
        supplemental_files.append(FOOTER_MD)
    if LOGO_PATH.exists():
        supplemental_files.append(LOGO_PATH)

    # Per-dataset YAMLs and MDs
    for ds_id in sorted(prov_per_dataset.keys()):
        for fname, digest in prov_per_dataset[ds_id]:
            lines.append(f"{fname} {digest}")
            all_hexes.append(digest)

    # Supplemental
    for p in supplemental_files:
        h = sha256_file(p)
        lines.append(f"{p.name} {h}")
        all_hexes.append(h)

    combined = sha256_bytes("".join(all_hexes).encode("utf-8")) if all_hexes else ""
    if combined:
        lines.append(f"Combined SHA-256: {combined}")

    return "\n".join(lines)


def load_datasets_config() -> List[Dict[str, Any]]:
    """
    Loads `config/datasets_config.yaml` and returns a list of groups:
      - heading: str
      - datasets: list[str]

    If the config file is missing or malformed, returns an empty list.
    """
    if not DATASETS_CONFIG.exists():
        return []
    cfg = read_yaml(DATASETS_CONFIG) or {}
    groups = cfg.get("groups") or []
    # Normalize: ensure each group is a mapping with heading and datasets list
    out: List[Dict[str, Any]] = []
    if isinstance(groups, list):
        for g in groups:
            if not isinstance(g, dict):
                continue
            heading = g.get("heading") or g.get("label") or ""
            datasets = g.get("datasets") or g.get("ids") or []
            if isinstance(datasets, str):
                datasets = [datasets]
            if not isinstance(datasets, list):
                datasets = []
            out.append({"heading": heading, "datasets": list(datasets)})
    return out

# -------- Template rendering --------

def get_git_sha() -> str:
    """
    Get the current git commit SHA. Returns empty string if not a git repo
    or if git is not available.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""

def get_build_date() -> str:
    """
    Get the current build date and time in ISO format, rounded to whole seconds.
    """
    return datetime.now().replace(microsecond=0).isoformat()

def render_html(datasets: List[Dict[str, Any]], intro_html: str, provenance_text: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"])
    )
    tmpl = env.get_template(TEMPLATE_NAME)
    data_json = json.dumps(datasets, ensure_ascii=False, separators=(",", ":"))

    html = tmpl.render(
        data_json=data_json,
        intro_html=intro_html,
        git_sha=get_git_sha(),
        build_date=get_build_date(),
        footer_html=load_footer_html(),
        logo_data_uri=load_logo_data_uri()
    )
    return html


# -------- Excel export --------

def export_to_excel(datasets_raw: List[Dict[str, Any]], output_path: Path) -> None:
    """
    Export processed variable lists to Excel (.xlsx).
    Each dataset gets its own sheet with columns (in desired order):
    - Selection: empty column for users to mark selected variables
    - Label: display label
    - Notes: description/notes
    - Variable name: variable/group name (previously "Name")
    - Source variable name: source variable name (previously "Source")
    - Categories: comma-separated list of categories
    - Grouped: Yes/No if this is a synthetic group variable
    - Members: for groups, comma-separated list of member variable names

    Args:
        datasets_raw: The raw datasets list (as assembled in build()).
                     Can be a flat list or a list of grouped datasets with "heading" keys.
        output_path: Path where the Excel file should be written.
    """
    if not datasets_raw:
        print("Warning: No datasets to export to Excel.")
        return

    wb = Workbook()
    wb.remove(wb.active)  # Remove default sheet

    # Define styles for headers
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )

    # Extract flat list of datasets from potentially grouped structure
    flat_datasets: List[Dict[str, Any]] = []
    for item in datasets_raw:
        if isinstance(item, dict):
            # Check if this is a group object (has 'heading' and 'datasets' keys)
            if "heading" in item and "datasets" in item:
                # This is a grouped structure; extract the datasets
                for ds in item.get("datasets", []):
                    if isinstance(ds, dict):
                        flat_datasets.append(ds)
            elif "id" in item and "variables" in item:
                # This is a standalone dataset
                flat_datasets.append(item)

    # Create a sheet for each dataset
    for dataset in flat_datasets:
        ds_id = dataset.get("id", "unknown")
        ds_title = dataset.get("title", ds_id)
        variables = dataset.get("variables", [])

        # Sanitize sheet name (Excel has character and length restrictions)
        sheet_name = _sanitize_sheet_name(ds_title)

        ws = wb.create_sheet(title=sheet_name)

        # Define column headers (ordered to match HTML tables more closely)
        headers = [
            "Selection",
            "Label",
            "Notes",
            "Variable name",
            "Source variable name",
            "Categories",
            "Grouped",
            "Members",
        ]

        # Write headers
        for col_num, header_text in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header_text
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = border

        # Write variable rows
        for row_num, var in enumerate(variables, 2):
            if not isinstance(var, dict):
                continue

            var_name = var.get("name", "")
            var_label = var.get("label", "")
            var_notes = var.get("notes", "")
            var_source = var.get("source", "")
            var_categories = var.get("categories", [])
            is_group = var.get("is_group", False)
            members = var.get("members", [])

            # Format lists as comma-separated strings
            categories_str = ", ".join(var_categories) if isinstance(var_categories, list) else str(var_categories)
            members_str = ", ".join(members) if isinstance(members, list) else str(members)

            # Build row data in the new order; selection left blank for user input
            row_data = [
                "",  # Selection
                var_label,
                var_notes,
                var_name,
                var_source,
                categories_str,
                "Yes" if is_group else "No",
                members_str,
            ]

            # Write row data
            for col_num, cell_value in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = cell_value
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = border

        # Auto-adjust column widths
        _auto_adjust_column_widths(ws)

    # Save workbook
    wb.save(output_path)
    print(f"✓ Wrote {output_path}")


def _sanitize_sheet_name(name: str) -> str:
    """
    Sanitize a dataset title for use as an Excel sheet name.
    Excel sheet names have restrictions:
    - Max 31 characters
    - Cannot contain: [ ] : * ? /
    """
    # Remove or replace problematic characters
    sanitized = re.sub(r'[\[\]:*?/\\]', '', name)
    # Limit to 31 characters
    sanitized = sanitized[:31].strip()
    # If empty after sanitization, use a default
    if not sanitized:
        sanitized = "Sheet"
    return sanitized


def _auto_adjust_column_widths(ws) -> None:
    """
    Auto-adjust column widths to fit content.
    """
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except Exception:
                pass
        # Set column width with some padding
        adjusted_width = min(max_length + 2, 50)  # Cap at 50 to keep readable
        ws.column_dimensions[column_letter].width = adjusted_width


def load_logo_data_uri() -> str:
    """
    If `content/logo.*` exists, return a base64 data URI for embedding.
    Otherwise return empty string.
    """
    if not LOGO_PATH.exists():
        return ""
    data = LOGO_PATH.read_bytes()
    # Only support common raster types — infer from suffix
    suffix = LOGO_PATH.suffix.lower()
    if suffix in ('.png',):
        mime = 'image/png'
    elif suffix in ('.jpg', '.jpeg'):
        mime = 'image/jpeg'
    elif suffix in ('.svg',):
        # SVG is text; return raw svg string (no base64) to keep it crisp
        try:
            txt = data.decode('utf-8')
            return f"data:image/svg+xml;utf8,{txt}"
        except Exception:
            mime = 'image/svg+xml'
    else:
        mime = 'application/octet-stream'
    import base64
    b64 = base64.b64encode(data).decode('ascii')
    return f"data:{mime};base64,{b64}"

# -------- Build entrypoint --------

def build() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    groups_cfg, ignore_names, ignore_name_patterns, ignore_tags, ignore_categories = load_variables_config()

    discovered = discover_datasets()
    datasets: List[Dict[str, Any]] = []
    prov: Dict[str, List[Tuple[str, str]]] = {}

    # Load optional grouping/ordering configuration for datasets
    ds_groups_cfg = load_datasets_config()

    # Keep a mutable set of discovered ids to track which have been consumed
    remaining = set(discovered.keys())

    if ds_groups_cfg:
        # For each configured group, assemble datasets in the specified order
        for group in ds_groups_cfg:
            heading = group.get("heading") or ""
            group_list: List[Dict[str, Any]] = []
            for did in group.get("datasets", []) or []:
                if did not in discovered:
                    print(f"Warning: dataset '{did}' listed in {DATASETS_CONFIG.name} not found in data directory, ignoring.")
                    continue
                paths = discovered[did]
                ds, p = assemble_dataset(
                    ds_id=did,
                    codebook_path=paths.get("codebook"),
                    meta_path=paths.get("meta"),
                    groups_cfg=groups_cfg,
                    ignore_names=ignore_names,
                    ignore_name_patterns=ignore_name_patterns,
                    ignore_tags=ignore_tags,
                    ignore_categories=ignore_categories,
                )
                group_list.append(ds)
                prov[did] = p
                remaining.discard(did)
            # Only append non-empty groups
            if group_list:
                datasets.append({"heading": heading, "datasets": group_list})

    # Append remaining (ungrouped) datasets in alphabetical order
    if remaining:
        others = []
        for ds_id in sorted(remaining):
            paths = discovered[ds_id]
            ds, p = assemble_dataset(
                ds_id=ds_id,
                codebook_path=paths.get("codebook"),
                meta_path=paths.get("meta"),
                groups_cfg=groups_cfg,
                ignore_names=ignore_names,
                ignore_name_patterns=ignore_name_patterns,
                ignore_tags=ignore_tags,
                ignore_categories=ignore_categories,
            )
            others.append(ds)
            prov[ds_id] = p
        # If we had configured groups, put ungrouped under an "Other" heading,
        # otherwise simply present a flat list (legacy behavior).
        if ds_groups_cfg:
            datasets.append({"heading": "Other datasets", "datasets": others})
        else:
            # legacy: flat list expected by template
            datasets = others

    intro_html = load_intro_html()
    # Replace placeholder in intro HTML with a relative link to the Excel file
    excel_filename = "variables_browser.xlsx"
    if intro_html and "[EXCEL-SELECTIONS]" in intro_html:
        excel_link_html = f'<a href="{excel_filename}">Download Excel file</a>'
        intro_html = intro_html.replace("[EXCEL-SELECTIONS]", excel_link_html)

    provenance_text = format_provenance(prov)

    html = render_html(datasets, intro_html, provenance_text)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"✓ Wrote {OUTPUT_HTML}")

    # Export to Excel (file name used above for the intro link)
    excel_output = DIST_DIR / excel_filename
    export_to_excel(datasets, excel_output)


# -------- CLI --------

if __name__ == "__main__":
    build()

