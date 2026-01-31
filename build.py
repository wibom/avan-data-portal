from __future__ import annotations
from pathlib import Path
import hashlib
import json
import re
from typing import Any, Dict, List, Tuple, Set

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

# --------------------------------------------------------------------------------------
# PREDICT / Avan data portal — build script
#
# Features:
# - Reads dataset meta + codebooks from ./data
# - Supports external intro text (Markdown or HTML) from ./content
# - Supports variable grouping & UI overrides from ./config/variables_config.yaml
# - Supports ignore list (names and regex patterns)
# - Emits variables (and synthetic group rows) per dataset into a single self-contained
#   HTML at ./dist/variables_browser.html rendered by templates/index.html.j2
#
# Notes:
# - "groups" collapse many variables into a single logical UI row (is_group=True);
#   selection in the UI expands to member variables for CSV export (handled in JS).
# - "ignore" removes variables entirely (pre-grouping) from UI and CSV.
# - Group "source_variable_name_grouped" shows in the "Source variable name" column for
#   the synthetic row; member variables keep their own 'source' strings.
# --------------------------------------------------------------------------------------

DATA_DIR = Path("data")
CONTENT_DIR = Path("content")
CONFIG_DIR = Path("config")
TEMPLATES_DIR = Path("templates")
OUT_PATH = Path("dist/variables_browser.html")


# ---------------- Utilities ----------------

def read_yaml(p: Path) -> Any:
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------- Intro & Variables config ----------------

def load_intro_html() -> str:
    """Return HTML string for the optional introduction section."""
    intro_md = CONTENT_DIR / "intro.md"
    intro_html_file = CONTENT_DIR / "intro.html"
    if intro_md.exists():
        import markdown  # only import if needed
        return markdown.markdown(intro_md.read_text(encoding="utf-8"))
    if intro_html_file.exists():
        return intro_html_file.read_text(encoding="utf-8")
    return ""


def _to_list(x):
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return [str(t) for t in x if str(t).strip()]
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return []
        if "," in s:
            return [t.strip() for t in s.split(",") if t.strip()]
        if ";" in s:
            return [t.strip() for t in s.split(";") if t.strip()]
        return [s]
    return [str(x)]


def load_variables_config():
    """
    Load ./config/variables_config.yaml (if present) and return:
      - groups: List[Tuple[gid, priority, compiled_pattern, spec_dict]]
      - ignore_names: Set[str]
      - ignore_patterns: List[re.Pattern]
    """
    cfg_path = CONFIG_DIR / "variables_config.yaml"
    if not cfg_path.exists():
        return [], set(), []

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    # Compile groups
    groups: List[Tuple[str, int, re.Pattern, dict]] = []
    for gid, spec in (cfg.get("groups") or {}).items():
        pat = re.compile(spec.get("pattern", ".*"))
        prio = int(spec.get("priority", 1000))
        groups.append((gid, prio, pat, spec))
    groups.sort(key=lambda t: t[1])  # by priority (lower first)

    # Ignore lists
    ignore_cfg = cfg.get("ignore", {}) or {}
    ignore_names: Set[str] = set(ignore_cfg.get("names", []) or [])
    ignore_patterns: List[re.Pattern] = [re.compile(p) for p in (ignore_cfg.get("patterns", []) or [])]

    return groups, ignore_names, ignore_patterns


# ---------------- Normalization helpers ----------------

def _has_excluded_tag(tags) -> bool:
    tags_list = [t.lower() for t in _to_list(tags)]
    return any(t in {"internal", "identifier"} for t in tags_list)


