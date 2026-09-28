"""IDS-guided partition of a glyph's own ink into component masks (ids-mask-v1).

BabelStone IDS gives the structure; pixel boundaries here are an inference.
Every mask is a subset of the glyph's existing black pixels: nothing is drawn,
moved or erased. Overlap (⿻) and other unsupported operators are declined, and
so are splits that would cut through too many joined pixels. Their descendants
stay unassigned instead of being guessed.

Candidate cuts are scored by the joins they cut, and, once learned from clean
splits of other glyphs, by how well each part matches the same component's
usual size and known shapes. The best partition of the whole tree wins.
"""
from collections import Counter, defaultdict
from functools import lru_cache
import math

import numpy as np

from structure import database

ALGORITHM = 'ids-mask-v1'
# Single strokes still take part in the partition, but are not component forms.
STROKES = set('一丨丶丿亅乚乛乙乀𠃌𠃋𠄌𠃊𠄎𡿨𠃍⺄')
SEQUENCE = {'⿰': 'x', '⿲': 'x', '⿱': 'y', '⿳': 'y'}
# Sides of the outer component that must frame the inner rectangle.
ENCLOSURE = {'⿴': 'TBLR', '⿵': 'TLR', '⿶': 'BLR', '⿷': 'TBL', '⿼': 'TBR',
             '⿸': 'TL', '⿹': 'TR', '⿺': 'BL', '⿽': 'BR'}
MAX_BREAKS = 4      # joined 8-neighbour pairs one split may separate
BREAK = 1.0         # cost of each join cut
DEVIATION = 0.05    # per pixel per row away from the expected boundary
SHIFT = 0.35        # per pixel a seam bends between rows
UNRESOLVED = 1.5    # per component slot left without a mask
CANDIDATES = 4
DECAY = 0.6         # weight of a child's subtree cost; deep splits advise, not decide
CLEAN = 1           # most joins cut along a slot's path for it to teach priors


def is_stroke(symbol):
    return symbol in STROKES or 0x31C0 <= ord(symbol[0]) <= 0x31EF


def ink(rows):
    return frozenset((x, y) for y, r in enumerate(rows) for x, v in enumerate(r) if v == '#')


def pairs(mask):
    """Each 8-connected pair of black pixels once."""
    return [(x, y, x + dx, y + dy) for x, y in mask
            for dx, dy in [(1, -1), (1, 0), (1, 1), (0, 1)] if (x + dx, y + dy) in mask]


def box(mask):
    xs = [p[0] for p in mask]; ys = [p[1] for p in mask]
    return min(xs), min(ys), max(xs), max(ys)


def normal(mask):
    """Shape without position, for recognising the same form elsewhere."""
    x0, y0, _, _ = box(mask)
    return frozenset((x - x0, y - y0) for x, y in mask)


# ---------------------------------------------------------------- structure

def build(char, locale, db=None):
    """Mirror ShapesMixin._parts: same slot keys, same recursion and limits."""
    db = db or database()

    def named(symbol, key, ancestors):
        if symbol.startswith('{') or symbol in ['？', '?']:
            return None
        node = {'slot': key, 'symbol': symbol, 'sub': None}
        if symbol not in ancestors and len(ancestors) < 8:
            sub = db.lookup(symbol, locale)
            if sub['available'] and sub['tree']['children']:
                node['sub'] = walk(sub['tree'], key + '/', ancestors | {symbol})
        return node

    def walk(tree, key, ancestors):
        if not tree['children']:
            return named(tree['symbol'], key, ancestors)
        return {'op': tree['symbol'], 'children': [walk(c, key + str(i), ancestors)
                                                   for i, c in enumerate(tree['children'])]}

    return named(char, 'whole', set())


def slots(node):
    """Component slots (not strokes, not the whole glyph) below a node."""
    if node is None:
        return []
    if 'op' in node:
        return [s for c in node['children'] for s in slots(c)]
    own = [] if node['slot'] == 'whole' or is_stroke(node['symbol']) else [node['slot']]
    return own + slots(node['sub'])


