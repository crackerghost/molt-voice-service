"""Bounded teaching visuals and real image lookup; no model-invented asset URLs."""
import math
import html
import re
import threading
import time
from urllib.parse import urlsplit

import httpx

_CACHE = {}
_LOCK = threading.Lock()


def safe_url(value):
    src = str(value or '').strip()
    if not src or len(src) > 2048 or re.search(r'[\s\\<>]', src):
        return None
    if src.startswith('/') and not src.startswith('//'):
        return src
    try:
        url = urlsplit(src)
        return src if url.scheme == 'https' and url.netloc and not url.username and not url.password else None
    except ValueError:
        return None


def clean(value, size=80):
    return re.sub(r'[\u0900-\u097F]+', '', str(value if value is not None else '')).strip()[:size]


def number(value, default=0):
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default


def records(value, limit):
    return [v for v in value[:limit] if isinstance(v, dict)] if isinstance(value, list) else []


def normalize_regions(item):
    regions, seen = [], set()
    for r in records(item.get('regions'), 8):
        key = clean(r.get('id'))
        coords = [number(r.get(k), -1) for k in ('x', 'y', 'width', 'height')]
        x, y, w, h = coords
        if not key or key in seen or x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1.000001 or y + h > 1.000001:
            continue
        seen.add(key)
        regions.append(dict(zip(('x', 'y', 'width', 'height'), coords), id=key, label=clean(r.get('label'), 100)))
    return {'regions': regions, 'activeRegion': clean(item.get('activeRegion'))}


def normalize_scene(item):
    kind = item.get('kind')
    if kind not in ('array', 'box-model', 'nodes'):
        return None
    out = {'kind': kind, 'caption': clean(item.get('caption'), 240), 'sceneKey': re.sub(r'[^a-zA-Z0-9_-]', '', str(item.get('sceneKey') or ''))[:40]}
    if kind == 'array':
        items = item.get('items')
        if not isinstance(items, list) or len(items) > 16 or any(not isinstance(v, dict) for v in items):
            return None
        out['items'] = [{'id': clean(v.get('id') or f'cell-{i}'), 'value': clean(v.get('value'), 12)} for i, v in enumerate(items)]
        if len({v['id'] for v in out['items']}) != len(items):
            return None
        for key in ('active', 'visited'):
            values = item.get(key)
            out[key] = [v for v in values[:16] if type(v) is int and 0 <= v < len(items)] if isinstance(values, list) else []
        out['pointers'] = [{'label': clean(p.get('label'), 16), 'index': p['index']} for p in records(item.get('pointers'), 3) if type(p.get('index')) is int and 0 <= p['index'] < len(items)]
    if kind == 'box-model':
        out['padding'] = max(8, min(64, number(item.get('padding'), 24)))
        out['focus'] = item.get('focus') if item.get('focus') in ('content', 'padding', 'border', 'margin') else 'content'
    if kind == 'nodes':
        nodes, seen = [], set()
        for n in records(item.get('nodes'), 8):
            key = clean(n.get('id'))
            if not key or key in seen:
                continue
            seen.add(key)
            nodes.append({'id': key, 'label': clean(n.get('label'), 28), 'x': max(.1, min(.9, number(n.get('x'), .5))), 'y': max(.22, min(.75, number(n.get('y'), .5)))})
        if not nodes:
            return None
        out['nodes'] = nodes
        out['edges'] = [{'from': e['from'], 'to': e['to']} for e in records(item.get('edges'), 12) if e.get('from') in seen and e.get('to') in seen]
        out['focus'] = clean(item.get('focus'))
    out['variables'] = [{'label': clean(v.get('label'), 20), 'value': clean(v.get('value'), 30)} for v in records(item.get('variables'), 4)]
    return out


