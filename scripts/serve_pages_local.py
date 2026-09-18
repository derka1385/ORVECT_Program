"""Serve the GitHub Pages interface locally against a local API.

Usage: python scripts/serve_pages_local.py [--port 8080] [--api http://localhost:8000/api]

runtime-config.js is served with `apiBase` rewritten to the local API; the
committed file (pointing at the production API) is never modified. The public
Firebase configuration is read from the committed runtime-config.js itself.
"""
import argparse
import http.server
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--api", default="http://localhost:8000/api")
    args = parser.parse_args()
    committed = (ROOT / "runtime-config.js").read_text()
    config = re.sub(r"apiBase:\s*'[^']*'", f"apiBase: '{args.api}'", committed).encode()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(ROOT), **k)

        def do_GET(self):
            if self.path.split("?")[0] == "/runtime-config.js":
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.end_headers()
                self.wfile.write(config)
                return
            super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass

    print(f"ORVECT Pages → http://localhost:{args.port}/  (API: {args.api})")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