def symbols(node):
    out = {}
    def visit(n):
        if n is None:
            return
        if 'op' in n:
            for c in n['children']:
                visit(c)
        else:
            out[n['slot']] = n['symbol']; visit(n['sub'])
    visit(node)
    return out


def signature(node):
    """What a child is, for size priors: its symbol, or its structure."""
    if node is None:
        return '?'
    if 'op' in node:
        return node['op'] + ''.join(signature(c) for c in node['children'])
    return node['symbol']


def extent(node, axis):
    """How many components follow each other along an axis (fallback prior)."""
    if node is None:
        return 1
    if 'op' in node:
        values = [extent(c, axis) for c in node['children']]
        return sum(values) if SEQUENCE.get(node['op']) == axis else max(values)
    if is_stroke(node['symbol']) or node['sub'] is None:
        return 1
    return extent(node['sub'], axis)


# ---------------------------------------------------------------- priors

class Priors:
    """What clean splits of other glyphs taught about each component."""

    def __init__(self, sizes=None, counts=None, shapes=None):
        self.sizes = sizes or {}      # (signature, axis) -> median extent
        self.counts = counts or {}    # symbol -> median black pixels
        self.shapes = shapes or {}    # symbol -> Counter(normalised shape)

    def size(self, child, axis):
        return self.sizes.get((signature(child), axis), extent(child, axis) * 4.5)

    def fit(self, symbol, mask):
        """Cost of calling this mask the symbol: size mismatch minus shape support."""
        if is_stroke(symbol):
            return 0.0
        cost = 0.0
        median = self.counts.get(symbol)
        if median:
            cost += 1.5 * abs(math.log(len(mask) / median))
        seen = self.shapes.get(symbol)
        if seen:
            support = seen.get(normal(mask), 0)
            cost -= min(2.0, 0.6 * math.log2(1 + support))
        return cost


def learn(results):
    """Priors from slots whose whole path cut at most CLEAN joins."""
    sizes, counts, shapes = defaultdict(list), defaultdict(list), defaultdict(Counter)
    for node, found, cut in results:
        names = symbols(node)
        for s, m in found.items():
            if cut.get(s, 99) <= CLEAN and not is_stroke(names[s]) and s != 'whole':
                counts[names[s]].append(len(m)); shapes[names[s]][normal(m)] += 1

        def visit(n):
            if n is None:
                return
            if 'op' in n:
                axis = SEQUENCE.get(n['op'])
                for c in n['children']:
                    m = masks_of(c, found)
                    key = slot_of(c)
                    if axis and m and (key is None or cut.get(key, 99) <= CLEAN):
                        x0, y0, x1, y1 = box(m)
                        sizes[(signature(c), axis)].append(x1 - x0 + 1 if axis == 'x' else y1 - y0 + 1)
                    visit(c)
            else:
                visit(n['sub'])
        visit(node)
    return Priors({k: float(np.median(v)) for k, v in sizes.items() if len(v) >= 3},
                  {k: float(np.median(v)) for k, v in counts.items() if len(v) >= 3},
                  {k: Counter({f: n for f, n in v.items() if n >= 2}) for k, v in shapes.items()})


def slot_of(node):
    return None if node is None or 'op' in node else node['slot']


def masks_of(node, found):
    """Union of a child's assigned pixels, when its partition is known."""
    if node is None:
        return None
    if 'op' in node:
        parts = [masks_of(c, found) for c in node['children']]
        if any(p is None for p in parts):
            return None
        return frozenset().union(*parts)
    return found.get(node['slot'])


# ---------------------------------------------------------------- partitions

