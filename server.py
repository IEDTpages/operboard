from __future__ import annotations

import argparse
import json
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from refresh_data import DATA_PATH, load_current, refresh_file

ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()


def do_refresh():
    with LOCK:
        try:
            return refresh_file()
        except Exception as e:
            payload = load_current()
            payload['server_error'] = str(e)
            return payload


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/data':
            qs = parse_qs(parsed.query)
            payload = do_refresh() if qs.get('refresh') == ['1'] else load_current()
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == '/api/status':
            p = load_current(); body = json.dumps({'generated_at': p.get('generated_at'), 'data_as_of': p.get('data_as_of'), 'refresh_summary': p.get('refresh_summary')}, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        super().do_GET()


def refresh_loop(minutes: int):
    while True:
        time.sleep(max(5, minutes * 60))
        do_refresh()


def main():
    ap = argparse.ArgumentParser(description='HTML-версия Оперборда с автоматическим обновлением данных')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--refresh-minutes', type=int, default=60)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--no-initial-refresh', action='store_true')
    args = ap.parse_args()
    if not args.no_initial_refresh:
        threading.Thread(target=do_refresh, daemon=True).start()
    threading.Thread(target=refresh_loop, args=(args.refresh_minutes,), daemon=True).start()
    url = f'http://{args.host}:{args.port}/index.html'
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f'Оперборд запущен: {url}')
    print(f'Автоматическое обновление: каждые {args.refresh_minutes} мин.')
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
