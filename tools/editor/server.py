"""Tong Pixel Sans glyph editor: a local web page that edits glyphs/ and forms/ in place.

    python3 tools/editor/server.py [--port 8791]

Then open http://127.0.0.1:8791/. Only this machine can connect. Saving rewrites the glyph's page
file; review the result with `git diff` and commit it. Reference outlines and phase-searched drafts
need the packages in tools/requirements.txt and the fonts in reference-fonts/ (docs/reference-fonts.md);
everything else needs only Python 3.
"""
from __future__ import annotations

import argparse
import json
import secrets
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from store import ROOT, Conflict, Store

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/editor.js": ("editor.js", "text/javascript"),
          "/shapes-ui.js": ("shapes-ui.js", "text/javascript"), "/style.css": ("style.css", "text/css")}


def handler(store):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body, mime="application/json; charset=utf-8", status=200):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def check_host(self):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in allowed:
                raise ValueError("仅允许本机访问")

        def do_GET(self):
            try:
                self.check_host()
                url = urlparse(self.path)
                path, q = unquote(url.path), parse_qs(url.query)
                arg = lambda k, d="": q.get(k, [d])[0]
                if path in STATIC:
                    name, mime = STATIC[path]
                    self.send((WEB / name).read_bytes(), mime)
                elif path == "/representative.json":
                    f = HERE / "data/representative.json"
                    self.send(f.read_bytes() if f.exists() else b'{"glyphs": []}')
                elif path == "/api/session":
                    import draft
                    self.send({"token": token, "geometry": store.geometry, "root": str(store.root), "git": store.has_git(),
                               "phase_draft": draft.available(), "lists": store.lists()})
                elif path == "/api/queue":
                    self.send(store.queue())
                elif path == "/api/shapes":
                    self.send(store.shape_catalog(arg("glyph") or None))
                elif path == "/api/shape-library":
                    kind = arg("kind", "all") if arg("kind", "all") in ["all", "shared", "reference"] else "all"
                    self.send(store.shape_library(arg("symbol")[:8], arg("q")[:80], kind,
                                                  max(0, int(arg("offset", "0"))), min(240, max(1, int(arg("limit", "120"))))))
                elif path.startswith("/api/shape/"):
                    self.send(store.shape_detail(path.split("/")[-1]))
                elif path == "/api/approved":
                    self.send(store.reading(approved_only=True))
                elif path == "/api/reading":
                    self.send(store.reading())
                elif path.startswith("/api/glyph/"):
                    self.send(store.payload(path.split("/")[-1]))
                elif path.startswith("/api/phase/"):
                    self.send(store.phase_draft(path.split("/")[-1]))
                elif path.startswith("/api/overlay/"):
                    self.send(store.reference_svg(path.split("/")[-1], "#009ec0"), "image/svg+xml")
                elif path.startswith("/api/reference/"):
                    self.send(store.reference_svg(path.split("/")[-1], "#222"), "image/svg+xml")
                else:
                    self.send({"error": "Not found"}, status=404)
            except (ValueError, KeyError, FileNotFoundError) as e:
                self.send({"error": str(e)}, status=400)
            except Exception:
                traceback.print_exc()
                self.send({"error": "读取失败，请检查服务日志。"}, status=500)

        def do_POST(self):
            try:
                self.check_host()
                if self.headers.get("X-Review-Token") != token or self.headers.get("Content-Type") != "application/json":
                    self.send({"error": "页面已失效，请刷新"}, status=403)
                    return
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + self.headers.get("Host", ""):
                    raise ValueError("请求来源不匹配")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size < 2_000_000:
                    raise ValueError("请求大小无效")
                p = json.loads(self.rfile.read(size))
                routes = {"/api/save": store.save,
                          "/api/shape-link": store.shape_link,
                          "/api/shape-preview": lambda p: store.shape_link(p, preview=True),
                          "/api/shape-unlink": store.shape_unlink,
                          "/api/shape-unlink-all": store.shape_unlink_all,
                          "/api/shape-move": store.shape_move,
                          "/api/copy-from": store.copy_from,
                          "/api/shape-create": store.shape_create,
                          "/api/shape-edit": store.shape_edit}
                fn = routes.get(urlparse(self.path).path)
                if fn is None:
                    self.send({"error": "Not found"}, status=404)
                    return
                self.send(fn(p))
            except Conflict as e:
                self.send({"error": str(e)}, status=409)
            except (ValueError, KeyError, TypeError, FileNotFoundError) as e:
                self.send({"error": str(e)}, status=400)
            except Exception:
                traceback.print_exc()
                self.send({"error": "保存失败。请保留当前页面并检查服务日志。"}, status=500)

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    a = ap.parse_args()
    store = Store(a.root)
    server = ThreadingHTTPServer(("127.0.0.1", a.port), handler(store))
    print(f"Tong Pixel Sans 修字编辑器：http://127.0.0.1:{a.port}\n字形 {len(store.glyphs)} · 形态 {len(store.forms)} · "
          f"源文件 {store.root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
