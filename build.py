from __future__ import annotations
from pathlib import Path
import hashlib
import json
from typing import Any, Dict, List

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

DATA_DIR = Path('data')
OUT_PATH = Path('dist/variables_browser.html')

# ---------------- Utilities ----------------

def read_yaml(p: Path) -> Any:
    with p.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def collect_inputs() -> Dict[str, Dict[str, Path]]:
    """Return mapping {register_key: {meta: Path, codebook: Path}}."""
    codebooks: Dict[str, Path] = {}
    metas: Dict[str, Path] = {}
    for p in DATA_DIR.rglob('*.yaml'):
        name = p.name
        if '_register_codebook' in name:
            key = name.split('_register_codebook', 1)[0]
            codebooks[key] = p
        elif '_register_meta' in name:
            key = name.split('_register_meta', 1)[0]
            metas[key] = p
    pairs: Dict[str, Dict[str, Path]] = {}
    for key, cb in codebooks.items():
        meta = metas.get(key)
        if meta:
            pairs[key] = {'meta': meta, 'codebook': cb}
    return pairs

# ---------------- Normalization ----------------

def _to_list(x):
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return [str(t) for t in x if str(t).strip()]
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return []
        if ',' in s:
            return [t.strip() for t in s.split(',') if t.strip()]
        if ';' in s:
            return [t.strip() for t in s.split(';') if t.strip()]
        return [s]
    return [str(x)]

def _has_excluded_tag(tags) -> bool:
    tags_list = [t.lower() for t in _to_list(tags)]
    return any(t in {"internal", "identifier"} for t in tags_list)

def _first(d: Dict[str, Any], keys: List[str], default: Any = None):
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    return default

def normalize_dataset(register_id: str, meta: Dict[str, Any], codebook: Dict[str, Any]) -> Dict[str, Any]:
    # Dataset-level
    title = _first(meta, ['title', 'dataset_title', 'name'], register_id)
    subtitle = _first(meta, ['subtitle', 'sub_title', 'short'], '')
    info = _first(meta, ['info', 'description', 'about'], '')

    # Variables
    variables: List[Dict[str, Any]] = []
    items = list(codebook.items()) if isinstance(codebook, dict) else []
    for varname, props in items:
        props = props or {}
        if _has_excluded_tag(props.get('tags')):
            continue
        cats = _to_list(props.get('categories') if 'categories' in props else props.get('category'))
        tags = [t for t in _to_list(props.get('tags')) if t]
        variables.append({
            'name': str(varname),
            'label': _first(props, ['label', 'labels'], str(varname)),
            'notes': props.get('notes') or '',
            'source': _first(props, ['colname_silver', 'source', 'source_name'], ''),
            'type': _first(props, ['type', 'coltypes'], ''),
            'categories': cats,
            'tags': tags,
        })

    # Deterministic sort
    variables.sort(key=lambda v: (str(v.get('label', '')).casefold(), v['name'].casefold()))

    return {
        'id': register_id,
        'title': title,
        'subtitle': subtitle,
        'info': info,
        'variables': variables,
    }

# ---------------- Build pipeline ----------------

def build():
    pairs = collect_inputs()
    if not pairs:
        print('No input YAML files found in ./data. Place *meta.yaml and *codebook.yaml there.')

    datasets: List[Dict[str, Any]] = []
    input_files: List[Path] = []

    for key, paths in pairs.items():
        meta = read_yaml(paths['meta']) or {}
        codebook = read_yaml(paths['codebook']) or {}
        ds = normalize_dataset(key, meta, codebook)
        datasets.append(ds)
        input_files.extend([paths['meta'], paths['codebook']])

    # Sort datasets deterministically
    datasets.sort(key=lambda d: (str(d.get('title', '')).casefold(), d['id'].casefold()))

    # Provenance (build safely without unterminated strings)
    uniq_inputs = sorted({p.resolve() for p in input_files})
    concat_hasher = hashlib.sha256()
    lines: List[str] = []
    for p in uniq_inputs:
        h = sha256_file(p)
        lines.append(f"{p.name}  {h}")
        concat_hasher.update(p.read_bytes())
    combined = concat_hasher.hexdigest() if uniq_inputs else ""
    provenance = "\n".join(lines)
    if combined:
        provenance = provenance + "\n\nCombined SHA-256: " + combined

    # Render
    env = Environment(loader=FileSystemLoader('templates'), autoescape=select_autoescape(['html']))
    tpl = env.get_template('index.html.j2')
    data_json = json.dumps(datasets, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    html = tpl.render(data_json=data_json, provenance=provenance)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding='utf-8')
    print(f"Wrote {OUT_PATH}")

if __name__ == '__main__':
    build()