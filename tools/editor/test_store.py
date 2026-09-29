"""Tests for the editor store on a small synthetic repository in a temporary directory.

    python3 tools/editor/test_store.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from store import Conflict, Store  # noqa: E402

BLANK = "." * 13
TEN = ["#" * 12 + "."] + [BLANK] * 12                    # one long horizontal stroke
CROSS = [BLANK] * 6 + ["#" * 12 + "."] + [BLANK] * 6
HW_E = ["......."] * 5 + [".###...", "#...#..", "#####..", "#......", ".###..."] + ["......."] * 4
HW_E_ACUTE = ["......."] * 2 + ["...#...", "..#...."] + ["......."] + HW_E[5:]
E_FORM = [".###.", "#...#", "#####", "#....", ".###."]

PAGES = {
    "glyphs/SC/4Exx.txt": "\n\n".join([
        "\n".join(["U+4E00 一", "ai"] + TEN + ["@ whole 一 f1", "# AI: 横画"]),
        "\n".join(["U+4E01 丁", "approved"] + TEN),
        "\n".join(["U+4E03 七", "ai"] + CROSS),
    ]) + "\n",
    "glyphs/TC/4Exx.txt": "U+4E00 一 = U+4E00.SC\n",
    "glyphs/HW/00xx.txt": "\n\n".join([
        "\n".join(["U+0065 e adv=7", "approved"] + HW_E + ["@ mv:base e m1 0,5"]),
        "\n".join(["U+00E9 é adv=7", "ai"] + HW_E_ACUTE + ["@ mv:base e m1 0,5"]),
    ]) + "\n",
}
FORMS = "\n\n".join([
    "\n".join(["FORM m1 movable e HW e · 等宽"] + E_FORM),
    "\n".join(["FORM f1 fixed 一 SC 一 · 横"] + TEN),
]) + "\n"


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel, text in PAGES.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)
        (self.root / "forms").mkdir()
        (self.root / "forms/forms.txt").write_text(FORMS)
        self.s = Store(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, rel):
        return (self.root / rel).read_text()

    def test_loads_and_round_trips(self):
        self.assertEqual(len(self.s.glyphs), 5)
        self.assertEqual(self.s.aliases_of("U+4E00.SC"), ["U+4E00.TC"])
        self.s._commit_shapes([self.s._revision(self.s.current("U+4E03.SC"), CROSS, [], "")])
        for rel, text in PAGES.items():
            self.assertEqual(self.page(rel), text, rel)

    def test_save_sets_state_note_and_refuses_stale_revision(self):
        cur = self.s.current("U+4E03.SC")
        rows = list(CROSS); rows[0] = "#" + BLANK[1:]
        new = self.s.save({"id": "U+4E03.SC", "expected_revision": cur["revision"], "rows": rows,
                           "note": "加一点", "approved": False})
        self.assertEqual(new["state"], "edited")
        self.assertIn("# 人工: 加一点", self.page("glyphs/SC/4Exx.txt"))
        with self.assertRaises(Conflict):
            self.s.save({"id": "U+4E03.SC", "expected_revision": cur["revision"], "rows": rows, "note": "",
                         "approved": True})
        done = self.s.save({"id": "U+4E03.SC", "expected_revision": new["revision"], "rows": rows,
                            "note": "", "approved": True})
        self.assertEqual(done["state"], "approved")

    def test_first_change_archives_ai_original(self):
        cur = self.s.current("U+4E03.SC")
        rows = list(CROSS); rows[12] = "#" + BLANK[1:]
        self.s.save({"id": "U+4E03.SC", "expected_revision": cur["revision"], "rows": rows, "note": "",
                     "approved": False})
        archived = self.page("history/ai-originals/SC/4Exx.txt")
        self.assertEqual(archived, "\n".join(["U+4E03 七", "ai"] + CROSS) + "\n")
        self.assertEqual(self.s.ai_originals["U+4E03.SC"], CROSS)

    def test_cannot_erase_linked_pixels(self):
        cur = self.s.current("U+4E00.SC")
        with self.assertRaises(ValueError):
            self.s.save({"id": "U+4E00.SC", "expected_revision": cur["revision"], "rows": [BLANK] * 13,
                         "note": "", "approved": False})

    def test_editing_a_fixed_form_updates_its_users(self):
        f = self.s.forms["f1"]
        users = self.s._users("f1")
        rows = list(TEN); rows[1] = "#" + BLANK[1:]
        out = self.s.shape_edit({"shape_id": "f1", "expected_shape_revision": f["revision"],
                                 "expected_users": {u["id"]: u["revision"] for u in users},
                                 "name": f["name"], "rows": rows, "care": rows})
        self.assertEqual(out["updated_ids"], ["U+4E00.SC"])
        self.assertEqual(self.s.current("U+4E00.SC")["rows"][1], "#" + BLANK[1:])
        self.assertEqual(self.s.current("U+4E00.SC")["state"], "edited")
        self.assertIn("#" + BLANK[1:], self.page("forms/forms.txt"))

    def test_moving_a_movable_form_in_one_glyph(self):
        cur = self.s.current("U+00E9.HW")
        out = self.s.shape_move({"id": "U+00E9.HW", "expected_revision": cur["revision"], "slot": "mv:base",
                                 "dx": 1, "dy": 0})["current"]
        self.assertEqual(out["links"][0]["x"], 1)
        self.assertEqual(self.s.current("U+0065.HW")["links"][0]["x"], 0)
        self.assertIn("@ mv:base e m1 1,5", self.page("glyphs/HW/00xx.txt"))

    def test_unlinking_the_last_user_drops_the_form(self):
        cur = self.s.current("U+4E00.SC")
        self.s.shape_unlink({"id": "U+4E00.SC", "expected_revision": cur["revision"], "slot": "whole"})
        self.assertNotIn("f1", self.s.forms)
        self.assertNotIn("FORM f1", self.page("forms/forms.txt"))
        self.assertEqual(self.s.current("U+4E00.SC")["rows"], TEN)

    def test_import_ai_keeps_state_and_drops_broken_links(self):
        cur = self.s.current("U+4E00.SC")
        rows = [BLANK] * 6 + ["#" * 12 + "."] + [BLANK] * 6          # the stroke moves: 一's form no longer fits
        with self.assertRaises(Conflict):
            self.s.import_ai("U+4E00.SC", rows, "二次修字", "stale")
        out = self.s.import_ai("U+4E00.SC", rows, "二次修字", cur["revision"])
        self.assertEqual(out["current"]["state"], "ai")
        self.assertEqual(out["dropped_links"], ["一"])
        page = self.page("glyphs/SC/4Exx.txt")
        self.assertIn("U+4E00 一\nai\n", page)
        self.assertIn("# AI: 二次修字", page)
        self.assertNotIn("# AI: 横画", page)
        self.assertIn("# AI: 横画", self.page("history/ai-originals/SC/4Exx.txt"))
        self.assertNotIn("f1", self.s.forms)                           # no user left
        with self.assertRaises(Conflict):                               # only AI versions are replaced
            self.s.import_ai("U+4E01.SC", TEN, "x", self.s.current("U+4E01.SC")["revision"])

    def test_split_alias_then_make_alias_again(self):
        with self.assertRaises(ValueError):
            self.s.split_alias({"id": "U+4E00.SC"})                   # not an alias
        out = self.s.split_alias({"id": "U+4E00.TC"})
        self.assertEqual((out["source"], out["links"]), ("U+4E00.SC", 1))
        cur = self.s.current("U+4E00.TC")
        self.assertEqual((cur["rows"], cur["state"]), (TEN, "ai"))
        self.assertEqual(self.s.aliases_of("U+4E00.SC"), [])
        self.assertIn("U+4E00 一\nai\n" + "\n".join(TEN), self.page("glyphs/TC/4Exx.txt"))
        # pixels differ: refused; identical again: back to an alias, the AI version archived
        rows = list(TEN); rows[1] = "#" + BLANK[1:]
        changed = self.s.save({"id": "U+4E00.TC", "expected_revision": cur["revision"], "rows": rows,
                               "note": "", "approved": False})
        with self.assertRaises(ValueError):
            self.s.make_alias({"id": "U+4E00.TC", "target": "U+4E00.SC", "expected_revision": changed["revision"]})
        back = self.s.save({"id": "U+4E00.TC", "expected_revision": changed["revision"], "rows": TEN,
                            "note": "", "approved": False})
        with self.assertRaises(Conflict):
            self.s.make_alias({"id": "U+4E00.TC", "target": "U+4E00.SC", "expected_revision": changed["revision"]})
        self.s.make_alias({"id": "U+4E00.TC", "target": "U+4E00.SC", "expected_revision": back["revision"]})
        self.assertEqual(self.page("glyphs/TC/4Exx.txt"), "U+4E00 一 = U+4E00.SC\n")
        self.assertEqual(self.s.aliases_of("U+4E00.SC"), ["U+4E00.TC"])
        self.assertNotIn("U+4E00.TC", self.s.glyphs)
        self.assertIn("U+4E00 一\nai\n", self.page("history/ai-originals/TC/4Exx.txt"))
        self.assertIn("f1", self.s.forms)                              # still used by the SC glyph

    def test_split_alias_of_approved_glyph_is_edited(self):
        self.s.add_glyphs([{"group": "TC", "cp": 0x4E01, "alias": "U+4E01.SC"}])
        self.s.split_alias({"id": "U+4E01.TC"})
        self.assertEqual(self.s.current("U+4E01.TC")["state"], "edited")

    def test_add_glyphs_inserts_in_order_and_imports_ai(self):
        self.s.add_glyphs([{"group": "SC", "cp": 0x4E02, "rows": CROSS, "state": "draft", "ai_note": "底稿"},
                           {"group": "KR", "cp": 0x4E02, "alias": "U+4E02.SC"}])
        page = self.page("glyphs/SC/4Exx.txt")
        self.assertLess(page.index("U+4E01 丁"), page.index("U+4E02 丂\ndraft"))
        self.assertLess(page.index("U+4E02 丂"), page.index("U+4E03 七"))
        self.assertEqual(self.page("glyphs/KR/4Exx.txt"), "U+4E02 丂 = U+4E02.SC\n")
        with self.assertRaises(Conflict):
            self.s.add_glyphs([{"group": "SC", "cp": 0x4E02, "rows": CROSS, "state": "draft"}])
        cur = self.s.current("U+4E02.SC")
        out = self.s.import_ai("U+4E02.SC", TEN, "AI 修字", cur["revision"])
        self.assertEqual(out["current"]["state"], "ai")
        self.assertIn("U+4E02 丂\nai", self.page("history/ai-originals/SC/4Exx.txt"))

    def test_picks_up_outside_changes(self):
        path = self.root / "glyphs/SC/4Exx.txt"
        text = path.read_text().replace("U+4E03 七\nai", "U+4E03 七\napproved")
        time.sleep(0.01)
        path.write_text(text)
        os.utime(path, None)
        self.assertEqual(self.s.current("U+4E03.SC")["state"], "approved")


if __name__ == "__main__":
    unittest.main()
