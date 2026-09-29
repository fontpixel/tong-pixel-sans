"""The editor's view of the plain-text sources: glyphs/<GROUP>/<PAGE>xx.txt and forms/forms.txt.

All glyph pages and the form library are parsed once; a page changed on disk (a git checkout, a text
editor, a script) is re-read before the next request. Every save rewrites only the touched pages, in
exactly the format described in README.md, so untouched glyphs never show up in a diff. Each glyph's
and form's `revision` is a hash of its text block; a save that expects an older revision is refused.
History comes from git when the repository is under version control.
"""
from __future__ import annotations

import contextlib
import copy
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from pathlib import Path

import reference
from forms import ShapesMixin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build  # noqa: E402  (the fonts' assembly rules decide which glyphs are used)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
REGIONAL = ["SC", "TC", "JP", "KR"]
GROUPS = REGIONAL + ["HW", "PR", "GEOMETRIC-FULL", "GEOMETRIC-HALF"]
ORDER = {g: i for i, g in enumerate(GROUPS)}
# 13×13 ink in a 14×14 cell (blank left column and bottom row); as in the source packages' config.json
GEOMETRY = {"cell_width": 14, "cell_height": 14, "ink_width": 13, "ink_height": 13, "advance": 14, "x_base": 1,
            "ascent": 12, "descent": 2}
BASELINE_ROW = 11
MAX_PROPORTIONAL_WIDTH = 16
STATES = ("approved", "edited", "derived", "ai", "draft", "hangul-ai", "hangul-composed", "generated")