def search_image(query):
    """Fixed HTTPS endpoint, finite wait, bounded cache, no arbitrary server fetches."""
    query = clean(query, 160)
    if len(query) < 3:
        return None
    key = query.lower()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1]
    result = None
    try:
        with httpx.Client(timeout=4.0, follow_redirects=False) as client:
            response = client.get('https://commons.wikimedia.org/w/api.php', params={
                'action': 'query', 'format': 'json', 'generator': 'search',
                'gsrsearch': f'{query} filetype:bitmap', 'gsrnamespace': 6, 'gsrlimit': 5,
                'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'iiurlwidth': 1200,
            }, headers={'User-Agent': 'Molt-Classroom/1.0 (https://notmybug.com; educational image lookup)'})
            response.raise_for_status()
            data = response.json()
        pages = data.get('query', {}).get('pages', {})
        pages = sorted(pages.values(), key=lambda p: number(p.get('index'))) if isinstance(pages, dict) else []
        for page in pages[:5]:
            candidate = next(iter(records(page.get('imageinfo'), 1)), {})
            meta = candidate.get('extmetadata') or {}
            def metadata(key):
                field = meta.get(key) or {}
                return clean(html.unescape(re.sub(r'<[^>]+>', '', str(field.get('value') or ''))), 120) if isinstance(field, dict) else ''
            src = safe_url(candidate.get('thumburl') or candidate.get('url'))
            source = safe_url(candidate.get('descriptionurl'))
            license_name = metadata('LicenseShortName')
            # Only absolute media/source URLs and explicit reusable licenses.
            if not src or not src.startswith('https://') or not source or not source.startswith('https://') or not re.fullmatch(r'(?:CC BY(?:-SA)? [1-4]\.0|CC0(?: 1\.0)?|Public domain)', license_name):
                continue
            result = {'src': src, 'sourceUrl': source, 'alt': clean(page.get('title') or query, 240).removeprefix('File:'),
                      'credit': clean(f"{metadata('Artist') or 'Wikimedia Commons'} · {license_name}", 180)}
            break
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        pass  # A failed image lookup must never stop the spoken explanation.
    with _LOCK:
        _CACHE[key] = (now + (900 if result else 60), result)
        while len(_CACHE) > 64:
            _CACHE.pop(next(iter(_CACHE)))
    return result


def resolve_images(data):
    if not isinstance(data, dict) or not isinstance(data.get('elements'), list):
        return data
    elements, searches = [], 0
    for original in data['elements'][:40]:
        item = original.copy() if isinstance(original, dict) else original
        if isinstance(item, dict) and item.get('type') == 'image' and not item.get('src') and item.get('query'):
            asset = search_image(item['query']) if searches < 1 else None
            searches += 1
            if asset:
                item.update(asset)
                # Region coordinates require an inspected asset. A search query
                # alone is no evidence of where an object lies in the result.
                item.pop('regions', None)
                item.pop('activeRegion', None)
            else:
                item = {'id': item.get('id'), 'type': 'note', 'text': 'Image search is unavailable. Continue with the explanation or a diagram.', 'trigger': item.get('trigger', '')}
        elements.append(item)
    return {**data, 'elements': elements}


VISUAL_FIELDS = {
    'sceneKey': {'type': 'string', 'description': 'Stable short key, reused to update this same scene across spoken windows. Send complete state each time.'},
    'kind': {'type': 'string', 'enum': ['array', 'box-model', 'nodes']},
    'caption': {'type': 'string', 'description': 'One short explanation of the current state.'},
    'items': {'type': 'array', 'maxItems': 16, 'items': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'value': {'type': 'string'}}, 'required': ['id', 'value']}},
    'active': {'type': 'array', 'items': {'type': 'integer'}},
    'visited': {'type': 'array', 'items': {'type': 'integer'}},
    'pointers': {'type': 'array', 'maxItems': 3, 'items': {'type': 'object', 'properties': {'label': {'type': 'string'}, 'index': {'type': 'integer'}}, 'required': ['label', 'index']}},
    'variables': {'type': 'array', 'maxItems': 4, 'items': {'type': 'object', 'properties': {'label': {'type': 'string'}, 'value': {'type': 'string'}}, 'required': ['label', 'value']}},
    'focus': {'type': 'string', 'description': 'Box-model layer (content, padding, border, margin), or node id.'},
    'padding': {'type': 'number'},
    'nodes': {'type': 'array', 'maxItems': 8, 'items': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'label': {'type': 'string'}, 'x': {'type': 'number'}, 'y': {'type': 'number'}}, 'required': ['id', 'label', 'x', 'y']}},
    'edges': {'type': 'array', 'items': {'type': 'object', 'properties': {'from': {'type': 'string'}, 'to': {'type': 'string'}}, 'required': ['from', 'to']}},
    'query': {'type': 'string', 'description': 'Image only: a precise English image search query, when no known src exists. Real lookup runs before display. No invented URLs or region coordinates.'},
    'sourceUrl': {'type': 'string'},
    'activeRegion': {'type': 'string', 'description': 'Image only: id of the region being explained now.'},
    'regions': {'type': 'array', 'maxItems': 8, 'description': 'Image only, for an inspected known src. Coordinates are fractions of the full image, from 0 to 1.', 'items': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'label': {'type': 'string'}, 'x': {'type': 'number'}, 'y': {'type': 'number'}, 'width': {'type': 'number'}, 'height': {'type': 'number'}}, 'required': ['id', 'x', 'y', 'width', 'height']}},
}
