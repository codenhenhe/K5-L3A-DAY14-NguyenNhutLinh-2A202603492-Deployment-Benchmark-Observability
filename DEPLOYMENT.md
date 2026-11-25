# Deployment Information

## Public URL

[agent-production-ef571d64.up.railway.app](https://agent-production-ef571d64.up.railway.app)

## Platform

Railway, project `day14-cp6`, môi trường `production`. Nguồn triển khai là agent Part 6 trong `06-lab-complete/`.

## Test Commands

Nạp `AGENT_API_KEY` đã cấu hình trên Railway vào terminal trước khi kiểm tra request có xác thực.

```bash
BASE=https://agent-production-ef571d64.up.railway.app
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"  # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"   # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'  # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'  # 200
```

Kết quả kiểm tra thực tế trên URL public.

| Request | HTTP |
| --- | ---: |
| `GET /health` | 200 |
| `GET /ready` | 200 |
| `POST /ask` thiếu key | 401 |
| `POST /ask` có key hợp lệ | 200 |

## Environment Variables Set

- `PORT=8000`.
- `ENVIRONMENT=production`.
- `REDIS_URL` tham chiếu `${{Redis.REDIS_URL}}` để kết nối Redis trong cùng project.
- `AGENT_API_KEY` là khóa ứng dụng được lưu trong biến môi trường Railway.

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
