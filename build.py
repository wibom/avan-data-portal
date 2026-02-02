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
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

import yaml  # PyYAML
from jinja2 import Environment, FileSystemLoader, select_autoescape

# -------- Paths --------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
CONTENT_DIR = ROOT_DIR / "content"
CONFIG_DIR = ROOT_DIR / "config"
TEMPLATES_DIR = ROOT_DIR / "templates"
DIST_DIR = ROOT_DIR / "dist"

TEMPLATE_NAME = "index.html.j2"
OUTPUT_HTML = DIST_DIR / "variables_browser.html"

VARIABLES_CONFIG = CONFIG_DIR / "variables_config.yaml"
INTRO_MD = CONTENT_DIR / "intro.md"

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
    Convert intro.md to simple HTML.
    If 'markdown' is available, use it; otherwise, join paragraphs.
    """
    if not text:
        return ""
    try:
        import markdown  # optional
        return markdown.markdown(text, extensions=["extra", "sane_lists", "tables"])
    except Exception:
        parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
        return "".join(f"<p>{escape_html(p)}</p>" for p in parts)

def md_to_html_dataset(text: str) -> str:
    """
    Convert dataset description markdown to HTML.
    Uses the markdown library with support for lists, tables, and code blocks.
    """
    if not text:
        return ""
    try:
        import markdown  # optional
        # Use extensions to support various markdown features
        return markdown.markdown(text, extensions=["extra", "sane_lists", "tables", "nl2br"])
    except Exception:
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

# -------- Template rendering --------

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
        provenance=provenance_text
    )
    return html

# -------- Build entrypoint --------

def build() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    groups_cfg, ignore_names, ignore_name_patterns, ignore_tags, ignore_categories = load_variables_config()

    discovered = discover_datasets()
    datasets: List[Dict[str, Any]] = []
    prov: Dict[str, List[Tuple[str, str]]] = {}

    for ds_id, paths in sorted(discovered.items(), key=lambda kv: kv[0]):
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
        datasets.append(ds)
        prov[ds_id] = p

    intro_html = load_intro_html()
    provenance_text = format_provenance(prov)

    html = render_html(datasets, intro_html, provenance_text)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"✓ Wrote {OUTPUT_HTML}")

# -------- CLI --------

if __name__ == "__main__":
    build()