class Conflict(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def rows_ok(rows, w, h):
    if not isinstance(rows, list) or len(rows) != h or any(
            not isinstance(r, str) or len(r) != w or set(r) - {".", "#"} for r in rows):
        raise ValueError(f"点阵必须为 {w}×{h} 的 . / # 数组")
    return rows


def printable(ch):
    return unicodedata.category(ch)[0] in "LNPS" and not unicodedata.combining(ch)


def short_hash(text):
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".tmp-" + uuid.uuid4().hex)
    with tmp.open("x", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


# ---------------------------------------------------------------- text format
def parse_block(group, lines):
    head = lines[0].split(" ")
    cp = int(head[0][2:], 16)
    rec = {"id": f"U+{cp:04X}.{group}", "cp": cp, "group": group, "char": chr(cp)}
    if len(head) > 3 and head[2] == "=":
        rec["alias"] = head[3]
        return rec
    rec["metrics"] = head[2:]
    rec["state"] = lines[1]
    rec["rows"], rec["links"], rec["ai_note"], rec["human_note"] = [], [], [], []
    for line in lines[2:]:
        if line.startswith("@ "):
            parts = line.split(" ")
            link = {"slot": parts[1], "symbol": parts[2], "shape_id": parts[3]}
            if len(parts) > 4:
                x, y = parts[4].split(",")
                link.update(x=int(x), y=int(y))
            rec["links"].append(link)
        elif line.startswith("# AI: "):
            rec["ai_note"].append(line[6:])
        elif line.startswith("# 人工: "):
            rec["human_note"].append(line[6:])
        elif set(line) <= {".", "#"}:
            rec["rows"].append(line)
        else:
            raise ValueError(f"{rec['id']}: 无法识别的行 {line!r}")
    return rec


def block_text(rec):
    ch = rec["char"]
    head = [f"U+{rec['cp']:04X}", ch if printable(ch) else "-"]
    if "alias" in rec:
        return " ".join(head + ["=", rec["alias"]])
    lines = [" ".join(head + rec["metrics"]), rec["state"], *rec["rows"]]
    for l in rec["links"]:
        lines.append(f"@ {l['slot']} {l['symbol']} {l['shape_id']}" + (f" {l['x']},{l['y']}" if "x" in l else ""))
    lines += [f"# AI: {t}" for t in rec["ai_note"]] + [f"# 人工: {t}" for t in rec["human_note"]]
    return "\n".join(lines)


def parse_forms(text):
    out = {}
    for b in text.split("\n\n"):
        lines = [l for l in b.split("\n") if l]
        if not lines:
            continue
        _, sid, kind, symbol, locale, name = lines[0].split(" ", 5)
        rows = [l for l in lines[1:] if set(l) <= {".", "#"}]
        note = [l[2:] for l in lines[1:] if l.startswith("# ")]
        out[sid] = {"id": sid, "revision": short_hash("\n".join(lines)), "symbol": symbol, "locale": locale,
                    "name": name, "rows": rows, "care": list(rows), "kind": "shared", "movable": kind == "movable",
                    "note": "\n".join(note), "sources": []}
    return out


def form_text(f):
    return "\n".join([f"FORM {f['id']} {'movable' if f.get('movable') else 'fixed'} {f['symbol']} {f['locale']} {f['name']}"]
                     + f["rows"] + [f"# {l}" for l in (f.get("note") or "").splitlines() if l.strip()])


def forms_text(shapes):
    order = sorted(shapes.values(), key=lambda f: (bool(f.get("movable")), f["symbol"], f["name"]))
    return "\n\n".join(form_text(f) for f in order) + "\n"


# ---------------------------------------------------------------- store
class Store(ShapesMixin):
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.glyph_dir, self.forms_path = self.root / "glyphs", self.root / "forms/forms.txt"
        self.geometry, self.w, self.h = GEOMETRY, GEOMETRY["ink_width"], GEOMETRY["ink_height"]
        self.build = "text"
        self.mutex = threading.RLock()
        self.lock_state = threading.local()
        self.families = self._read_families()
        self.pages = {}       # page path -> (mtime_ns, [record ids in file order])
        self.records = {}     # glyph id -> record (own blocks and aliases)
        self.glyphs = {}      # glyph id -> editor view of glyphs with their own pixels
        self.forms, self.forms_mtime = {}, None
        self.generation = 0
        self.ids_version = 0  # changes when glyphs are added or removed (pages re-read from disk)
        self.base = {}        # glyph id -> rows of the last commit (or at start-up without git)
        with self.lock():
            self._sync()
        self.base = self._base_rows()
        self.ai_originals = self._read_ai_originals()

    # ---- locking and freshness
    @contextlib.contextmanager
    def lock(self):
        with self.mutex:
            if getattr(self.lock_state, "active", False):
                yield
                return
            with (self.root / ".editor.lock").open("a+b") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                self.lock_state.active = True
                try:
                    self._sync()
                    yield
                finally:
                    self.lock_state.active = False
                    fcntl.flock(f, fcntl.LOCK_UN)

    def _sync(self):
        """Re-read every page (and the form library) whose file changed since it was read."""
        changed = False
        seen = set()
        for p in sorted(self.glyph_dir.glob("*/*.txt")):
            seen.add(p)
            m = p.stat().st_mtime_ns
            if self.pages.get(p, (None,))[0] != m:
                self._load_page(p, m)
                changed = True
                self.ids_version += 1
        for p in set(self.pages) - seen:
            for gid in self.pages.pop(p)[1]:
                self.records.pop(gid, None); self.glyphs.pop(gid, None)
            changed = True
            self.ids_version += 1
        m = self.forms_path.stat().st_mtime_ns
        if m != self.forms_mtime:
            self.forms, self.forms_mtime = parse_forms(self.forms_path.read_text(encoding="utf-8")), m
            changed = True
        if changed:
            self.generation += 1

    def _load_page(self, path, mtime):
        group = path.parent.name
        if group not in GROUPS:
            raise ValueError(f"未知分组 {group}")
        for gid in self.pages.get(path, (None, []))[1]:
            self.records.pop(gid, None); self.glyphs.pop(gid, None)
        ids = []
        for b in path.read_text(encoding="utf-8").split("\n\n"):
            lines = [l for l in b.split("\n") if l]
            if not lines:
                continue
            rec = parse_block(group, lines)
            rec["page"] = path
            self.records[rec["id"]] = rec
            ids.append(rec["id"])
            if "alias" not in rec:
                self.glyphs[rec["id"]] = self._view(rec)
        self.pages[path] = (mtime, ids)

    def _view(self, rec):
        """Static facts about a glyph (what the old store called the AI original, minus the pixels)."""
        g = {"id": rec["id"], "char": rec["char"], "locale": rec["group"], "group": rec["group"],
             "note": "\n".join(rec["ai_note"])}
        grp = rec["group"]
        if grp in REGIONAL:
            return g
        meta = dict(t.split("=", 1) for t in rec["metrics"])
        width = len(rec["rows"][0])
        kind = "prop" if grp == "PR" else "mono"
        adv = meta.get("adv", "7" if grp.endswith("HALF") else "14")
        g.update(kind=kind, cell=(width, len(rec["rows"])), baseline_row=BASELINE_ROW,
                 advance=width if adv == "auto" else int(adv), auto_advance=adv == "auto",
                 x_offset=int(meta.get("x", 0)))
        if rec["cp"] in self.families and grp in ("HW", "PR"):
            g["family"] = self.families[rec["cp"]]
        return g

    def _read_ai_originals(self):
        """history/ai-originals: the AI's version of every glyph whose pixels were changed since. The
        store adds a glyph here the first time its AI pixels change (see _commit_shapes)."""
        self.ai_records = {}
        for p in sorted((self.root / "history/ai-originals").glob("*/*.txt")):
            for b in p.read_text(encoding="utf-8").split("\n\n"):
                lines = [l for l in b.split("\n") if l]
                if lines:
                    rec = parse_block(p.parent.name, lines)
                    self.ai_records[rec["id"]] = rec
        return {gid: r["rows"] for gid, r in self.ai_records.items()}

    def _keep_ai_original(self, rec):
        """Archive an AI glyph's pixels before they change for the first time."""
        keep = {"id": rec["id"], "cp": rec["cp"], "group": rec["group"], "char": rec["char"], "metrics": [],
                "state": "ai", "rows": list(rec["rows"]), "links": [], "ai_note": list(rec["ai_note"]), "human_note": []}
        self.ai_records[rec["id"]] = keep
        self.ai_originals[rec["id"]] = keep["rows"]
        return self.root / "history/ai-originals" / rec["group"] / f"{rec['cp'] >> 8:02X}xx.txt"

    def _write_ai_page(self, path):
        group, page = path.parent.name, int(path.name[:-6], 16)
        recs = sorted((r for r in self.ai_records.values() if r["group"] == group and r["cp"] >> 8 == page),
                      key=lambda r: r["cp"])
        atomic_write(path, "\n\n".join(block_text(r) for r in recs) + "\n")

    @staticmethod
    def _read_families():
        out = {}
        for line in (HERE / "data/families.txt").read_text(encoding="utf-8").splitlines():
            if line.startswith("U+"):
                cp, _, script, name, base, marks = line.split("\t")
                out[int(cp[2:], 16)] = {"script": script, "name": name, "base": base,
                                        "marks": [m for m in marks.split(",") if m]}
        return out

    def heads_key(self):
        return self.generation

    def usage(self):
        """{glyph id: [face names that use it]} and {code point: {face name: glyph id}}, from the
        same assembly rules as tools/build.py. Recomputed when the set of glyphs changes, not on
        pixel edits (usage does not depend on pixels)."""
        key = self.ids_version
        if getattr(self, "_usage_faces_key", None) != key:
            used, served = {}, {}
            for region, prop, mono in build.faces(self.root):
                for kind, face in (("", prop), ("Mono ", mono)):
                    name = f"{kind}{region}"
                    for cp, g in face.items():
                        if g.get("src"):
                            used.setdefault(g["src"], []).append(name)
                            served.setdefault(cp, {})[name] = g["src"]
            self._usage_faces, self._usage_faces_key = (used, served), key
        return self._usage_faces

    def usage_of(self, gid):
        """Where a glyph is used; for an unused one, which glyphs the fonts use instead and why."""
        used, served = self.usage()
        faces = used.get(gid, [])
        out = {"faces": faces, "unused": not faces}
        if not faces:
            rec = self.records[gid]
            cp, group = rec["cp"], rec["group"]
            instead = {}
            for face, src in sorted(served.get(rec["cp"], {}).items()):
                instead.setdefault(src, []).append(face)
            out["instead"] = [{"id": src, "faces": f} for src, f in sorted(instead.items())]
            if group in REGIONAL and cp in build.read_narrow(self.root).get(group, set()):
                out["reason"] = f"思源黑体 {group} 里它是半角或比例宽，字体里改用西文字形"
            elif group in REGIONAL and build.letter(cp):
                out["reason"] = "字母在比例版用西文比例字形，在等宽版用半角字形"
            elif group == "GEOMETRIC-FULL":
                out["reason"] = "比例版只用全宽的制表符和方块元素，其余用半宽"
            elif group == "PR":
                out["reason"] = "这个码位用地区全角字形或半角字形"
        return out

    # ---- git
    def _git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=True).stdout

    def has_git(self):
        try:
            return self._git("rev-parse", "--verify", "HEAD").strip() != ""
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _base_rows(self):
        """Rows as of the last git commit (the editor's “changes” are measured from it); without git,
        the rows at start-up."""
        base = {gid: list(r["rows"]) for gid, r in self.records.items() if "alias" not in r}
        if not self.has_git():
            return base
        listing = self._git("ls-tree", "-r", "HEAD", "--", "glyphs")
        paths = [l.split("\t", 1)[1] for l in listing.splitlines() if l.endswith(".txt")]
        proc = subprocess.run(["git", "-C", str(self.root), "cat-file", "--batch"], input="".join(f"HEAD:{p}\n" for p in paths),
                              capture_output=True, text=True, check=True)
        out, pos = proc.stdout, 0
        for p in paths:
            nl = out.index("\n", pos)
            size = int(out[pos:nl].split()[2])
            # sizes are in bytes; slice on the encoded text
            raw = out[nl + 1:].encode()[:size].decode()
            pos = nl + 1 + len(raw) + 1
            group = p.split("/")[1]
            for b in raw.split("\n\n"):
                lines = [l for l in b.split("\n") if l]
                if lines:
                    rec = parse_block(group, lines)
                    if "alias" not in rec:
                        base[rec["id"]] = rec["rows"]
        return base

    def history(self, gid):
        """Committed versions of this glyph, newest first (git), each only when it changed."""
        rec = self.records[gid]
        if not self.has_git():
            return []
        rel = str(rec["page"].relative_to(self.root))
        out, last = [], None
        log = self._git("log", "-n", "20", "--format=%H%x09%cI%x09%s", "--", rel).splitlines()
        for i, line in enumerate(log):
            commit, when, subject = line.split("\t", 2)
            try:
                text = self._git("show", f"{commit}:{rel}")
            except subprocess.CalledProcessError:
                continue
            for b in text.split("\n\n"):
                lines = [l for l in b.split("\n") if l]
                if lines and lines[0].split(" ")[0] == f"U+{rec['cp']:04X}":
                    old = parse_block(rec["group"], lines)
                    if "alias" in old or block_text(old) == last:
                        break
                    last = block_text(old)
                    out.append({"revision": commit[:12], "sequence": len(log) - i, "saved_at": when, "subject": subject,
                                "approved": old["state"] == "approved", "state": old["state"], "origin": "git",
                                "rows": old["rows"], "note": "\n".join(old["human_note"]), "reused": []})
                    break
        return out

    # ---- glyph access
    def original(self, gid):
        if gid not in self.glyphs:
            raise ValueError("没有这个字形（ID 须带地区或分组后缀，如 .SC / .HW）")
        return self.glyphs[gid]

    def current(self, gid):
        with self.lock():
            rec = self.records.get(gid)
            if rec is None or "alias" in rec:
                raise ValueError("没有这个字形（ID 须带地区或分组后缀，如 .SC / .HW）")
            return {"id": gid, "revision": short_hash(block_text(rec)), "rows": list(rec["rows"]),
                    "links": copy.deepcopy(rec["links"]), "note": "\n".join(rec["human_note"]),
                    "approved": rec["state"] == "approved", "state": rec["state"], "reused": []}

    def size(self, gid):
        g = self.original(gid)
        if self.flexible_width(gid):
            rows = self.records[gid]["rows"]
            return len(rows[0]), len(rows)
        return tuple(g.get("cell", (self.w, self.h)))

    def flexible_width(self, gid):
        """Proportional glyphs with adv=auto: the build takes the advance from the ink, so the width may
        change; the height stays 14."""
        return bool(self.original(gid).get("auto_advance"))

    def rows_fit(self, gid, rows):
        if self.flexible_width(gid):
            w = len(rows[0]) if isinstance(rows, list) and rows and isinstance(rows[0], str) else 0
            if not 1 <= w <= MAX_PROPORTIONAL_WIDTH:
                raise ValueError(f"比例字宽度须为 1–{MAX_PROPORTIONAL_WIDTH} 像素")
            return rows_ok(rows, w, self.original(gid)["cell"][1])
        return rows_ok(rows, *self.size(gid))

    def geometry_of(self, gid):
        g = self.original(gid)
        if "cell" not in g:
            return self.geometry
        w, h = self.size(gid)
        full = g["group"] == "GEOMETRIC-FULL"
        return {"cell_width": w, "cell_height": h, "ink_width": w, "ink_height": h, "x_base": 0,
                "flexible_width": self.flexible_width(gid),
                "advance": w if g["auto_advance"] else g["advance"], "x_offset": g["x_offset"],
                "ascent": BASELINE_ROW, "descent": h - BASELINE_ROW, "baseline_row": BASELINE_ROW,
                "kind": "mono" if full else g["kind"],
                "reference_label": reference.label(gid)}

    def sibling_ids(self, gid):
        char = self.original(gid)["char"]
        if getattr(self, "_char_key", None) != self.generation:
            index = {}
            for other, g in self.glyphs.items():
                index.setdefault(g["char"], []).append(other)
            self._char_index, self._char_key = index, self.generation
        return sorted((o for o in self._char_index.get(char, []) if o != gid),
                      key=lambda o: (ORDER.get(o.rsplit(".", 1)[-1], 9), o))

    def aliases_of(self, gid):
        return sorted(i for i, r in self.records.items() if r.get("alias") == gid)

    def can_copy(self, source, gid):
        if self.size(source) == self.size(gid):
            return True
        return self.flexible_width(gid) and self.size(source)[1] == self.size(gid)[1]

    def fitted_copy(self, source, gid):
        rows = self.current(source)["rows"]
        if self.size(source) == self.size(gid) and not self.flexible_width(gid):
            return rows
        if not self.flexible_width(gid):
            raise ValueError("字格大小不同，不能整字复制")
        cols = [x for r in rows for x, v in enumerate(r) if v == "#"]
        if not cols:
            return ["."] * len(rows)
        x0, x1 = min(cols), max(cols)
        return [r[x0:x1 + 1] + "." for r in rows]

    def siblings(self, gid):
        out = []
        for other in self.sibling_ids(gid):
            c = self.current(other)
            out.append({"id": other, "locale": self.original(other)["locale"], "rows": c["rows"], "revision": c["revision"],
                        "approved": c["approved"], "edited": c["state"] in ("edited", "derived"), "state": c["state"],
                        "links": len(c["links"]), "same_size": self.can_copy(other, gid),
                        "geometry": self.geometry_of(other), "aliases": self.aliases_of(other)})
        return out

    @staticmethod
    def lists():
        """Named glyph lists (data/lists/<name>.txt: one glyph id per line, # comments) for the filter."""
        out = {}
        for p in sorted((HERE / "data/lists").glob("*.txt")):
            ids = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
            out[p.stem] = ids
        return out

    @staticmethod
    def packed(rows):
        """Compact pixels for the glyph list's previews: width, then each row as hex (bit 0 = leftmost)."""
        w = len(rows[0]) if rows else 0
        n = (w + 3) // 4
        return f"{w}:" + ".".join(format(int(r.replace(".", "0").replace("#", "1")[::-1], 2), f"0{n}x") for r in rows)

    def queue(self):
        with self.lock():
            out, used = [], self.usage()[0]
            for gid, g in self.glyphs.items():
                rec = self.records[gid]
                out.append({"id": gid, "char": g["char"], "locale": g["locale"], "batch": rec["state"],
                            "concern": g["note"], "approved": rec["state"] == "approved",
                            "unused": gid not in used, "b": self.packed(rec["rows"]),
                            "edited": rec["state"] in ("edited", "derived") or rec["rows"] != self.base.get(gid)})
            out.sort(key=lambda q: (ORDER[q["locale"]], q["id"]))
            return out

    def payload(self, gid):
        with self.lock():
            g = self.original(gid)
            base = self.base.get(gid, self.records[gid]["rows"])
            ai = self.ai_originals.get(gid)
            if ai is not None and not self.flexible_width(gid) and self.size(gid) != (len(ai[0]), len(ai)):
                ai = None
            ref = reference.available(gid)
            original = {**g, "rows": base, "base_label": "上次提交" if self.has_git() else "编辑器启动时",
                        "ai_rows": ai, "batch": self.records[gid]["state"]}
            return {"original": original, "current": self.current(gid), "geometry": self.geometry_of(gid),
                    "reference": f"/api/reference/{gid}" if ref else None,
                    "overlay": f"/api/overlay/{gid}" if ref else None,
                    "history": self.history(gid), "linked_forms": self.linked_forms(gid),
                    "siblings": self.siblings(gid), "aliases": self.aliases_of(gid), "usage": self.usage_of(gid)}

    def phase_draft(self, gid):
        """The phase-searched draft (“相位底稿”) of a glyph, computed now from the reference fonts."""
        import draft
        g = self.original(gid)
        return draft.compute(gid, g["char"], g["group"], reference.label(gid), (g.get("family") or {}).get("script", ""))

    def reference_svg(self, gid, fill):
        g = self.original(gid)
        geom = self.geometry_of(gid)
        return reference.svg(gid, g["char"], geom["cell_width"], geom["cell_height"], fill)

    def reading(self, approved_only=False):
        with self.lock():
            out = []
            for gid, g in self.glyphs.items():
                rec = self.records[gid]
                if approved_only and rec["state"] != "approved":
                    continue
                out.append({"id": gid, "char": g["char"], "locale": g["locale"], "rows": rec["rows"],
                            "approved": rec["state"] == "approved",
                            **({"advance": len(rec["rows"][0]) if g["auto_advance"] else g["advance"], "x_base": 0}
                               if "cell" in g else {})})
            out.sort(key=lambda q: (ORDER[q["locale"]], q["id"]))
            return out

    # ---- saving
    @staticmethod
    def _state(old, rows, approved, origin):
        if approved:
            return "approved"
        if origin == "ai":
            return "ai"   # a new AI version (e.g. a second repair pass), never approved
        if rows != old["rows"]:
            return "derived" if origin == "program" else "edited"
        if old["state"] == "approved":
            return "edited"   # withdrawn approval: a person looked at it
        return old["state"]

    def _revision(self, old, rows, links, reason, approved=False, origin="human"):
        return {**old, "rows": rows, "links": links, "approved": approved, "origin": origin,
                "state": self._state(old, rows, approved, origin), "change_reason": reason, "reused": []}

    def save(self, p):
        gid = p["id"]
        self.rows_fit(gid, p["rows"])
        if type(p.get("approved")) is not bool or not isinstance(p.get("note"), str):
            raise ValueError("缺少审核状态或修改说明")
        if len(p["note"]) > 3000:
            raise ValueError("说明过长")
        with self.lock():
            old = self.current(gid)
            if p.get("expected_revision") != old["revision"]:
                raise Conflict("此字已在别处保存或文件已变化，请重新载入后再修改")
            self.check_linked_pixels(gid, p["rows"], old["links"])
            origin = "program" if p.get("origin") == "program" and not p["approved"] else "human"
            value = self._revision(old, p["rows"], old["links"], "", p["approved"], origin)
            value["note"] = p["note"]
            self._commit_shapes([value])
            return self.current(gid)

    def import_ai(self, gid, rows, ai_note, expected_revision):
        """Replace an unreviewed AI glyph or a draft by a new AI version (state becomes `ai`, the `# AI:` note is
        replaced). The first AI version is archived in history/ai-originals. Links whose form pixels
        are no longer all in the new rows are removed from this glyph only (forms are not changed; a
        form no glyph uses any more leaves the library). Refused if the glyph changed since
        expected_revision or is not in state `ai`."""
        self.rows_fit(gid, rows)
        with self.lock():
            old = self.current(gid)
            if old["revision"] != expected_revision:
                raise Conflict(f"{gid} 已被修改，未导入")
            if old["state"] not in ("ai", "draft"):
                raise Conflict(f"{gid} 状态为 {old['state']}，只替换 AI 版本或底稿")
            lib = self._library()
            w, h = len(rows[0]), len(rows)
            ink = {(y, x) for y, r in enumerate(rows) for x, v in enumerate(r) if v == "#"}
            keep, dropped = [], []
            for l in old["links"]:
                f = lib["shapes"].get(l["shape_id"])
                placed = self._placed(f, l, w, h) if f else None
                ok = placed is not None and all((y, x) in ink for y, r in enumerate(placed) for x, v in enumerate(r) if v == "#")
                (keep if ok else dropped).append(l)
            value = self._revision(old, rows, keep, "AI 版本导入", approved=False, origin="ai")
            value["ai_note"] = ai_note
            self._collect(lib, {gid: value})
            self._commit_shapes([value], lib)
            return {"current": self.current(gid), "kept_links": len(keep), "dropped_links": [l["symbol"] for l in dropped]}

    def add_glyphs(self, new):
        """Add glyphs that do not exist yet: [{'group', 'cp', 'rows' | 'alias', 'state', 'metrics', 'ai_note'}].
        Each goes on its page in code point order (a new page file if needed). Refuses existing ids."""
        with self.lock():
            touched = set()
            for n in new:
                gid = f"U+{n['cp']:04X}.{n['group']}"
                if gid in self.records:
                    raise Conflict(f"{gid} 已存在")
                page = self.glyph_dir / n["group"] / f"{n['cp'] >> 8:02X}xx.txt"
                rec = {"id": gid, "cp": n["cp"], "group": n["group"], "char": chr(n["cp"]), "page": page}
                if "alias" in n:
                    rec["alias"] = n["alias"]
                else:
                    if n["state"] not in STATES:
                        raise ValueError(f"未知状态 {n['state']}")
                    rec.update(metrics=list(n.get("metrics", [])), state=n["state"], rows=list(n["rows"]), links=[],
                               ai_note=[t for t in (n.get("ai_note") or "").splitlines() if t.strip()], human_note=[])
                self.records[gid] = rec
                ids = self.pages.get(page, (None, []))[1]
                ids = sorted(ids + [gid], key=lambda i: self.records[i]["cp"])
                self.pages[page] = (None, ids)
                touched.add(page)
            for page in touched:
                ids = self.pages[page][1]
                atomic_write(page, "\n\n".join(block_text(self.records[i]) for i in ids) + "\n")
                self.pages[page] = (page.stat().st_mtime_ns, ids)
                for gid in ids:
                    if "alias" not in self.records[gid]:
                        self.glyphs[gid] = self._view(self.records[gid])
            self.generation += 1
            self.ids_version += 1
            return len(new)

    def _write_pages(self, pages):
        for page in pages:
            ids = self.pages[page][1]
            atomic_write(page, "\n\n".join(block_text(self.records[i]) for i in ids) + "\n")
            self.pages[page] = (page.stat().st_mtime_ns, ids)

    def split_alias(self, p):
        """Give an alias its own copy of the glyph it shares, so this region can be edited alone: the
        pixels, metrics and notes, then the form links where this region's component slots match
        (as copy_from). An approved or edited source gives state `edited` (this region is not
        reviewed yet); otherwise the source's state is kept."""
        with self.lock():
            gid = p["id"]
            rec = self.records.get(gid)
            if rec is None or "alias" not in rec:
                raise ValueError(f"{gid} 不是别名")
            src = rec["alias"]
            s = self.records[src]
            state = "edited" if s["state"] in ("approved", "edited") else s["state"]
            own = {k: rec[k] for k in ("id", "cp", "group", "char", "page")}
            own.update(metrics=list(s["metrics"]), state=state, rows=list(s["rows"]), links=[],
                       ai_note=list(s["ai_note"]), human_note=[f"拆开别名，复制自 {src}"])
            self.records[gid] = own
            self.glyphs[gid] = self._view(own)
            self._write_pages([own["page"]])
            self.generation += 1
            self.ids_version += 1
            if s["links"] and self.can_copy(src, gid):
                r = self.copy_from({"id": gid, "expected_revision": self.current(gid)["revision"], "source_id": src})
                return {"current": self.current(gid), "source": src, "links": r["links"], "dropped": r["dropped"]}
            return {"current": self.current(gid), "source": src, "links": 0, "dropped": []}

    def make_alias(self, p):
        """Make a glyph an alias of another glyph of the same code point whose pixels are identical.
        Aliases of this glyph move to the target; its links are dropped (a form no glyph uses any
        more leaves the library); an AI version or draft is archived in history/ai-originals first."""
        with self.lock():
            gid, target = p["id"], p.get("target")
            old = self.current(gid)
            if old["revision"] != p.get("expected_revision"):
                raise Conflict(f"{gid} 已被修改，请重新载入")
            if target not in self.sibling_ids(gid):
                raise ValueError("只能设为同码位其他字形的别名")
            if self.size(target) != self.size(gid) or self.flexible_width(gid) != self.flexible_width(target):
                raise ValueError("字格大小不同，不能共用字形")
            rec, tgt = self.records[gid], self.records[target]
            if rec["rows"] != tgt["rows"] or rec["metrics"] != tgt["metrics"]:
                raise ValueError("像素或度量与目标不完全相同，不能共用字形")
            lib = self._library()
            self._collect(lib, {gid: {"links": []}})
            pages = {rec["page"]}
            for a in self.aliases_of(gid):
                self.records[a]["alias"] = target
                pages.add(self.records[a]["page"])
            if rec["state"] in ("ai", "hangul-ai", "draft") and gid not in self.ai_originals:
                self._write_ai_page(self._keep_ai_original(rec))
            self.records[gid] = {k: rec[k] for k in ("id", "cp", "group", "char", "page")} | {"alias": target}
            self.glyphs.pop(gid, None)
            if set(lib["shapes"]) != set(self.forms):
                self._commit_shapes([], lib)
            self._write_pages(pages)
            self.generation += 1
            self.ids_version += 1
            return {"id": gid, "alias": target}

    def _library(self):
        return {"generation": self.generation, "shapes": dict(self.forms), "retired": []}

    def _references(self):
        return []   # the old extracted reference forms are not part of the sources

    def component_catalog(self):
        return []

    def _commit_shapes(self, revisions, library=None):
        """Write changed glyphs (and the form library) back to their text files."""
        with self.lock():
            touched, ai_pages = set(), set()
            if library is not None:
                shapes = {}
                for sid, f in library["shapes"].items():
                    f = {**f, "care": list(f["rows"])}
                    f["revision"] = short_hash(form_text(f))
                    shapes[sid] = f
                used = {l["shape_id"] for r in revisions for l in r.get("links", [])}
                missing = used - set(shapes)
                if missing:
                    raise ValueError(f"关联到不存在的形态：{sorted(missing)}")
                self.forms = shapes
            for r in revisions:
                rec = self.records[r["id"]]
                if r["state"] not in STATES:
                    raise ValueError(f"未知状态 {r['state']}")
                if r["rows"] != rec["rows"] and rec["state"] in ("ai", "hangul-ai", "draft") and rec["id"] not in self.ai_originals:
                    ai_pages.add(self._keep_ai_original(rec))
                rec["rows"] = list(r["rows"])
                links = []
                for l in r.get("links", []):
                    link = {"slot": l["slot"], "symbol": l["symbol"], "shape_id": l["shape_id"]}
                    if self.forms.get(l["shape_id"], {}).get("movable"):
                        link.update(x=l.get("x", 0), y=l.get("y", 0))
                    links.append(link)
                rec["links"] = links
                rec["state"] = r["state"]
                rec["human_note"] = [t.strip() for t in (r.get("note") or "").splitlines() if t.strip()]
                if "ai_note" in r:
                    rec["ai_note"] = [t.strip() for t in r["ai_note"].splitlines() if t.strip()]
                touched.add(rec["page"])
            for path in ai_pages:
                self._write_ai_page(path)
            if library is not None:
                atomic_write(self.forms_path, forms_text(self.forms))
                self.forms_mtime = self.forms_path.stat().st_mtime_ns
            for page in touched:
                ids = self.pages[page][1]
                atomic_write(page, "\n\n".join(block_text(self.records[i]) for i in ids) + "\n")
                self.pages[page] = (page.stat().st_mtime_ns, ids)
            for page in touched:
                for gid in self.pages[page][1]:
                    if "alias" not in self.records[gid]:
                        self.glyphs[gid] = self._view(self.records[gid])
            self.generation += 1
