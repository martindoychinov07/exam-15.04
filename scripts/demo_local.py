import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import urlopen

import matplotlib.pyplot as plt
import requests
import uvicorn

BASE = Path('/mnt/data/fallback-prometheus')
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from app import app
SCREENSHOT = BASE / 'fallback_counter_demo.png'


class PrimaryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/todos/'):
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"primary failure"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


class SecondaryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/todos/'):
            todo_id = int(self.path.rsplit('/', 1)[-1])
            payload = {
                'id': todo_id,
                'todo': f'secondary todo {todo_id}',
                'completed': False,
                'userId': 99,
            }
            body = json.dumps(payload).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


def serve(server):
    server.serve_forever()


def start_http_server(port, handler):
    server = HTTPServer(('127.0.0.1', port), handler)
    thread = threading.Thread(target=serve, args=(server,), daemon=True)
    thread.start()
    return server


def start_app():
    config = uvicorn.Config(app, host='127.0.0.1', port=8000, log_level='warning')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def sample_counter():
    text = requests.get('http://127.0.0.1:8000/metrics', timeout=2).text
    for line in text.splitlines():
        if line.startswith('backend_fallback_total') and 'reason=' in line:
            return float(line.rsplit(' ', 1)[-1])
    return 0.0


def main():
    primary = start_http_server(18081, PrimaryHandler)
    secondary = start_http_server(18082, SecondaryHandler)

    import os
    os.environ['PRIMARY_BASE_URL'] = 'http://127.0.0.1:18081/todos'
    os.environ['SECONDARY_BASE_URL'] = 'http://127.0.0.1:18082/todos'

    # app imports env on module import, so patch globals directly
    import app as app_module
    app_module.PRIMARY_BASE_URL = 'http://127.0.0.1:18081/todos'
    app_module.SECONDARY_BASE_URL = 'http://127.0.0.1:18082/todos'
    app_module.REQUEST_TIMEOUT_SECONDS = 1.0

    server, thread = start_app()
    time.sleep(1.2)

    xs = []
    ys = []
    for i in range(1, 6):
        r = requests.get(f'http://127.0.0.1:8000/todos/{i}', timeout=2)
        r.raise_for_status()
        xs.append(i)
        ys.append(sample_counter())
        time.sleep(0.3)

    plt.figure(figsize=(10, 4.8))
    plt.plot(xs, ys, marker='o')
    plt.title('Fallback Counter Demo')
    plt.xlabel('Request number')
    plt.ylabel('backend_fallback_total')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(SCREENSHOT, dpi=160)
    print(SCREENSHOT)

    primary.shutdown()
    secondary.shutdown()


if __name__ == '__main__':
    main()
