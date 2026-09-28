"""Local IDS lookup and conservative, traceable crops of approved human bitmaps.

IDS describes relative structure. Pixel boundaries below are our inference, never
claimed to be coordinates supplied by BabelStone or separately approved by a user.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

VENDOR = Path(__file__).resolve().parent / 'vendor/babelstone'
ARITY = {**{c: 2 for c in '⿰⿱⿴⿵⿶⿷⿸⿹⿺⿻⿼⿽㇯'}, '⿲': 3, '⿳': 3, '⿾': 1, '⿿': 1, '〾': 1}
POSITIONS = {'⿰': ['左', '右'], '⿱': ['上', '下'], '⿲': ['左', '中', '右'],
             '⿳': ['上', '中', '下'], **{c: ['包围', '内部'] for c in '⿴⿵⿶⿷⿸⿹⿺⿼⿽'},
             '⿻': ['重叠', '重叠'], '㇯': ['原形', '减去'], '⿾': ['镜像'], '⿿': ['旋转'], '〾': ['变体']}


def stable(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def parse(expression):
    tokens = re.findall(r'\{\d+\}|.', expression)
    def walk(index):
        if index >= len(tokens):
            raise ValueError('Incomplete IDS')
        symbol = tokens[index]; index += 1; children = []
        for _ in range(ARITY.get(symbol, 0)):
            node, index = walk(index); children.append(node)
        return {'symbol': symbol, 'children': children}, index
    root, end = walk(0)
    if end != len(tokens):
        raise ValueError('Trailing IDS tokens')
    return root


def expression(node):
    return node['symbol'] + ''.join(expression(c) for c in node['children'])


class IDS:
    def __init__(self, path=None):
        self.entries = {}
        if path is None:
            metadata = json.loads((VENDOR/'metadata.json').read_text())
            actual = hashlib.sha256((VENDOR/'IDS.TXT').read_bytes()).hexdigest()
            if actual != metadata['sha256']:
                raise ValueError('IDS 数据与固定版本哈希不一致')
        path = path or VENDOR / 'IDS.TXT'
        for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
            if not line.startswith('U+'):
                continue
            fields = line.split('\t'); variants = []
            for value in fields[2:]:
                match = re.fullmatch(r'\^(.+)\$\(([^)]+)\)', value.strip())
                if match:
                    try:
                        variants.append({'ids': match[1], 'regions': match[2], 'tree': parse(match[1])})
                    except ValueError:
                        pass  # An unsupported sequence is unavailable, not silently repaired.
            self.entries[fields[1]] = variants

    def lookup(self, char, locale):
        # BabelStone source codes: G = mainland (SC), T = Taiwan (TC), J = Japan (JP), K = Korea (KR).
        region = {'SC': 'G', 'TC': 'T', 'JP': 'J', 'KR': 'K'}.get(locale)
        if region is None:
            return {'char': char, 'locale': locale, 'available': False, 'alternatives': [],
                    'reason': '仅支持 SC / TC / JP / KR 的结构数据'}
        variants = self.entries.get(char, [])
        matching = [v for v in variants if region in v['regions'] and not v['regions'].startswith(('X', 'Z'))]
        # As documented by the database, a unique structure across actual source
        # forms can be used where this particular source has no assigned form.
        actual = [v for v in variants if v['regions'] not in ['X', 'Z']]
        fallback = False
        if not matching and len({v['ids'] for v in actual}) == 1:
            matching = actual; fallback = True
        unique = {v['ids']: v for v in matching}
        if len(unique) != 1:
            return {'char': char, 'locale': locale, 'available': False, 'alternatives': variants,
                    'reason': '无明确地区结构，保留歧义，不套用其他地区字形。'}
        v = next(iter(unique.values()))
        return {**v, 'char': char, 'locale': locale, 'available': True,
                'region_fallback': fallback, 'database': 'BabelStone IDS'}


@lru_cache(maxsize=1)
def database():
    return IDS()


def bounds(rows, rect):
    x, y, w, h = rect
    points = [(xx, yy) for yy in range(y, y+h) for xx in range(x, x+w) if rows[yy][xx] == '#']
    if not points:
        return None
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs)-min(xs)+1, max(ys)-min(ys)+1]


def split(rows, rect, operator):
    """Choose a low-contact separating line; decline joined/ambiguous shapes.

    No cropping by a guessed 50% split. The threshold deliberately leaves some
    components unavailable; enclosure and overlap need a model-proposed mask.
    """
    if operator not in ['⿰', '⿱']:
        return None
    x, y, w, h = rect
    vertical = operator == '⿰'; size = w if vertical else h
    candidates = []
    for cut in range(2, size-1):
        if not 0.2 <= cut/size <= 0.8:
            continue
        a = [x, y, cut, h] if vertical else [x, y, w, cut]
        b = [x+cut, y, w-cut, h] if vertical else [x, y+cut, w, h-cut]
        aa, bb = bounds(rows, a), bounds(rows, b)
        if not aa or not bb:
            continue
        cross = 0
        if vertical:
            for yy in range(y, y+h):
                if rows[yy][x+cut-1] == '#':
                    cross += sum(rows[ny][x+cut] == '#' for ny in range(max(y, yy-1), min(y+h, yy+2)))
        else:
            for xx in range(x, x+w):
                if rows[y+cut-1][xx] == '#':
                    cross += sum(rows[y+cut][nx] == '#' for nx in range(max(x, xx-1), min(x+w, xx+2)))
        ink = [sum(rows[yy][xx]=='#' for yy in range(r[1],r[1]+r[3]) for xx in range(r[0],r[0]+r[2])) for r in [aa,bb]]
        if min(ink) < 4:
            continue
        score = cross * 10 + abs(cut/size - 0.45)
        candidates.append((score, cross, aa, bb))
    if not candidates:
        return None
    candidates.sort(key=lambda a: a[0])
    best = candidates[0]
    if best[1] > 1:
        return None
    return {'rects': [best[2], best[3]], 'boundary': '分隔处无像素接触' if best[1] == 0 else '分隔处有一处邻接，边界需看整字',
            'confidence': 'clear_gap' if best[1] == 0 else 'limited_contact'}


def slots(char, locale, rows, db=None):
    db = db or database(); info = db.lookup(char, locale)
    output = []
    if not info['available']:
        return info, output
    def visit(node, rect, path, depth, seen):
        # Keep named components whole. Recursing into 亻/木/etc. would suggest
        # individual strokes, and a projection cut cannot establish their identity.
        if not node['children']:
            return
        parts = split(rows, rect, node['symbol']) if rect else None
        for i, child in enumerate(node['children']):
            position = POSITIONS.get(node['symbol'], ['未知'] * len(node['children']))[i]
            location = path + [position]
            child_rect = parts['rects'][i] if parts else None
            if not child['children']:
                output.append({'symbol': child['symbol'], 'position': position, 'path': location,
                               'rect': child_rect, 'boundary': parts['boundary'] if parts else 'IDS 只有相对位置；尚无可靠像素边界',
                               'confidence': parts['confidence'] if parts else 'structure_only'})
            if depth < 2:
                visit(child, child_rect, location, depth+1, seen)
    visit(info['tree'], [0, 0, len(rows[0]), len(rows)], [], 0, {char})
    return info, output


def extract(original, current, db=None):
    if not current['approved']:
        return []
    _, found = slots(original['char'], original['locale'], current['rows'], db)
    # The whole approved glyph can itself be a component, with its own size.
    found.insert(0, {'symbol': original['char'], 'position': '独体', 'path': [],
                    'rect': bounds(current['rows'], [0,0,len(current['rows'][0]),len(current['rows'])]),
                    'boundary': '完整通过字的墨迹范围', 'confidence': 'whole_glyph'})
    result = []
    for part in found:
        if not part['rect'] or part['symbol'].startswith('{') or part['symbol'] == '？':
            continue
        x,y,w,h = part['rect']; pixels = [r[x:x+w] for r in current['rows'][y:y+h]]
        c = {**part, 'name': part['symbol']+' · '+('/'.join(part['path']) or '独体'),
             'source_id': original['id'], 'source_revision': current['revision'], 'source_hash': original['source_hash'],
             'source_char': original['char'], 'locale': original['locale'], 'width': w, 'height': h,
             'rows': pixels, 'care': ['#'*w]*h, 'status': 'automatic', 'usable': True,
             'note': part['boundary']+'；像素取自通过整字，分割未单独人审。', 'algorithm': 'ids-gap-v1'}
        c['id'] = stable(c)[:32]; result.append(c)
    return result


def recommend(info, target_slots, catalog, locale, target_id, query='', width=13, height=13):
    matches = []
    for c in catalog:
        if not c.get('usable') or c['locale'] != locale or c.get('status') == 'rejected':
            continue
        if query and query not in c['name'] and query not in c['source_id'] and query not in c.get('source_char',''):
            continue
        symbol = c.get('symbol')
        # Legacy names carry no semantic key: use a unique known component name
        # contained in the label; a model can provide an explicit symbol later.
        if not symbol:
            names = {p['symbol'] for p in target_slots if p['symbol'] in c['name']}
            symbol = next(iter(names)) if len(names) == 1 else None
        targets = [p for p in target_slots if p['symbol'] == symbol]
        if not targets and not query:
            continue
        for target in targets or [None]:
            if not query and c['source_id'] == target_id:
                continue
            place = target.get('rect') if target else None
            same = bool(target and c['position'] == target['position'])
            # Keep exact size. Anchor to the target component's inferred corner,
            # or the source coordinates where the target has no safe boundary.
            x,y = place[:2] if place else c['rect'][:2]
            fits = x+c['width'] <= width and y+c['height'] <= height
            score = (0 if same else 20) + (0 if place else 10) + {'approved':0, 'proposed':1, 'automatic':4}.get(c['status'],5)
            if c.get('confidence') == 'limited_contact':
                score += 4
            if place:
                score += abs(place[2]-c['width']) + abs(place[3]-c['height'])
            matches.append({**c, 'target': target, 'placement': [x,y], 'fits': fits,
                            'match_note': '同地区、同位置' if same else '同地区；位置或尺寸需比较', 'score': score})
    matches.sort(key=lambda c: (not c['fits'], c['score'], c['source_id'], c['id']))
    # Collapse identical shapes at the same target location while retaining all
    # source references for evidence. Different variants stay separate.
    grouped = {}
    for c in matches:
        key = stable([c.get('symbol'), c['position'], c['rows'], c.get('care'), c['placement']])
        source = {k:c.get(k) for k in ['source_id','source_revision','source_char']}
        if key in grouped:
            grouped[key]['other_sources'].append(source)
        else:
            grouped[key] = {**c, 'other_sources': [source]}
    return list(grouped.values())
