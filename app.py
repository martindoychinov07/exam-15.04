import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional, Tuple

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

PRIMARY_BASE_URL = os.getenv('PRIMARY_BASE_URL', 'https://jsonplaceholder.typicode.com/todos')
SECONDARY_BASE_URL = os.getenv('SECONDARY_BASE_URL', 'https://dummyjson.com/todos')
REQUEST_TIMEOUT_SECONDS = float(os.getenv('REQUEST_TIMEOUT_SECONDS', '2.5'))
APP_PORT = int(os.getenv('PORT', '8000'))

FALLBACK_COUNTER = Counter(
    'backend_fallback_total',
    'Number of times the secondary backend was used after primary backend failure',
    ['reason'],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        extra_fields = ['event', 'reason', 'primary_url', 'secondary_url', 'todo_id', 'status_code']
        for field in extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger('fallback-app')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

app = FastAPI(title='Fallback API with Prometheus')


def normalize_primary(todo: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'id': todo['id'],
        'title': todo['title'],
        'completed': todo['completed'],
        'source': 'primary',
        'raw': todo,
    }


def normalize_secondary(todo: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'id': todo['id'],
        'title': todo['todo'],
        'completed': todo['completed'],
        'source': 'secondary',
        'raw': todo,
    }


def fetch_json(url: str) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    status_code = response.status_code
    response.raise_for_status()
    return response.json(), status_code


@app.get('/health')
def health() -> Dict[str, str]:
    return {'status': 'ok'}


@app.get('/metrics')
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest().decode('utf-8'), media_type=CONTENT_TYPE_LATEST)


@app.get('/todos/{todo_id}')
def get_todo(todo_id: int) -> JSONResponse:
    primary_url = f'{PRIMARY_BASE_URL}/{todo_id}'
    secondary_url = f'{SECONDARY_BASE_URL}/{todo_id}'

    try:
        payload, _ = fetch_json(primary_url)
        if not payload:
            raise HTTPException(status_code=404, detail='Todo not found in primary backend')
        return JSONResponse(normalize_primary(payload))
    except requests.RequestException as exc:
        reason = type(exc).__name__
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)

        FALLBACK_COUNTER.labels(reason=reason).inc()
        logger.info(
            f'Fallback triggered for todo_id={todo_id}',
            extra={
                'event': 'fallback_triggered',
                'reason': reason,
                'primary_url': primary_url,
                'secondary_url': secondary_url,
                'todo_id': todo_id,
                'status_code': status_code,
            },
        )

        try:
            payload, _ = fetch_json(secondary_url)
            if not payload:
                raise HTTPException(status_code=404, detail='Todo not found in secondary backend')
            return JSONResponse(normalize_secondary(payload))
        except requests.RequestException as secondary_exc:
            raise HTTPException(
                status_code=502,
                detail={
                    'message': 'Primary and secondary backends failed',
                    'primary_error': str(exc),
                    'secondary_error': str(secondary_exc),
                },
            ) from secondary_exc


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=APP_PORT)