def seam(mask, axis, expected):
    """Distinct low-cost boundaries across an axis: [(breaks, cost, first, rest)].

    A boundary value b in each row (column for 'y') puts pixels with
    coordinate < b in the first part; it may bend one pixel per row. Cost is
    one scalar: joins cut, distance from the expected boundary, and bends.
    """
    if axis == 'y':
        return [(k, c, frozenset((y, x) for x, y in a), frozenset((y, x) for x, y in b))
                for k, c, a, b in seam(frozenset((y, x) for x, y in mask), 'x', expected)]
    x0, y0, x1, y1 = box(mask)
    if x1 - x0 < 1:
        return []
    values = range(x0 + 1, x1 + 1)

    def within(y, b):
        return int((b - 1, y) in mask and (b, y) in mask)

    def across(y, b, c):
        return sum(1 for x in range(x0, x1 + 1) if (x, y) in mask
                   for dx in (-1, 0, 1) if (x + dx, y + 1) in mask and (x < b) != (x + dx < c))

    results = []
    # One optimum per anchor column gives distinct alternatives to the caller,
    # which keeps whichever also lets the children split and fit.
    for anchor in values:
        def pull(b):
            return abs(b - anchor) * 0.3
        best = {b: (within(y0, b), abs(b - expected) * DEVIATION + pull(b), (b,)) for b in values}
        for y in range(y0 + 1, y1 + 1):
            nxt = {}
            for c in values:
                for b in (c - 1, c, c + 1):
                    if b not in best:
                        continue
                    k, cost, path = best[b]
                    kk = k + across(y - 1, b, c) + within(y, c)
                    cc = cost + abs(b - c) * SHIFT + abs(c - expected) * DEVIATION + pull(c)
                    if c not in nxt or kk * BREAK + cc < nxt[c][0] * BREAK + nxt[c][1]:
                        nxt[c] = (kk, cc, path + (c,))
            best = nxt
        k, cost, path = min(best.values(), key=lambda o: o[0] * BREAK + o[1])
        first = frozenset((x, y) for x, y in mask if x < path[y - y0])
        if first and first != mask:
            results.append((k, cost - sum(pull(b) for b in path), first, mask - first))
    unique = {}
    for r in sorted(results, key=lambda r: r[0] * BREAK + r[1]):
        unique.setdefault(r[2], r)
    return list(unique.values())


def plausible(parts, axis, children):
    """Parts follow each other and none is a sliver of a real component."""
    total = sum(len(p) for p in parts)
    for part, child in zip(parts, children):
        stroke = child is not None and 'op' not in child and is_stroke(child['symbol'])
        if len(part) < (1 if stroke else max(2, 0.1 * total)):
            return False
    i = 0 if axis == 'x' else 1
    centres = [sum(p[i] for p in part) / len(part) for part in parts]
    return all(a < b for a, b in zip(centres, centres[1:]))


def sequence(mask, axis, children, prior):
    """Two or three parts in reading order."""
    x0, y0, x1, y1 = box(mask)
    lo, span = (x0, x1 - x0 + 1) if axis == 'x' else (y0, y1 - y0 + 1)
    sizes = [prior.size(c, axis) for c in children]
    options = []
    for n, cost, first, rest in seam(mask, axis, lo + span * sizes[0] / sum(sizes)):
        if n > MAX_BREAKS:
            continue
        if len(children) == 2:
            if plausible([first, rest], axis, children):
                options.append((n, cost, [first, rest]))
            continue
        r0 = box(rest)
        rlo, rspan = (r0[0], r0[2] - r0[0] + 1) if axis == 'x' else (r0[1], r0[3] - r0[1] + 1)
        for m, cost2, second, third in seam(rest, axis, rlo + rspan * sizes[1] / (sizes[1] + sizes[2])):
            if n + m <= MAX_BREAKS and plausible([first, second, third], axis, children):
                options.append((n + m, cost + cost2, [first, second, third]))
    return options


