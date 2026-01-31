
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import re
from typing import Any, Dict, List

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

DATA_DIR = Path('data')
TEMPLATE_PATH = Path('templates/index.html.j2')
OUT_PATH = Path('dist/variables_browser.html')

# ---- Utilities ----

def read_yaml(p: Path) -> Any:
    with p.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def collect_inputs() -> Dict[str, Dict[str, Path]]:
    # Return mapping {register_key: {meta: Path, codebook: Path}}.
    # A register key is derived from filenames like 'ps_cancer_register_codebook.yaml'.
    codebooks = {}
    metas = {}
    for p in DATA_DIR.rglob('*.yaml'):
        name = p.name
        if '_register_codebook' in name:
            key = name.split('_register_codebook', 1)[0]
            codebooks[key] = p
        elif '_register_meta' in name:
            key = name.split('_register_meta', 1)[0]
            metas[key] = p
    # pair them
    pairs = {}
    for key, cb in codebooks.items():
        meta = metas.get(key)
        if meta:
            pairs[key] = {'meta': meta, 'codebook': cb}
    return pairs


# ---- Normalization ----

def to_list(x):
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    # split strings by comma/semicolon/space
    if isinstance(x, str):
        # prefer comma or semicolon; if neither exists, keep as single item
        if ',' in x:
            return [t.strip() for t in x.split(',') if t.strip()]
        if ';' in x:
            return [t.strip() for t in x.split(';') if t.strip()]
        # split on whitespace for words
        import re as _re
        return [t.strip() for t in _re.split(r"\s+", x) if t.strip()]
    return [x]


def has_excluded_tag(tags) -> bool:
    tags_list = [t.lower() for t in to_list(tags)]
    return any(t in {"internal", "identifier"} for t in tags_list)


def get_first(d: Dict[str, Any], keys: List[str], default: Any = None):
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    return default


def normalize_dataset(register_id: str, meta: Dict[str, Any], codebook: Dict[str, Any]) -> Dict[str, Any]:
    # Dataset-level fields
    title = get_first(meta, ['title', 'dataset_title', 'name'], register_id)
    subtitle = get_first(meta, ['subtitle', 'sub_title', 'short'], '')
    info = get_first(meta, ['info', 'description', 'about'], '')

    # Variables live in codebook: expect mapping {varname: props}
    variables = []
    if isinstance(codebook, dict):
        items = list(codebook.items())
    else:
        items = []

    for varname, props in items:
        props = props or {}
        # Skip excluded tags
        if has_excluded_tag(props.get('tags')):
            continue
        variable = {
            'name': str(varname),
            'label': get_first(props, ['label', 'labels'], str(varname)),
            'notes': props.get('notes') or '',
            'source': get_first(props, ['colname_silver', 'source', 'source_name'], ''),
            'type': get_first(props, ['type', 'coltypes'], ''),
            'category': get_first(props, ['category', 'categories'], ''),
        }
        variables.append(variable)

    # Deterministic sort: by label (casefold), then name
    variables.sort(key=lambda v: (str(v.get('label','')).casefold(), str(v['name']).casefold()))

    dataset = {
        'id': register_id,
        'title': title,
        'subtitle': subtitle,
        'info': info,
        'variables': variables,
    }
    return dataset


# ---- Build pipeline ----

def build():
    pairs = collect_inputs()
    if not pairs:
        print("No input YAML files found in ./data. Place *meta.yaml and *codebook.yaml there.")
    datasets = []
    input_files: List[Path] = []

    for key, paths in pairs.items():
        meta = read_yaml(paths['meta']) or {}
        codebook = read_yaml(paths['codebook']) or {}
        ds = normalize_dataset(key, meta, codebook)
        datasets.append(ds)
        input_files.extend([paths['meta'], paths['codebook']])

    # Sort datasets deterministically by title then id
    datasets.sort(key=lambda d: (str(d.get('title','')).casefold(), d['id'].casefold()))

    # Prepare provenance
    input_files = sorted({p.resolve() for p in input_files})
    concat_hash = hashlib.sha256()
    prov_lines = []
    for p in input_files:
        h = sha256_file(p)
        prov_lines.append(f"{p.name}  {h}")
        concat_hash.update(p.read_bytes())
    provenance = "\n".join(prov_lines) + ("\n\nCombined SHA-256: " + concat_hash.hexdigest() if input_files else "")

    # Render
    env = Environment(
        loader=FileSystemLoader(str(Path('templates'))),
        autoescape=select_autoescape(['html'])
    )
    tpl = env.get_template('index.html.j2')

    data_json = json.dumps(datasets, ensure_ascii=False, sort_keys=True, separators=(',',':'))
    html = tpl.render(data_json=data_json, provenance=provenance)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding='utf-8')
    print(f"Wrote {OUT_PATH}")


if __name__ == '__main__':
    build()
