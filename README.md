# Fallback API + Prometheus + Docker

## Какво има вътре
- Fallback между два backend-а:
  - Primary: `https://jsonplaceholder.typicode.com/todos/{id}`
  - Secondary: `https://dummyjson.com/todos/{id}`
- Prometheus Counter: `backend_fallback_total{reason="..."}`
- `/metrics` endpoint
- JSON логове при всеки fallback
- `docker-compose.yml` за приложението + Prometheus

## API
- `GET /todos/{id}` — чете todo от primary backend; при грешка fallback-ва към secondary
- `GET /metrics` — Prometheus метрики
- `GET /health` — health check

## Стартиране с Docker
```bash
docker compose up --build
```

## Примери
Извикване на API:
```bash
curl http://localhost:8000/todos/1
```

Метрики:
```bash
curl http://localhost:8000/metrics | grep backend_fallback_total
```

Prometheus UI:
- Отворете `http://localhost:9090`
- Query: `backend_fallback_total`
- За графика може да използвате и:
  - `sum(backend_fallback_total)`
  - `increase(backend_fallback_total[5m])`

## Как да форсирате fallback локално
Променете `PRIMARY_BASE_URL` към невалиден URL или временен mock, например:
```bash
PRIMARY_BASE_URL=http://primary-does-not-exist:9999/todos docker compose up --build
```
Тогава заявка към `/todos/1` ще мине през secondary и counter-ът ще се увеличи.

## Примерен JSON лог при fallback
```json
{
  "timestamp": "2026-04-15T12:00:00+0000",
  "level": "INFO",
  "logger": "fallback-app",
  "message": "Fallback triggered for todo_id=1",
  "event": "fallback_triggered",
  "reason": "ConnectionError",
  "primary_url": "http://primary-does-not-exist:9999/todos/1",
  "secondary_url": "https://dummyjson.com/todos/1",
  "todo_id": 1
}
```