def enclosure(mask, op, children=(None, None)):
    """Outer frame and inner rectangle: every candidate rectangle, vectorised.

    Joins are counted as inner pixels touching the frame, so a cross whose four
    arm tips meet a box (田) counts four, not the twelve neighbour pairs.
    """
    sides = ENCLOSURE[op]
    inner_child = children[1]
    stroke = inner_child is not None and 'op' not in inner_child and is_stroke(inner_child['symbol'])
    x0, y0, x1, y1 = box(mask)
    pts = np.array(sorted(mask))
    pr = np.array(pairs(mask)) if len(mask) > 1 else np.zeros((0, 4), int)
    # A framed side leaves at least one column/row of frame outside; an open
    # side may still tighten, since a frame stroke can reach into it.
    lo_x = range(x0 + 1, x1) if 'L' in sides else range(x0, x1)
    hi_x = range(x0 + 2, x1 + 1) if 'R' in sides else range(x0 + 2, x1 + 2)
    lo_y = range(y0 + 1, y1) if 'T' in sides else range(y0, y1)
    hi_y = range(y0 + 2, y1 + 1) if 'B' in sides else range(y0 + 2, y1 + 2)
    rects = np.array([(l, r, t, b) for l in lo_x for r in hi_x if r - l >= 2
                      for t in lo_y for b in hi_y if b - t >= 2])
    if not len(rects):
        return []
    L, R, T, B = (rects[:, i:i + 1] for i in range(4))

    def inside(x, y):
        return (L <= x) & (x < R) & (T <= y) & (y < B)

    inner = inside(pts[:, 0], pts[:, 1])
    count = inner.sum(1)
    index = {tuple(p): i for i, p in enumerate(pts.tolist())}
    contact = np.zeros(inner.shape, bool)
    if len(pr):
        ia, ib = inside(pr[:, 0], pr[:, 1]), inside(pr[:, 2], pr[:, 3])
        cross = ia != ib
        for j, (ax, ay, bx, by) in enumerate(pr.tolist()):
            contact[:, index[(ax, ay)]] |= cross[:, j] & ia[:, j]
            contact[:, index[(bx, by)]] |= cross[:, j] & ib[:, j]
    n_breaks = contact.sum(1)
    grid = np.zeros((y1 + 3, x1 + 3), int)
    for x, y in mask:
        grid[y, x] = 1
    least = 1 if stroke else max(3, 0.15 * len(mask))
    ok = (count >= least) & (count <= 0.85 * len(mask)) & (n_breaks <= MAX_BREAKS)
    options = []
    for i in np.nonzero(ok)[0]:
        l, r, t, b = (int(v) for v in rects[i])
        # The frame must actually run along each required side of the inner box.
        need = []
        if 'T' in sides:
            need.append(max(grid[y, max(l - 1, 0):r + 1].sum() for y in range(max(t - 2, 0), t)) / (r - l + 1))
        if 'B' in sides:
            need.append(max(grid[y, max(l - 1, 0):r + 1].sum() for y in range(b, b + 2)) / (r - l + 1))
        if 'L' in sides:
            need.append(max(grid[max(t - 1, 0):b + 1, x].sum() for x in range(max(l - 2, 0), l)) / (b - t + 1))
        if 'R' in sides:
            need.append(max(grid[max(t - 1, 0):b + 1, x].sum() for x in range(r, r + 2)) / (b - t + 1))
        if min(need) < (0.3 if op == '⿺' else 0.45):
            continue
        cost = -2 * count[i] / len(mask) + (r - l) * (b - t) * 0.004 - sum(need) * 0.5
        options.append((int(n_breaks[i]), cost, i))
    options.sort(key=lambda o: o[0] * BREAK + o[1])
    out, seen = [], set()
    for n, cost, i in options:
        inner_mask = frozenset(tuple(p) for p in pts[inner[i]].tolist())
        if inner_mask in seen:
            continue
        seen.add(inner_mask)
        out.append((n, cost, [mask - inner_mask, inner_mask]))
        if len(out) >= 2 * CANDIDATES:
            break
    return out


# ---------------------------------------------------------------- assignment

def assign(node, mask, prior, cut=0, memo=None):
    """(cost, {slot: mask}, {slot: joins cut along its path}) for the best tree."""
    memo = {} if memo is None else memo
    key = (id(node), mask, cut)
    if key not in memo:
        memo[key] = _assign(node, mask, prior, cut, memo)
    return memo[key]