def _first(d: Dict[str, Any], keys: List[str], default: Any = None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


# ---------------- Core: normalization with grouping & ignore ----------------

def normalize_dataset(
    register_id: str,
    meta: Dict[str, Any],
    codebook: Dict[str, Any],
    groups: List[Tuple[str, int, re.Pattern, dict]],
    ignore_names: Set[str],
    ignore_patterns: List[re.Pattern],
) -> Dict[str, Any]:
    # Dataset-level
    title = _first(meta, ["title", "dataset_title", "name"], register_id)
    subtitle = _first(meta, ["subtitle", "sub_title", "short"], "")
    info = _first(meta, ["info", "description", "about"], "")

    # Build raw variables list and a full map (for CSV expansion later)
    raw_list: List[Dict[str, Any]] = []
    var_map: Dict[str, Dict[str, Any]] = {}
    items = list(codebook.items()) if isinstance(codebook, dict) else []

    for varname, props in items:
        props = props or {}

        # Exclude by tag first
        if _has_excluded_tag(props.get("tags")):
            continue

        # Ignore list (names or patterns)
        if varname in ignore_names:
            continue
        if any(p.search(varname) for p in ignore_patterns):
            continue

        cats = _to_list(props.get("categories") if "categories" in props else props.get("category"))
        tags = [t for t in _to_list(props.get("tags")) if t]

        v = {
            "name": str(varname),
            "label": _first(props, ["label", "labels"], str(varname)),
            "notes": props.get("notes") or "",
            "source": _first(props, ["colname_silver", "source", "source_name"], ""),
            "type": _first(props, ["type", "coltypes"], ""),
            "categories": cats,
            "tags": tags,
            "is_group": False,
        }
        raw_list.append(v)
        var_map[v["name"]] = v

    # Group assignment: each var belongs to at most one group
    assigned: Dict[str, str] = {}         # varname -> group_id
    group_members: Dict[str, List[str]] = {}
    group_specs: Dict[str, dict] = {gid: spec for gid, _, _, spec in groups}

    for v in raw_list:
        for gid, _prio, pat, _spec in groups:
            if pat.search(v["name"]):
                assigned[v["name"]] = gid
                group_members.setdefault(gid, []).append(v["name"])
                break  # first match wins (by priority)

    # Build render rows: start with ungrouped variables
    render_rows: List[Dict[str, Any]] = [v for v in raw_list if v["name"] not in assigned]

    # Build synthetic group rows (compute categories; use configured source for group)
    for gid, names in group_members.items():
        spec = group_specs.get(gid, {})
        strat = (spec.get("category_strategy") or "union").lower()
        override = _to_list(spec.get("categories_override"))

        # Aggregate categories
        if strat == "override" and override:
            cats = override
        else:
            sets = [set(var_map[n].get("categories") or []) for n in names]
            if not sets:
                cats = []
            elif strat == "intersection":
                inter = sets[0]
                for s in sets[1:]:
                    inter = inter & s
                cats = sorted(inter)
            else:  # union (default)
                uni = set()
                for s in sets:
                    uni |= s
                cats = sorted(uni)

        group_source = spec.get("source_variable_name_grouped", "")  # simple explicit override

        render_rows.append({
            "name": gid,
            "label": spec.get("label") or gid,
            "notes": spec.get("notes") or "",
            "source": group_source,     # UI shows this in the Source column
            "type": "",
            "categories": cats,
            "tags": [],
            "is_group": True,
            "members": sorted(names),
        })

    # Deterministic sort of rows: by label then by name
    render_rows.sort(key=lambda v: (str(v.get("label", "")).casefold(), v["name"].casefold()))

    return {
        "id": register_id,
        "title": title,
        "subtitle": subtitle,
        "info": info,
        "variables": render_rows,
        "var_map": var_map,  # includes all real variables (for CSV expansion in the UI)
    }


# ---------------- Build pipeline ----------------

def collect_pairs() -> Dict[str, Dict[str, Path]]:
    """Return mapping {register_key: {meta: Path, codebook: Path}}."""
    codebooks: Dict[str, Path] = {}
    metas: Dict[str, Path] = {}
    for p in DATA_DIR.rglob("*.yaml"):
        name = p.name
        if "_register_codebook" in name:
            key = name.split("_register_codebook", 1)[0]
            codebooks[key] = p
        elif "_register_meta" in name:
            key = name.split("_register_meta", 1)[0]
            metas[key] = p

    pairs: Dict[str, Dict[str, Path]] = {}
    for key, cb in codebooks.items():
        meta = metas.get(key)
        if meta:
            pairs[key] = {"meta": meta, "codebook": cb}
    return pairs


def build():
    pairs = collect_pairs()
    if not pairs:
        print("No input YAML files found in ./data. Place *meta.yaml and *codebook.yaml there.")

    intro_html = load_intro_html()
    groups, ignore_names, ignore_patterns = load_variables_config()

    datasets: List[Dict[str, Any]] = []
    input_files: List[Path] = []
    for key, paths in pairs.items():
        meta = read_yaml(paths["meta"]) or {}
        codebook = read_yaml(paths["codebook"]) or {}
        ds = normalize_dataset(key, meta, codebook, groups, ignore_names, ignore_patterns)
        datasets.append(ds)
        input_files.extend([paths["meta"], paths["codebook"]])

    # Sort datasets deterministically
    datasets.sort(key=lambda d: (str(d.get("title", "")).casefold(), d["id"].casefold()))

    # Provenance
    uniq_inputs = sorted({p.resolve() for p in input_files})
    h = hashlib.sha256()
    prov_lines = []
    for p in uniq_inputs:
        file_hash = sha256_file(p)
        prov_lines.append(f"{p.name}  {file_hash}")
        h.update(p.read_bytes())
    provenance = "\n".join(prov_lines)
    if uniq_inputs:
        provenance += "\n\nCombined SHA-256: " + h.hexdigest()

    # Render
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(["html"]))
    tpl = env.get_template("index.html.j2")

    data_json = json.dumps(datasets, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    html = tpl.render(data_json=data_json, provenance=provenance, intro_html=intro_html)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    build()
    