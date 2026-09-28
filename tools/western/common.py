"""Shared helpers for the western family scripts (sync_pr, propagate_family, derive_pr, link_western).

They work on the same sources as the editor (tools/editor/store.py) and save through it, so every
change is an ordinary edit: the glyph's state becomes `derived` (written by a script, not yet
approved) and `git diff` shows exactly what changed. Who drew a glyph is read from its state:
approved / edited = you, derived = a script, ai = the AI original (history/ai-originals keeps the
AI version of every glyph whose pixels changed).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
REPORTS = ROOT / "reports"
sys.path.insert(0, str(HERE.parent / "editor"))
from store import Store  # noqa: E402

FONT = ROOT / "reference-fonts/SourceHanSansSC-VF.otf"   # labels on the report sheets


def open_store():
    return Store(ROOT)


def items(store, groups=("HW", "PR"), scripts=("western",)):
    """{glyph id: {'id', 'char', 'family', 'group'}} of the .HW/.PR glyphs with a letter family.
    group is the old package's name (western-hw, western-pr, kana-hw …)."""
    out = {}
    for gid, g in store.glyphs.items():
        grp = gid.rsplit(".", 1)[-1]
        f = g.get("family")
        if grp in groups and f and f["script"] in scripts:
            out[gid] = {"id": gid, "char": g["char"], "family": f, "group": f"{f['script']}-{grp.lower()}"}
    return out


def state(store, gid):
    return store.records[gid]["state"]


def ai_rows(store, gid):
    """The AI's pixels: archived when the glyph was changed, else its current pixels."""
    return store.ai_originals.get(gid) or store.current(gid)["rows"]


def changed(store, gid):
    return store.current(gid)["rows"] != ai_rows(store, gid)


def by_script(store, gid):
    """Current pixels were last written by a script and are not approved."""
    return state(store, gid) == "derived"


def yours(store, gid):
    """You drew or approved the current version."""
    return state(store, gid) in ("edited", "approved")


def drawn_by(store, gid):
    return {"edited": "你", "approved": "你", "derived": "程序"}.get(state(store, gid), "AI")


def save_derived(store, gid, rows, note):
    """Save rows as a script's version; False if unchanged, or if it would delete black pixels of a
    linked form (then it is listed for you: edit the form or unlink it first)."""
    cur = store.current(gid)
    if cur["rows"] == rows:
        return False
    try:
        store.save({"id": gid, "expected_revision": cur["revision"], "rows": rows, "note": note,
                    "approved": False, "origin": "program"})
    except ValueError as e:
        if "关联形态" not in str(e):
            raise
        print(f"skipped {gid} {store.original(gid)['char']}: would delete pixels of a linked form")
        return False
    return True
