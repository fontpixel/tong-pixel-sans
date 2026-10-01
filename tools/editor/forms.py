"""Shared component forms (forms/forms.txt): linking, unlinking, editing a form and updating every glyph
that uses it. Carried over from the old review editor (archive/tong-review-v1/shapes.py); storage is in store.py.

Only black pixels belong to a form; white is transparent. Linking never changes a pixel except where
the user replaces a linked form. The store provides _library(), _revision() and _commit_shapes().
"""
from collections import Counter
import unicodedata
from copy import deepcopy
import json
from pathlib import Path
import uuid

CROSS_REGION = Path(__file__).resolve().parent / 'data/cross-region.json'
REGION_ORDER = ['SC', 'TC', 'JP']


class ShapesMixin:
    def _cross_region(self):
        """data/cross-region.json (made by archive/tong-review-v1/cross_region.py), reloaded when it changes; None if absent."""
        try:
            stat = CROSS_REGION.stat()
        except FileNotFoundError:
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        if getattr(self, '_cross_key', None) != key:
            self._cross_data, self._cross_key = json.loads(CROSS_REGION.read_text()), key
        return self._cross_data

    def region_ok(self, symbol, form_locale, target_locale, char):
        """(allowed, reason) for using a form of form_locale in a glyph of target_locale.

        Same region: always. Across regions: the character's own outline comparison for this
        component decides first; otherwise the component's class over all compared characters
        must be “shared”. Mixed, different and unknown components stay within their region.
        """
        if form_locale == target_locale:
            return True, ''
        if form_locale not in REGION_ORDER or target_locale not in REGION_ORDER:
            return False, '此地区没有跨地区等价数据'
        data = self._cross_region()
        if not data:
            return False, '尚未生成跨地区等价表（cross_region.py）'
        a, b = sorted([form_locale, target_locale], key=REGION_ORDER.index)
        key = f'{a}-{b}'
        verdict = data['chars'].get(char, {}).get(key, {}).get(symbol)
        if verdict == 'same':
            return True, f'思源轮廓中，本字的{symbol}在 {a}/{b} 相同'
        if verdict == 'different':
            return False, f'思源轮廓中，本字的{symbol}在 {a}/{b} 写法不同'
        c = data['components'].get(symbol, {}).get(key)
        if c and c['class'] == 'shared':
            return True, f'{symbol}在 {a}/{b} 通常相同（{c["same"]} 字相同、{c["different"]} 字不同）'
        if c:
            label = {'different': '写法不同', 'mixed': '写法因字而异'}[c['class']]
            return False, f'{symbol}在 {a}/{b} {label}（{c["same"]} 字相同、{c["different"]} 字不同）'
        return False, f'缺少{symbol}在 {a}/{b} 的比较数据'

    def region_use(self, symbol, form_locale, target_locale, char):
        """(verified, note) for a manual, user-chosen association across regions.

        The user may mix regions freely (their decision, 2026-09-27). `verified` says whether the
        cross-region table confirms the component is written the same; otherwise the note warns.
        """
        if form_locale == target_locale or {form_locale, target_locale} <= {'HW', 'PR', 'WEST'}:
            return True, ''
        ok, reason = self.region_ok(symbol, form_locale, target_locale, char)
        return ok, (reason if ok else '注意：' + reason + '；请确认写法适用')

    def _parts(self, gid):
        from structure import database, split, bounds
        g = self.original(gid)
        rows = self.current(gid)['rows']
        db = database()
        info = db.lookup(g['char'], g['locale'])
        out = []

        def named(symbol, key, rect, ancestors):
            if symbol.startswith('{') or symbol in ['？', '?']:
                return
            out.append({'key': key, 'symbol': symbol, 'rect': rect})
            if symbol in ancestors or len(ancestors) >= 8:
                return
            sub = db.lookup(symbol, g['locale'])
            if sub['available'] and sub['tree']['children']:
                walk(sub['tree'], key + '/', rect, ancestors | {symbol})

        def walk(node, key, rect, ancestors):
            if not node['children']:
                named(node['symbol'], key, rect, ancestors)
                return
            parts = split(rows, rect, node['symbol']) if rect else None
            for i, child in enumerate(node['children']):
                walk(child, key + str(i), parts['rects'][i] if parts else None, ancestors)

        named(g['char'], 'whole', bounds(rows, [0, 0, len(rows[0]), len(rows)]), set())
        # Western letters: the parts are the base letter and each separable diacritic (like IDS for
        # hanzi), listed whether linked or not; a linked movable form gives the part its place.
        lib = self._library()
        links = {l['slot']: l for l in self.current(gid).get('links', [])}
        if g.get('family') and g.get('kind') in ('mono', 'prop') and unicodedata.category(g['char'])[0] == 'L':
            from western import slots
            for key, symbol, _ in slots(g['char'], g['family']):
                out.append({'key': key, 'symbol': symbol, 'rect': None, 'movable': True})
        for key, l in links.items():
            f = lib['shapes'].get(l['shape_id'])
            if f and f.get('movable'):
                fh, fw = len(f['rows']), len(f['rows'][0])
                rect = [l.get('x', 0), l.get('y', 0), fw, fh]
                part = next((p for p in out if p['key'] == key), None)
                if part:
                    part['rect'] = rect
                else:
                    out.append({'key': key, 'symbol': l['symbol'], 'rect': rect, 'movable': True})
        # Keep a stable occurrence key. Multiple occurrences of 木 stay distinct;
        # users never need to label a component as left/right/top/bottom.
        for symbol in {p['symbol'] for p in out}:
            group = [p for p in out if p['symbol'] == symbol]
            for i, p in enumerate(group):
                p['label'] = symbol + (f' · 第{i+1}处' if len(group) > 1 else '')
        return info, [p for p in out if p['key'] != 'whole'] + [p for p in out if p['key'] == 'whole']

    def _form_ok(self, p):
        from store import rows_ok
        rows_ok(p['rows'], self.w, self.h)
        if 'care' in p:
            rows_ok(p['care'], self.w, self.h)
        if not any('#' in r for r in p['rows']):
            raise ValueError('形态至少需要一个黑色像素')
        p['care'] = p['rows'].copy()
        if not isinstance(p.get('name'), str) or not p['name'].strip() or len(p['name']) > 80:
            raise ValueError('形态名称须为1至80个字符')

    def _fingerprint(self, shape):
        from store import digest
        # A saved form's pixels change only with a new revision.
        key = (shape.get('id'), shape.get('revision'))
        cache = self.__dict__.setdefault('_fingerprints', {})
        if key[1] is not None and key in cache:
            return cache[key]
        value = digest([shape['symbol'], shape['locale'], shape['rows'], shape['rows']])
        if key[1] is not None:
            cache[key] = value
        return value

    def _users(self, sid):
        result = []
        for gid in self._usage(self._library()).get(sid, {}):
            g, c = self.original(gid), self.current(gid)
            occurrences = [link for link in c.get('links', []) if link['shape_id'] == sid]
            if occurrences:
                result.append({'id': gid, 'char': g['char'], 'locale': g['locale'],
                               'approved': c['approved'], 'revision': c['revision'],
                               'rows': c['rows'], 'occurrences': occurrences})
        return result

    def _usage(self, lib):
        """{shape_id: {glyph_id: user}}, rebuilt only when a glyph head or the library changes."""
        key = (lib['generation'], self.heads_key())
        if getattr(self, '_usage_key', None) != key:
            usage = {}
            for gid, g in self.glyphs.items():
                c = self.current(gid)
                for link in c.get('links', []):
                    usage.setdefault(link['shape_id'], {})[gid] = {
                        'id': gid, 'char': g['char'], 'locale': g['locale'], 'approved': c['approved']}
            self._usage_cache, self._usage_key = usage, key
        return self._usage_cache

    def _forms(self, lib):
        """Every active and reference form, with usage counts and bounds, no user lists."""
        from structure import bounds
        active = list(lib['shapes'].values())
        hidden = set(lib['retired']) | {self._fingerprint(s) for s in active}
        hidden.update(fp for s in active for fp in s.get('reference_fingerprints', []))
        references = [r for r in self._references()
                      if not hidden.intersection(r['reference_fingerprints'])]
        usage = self._usage(lib)
        derived = self.__dict__.setdefault('_derived', {})
        forms = []
        # Shallow copies: callers only read and serialise these forms.
        for f in active + references:
            key = (f['id'], f.get('revision'))
            if key not in derived or f.get('revision') is None:
                derived[key] = (bounds(f['rows'], [0, 0, len(f['rows'][0]), len(f['rows'])]), sum(r.count('#') for r in f['rows']))
            box, count = derived[key]
            forms.append({**f, 'usage_count': len(usage.get(f['id'], {})), 'bounds': box, 'pixel_count': count})
        return forms

    def shape_catalog(self, gid=None, limit=12):
        """Forms for one glyph's parts: its linked forms, then the closest same-region forms.

        With thousands of forms, the sidebar gets the `limit` forms per
        component that already overlap this glyph's ink best; `totals` tells how
        many exist, and shape_library pages through all of them.
        """
        with self.lock():
            lib = self._library()
            forms = self._forms(lib)
            result = {'generation': lib['generation']}
            if not gid:
                result['forms'] = forms
                return result
            info, parts = self._parts(gid)
            current = self.current(gid)
            locale = self.original(gid)['locale']
            wanted = {p['symbol'] for p in parts}
            linked = {l['shape_id'] for l in current.get('links', [])}
            ink = {(x, y) for y, r in enumerate(current['rows']) for x, v in enumerate(r) if v == '#'}

            def overlap(f):
                if f.get('movable'):
                    rows_f = f.get('form_rows', f['rows'])
                    if len(rows_f) > len(current['rows']) or len(rows_f[0]) > len(current['rows'][0]):
                        return 0
                    at = self._best_offset({'rows': rows_f}, current['rows'])
                    pts = [(x + at['x'], y + at['y']) for y, r in enumerate(rows_f) for x, v in enumerate(r) if v == '#']
                else:
                    pts = [(x, y) for y, r in enumerate(f['rows']) for x, v in enumerate(r) if v == '#']
                return sum(p in ink for p in pts) / max(1, len(pts))

            char = self.original(gid)['char']
            sibling = {}
            for other in self.sibling_ids(gid):
                for l in self.current(other).get('links', []):
                    sibling.setdefault(l['shape_id'], other.rsplit('.', 1)[-1])
            chosen, totals = [], {}
            for symbol in wanted:
                # forms are drawn for one cell height: the Large size (-L) and the Small size never share
                family = [f for f in forms if f['symbol'] == symbol and f['locale'].endswith('-L') == locale.endswith('-L')]
                totals[symbol] = len(family)
                # Every region's forms are offered: same region first, then cross-region forms the
                # table confirms, then the rest with a caution note (the user decides).
                use = {r: self.region_use(symbol, r, locale, char) for r in {f['locale'] for f in family}}
                # Forms that other glyphs of this code point already use come first (all of them).
                near = sorted((f for f in family if f['id'] not in linked),
                              key=lambda f: (f['id'] not in sibling, f['locale'] != locale, not use[f['locale']][0],
                                             -overlap(f), -f['usage_count'], f.get('name', '')))
                def tag(f):
                    t = {**f, 'usable_here': True, 'region_note': use[f['locale']][1],
                         'region_caution': not use[f['locale']][0], 'sibling_locale': sibling.get(f['id'])}
                    if f.get('movable'):   # show where it would go in this glyph
                        w, h = len(current['rows'][0]), len(current['rows'])
                        fr = f['rows']
                        if len(fr) <= h and len(fr[0]) <= w:
                            l = next((l for l in current.get('links', []) if l['shape_id'] == f['id']), None) \
                                or self._best_offset(f, current['rows'])
                            t.update(form_rows=fr, rows=self._placed(f, l, w, h))
                    return t
                chosen += [tag(f) for f in family if f['id'] in linked]
                n_sib = sum(f['id'] in sibling for f in near)
                chosen += [tag(f) for f in near[:max(limit, n_sib + limit)]]
            # Movable forms (western letters, diacritics) are listed by their links, placed in this glyph.
            have = {f['id'] for f in chosen}
            w, h = len(current['rows'][0]), len(current['rows'])
            for l in current.get('links', []):
                f = lib['shapes'].get(l['shape_id'])
                if f and f.get('movable') and f['id'] not in have:
                    chosen.append({**f, 'form_rows': f['rows'], 'rows': self._placed(f, l, w, h),
                                   'usable_here': True, 'region_note': '', 'movable_slot': l['slot']})
                    have.add(f['id'])
            result.update(forms=chosen, totals=totals, structure=info, parts=parts,
                          links=current.get('links', []))
            return result

    def shape_library(self, symbol='', query='', kind='all', offset=0, limit=120):
        """One page of the whole library, grouped by component, searchable on the server."""
        with self.lock():
            lib = self._library()
            usage = self._usage(lib)
            query = query.strip().lower()

            def matches(f):
                if kind != 'all' and f['kind'] != kind:
                    return False
                if not query:
                    return True
                text = [f['symbol'], f.get('name', ''), f['id'], f['locale']]
                text += [s['char'] + ' ' + s['id'] for s in f.get('sources', [])]
                text += [u['char'] + ' ' + u['id'] for u in usage.get(f['id'], {}).values()]
                return query in ' '.join(text).lower()

            found = [f for f in self._forms(lib) if matches(f)]
            counts = Counter(f['symbol'] for f in found)
            page = sorted((f for f in found if not symbol or f['symbol'] == symbol),
                          key=lambda f: (f['symbol'], f['kind'] != 'shared', f['locale'],
                                         -f['usage_count'], f.get('name', '')))
            return {'generation': lib['generation'], 'total': len(page), 'offset': offset,
                    'symbols': sorted(counts.items()), 'forms': page[offset:offset + limit]}

    def auto_link(self, plan, algorithm):
        """Link every planned component form in one recoverable transaction.

        A planned form must be a subset of the glyph's current ink, so linking
        changes no pixel and keeps each glyph's approval. Only the outermost
        planned component over any pixels is linked (see _outermost); inner
        ones fill in where the outer one could not be split. Identical ink at the
        same coordinates reuses one shared form; a form the user removed before
        (a retired fingerprint) is left out, and an occupied slot is kept.
        """
        from store import now
        with self.lock():
            lib = self._library()
            index = {self._fingerprint(s): s for s in lib['shapes'].values()}
            by_pixels = {}  # (symbol, rows) -> shared forms of any region, for cross-region reuse
            for s in lib['shapes'].values():
                by_pixels.setdefault((s['symbol'], tuple(s['rows'])), []).append(s)
            retired = set(lib['retired'])
            names = {(s['symbol'], s['locale'], s['name']) for s in lib['shapes'].values()}
            stats = Counter()
            revisions = []
            for item in plan:
                gid = item['id']
                old = self.current(gid)
                if old['revision'] != item.get('expected_revision', old['revision']):
                    stats['字已被他处修改，跳过'] += 1
                    continue
                locale = self.original(gid)['locale']
                _, parts = self._parts(gid)
                slots = {p['key']: p['symbol'] for p in parts}
                links = list(old.get('links', []))
                ink = {(x, y) for y, r in enumerate(old['rows']) for x, v in enumerate(r) if v == '#'}
                added = 0
                for e in sorted(item['links'], key=lambda e: e['slot'].count('/')):
                    if any(l['slot'] == e['slot'] for l in links):
                        stats['部件已有关联，保留原关联'] += 1
                        continue
                    if any(self._overlaps(l['slot'], e['slot']) for l in links):
                        stats['已由外层部件或原有关联覆盖'] += 1
                        continue
                    if slots.get(e['slot']) != e['symbol']:
                        stats['数据库部件已变化'] += 1
                        continue
                    pts = {(x, y) for y, r in enumerate(e['rows']) for x, v in enumerate(r) if v == '#'}
                    if not pts or not pts <= ink:
                        raise ValueError(f'{gid} {e["slot"]} 的形态含有该字没有的黑点')
                    f = {'symbol': e['symbol'], 'locale': locale, 'rows': e['rows']}
                    fp = self._fingerprint(f)
                    if fp in retired:
                        stats['用户移除过的相同形态，未重建'] += 1
                        continue
                    shape = index.get(fp)
                    if shape is None:
                        char = self.original(gid)['char']
                        shape = next((s for s in by_pixels.get((e['symbol'], tuple(e['rows'])), [])
                                      if self._fingerprint(s) not in retired
                                      and self.region_ok(e['symbol'], s['locale'], locale, char)[0]), None)
                        if shape is not None:
                            stats['跨地区复用相同形态'] += 1
                    if shape is None:
                        x0 = min(x for x, _ in pts); y0 = min(y for _, y in pts)
                        w = max(x for x, _ in pts) - x0 + 1; h = max(y for _, y in pts) - y0 + 1
                        base = f"{e['symbol']} · {e['position']} {w}×{h} @{x0},{y0}"
                        name, n = base, 1
                        while (e['symbol'], locale, name) in names:
                            n += 1; name = f'{base} · 变体{n}'
                        names.add((e['symbol'], locale, name))
                        shape = {**f, 'id': uuid.uuid4().hex, 'revision': uuid.uuid4().hex,
                                 'care': e['rows'].copy(), 'name': name, 'kind': 'shared', 'sources': [],
                                 'note': f'自动分割（{algorithm}）：BabelStone IDS 结构，边界由本字黑点推断，未人审。',
                                 'origin': algorithm, 'created_at': now(), 'updated_at': now()}
                        index[fp] = lib['shapes'][shape['id']] = shape
                        by_pixels.setdefault((e['symbol'], tuple(e['rows'])), []).append(shape)
                        stats['新建形态'] += 1
                    links.append({'slot': e['slot'], 'symbol': e['symbol'], 'shape_id': shape['id'],
                                  'shape_revision': shape['revision'],
                                  'segmentation': {'algorithm': algorithm, 'joins_cut': e['joins_cut']}})
                    added += 1
                if not added:
                    continue
                if self._compose(old['rows'], links, lib) != old['rows']:
                    raise ValueError(f'{gid} 关联后像素会变化，已中止')
                stats['关联部件'] += added; stats['关联字'] += 1
                revisions.append(self._revision(old, old['rows'], links,
                                                 f'自动部件关联（{algorithm}）：{added} 个部件，像素不变',
                                                 approved=old['approved'], origin='automatic-link'))
            if revisions:
                self._commit_shapes(revisions, lib)
            return dict(stats)

    def prune_nested_links(self, algorithm):
        """Remove automatic links inside another link; pixels and approval stay."""
        with self.lock():
            lib = self._library()
            revisions, stats = [], Counter()
            for gid in self.glyphs:
                old = self.current(gid)
                links = old.get('links', [])
                auto = [l for l in links if l.get('segmentation', {}).get('algorithm') == algorithm]
                if not auto:
                    continue
                kept = self._outermost([l for l in links if l not in auto], auto)
                if len(kept) == len(links):
                    continue
                kept = [l for l in links if l in kept]
                n = len(links) - len(kept)
                stats['解除内层自动关联'] += n; stats['涉及字'] += 1
                revisions.append(self._revision(old, old['rows'], kept,
                                                 f'只保留最外层自动关联：解除 {n} 个内层部件，像素不变',
                                                 approved=old['approved'], origin='automatic-link'))
            if revisions:
                before = len(lib['shapes'])
                self._collect(lib, {r['id']: r for r in revisions}, unchosen=algorithm)
                stats['移出无人使用的自动形态'] = before - len(lib['shapes'])
                self._commit_shapes(revisions, lib)
            return dict(stats)


    @staticmethod
    def _placed(shape, link, w, h):
        """The form's pixels in a w×h glyph. Fixed forms carry glyph coordinates; a movable form
        (Latin letters, diacritics) is its own small bitmap placed at the link's x/y."""
        if not shape.get('movable'):
            return shape['rows']
        x0, y0 = link.get('x', 0), link.get('y', 0)
        grid = [['.'] * w for _ in range(h)]
        for y, r in enumerate(shape['rows']):
            for x, v in enumerate(r):
                if v == '#':
                    yy, xx = y + y0, x + x0
                    if not (0 <= yy < h and 0 <= xx < w):
                        raise ValueError(f'可移动形态“{shape.get("name", "")}”超出字格')
                    grid[yy][xx] = '#'
        return [''.join(r) for r in grid]

    def linked_forms(self, gid):
        lib = self._library()
        cur = self.current(gid)
        w, h = len(cur['rows'][0]), len(cur['rows'])
        out = []
        for l in cur.get('links', []):
            f = deepcopy(lib['shapes'][l['shape_id']])
            if f.get('movable'):
                f = {**f, 'form_rows': f['rows'], 'rows': self._placed(f, l, w, h), 'x': l.get('x', 0), 'y': l.get('y', 0)}
            out.append({**f, 'slot': l['slot']})
        return out

    def _compose(self, rows, links, lib):
        result = [list(r) for r in rows]
        w, h = len(rows[0]), len(rows)
        for link in links:
            f = lib['shapes'].get(link['shape_id'])
            if f is None:
                raise ValueError('关联形态已不存在，请重新载入')
            for y, r in enumerate(self._placed(f, link, w, h)):
                for x, v in enumerate(r):
                    if v != '#':
                        continue
                    result[y][x] = '#'
        return [''.join(r) for r in result]

    def _clear(self, rows, grids):
        """Remove the ink of already placed forms (glyph-size grids) from rows."""
        result = [list(r) for r in rows]
        for g in grids:
            for y, r in enumerate(g):
                for x, v in enumerate(r):
                    if v == '#':
                        result[y][x] = '.'
        return [''.join(r) for r in result]

    def check_linked_pixels(self, gid, rows, links):
        expected = self._compose(rows, links, self._library())
        if expected != rows:
            raise ValueError('不能删除关联形态的黑点；请独立编辑形态，或先解除关联。空白位置可自由编辑')

    def _target(self, p):
        from store import Conflict
        old = self.current(p['id'])
        if old['revision'] != p.get('expected_revision'):
            raise Conflict('此字已更新，请保存草稿后重新载入')
        _, parts = self._parts(p['id'])
        target = next((part for part in parts if part['key'] == p['slot']), None)
        if not target:
            raise ValueError('数据库部件已变化，请重新载入')
        return old, target

    def _collect(self, lib, replacements, unchosen=None):
        """Drop forms no glyph uses. A removed form is retired so it does not
        come back as a reference, except automatic forms of algorithm
        `unchosen` that tidying removed: no user ever rejected those."""
        usage = self._usage(lib)
        used = {sid for sid, users in usage.items() if any(gid not in replacements for gid in users)}
        for c in replacements.values():
            used.update(l['shape_id'] for l in c.get('links', []))
        for sid in list(lib['shapes']):
            if sid not in used:
                shape = lib['shapes'].pop(sid)
                if unchosen and shape.get('origin') == unchosen:
                    continue
                lib['retired'] = sorted(set(lib['retired']) | {self._fingerprint(shape)}
                                        | set(shape.get('reference_fingerprints', [])))

    @staticmethod
    def _overlaps(a, b):
        """Same slot, or one component inside the other (named slots nest with '/')."""
        return a == b or a.startswith(b + '/') or b.startswith(a + '/')

    def _outermost(self, fixed, candidates):
        """Keep `fixed` links; add candidates outermost first, never over another link.

        Each black pixel then belongs to at most one linked form: a form nested
        in another could not be edited, since the outer form keeps its old ink.
        An inner component is used only where its outer one is not linked.
        """
        kept = list(fixed)
        for c in sorted(candidates, key=lambda c: c['slot'].count('/')):
            if not any(self._overlaps(c['slot'], k['slot']) for k in kept):
                kept.append(c)
        return kept

    @staticmethod
    def _best_offset(shape, rows):
        """Where a movable form fits a glyph: an exact position (form ⊆ ink), else the most overlap."""
        w, h = len(rows[0]), len(rows)
        ink = {(y, x) for y, r in enumerate(rows) for x, v in enumerate(r) if v == '#'}
        pts = [(y, x) for y, r in enumerate(shape['rows']) for x, v in enumerate(r) if v == '#']
        fh, fw = len(shape['rows']), len(shape['rows'][0])
        best = None
        for y0 in range(0, h - fh + 1):
            for x0 in range(0, w - fw + 1):
                hit = sum((y + y0, x + x0) in ink for y, x in pts)
                if best is None or hit > best[0]:
                    best = (hit, x0, y0)
        if best is None:
            raise ValueError('形态比此字的字格还大')
        return {'x': best[1], 'y': best[2]}

    @staticmethod
    def _in_selection(shape, rows, sel):
        """Place a movable form inside the box you selected: where it matches the glyph's ink best
        within the box; a form larger than the box goes at the box's top-left. None without a box."""
        if not isinstance(sel, dict) or not all(type(sel.get(k)) is int for k in 'xywh'):
            return None
        w, h = len(rows[0]), len(rows)
        fr = shape['rows']; fh, fw = len(fr), len(fr[0])
        pts = [(y, x) for y, r in enumerate(fr) for x, v in enumerate(r) if v == '#']
        ink = {(y, x) for y, r in enumerate(rows) for x, v in enumerate(r) if v == '#'}
        sx, sy, sw, sh = sel['x'], sel['y'], sel['w'], sel['h']
        cands = [(x0, y0) for y0 in range(sy, sy + sh - fh + 1) for x0 in range(sx, sx + sw - fw + 1)]
        if not cands:
            return {'x': min(max(sx, 0), w - fw), 'y': min(max(sy, 0), h - fh)}
        best = max(cands, key=lambda c: (sum((y + c[1], x + c[0]) in ink for y, x in pts),
                                         -abs(c[0] + fw / 2 - (sx + sw / 2)) - abs(c[1] + fh / 2 - (sy + sh / 2))))
        return {'x': best[0], 'y': best[1]}

    BELOW_MARKS = {'¸', '˛', '̣', '̦'}

    def _movable_anchor(self, old, target, shape, lib):
        """Where a movable form goes when you link it: a base letter at its exact place in the glyph;
        a diacritic over the glyph's own pixels outside the linked base (bottom-aligned above the
        base, top-aligned below it, centred), else one row above/below the base, centred."""
        rows = old['rows']; w, h = len(rows[0]), len(rows)
        fr = shape['rows']; fh, fw = len(fr), len(fr[0])
        if not target['key'].startswith('mv:mark'):
            return self._best_offset(shape, rows)
        ink = {(y, x) for y, r in enumerate(rows) for x, v in enumerate(r) if v == '#'}
        base = set(); others = set()
        for l in old.get('links', []):
            f = lib['shapes'].get(l['shape_id'])
            if not f or l['slot'] == target['key']:
                continue
            pts = {(y, x) for y, r in enumerate(self._placed(f, l, w, h)) for x, v in enumerate(r) if v == '#'}
            (base if l['slot'] == 'mv:base' else others).update(pts)
        if not base:
            return self._best_offset(shape, rows)
        by0 = min(y for y, _ in base); by1 = max(y for y, _ in base)
        bx0 = min(x for _, x in base); bx1 = max(x for _, x in base)
        below = shape['symbol'] in self.BELOW_MARKS
        rest = {(y, x) for y, x in ink - base - others if (y > by1 if below else y < by0)}
        if rest:
            ry0 = min(y for y, _ in rest); ry1 = max(y for y, _ in rest)
            cx = (min(x for _, x in rest) + max(x for _, x in rest)) / 2
            y0 = ry0 if below else ry1 - fh + 1
        else:
            cx = (bx0 + bx1) / 2
            y0 = by1 + 1 if below else by0 - 1 - fh
        x0 = int(cx - (fw - 1) / 2 + 0.5)
        x0 = min(max(x0, 0), w - fw); y0 = min(max(y0, 0), h - fh)
        return {'x': x0, 'y': y0}

    def _associate(self, old, target, shape, lib, at=None):
        previous = [l for l in old.get('links', []) if l['slot'] == target['key']]
        links = [l for l in old.get('links', []) if l['slot'] != target['key']]
        w, h = len(old['rows'][0]), len(old['rows'])
        rows = self._clear(old['rows'], [self._placed(lib['shapes'][l['shape_id']], l, w, h) for l in previous])
        # Only an explicitly associated form owns ink. Inferred rectangles and
        # all white cells are transparent, including on the first association.
        link = {'slot': target['key'], 'symbol': target['symbol'], 'shape_id': shape['id'],
                'shape_revision': shape['revision']}
        if shape.get('movable'):
            link.update(at or self._movable_anchor(old, target, shape, lib))
        links.append(link)
        rows = self._compose(rows, links, lib)
        return self._revision(old, rows, links, '关联并应用：' + shape['name'],
                              approved=old['approved'] and rows == old['rows'])

    def shape_link(self, p, preview=False):
        from store import Conflict, now
        with self.lock():
            old, target = self._target(p)
            lib = self._library()
            sid = p['shape_id']
            if sid.startswith('ref-'):
                f = next((r for r in self._references()
                          if sid[4:] in r['reference_fingerprints']), None)
                if not f:
                    raise Conflict('参考来源已更新，请重新载入形态列表')
                shape = next((s for s in lib['shapes'].values()
                              if self._fingerprint(s) == f['fingerprint']), None)
                if shape is None:
                    shape = {**f, 'id': uuid.uuid4().hex, 'revision': uuid.uuid4().hex,
                             'kind': 'shared', 'created_at': now(), 'updated_at': now(),
                             'reference_fingerprints': f['reference_fingerprints'].copy()}
            else:
                shape = lib['shapes'].get(sid)
                if not shape or shape['revision'] != p.get('expected_shape_revision'):
                    raise Conflict('形态已更新或移除，请重新载入')
            if shape['symbol'] != target['symbol']:
                raise ValueError('形态与所选数据库部件不一致')
            # Cross-region use is allowed for a user's explicit choice; the form keeps its region.
            lib['shapes'][shape['id']] = shape
            at = self._in_selection(shape, old['rows'], p.get('selection')) if shape.get('movable') else None
            value = self._associate(old, target, shape, lib, at=at)
            if preview:
                return {'before': old['rows'], 'after': value['rows'], 'shape': shape,
                        'boundary_known': target['rect'] is not None}
            self._collect(lib, {old['id']: value})
            self._commit_shapes([value], lib)
            return {'current': value, 'shape': shape}

    def shape_move(self, p):
        """Move a movable form within this one glyph (dx, dy); other glyphs keep their place."""
        from store import Conflict
        dx, dy = p.get('dx'), p.get('dy')
        if type(dx) is not int or type(dy) is not int or abs(dx) > 16 or abs(dy) > 16:
            raise ValueError('移动量无效')
        with self.lock():
            old, target = self._target(p)
            lib = self._library()
            link = next((l for l in old.get('links', []) if l['slot'] == target['key']), None)
            shape = lib['shapes'].get(link['shape_id']) if link else None
            if not shape or not shape.get('movable'):
                raise ValueError('此部件没有关联可移动形态')
            w, h = len(old['rows'][0]), len(old['rows'])
            moved = {**link, 'x': link.get('x', 0) + dx, 'y': link.get('y', 0) + dy}
            placed_new = self._placed(shape, moved, w, h)   # raises if it would leave the cell
            links = [moved if l is link else l for l in old['links']]
            rows = self._compose(self._clear(old['rows'], [self._placed(shape, link, w, h)]), links, lib)
            value = self._revision(old, rows, links, f'本字中移动形态：{shape["name"]}（{dx:+d}, {dy:+d}）',
                                   approved=old['approved'] and rows == old['rows'])
            self._commit_shapes([value], lib)
            return {'current': value}

    def shape_unlink(self, p):
        with self.lock():
            old, target = self._target(p)
            links = [l for l in old.get('links', []) if l['slot'] != target['key']]
            if links == old.get('links', []):
                raise ValueError('此部件尚未关联形态')
            lib = self._library()
            value = self._revision(old, old['rows'], links, '解除关联，保留当前像素', old['approved'])
            self._collect(lib, {old['id']: value})
            self._commit_shapes([value], lib)
            return {'current': value}

    def shape_unlink_all(self, p):
        """Remove every form link of one glyph in one transaction; pixels and review state stay."""
        from store import Conflict
        with self.lock():
            old = self.current(p['id'])
            if old['revision'] != p.get('expected_revision'):
                raise Conflict('此字已更新，请保存草稿后重新载入')
            if not old.get('links'):
                raise ValueError('此字没有关联形态')
            lib = self._library()
            n = len(old['links'])
            value = self._revision(old, old['rows'], [], f'解除全部 {n} 处关联，保留当前像素', old['approved'])
            self._collect(lib, {old['id']: value})
            self._commit_shapes([value], lib)
            return {'current': value, 'removed_links': n}

    def copy_from(self, p):
        """Replace this glyph by another glyph of the same code point: all its pixels and its form
        links (the same shared forms). The glyph's previous pixels and links are dropped (history
        keeps them). A link goes to this glyph's slot with the same key, else the next unused slot
        of the same component symbol; a form without a matching slot is dropped, its pixels stay."""
        from store import Conflict
        with self.lock():
            gid, src = p['id'], p.get('source_id')
            old = self.current(gid)
            if old['revision'] != p.get('expected_revision'):
                raise Conflict('此字已更新，请保存草稿后重新载入')
            if src not in self.sibling_ids(gid):
                raise ValueError('只能复制同码位的其他字形')
            if not self.can_copy(src, gid):
                raise ValueError('字格大小不同，不能整字复制')
            source = {**self.current(src), 'rows': self.fitted_copy(src, gid)}
            lib = self._library()
            _, parts = self._parts(gid)
            slots = {q['key']: q['symbol'] for q in parts}
            used, links, dropped = set(), [], []
            for link in (source.get('links', []) if self.size(src) == self.size(gid) else []):
                if lib['shapes'].get(link['shape_id'], {}).get('movable'):   # position-based: same size, same place
                    links.append(dict(link)); continue
                key = link['slot'] if slots.get(link['slot']) == link['symbol'] and link['slot'] not in used else next(
                    (k for k, sym in slots.items() if sym == link['symbol'] and k not in used), None)
                if key is None or link['shape_id'] not in lib['shapes']:
                    dropped.append(link['symbol']); continue
                used.add(key)
                links.append({**link, 'slot': key})
            rows = list(source['rows'])
            if self._compose(rows, links, lib) != rows:
                raise ValueError('关联形态与来源字形的像素不一致，已中止')
            note = f'整字复制自 {src}（{len(links)} 处关联）' + (f'；未对应的部件：{"、".join(dropped)}' if dropped else '')
            value = self._revision(old, rows, links, note, approved=False)
            value['note'] = note
            self._collect(lib, {gid: value})
            self._commit_shapes([value], lib)
            return {'current': value, 'links': len(links), 'dropped': dropped}

    def shape_create(self, p):
        from store import now
        with self.lock():
            old, target = self._target(p)
            if target.get('movable'):
                return self._movable_create(p, old, target)
            self._form_ok(p)
            lib = self._library()
            f = {'id': uuid.uuid4().hex, 'revision': uuid.uuid4().hex, 'symbol': target['symbol'],
                 'locale': self.original(p['id'])['locale'], 'name': p['name'].strip(),
                 'rows': p['rows'], 'care': p['care'], 'kind': 'shared', 'sources': [],
                 'note': '', 'created_at': now(), 'updated_at': now()}
            # Only ink and its fixed coordinates determine a form's pixel identity.
            existing = next((s for s in lib['shapes'].values()
                             if self._fingerprint(s) == self._fingerprint(f)), None)
            f = existing or f
            lib['shapes'][f['id']] = f
            value = self._associate(old, target, f, lib)
            self._collect(lib, {old['id']: value})
            self._commit_shapes([value], lib)
            return {'current': value, 'shape': f, 'reused_existing': existing is not None}

    def shape_edit(self, p):
        from store import Conflict, now
        with self.lock():
            lib = self._library()
            old = lib['shapes'].get(p['shape_id'])
            if not old or old['revision'] != p.get('expected_shape_revision'):
                raise Conflict('形态已更新或移除，请重新打开后编辑')
            if old.get('movable'):
                return self._movable_edit(p, old, lib)
            self._form_ok(p)
            users = self._users(old['id'])
            # The exact affected set is part of the user's save decision. A
            # concurrently linked or edited glyph forces a fresh preview.
            if p.get('expected_users') != {u['id']: u['revision'] for u in users}:
                raise Conflict('关联字已变化，请重新打开形态以查看最新影响范围')
            changed = old['rows'] != p['rows']
            shape = {**old, 'name': p['name'].strip(), 'rows': p['rows'], 'care': p['care'],
                     'revision': uuid.uuid4().hex, 'updated_at': now()}
            if 'fingerprint' in shape:
                shape['fingerprint'] = self._fingerprint(shape)
            lib['shapes'][shape['id']] = shape
            revisions = []
            for u in users:
                c = self.current(u['id'])
                links = [{**l, 'shape_revision': shape['revision']} if l['shape_id'] == shape['id']
                         else l for l in c['links']]
                rows = self._compose(self._clear(c['rows'], [old['rows']]), links, lib) if changed else c['rows']
                revisions.append(self._revision(c, rows, links, '共享形态更新：' + shape['name'],
                                                c['approved'] and not changed))
            if p.get('preview'):
                return {'affected': [{'id': r['id'], 'char': self.original(r['id'])['char'],
                                      'before': self.current(r['id'])['rows'], 'after': r['rows']}
                                     for r in revisions]}
            self._commit_shapes(revisions, lib)
            return {'shape': shape, 'updated_ids': [r['id'] for r in revisions]}

    def _movable_create(self, p, old, target):
        """New movable form for a western part (base letter or diacritic): drawn in this glyph's
        grid, stored cropped to its ink, linked where it was drawn."""
        from store import now, rows_ok
        if not isinstance(p.get('name'), str) or not p['name'].strip() or len(p['name']) > 80:
            raise ValueError('形态名称须为1至80个字符')
        w, h = len(old['rows'][0]), len(old['rows'])
        rows_ok(p['rows'], w, h)
        pts = [(y, x) for y, r in enumerate(p['rows']) for x, v in enumerate(r) if v == '#']
        if not pts:
            raise ValueError('形态至少需要一个黑色像素')
        y0, x0 = min(y for y, _ in pts), min(x for _, x in pts)
        y1, x1 = max(y for y, _ in pts), max(x for _, x in pts)
        form = [p['rows'][y][x0:x1 + 1] for y in range(y0, y1 + 1)]
        locale = 'WEST' if target['key'].startswith('mv:mark') else self.original(p['id'])['locale']
        lib = self._library()
        f = {'id': uuid.uuid4().hex, 'revision': uuid.uuid4().hex, 'symbol': target['symbol'], 'locale': locale,
             'name': p['name'].strip(), 'rows': form, 'care': form, 'kind': 'shared', 'movable': True,
             'sources': [], 'note': '', 'created_at': now(), 'updated_at': now()}
        existing = next((sh for sh in lib['shapes'].values() if sh.get('movable') and sh['name'] == f['name']
                         and self._fingerprint(sh) == self._fingerprint(f)), None)
        f = existing or f
        lib['shapes'][f['id']] = f
        value = self._associate(old, target, f, lib, at={'x': x0, 'y': y0})
        self._collect(lib, {old['id']: value})
        self._commit_shapes([value], lib)
        return {'current': value, 'shape': f, 'reused_existing': existing is not None}

    def _movable_edit(self, p, old, lib):
        """Edit a movable form inside one glyph that uses it (context_id): the drawn pixels become
        the form, cropped to their ink; every link's position moves with the form's top-left corner."""
        from store import Conflict, now, rows_ok
        if not isinstance(p.get('name'), str) or not p['name'].strip() or len(p['name']) > 80:
            raise ValueError('形态名称须为1至80个字符')
        users = self._users(old['id'])
        if p.get('expected_users') != {u['id']: u['revision'] for u in users}:
            raise Conflict('关联字已变化，请重新打开形态以查看最新影响范围')
        ctx = p.get('context_id')
        c_ctx = self.current(ctx) if ctx in self.glyphs else None
        link = next((l for l in (c_ctx or {}).get('links', []) if l['shape_id'] == old['id']), None)
        if link is None:
            raise ValueError('请在使用此形态的字里打开并编辑它')
        w, h = len(c_ctx['rows'][0]), len(c_ctx['rows'])
        rows_ok(p['rows'], w, h)
        pts = [(y, x) for y, r in enumerate(p['rows']) for x, v in enumerate(r) if v == '#']
        if not pts:
            raise ValueError('形态至少需要一个黑色像素')
        y0, x0 = min(y for y, _ in pts), min(x for _, x in pts)
        y1, x1 = max(y for y, _ in pts), max(x for _, x in pts)
        form = [p['rows'][y][x0:x1 + 1] for y in range(y0, y1 + 1)]
        dy, dx = y0 - link.get('y', 0), x0 - link.get('x', 0)
        changed = form != old['rows'] or (dy, dx) != (0, 0)
        shape = {**old, 'name': p['name'].strip(), 'rows': form, 'care': form,
                 'revision': uuid.uuid4().hex, 'updated_at': now()}
        if 'fingerprint' in shape:
            shape['fingerprint'] = self._fingerprint(shape)
        lib['shapes'][shape['id']] = shape
        revisions = []
        for u in users:
            c = self.current(u['id'])
            cw, ch = len(c['rows'][0]), len(c['rows'])
            olds = [self._placed(old, l, cw, ch) for l in c['links'] if l['shape_id'] == old['id']]
            links = [{**l, 'shape_revision': shape['revision'], 'x': l.get('x', 0) + dx, 'y': l.get('y', 0) + dy}
                     if l['shape_id'] == shape['id'] else l for l in c['links']]
            try:
                rows = self._compose(self._clear(c['rows'], olds), links, lib) if changed else c['rows']
            except ValueError:
                raise ValueError(f'修改后放不进“{self.original(u["id"])["char"]}”（{u["id"]}）的字格')
            revisions.append(self._revision(c, rows, links, '共享形态更新：' + shape['name'],
                                            c['approved'] and rows == c['rows']))
        if p.get('preview'):
            return {'affected': [{'id': r['id'], 'char': self.original(r['id'])['char'],
                                  'before': self.current(r['id'])['rows'], 'after': r['rows']} for r in revisions]}
        self._commit_shapes(revisions, lib)
        return {'shape': shape, 'updated_ids': [r['id'] for r in revisions]}

    def movable_link(self, forms, plan, note):
        """Create movable forms and link them, in one recoverable transaction; pixels never change.

        forms: {key: {'symbol', 'locale', 'name', 'rows'}} (rows = the form's own cropped bitmap);
        identical forms (same symbol, region and pixels) are reused. plan: {glyph id: [{'form': key,
        'slot', 'symbol', 'x', 'y'}]}. A glyph whose slot is already linked keeps that link. A link
        that would change a pixel aborts everything. Approval stays; revisions are automatic-link.
        """
        from store import now
        with self.lock():
            lib = self._library()
            # reuse only the same form (same name and pixels): upper/lower, .HW/.PR stay separate
            index = {(self._fingerprint(sh), sh['name']): sh for sh in lib['shapes'].values() if sh.get('movable')}
            made = {}
            for key, f in forms.items():
                cand = {'symbol': f['symbol'], 'locale': f['locale'], 'rows': f['rows']}
                sh = index.get((self._fingerprint(cand), f['name']))
                if sh is None:
                    sh = {**cand, 'id': uuid.uuid4().hex, 'revision': uuid.uuid4().hex, 'care': list(f['rows']),
                          'name': f['name'], 'kind': 'shared', 'movable': True, 'sources': [],
                          'note': f.get('note', ''), 'origin': 'movable-auto', 'created_at': now(), 'updated_at': now()}
                    lib['shapes'][sh['id']] = sh
                    index[(self._fingerprint(sh), sh['name'])] = sh
                made[key] = sh
            revisions, linked = [], 0
            for gid, items in plan.items():
                old = self.current(gid)
                links = list(old.get('links', []))
                slots = {l['slot'] for l in links}
                added = 0
                for it in items:
                    if it['slot'] in slots:
                        continue
                    sh = made[it['form']]
                    links.append({'slot': it['slot'], 'symbol': it['symbol'], 'shape_id': sh['id'],
                                  'shape_revision': sh['revision'], 'x': it['x'], 'y': it['y']})
                    slots.add(it['slot']); added += 1
                if not added:
                    continue
                if self._compose(old['rows'], links, lib) != old['rows']:
                    raise ValueError(f'{gid} 关联后像素会变化，已中止')
                revisions.append(self._revision(old, old['rows'], links, note, approved=old['approved'],
                                                origin='automatic-link'))
                linked += added
            if revisions:
                self._commit_shapes(revisions, lib)
            return {'forms': len({sh['id'] for sh in made.values()}), 'glyphs': len(revisions), 'links': linked,
                    'form_ids': {k: sh['id'] for k, sh in made.items()}}

    def movable_unlink(self, ids, reason):
        """Remove every movable-form link of these glyphs in one transaction; pixels and approval stay."""
        with self.lock():
            lib = self._library()
            revisions = []
            for gid in ids:
                old = self.current(gid)
                keep = [l for l in old.get('links', []) if not lib['shapes'].get(l['shape_id'], {}).get('movable')]
                if len(keep) == len(old.get('links', [])):
                    continue
                revisions.append(self._revision(old, old['rows'], keep, reason, approved=old['approved'],
                                                origin='automatic-link'))
            if revisions:
                self._collect(lib, {r['id']: r for r in revisions}, unchosen='movable-auto')
                self._commit_shapes(revisions, lib)
            return {'glyphs': len(revisions)}

    def shape_detail(self, sid):
        with self.lock():
            lib = self._library()
            f = lib['shapes'].get(sid)
            if not f:
                raise ValueError('形态已移除，请重新载入')
            return {'shape': deepcopy(f), 'users': self._users(sid)}