def _assign(node, mask, prior, cut, memo):
    if node is None or not mask:
        return UNRESOLVED * len(slots(node)), {}, {}
    if 'op' not in node:
        cost = prior.fit(node['symbol'], mask) if node['slot'] != 'whole' else 0.0
        found, cuts = {node['slot']: mask}, {node['slot']: cut}
        if node['sub'] is not None:
            c, f, t = assign(node['sub'], mask, prior, cut, memo)
            cost += c; found.update(f); cuts.update(t)
        return cost, found, cuts
    op, children = node['op'], node['children']
    if not slots(node):
        return 0.0, {}, {}  # only strokes below: nothing to name, nothing to decide
    if op in SEQUENCE and len(children) in (2, 3):
        options = sequence(mask, SEQUENCE[op], children, prior)
    elif op in ENCLOSURE and len(children) == 2:
        options = enclosure(mask, op, children)
    else:
        options = []
    options.sort(key=lambda o: o[0] * BREAK + o[1])
    best = None
    for n, cost, parts in options[:CANDIDATES]:
        total, found, cuts = n * BREAK + cost, {}, {}
        for child, part in zip(children, parts):
            c, f, t = assign(child, part, prior, max(cut, n), memo)
            total += DECAY * c; found.update(f); cuts.update(t)
        if best is None or total < best[0]:
            best = (total, found, cuts)
    return best or (UNRESOLVED * len(slots(node)), {}, {})


@lru_cache(maxsize=None)
def structure(char, locale):
    return build(char, locale)


def segment(char, locale, rows, prior=None):
    """(tree, {slot: mask}, {slot: joins cut}) for every slot the partition resolved.

    Strokes and the whole glyph are included so priors can see the full
    partition; use slots(tree) for the component slots worth a shared form.
    """
    node = structure(char, locale)
    _, found, cuts = assign(node, ink(rows), prior or Priors())
    return node, found, cuts


# ---------------------------------------------------------------- whole library

def positions(node):
    """The relation label of each slot inside its parent, e.g. 左 / 下 / 内部."""
    from structure import POSITIONS
    out = {}

    def visit(n, label):
        if n is None:
            return
        if 'op' in n:
            names = POSITIONS.get(n['op'], ['未知'] * len(n['children']))
            for i, c in enumerate(n['children']):
                visit(c, names[i] if i < len(names) else '未知')
        else:
            out[n['slot']] = label
            visit(n['sub'], label)
    visit(node, '独体')
    return out


def _work(item):
    gid, char, locale, rows, prior = item
    _, found, cuts = segment(char, locale, rows, prior)
    return gid, found, cuts


def segment_all(glyphs, passes=3, workers=None):
    """{gid: (found, cuts)} and the final priors, for [(gid, char, locale, rows)].

    Each pass relearns size and shape priors from the previous pass's clean
    splits, so one glyph's clear gap helps a crowded glyph with the same parts.
    """
    from multiprocessing import Pool
    prior, results = Priors(), {}
    with Pool(workers) as pool:
        for _ in range(passes):
            done = pool.map(_work, [(*g, prior) for g in glyphs], chunksize=8)
            results = {gid: (found, cuts) for gid, found, cuts in done}
            prior = learn([(structure(c, l), *results[gid]) for gid, c, l, _ in glyphs])
    return results, prior


def plan(glyphs, results, prior, width=13, height=13):
    """Component forms worth linking: [{id, links: [...]}], plus declined counts."""
    out, declined = [], Counter()
    for gid, char, locale, rows in glyphs:
        node = structure(char, locale)
        found, cuts = results[gid]
        names, where = symbols(node), positions(node)
        links = []
        for s in slots(node):
            mask = found.get(s)
            if mask is None:
                declined['未能明确分开'] += 1
                continue
            median = prior.counts.get(names[s])
            if len(mask) < 2 or (median and not 0.4 <= len(mask) / median <= 2.5):
                declined['黑点数与同部件差异过大'] += 1
                continue
            grid = [['.'] * width for _ in range(height)]
            for x, y in mask:
                grid[y][x] = '#'
            links.append({'slot': s, 'symbol': names[s], 'position': where[s],
                          'rows': [''.join(r) for r in grid], 'joins_cut': cuts.get(s, 0)})
        out.append({'id': gid, 'links': links})
    return out, declined
