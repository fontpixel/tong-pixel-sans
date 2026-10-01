"""Queue and checkpoints of an AI repair round. Writes only inside the round's directory.

    WF="$PY tools/airepair/workflow.py --round NAME"      (NAME = a directory under work/airepair/)
    $WF status
    $WF claim --owner OWNER [--batch b001]               -> batch, token
    $WF register-agent --batch B --token T --agent-id ID
    $WF context --batch B --token T
    $WF checkpoint --batch B --token T --file delta.json
    $WF render --batch B --token T                       -> render id and page paths
    $WF viewed --batch B --token T --render-id R --pages 1 2 3
    $WF submit --batch B --token T
    $WF release --batch B --token T --reason TEXT

Delta file: {"glyphs": [{"id": "U+5B57.SC", "changes": {"4": "#############"}, "note": "",
                          "tumbled": "借鉴", "reuse": ["宀←U+5B87.SC"]}]}
changes: row number (0–12) -> the whole new 13-character row, relative to the CURRENT version given in
inputs.txt (also in later rounds); {} = keep the current version. tumbled: 借鉴 / 部分借鉴 / 未借鉴.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROUNDS, cell, draw_bits, font, one_to_one, wide_gaps  # noqa: E402

HERE = STATE = WORK = RESULTS = None   # set from --round in main()
TUMBLED = {"借鉴", "部分借鉴", "未借鉴"}
MAX_ROUNDS = 2                         # visual review rounds per glyph; a round may set "max_views" in round.json


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".tmp-" + uuid.uuid4().hex)
    with tmp.open("x") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.flush(); os.fsync(f.fileno())
    tmp.replace(path)


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


@contextlib.contextmanager
def lock():
    STATE.mkdir(exist_ok=True)
    with (STATE / ".lock").open("a+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def items():
    return {i["id"]: i for i in read(HERE / "items.json")["items"]}


def batch_ids(b):
    p = HERE / "batches" / b / "batch.json"
    if not p.exists():
        raise SystemExit(f"no batch {b}")
    return read(p)["ids"]


def job(b):
    return read(STATE / f"{b}.json", {"batch": b, "status": "pending"})


def check_token(b, token):
    j = job(b)
    if j.get("token") != token or j["status"] not in ("claimed",):
        raise SystemExit(f"stale or wrong token for {b} (status {j['status']}); stop writing and report")
    return j


def apply(rows, changes):
    out = list(rows)
    for k, v in changes.items():
        out[int(k)] = v
    return out


def digest(rows):
    return hashlib.sha1("\n".join(rows).encode()).hexdigest()[:12]


def saved(b):
    return read(WORK / b / "saved.json", {"glyphs": {}, "viewed": {}, "renders": []})


def cmd_status(a):
    out = []
    for d in sorted((HERE / "batches").iterdir()):
        j = job(d.name); s = saved(d.name)
        out.append(f"{d.name}: {j['status']}{' owner=' + j['owner'] if j.get('owner') else ''} "
                   f"saved {len(s['glyphs'])}/{len(batch_ids(d.name))}")
    print("\n".join(out))


def cmd_claim(a):
    with lock():
        for d in sorted((HERE / "batches").iterdir()):
            j = job(d.name)
            if j["status"] == "claimed" and j.get("owner") == a.owner:
                print(json.dumps({"batch": d.name, "token": j["token"], "note": "already claimed by this owner"})); return
        names = [a.batch] if a.batch else [d.name for d in sorted((HERE / "batches").iterdir())]
        for b in names:
            j = job(b)
            if j["status"] == "pending":
                rnd = read(HERE / "round.json")
                j = {"batch": b, "status": "claimed", "owner": a.owner, "token": secrets.token_hex(8), "claimed_at": now(),
                     "model": rnd["model"], "effort": rnd["effort"], "history": j.get("history", [])}
                atomic(STATE / f"{b}.json", j)
                print(json.dumps({"batch": b, "token": j["token"], "inputs": str(HERE / "batches" / b / "inputs.txt"),
                                  "protocol": str(HERE / "PROTOCOL.md")}, ensure_ascii=False)); return
        print(json.dumps({"batch": None, "note": "nothing pending"}))


def cmd_register(a):
    with lock():
        j = check_token(a.batch, a.token); j["agent_id"] = a.agent_id
        atomic(STATE / f"{a.batch}.json", j)
    print("ok")


def cmd_release(a):
    with lock():
        j = check_token(a.batch, a.token)
        j["history"] = j.get("history", []) + [{"owner": j["owner"], "token": j["token"], "released_at": now(), "reason": a.reason}]
        for k in ("owner", "token", "agent_id", "claimed_at"):
            j.pop(k, None)
        j["status"] = "pending"
        atomic(STATE / f"{a.batch}.json", j)
    print("released; checkpoints kept")


def cmd_context(a):
    check_token(a.batch, a.token)
    ids, s = batch_ids(a.batch), saved(a.batch)
    print(json.dumps({"batch": a.batch, "inputs": str(HERE / "batches" / a.batch / "inputs.txt"),
                      "input_pages": sorted(str(p) for p in (HERE / "batches" / a.batch).glob("input-*.png")),
                      "example_pages": sorted(str(p) for p in (HERE / "batches" / a.batch).glob("examples-*.png"))
                      + sorted(str(p) for p in (HERE / "batches" / a.batch).glob("earlier-*.png")),
                      "lessons": str(HERE / "LESSONS.md"), "saved": len(s["glyphs"]), "total": len(ids),
                      "pending_ids": [i for i in ids if i not in s["glyphs"]],
                      "rounds": {i: len(v) for i, v in s["viewed"].items()},
                      "renders": [{"id": r["id"], "viewed": r.get("viewed", False)} for r in s["renders"]]}, ensure_ascii=False, indent=1))


def cmd_checkpoint(a):
    with lock():
        check_token(a.batch, a.token)
        ids, it = set(batch_ids(a.batch)), items()
        data = json.loads(Path(a.file).read_text(), object_pairs_hook=lambda kv: dict(_unique(kv)))
        if set(data) != {"glyphs"} or not isinstance(data["glyphs"], list) or not data["glyphs"]:
            raise SystemExit('delta must be {"glyphs": [...]} with at least one glyph')
        s = saved(a.batch)
        for g in data["glyphs"]:
            if set(g) - {"id", "changes", "note", "tumbled", "reuse"} or not {"id", "changes", "note", "tumbled"} <= set(g):
                raise SystemExit(f"fields must be id, changes, note, tumbled[, reuse]: {g.get('id')}")
            gid = g["id"]
            if gid not in ids:
                raise SystemExit(f"{gid} is not in batch {a.batch}")
            ch = g["changes"]
            base = it[gid]["rows"]
            h, w, flexible = len(base), len(base[0]), gid.endswith((".PR", ".PR-L"))
            if not isinstance(ch, dict) or any(not k.isdigit() or not 0 <= int(k) < h or not isinstance(v, str)
                                               or not (2 <= len(v) <= 24 if flexible else len(v) == w) or set(v) - {".", "#"}
                                               for k, v in ch.items()):
                raise SystemExit(f"{gid}: changes keys must be 0–{h - 1}, values {'2–24' if flexible else w} characters of . and #")
            if flexible and len({len(r) for r in apply(base, ch)}) != 1:
                raise SystemExit(f"{gid}: a proportional glyph that changes width must give every row, all of the same width")
            if g["tumbled"] not in TUMBLED:
                raise SystemExit(f"{gid}: tumbled must be one of {sorted(TUMBLED)}")
            if not isinstance(g["note"], str) or len(g["note"]) > 300:
                raise SystemExit(f"{gid}: note must be a string of at most 300 characters")
            if "reuse" in g and (not isinstance(g["reuse"], list) or not all(isinstance(x, str) for x in g["reuse"])):
                raise SystemExit(f"{gid}: reuse must be a list of strings")
            rows = apply(it[gid]["rows"], ch)
            if not any("#" in r for r in rows):
                raise SystemExit(f"{gid}: empty glyph")
            seen = s["viewed"].get(gid, [])
            if len(seen) >= MAX_ROUNDS and digest(rows) != seen[-1]:
                raise SystemExit(f"{gid}: already had {MAX_ROUNDS} visual rounds; keep the last viewed version")
            s["glyphs"][gid] = {**g, "rows": rows, "saved_at": now()}
        atomic(WORK / a.batch / "saved.json", s)
    print(json.dumps({"saved": len(s["glyphs"]), "total": len(ids)}))


def _unique(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise SystemExit(f"duplicate JSON key in {keys}")
    return pairs


def render_pages(b, s, out_dir):
    from PIL import Image, ImageDraw
    it = items()
    big, small = font(18), font(13)
    ids = [i for i in batch_ids(b) if i in s["glyphs"]]
    sc = 8
    rowh = (max(len(it[i]["rows"]) for i in ids) + 1) * sc + 34 if ids else 15 * sc + 34
    W = 20 + 130 + 3 * (15 * sc + 30) + 70
    pages = []
    for k in range(0, len(ids), 12):
        part = ids[k:k + 12]
        im = Image.new("RGB", (W * 2, 40 + rowh * ((len(part) + 1) // 2)), "white")
        d = ImageDraw.Draw(im)
        derive = any(it[gid].get("master") for gid in part)
        d.text((10, 8), f"{b} 复看 第 {k // 12 + 1} 页 · " + ("思源（本字地区）| 思源（母版地区）| 修前（母版副本）| 修后" if derive else
                                                             "思源参考 | 圆石 13×14 | 修前（当前）| 修后") + " · 红字：部件间空了 2 列以上（L049）",
               font=big, fill=(0, 0, 0))
        for i, gid in enumerate(part):
            g, x0 = it[gid], (i % 2) * W + 10
            y0 = 40 + (i // 2) * rowh
            after = s["glyphs"][gid]["rows"]
            n = sum(p != q for r1, r2 in zip(g["rows"], after) for p, q in zip(r1, r2))
            gaps = wide_gaps(g["char"], g["region"], after) if g["region"] in ("SC", "TC", "JP", "KR") else []
            d.text((x0, y0), f"{g['char']} {gid} · 改 {n} 点 · " + (f"母版 {g['master']['id']}" if g.get("master") else f"圆石：{s['glyphs'][gid]['tumbled']}"),
                   font=small, fill=(0, 0, 0))
            if gaps:
                d.text((x0 + 330, y0), "间距 " + " ".join(f"{p}|{q} 空{c}列" for p, q, c in gaps), font=small, fill=(210, 30, 30))
            im.paste(Image.open(HERE / g["reference"]).convert("RGB").resize((112, 112)), (x0, y0 + 18))
            x = x0 + 130
            for rows, label in ((g["tumbled"], "圆石"), (g["rows"], "修前"), (after, "修后")):
                if label == "圆石" and g.get("master"):
                    im.paste(Image.open(HERE / g["master_reference"]).convert("RGB").resize((112, 112)), (x, y0 + 18))
                    d.text((x, y0 + 18 + 114), f"思源 {g['master']['id'][-2:]}（母版）", font=small, fill=(90, 90, 90))
                elif rows:
                    box, xo = cell(gid, rows)
                    draw_bits(d, rows, x, y0 + 18, sc, box=box, x_off=xo, label=label, fnt=small)
                else:
                    d.text((x, y0 + 60), "（圆石没有此字）", font=small, fill=(90, 90, 90))
                x += 15 * sc + 30
            one_to_one(im, [g["rows"], after], x, y0 + 30, gap=20)
            d.text((x, y0 + 50), "1:1 前/后", font=small, fill=(90, 90, 90))
        path = out_dir / f"page-{k // 12 + 1:02d}.png"
        im.save(path); pages.append(str(path))
    return pages


def cmd_render(a):
    with lock():
        check_token(a.batch, a.token)
        s = saved(a.batch)
        if not s["glyphs"]:
            raise SystemExit("nothing saved yet")
        state = {gid: digest(g["rows"]) for gid, g in s["glyphs"].items()}
        last = s["renders"][-1] if s["renders"] else None
        if last and last["state"] == state:
            print(json.dumps({"render_id": last["id"], "pages": last["pages"], "note": "unchanged since this render"}, ensure_ascii=False, indent=1)); return
        rid = len(s["renders"]) + 1
        out = WORK / a.batch / f"render-{rid:02d}"
        out.mkdir(parents=True, exist_ok=True)
        pages = render_pages(a.batch, s, out)
        s["renders"].append({"id": rid, "state": state, "pages": pages, "at": now()})
        atomic(WORK / a.batch / "saved.json", s)
    print(json.dumps({"render_id": rid, "pages": pages}, ensure_ascii=False, indent=1))


def cmd_viewed(a):
    with lock():
        check_token(a.batch, a.token)
        s = saved(a.batch)
        r = next((r for r in s["renders"] if r["id"] == a.render_id), None)
        if r is None:
            raise SystemExit("unknown render id")
        if sorted(a.pages) != list(range(1, len(r["pages"]) + 1)):
            raise SystemExit(f"view all {len(r['pages'])} pages of render {a.render_id}")
        cur = {gid: digest(g["rows"]) for gid, g in s["glyphs"].items()}
        if r["state"] != cur:
            raise SystemExit("glyphs changed after this render; render again and view the new pages")
        r["viewed"] = True
        for gid, h in r["state"].items():
            seen = s["viewed"].setdefault(gid, [])
            if not seen or seen[-1] != h:
                seen.append(h)
        atomic(WORK / a.batch / "saved.json", s)
    print(json.dumps({"viewed_render": a.render_id, "rounds": {i: len(v) for i, v in s["viewed"].items()}}))


def cmd_submit(a):
    with lock():
        j = check_token(a.batch, a.token)
        ids, s, it = batch_ids(a.batch), saved(a.batch), items()
        missing = [i for i in ids if i not in s["glyphs"]]
        if missing:
            raise SystemExit(f"not saved yet: {missing}")
        unviewed = [i for i in ids if not s["viewed"].get(i) or s["viewed"][i][-1] != digest(s["glyphs"][i]["rows"])]
        if unviewed:
            raise SystemExit(f"final versions not viewed: {unviewed}")
        result = {"batch": a.batch, "owner": j["owner"], "model": j["model"], "effort": j["effort"], "submitted_at": now(),
                  "glyphs": [{"id": i, "char": it[i]["char"], "region": it[i]["region"], "before": it[i]["rows"],
                              "rows": s["glyphs"][i]["rows"], "changes": s["glyphs"][i]["changes"],
                              "note": s["glyphs"][i]["note"], "tumbled": s["glyphs"][i]["tumbled"],
                              "reuse": s["glyphs"][i].get("reuse", []), "rounds": len(s["viewed"][i])} for i in ids]}
        atomic(RESULTS / f"{a.batch}.json", result)
        j.update(status="submitted", submitted_at=now())
        atomic(STATE / f"{a.batch}.json", j)
    print(json.dumps({"batch": a.batch, "submitted": len(ids), "result": str(RESULTS / f"{a.batch}.json")}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", required=True, help="round name (directory under work/airepair/) or its path")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("claim"); p.add_argument("--owner", required=True); p.add_argument("--batch")
    p = sub.add_parser("register-agent"); p.add_argument("--batch", required=True); p.add_argument("--token", required=True); p.add_argument("--agent-id", required=True)
    p = sub.add_parser("release"); p.add_argument("--batch", required=True); p.add_argument("--token", required=True); p.add_argument("--reason", required=True)
    for name in ("context", "render", "submit"):
        p = sub.add_parser(name); p.add_argument("--batch", required=True); p.add_argument("--token", required=True)
    p = sub.add_parser("checkpoint"); p.add_argument("--batch", required=True); p.add_argument("--token", required=True); p.add_argument("--file", required=True)
    p = sub.add_parser("viewed"); p.add_argument("--batch", required=True); p.add_argument("--token", required=True)
    p.add_argument("--render-id", type=int, required=True); p.add_argument("--pages", type=int, nargs="+", required=True)
    a = ap.parse_args()
    global HERE, STATE, WORK, RESULTS
    HERE = Path(a.round) if "/" in a.round else ROUNDS / a.round
    if not (HERE / "round.json").exists():
        raise SystemExit(f"no round at {HERE}")
    STATE, WORK, RESULTS = HERE / "state", HERE / "work", HERE / "results"
    global MAX_ROUNDS
    MAX_ROUNDS = json.loads((HERE / "round.json").read_text()).get("max_views", MAX_ROUNDS)
    {"status": cmd_status, "claim": cmd_claim, "register-agent": cmd_register, "release": cmd_release,
     "context": cmd_context, "checkpoint": cmd_checkpoint, "render": cmd_render, "viewed": cmd_viewed,
     "submit": cmd_submit}[a.cmd](a)


if __name__ == "__main__":
    main()
