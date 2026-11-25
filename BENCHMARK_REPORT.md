# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyen Nhut Linh  
**Ngày chạy:** 2026-11-25 (GMT+7)  
**Môi trường:** Linux x86_64, Intel Core 5 210H, 12 CPU logic, Python 3.11.18. Agent v1 chạy ở cổng `8001`, agent v2 ở cổng `8002`, model `mock-llm-small`.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Ngưỡng mặc định của `load_test.py`, phản ánh thời gian chờ của phần lớn người dùng. |
| Error rate `/ask` | ≤ 2% | Ngưỡng mặc định của `load_test.py` để kiểm soát tỷ lệ request thất bại. |
| Accuracy trên golden dataset | ≥ 85% | Ngưỡng CI trong Exercise 7.3. Lần eval chốt CP7 dùng ngưỡng 100% kèm kiểm tra regression. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.0 Metrics (Exercise 7.1)

Trích `/metrics` của v2 sau một request hỏi về Prometheus.

```text
# TYPE http_requests_total counter
http_requests_total{method="POST",route="/ask",status="200"} 1.0
# TYPE agent_in_flight_requests gauge
agent_in_flight_requests 0.0
# TYPE agent_question_length_chars histogram
agent_question_length_chars_bucket{le="50.0"} 1.0
agent_question_length_chars_count 1.0
agent_question_length_chars_sum 40.0
```

Counter đếm request tích lũy. Gauge thể hiện số request đang xử lý tại lúc scrape. Histogram mới ghi nhận câu hỏi dài 40 ký tự và xếp vào các bucket phù hợp. Nếu dùng URL thật làm label `route`, mỗi URL lạ có thể tạo thêm series, làm tăng RAM và dung lượng lưu trữ của Prometheus. Dùng route template và gộp URL không khớp vào `unmatched` giữ số giá trị label ở mức hữu hạn.

### 2.1 Concurrency vs latency (agent v2)

Mỗi lượt gửi 300 request, dùng `MOCK_SLOW_RATE=0.03` và `MOCK_ERROR_RATE=0.01`. Latency trong bảng tính trên request trả `200`, theo cách đo của `load_test.py`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.99 | 193.7 | 224.4 | 1704.5 | 1.67% | PASS |
| 10 | 36.06 | 195.6 | 222.4 | 1681.3 | 1.00% | PASS |
| 50 | 108.43 | 197.4 | 243.6 | 1678.6 | 0.67% | PASS |
| 100 | 64.05 | 341.3 | 2861.7 | 3156.8 | 1.00% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Throughput tăng đến 108.43 RPS ở mức 50, rồi giảm còn 64.05 RPS ở mức 100. p95 ở mức 100 tăng lên 2861.7 ms và vượt ngưỡng 500 ms. Khi client và agent chạy cùng máy, tăng số request đồng thời còn làm tăng chi phí xử lý kết nối và thời gian chờ. Số đo end-to-end ở đây cho thấy hiệu năng giảm ở mức 100 mà chưa xác định được nút thắt riêng của client hay server.

### 2.2 Tail latency

Khởi động lại v2 cho từng giá trị `MOCK_SLOW_RATE`. Mỗi lượt gửi 300 request ở concurrency 20, giữ `MOCK_ERROR_RATE=0.01`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 193.8 | 225.3 | 258.3 |
| 0.03 (mặc định) | 235.5 | 222.9 | 1695.3 |
| 0.1 | 377.4 | 1698.8 | 1713.5 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

Ở mức `0.03`, p99 tăng từ 258.3 lên 1695.3 ms trong khi p95 vẫn quanh 225 ms. Khi tăng lên `0.1`, nhóm request chậm đủ lớn để đẩy cả p95 lên 1698.8 ms. Trung bình bị pha loãng bởi số đông request nhanh, nên dùng p95 cho SLO và theo dõi thêm p99 để thấy độ trễ ở phần đuôi. Lượt `0` đạt ngưỡng latency nhưng error rate là 2.33%, vượt SLO 2%.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Cả ba lần eval đều dùng `MOCK_ERROR_RATE=0` và `MOCK_SLOW_RATE=0` để so sánh khả năng trả lời trên cùng golden dataset.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100% (23/23) |
| Avg tokens / câu | 57.0 | 108.8 | 113.7 |
| Tổng cost (USD) | 0.000403 | 0.000757 | 0.000791 |
| Cost / câu đúng (USD) | 0.00040335 | 0.00003607 | 0.00003440 |
| Quality gate | FAIL (ngưỡng 80%) | PASS (ngưỡng 80%) | PASS (ngưỡng 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu phân biệt JWT và API key, mô tả claims, thời hạn và kiểm tra chữ ký JWT. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm tài liệu mô tả cách Kubernetes HPA điều chỉnh số Pod dựa trên CPU, memory và custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

v2 dùng thêm retrieval nên số token trung bình tăng từ 57.0 lên 108.8 và p95 eval từ 187.9 lên 222.6 ms. Accuracy tăng từ 1/23 lên 21/23, vì vậy chi phí cho mỗi câu đúng giảm dù tổng chi phí tăng. Bản sửa đạt 23/23 và giảm chi phí mỗi câu đúng từ 0.00003607 xuống 0.00003440 USD so với v2 ban đầu. Cost trên mỗi câu đúng tính cả phần chi phí đã dùng cho câu sai, nên phù hợp hơn khi so sánh hai bản có accuracy khác nhau.

**Quality gate trong CI.** Khởi động agent v2 với `MOCK_ERROR_RATE=0`, rồi chạy `python eval/run_eval.py --min-accuracy 0.85` và truyền `--baseline` với report của bản đã chấp nhận để chặn cả regression. Đặt job này làm trạng thái bắt buộc trước khi merge. Script trả `1` nếu accuracy dưới ngưỡng hoặc một câu từng đúng bị trả lời sai, khiến job thất bại.

Các JSON để nộp nằm trong [`reports/`](reports/).

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] [Grafana đang có tải, hàng Golden Signals](screenshots/grafana-dashboard.png)
- [x] [Trace chậm trong Jaeger](screenshots/jaeger-slow-trace.png)
- [x] [Trace lỗi trong Jaeger có event `exception`](screenshots/jaeger-error-trace.png)
- [x] [Trang Alerts của Prometheus với 2 alert cùng **firing**](screenshots/prometheus-alert-firing.png)

**Exercise 7.4**

1. Với 30 người dùng, ramp-up 5 người/giây và 2 replica, p95 khoảng **292 ms** còn trung bình khoảng **227 ms**. Khoảng cách cho thấy một nhóm request phải chờ lâu hơn mức điển hình. Đường p99 trên dashboard còn cao hơn rõ rệt. Tỷ lệ lỗi của `POST /ask` là **1,67%** theo [ảnh Grafana](screenshots/grafana-dashboard.png).
2. Hai instance xử lý lần lượt **9,20 và 9,33 request/giây** tại thời điểm đọc panel, nên lưu lượng được chia gần đều.
3. Input khoảng **1.352 token/giây**, nhiều hơn output khoảng **719 token/giây**. Prompt v2 gồm câu hỏi và ngữ cảnh retrieval, còn output chỉ gồm câu trả lời.
4. `GET http://localhost:8080/metrics` trả **404**. Nginx chặn endpoint này. Prometheus scrape `/metrics` trực tiếp từ các instance agent qua mạng Docker nội bộ.

### 4.2 Thí nghiệm "phá hệ thống"

Locust duy trì 30 người dùng trên 2 replica. Thời gian tính từ lúc chạy lệnh áp dụng cấu hình đến lần đầu Prometheus API trả trạng thái `firing`, với chu kỳ kiểm tra 1 giây. Giữ `MOCK_ERROR_RATE=0.2` khi chạy B để quan sát cả hai alert cùng `firing`. `promtool test rules` trả `SUCCESS`. [Dữ liệu đo từ Prometheus](reports/alert_experiments.json).

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | 81,7 giây | [Error rate](screenshots/grafana-alert-a.png). Tỷ lệ `5xx` trên `/ask` đạt 21,43% lúc alert firing sau khi vượt 5% liên tục 1 phút. [Prometheus](screenshots/prometheus-alert-a.png). |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | 146,3 giây | [Latency p95](screenshots/grafana-alert-b.png). P95 của `/ask` tăng từ 292 ms ở A lên 1,89 giây ở B. Điều kiện vượt 1 giây kéo dài 2 phút trước khi alert firing. |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Chạy eval trên golden dataset trước khi deploy và theo dõi accuracy theo phiên bản. Dùng v2 đã qua kiểm tra làm baseline để quality gate chặn câu từng đúng bị sai. Dashboard hạ tầng đo độ trễ, lỗi HTTP và tài nguyên, nên chất lượng câu trả lời cần tín hiệu riêng.

### 4.3 Debug bằng trace

**Trace chậm**

- `trace_id` là `e542fa9975139afc5fe75a75628e95c5`.
- Tổng thời gian `POST /ask` là **1.728,728 ms**. Span `chat mock-llm-small` chiếm **1.698,847 ms**, tương đương **98,27%** tổng thời gian.
- Log `llm_call` có cùng `trace_id`.

```json
{"ts":"2026-11-25T10:25:14.230333+00:00","level":"INFO","service":"observable-agent","instance":"da9c3908cbdc","event":"llm_call","trace_id":"e542fa9975139afc5fe75a75628e95c5","span_id":"2c69e941e36d5336","request_id":"fee876f929c1","model":"mock-llm-small","agent_version":"v2","input_tokens":95,"output_tokens":55,"cost_usd":4.7e-05,"llm_ms":1698.6}
```

**Trace lỗi**

- `trace_id` là `42c2ffec8cb893a27c47f5acdd0d9878`. `POST /ask` trả **HTTP 503** trong **113,241 ms**.
- Span `chat mock-llm-small` kéo dài **83,495 ms**. Event `exception` ghi `utils.mock_llm.LLMError` và thông báo upstream 503. Log `llm_error` có cùng `trace_id`.

```json
{"ts":"2026-11-25T10:28:20.422785+00:00","level":"INFO","service":"observable-agent","instance":"5ed1dcfb368b","event":"llm_error","trace_id":"42c2ffec8cb893a27c47f5acdd0d9878","span_id":"dfc2717df894458a","request_id":"378d4b8d5652","error":"Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 64.94 | 200 | 400 | 1700 | 58 (0,75%) |
| 3 | 65.87 | 190 | 230 | 1700 | 61 (0,78%) |

Số trong bảng lấy từ dòng `Aggregated` ở [CSV 1 replica](benchmark-results/scale_1_stats.csv) và [CSV 3 replica](benchmark-results/scale_3_stats.csv). Dùng `docker compose run --no-deps` cho Locust để giữ đúng số replica đã đặt, rồi kiểm tra số replica trước và sau mỗi lượt.

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Khi scale từ 1 lên 3 replica, p95 tổng hợp giảm từ 400 xuống 230 ms (**42,5%**). Riêng `/ask`, p95 giảm từ 440 xuống 240 ms. RPS tăng nhẹ trong kịch bản cố định 100 người dùng có thời gian nghỉ giữa các request. p99 vẫn là 1.700 ms ở cả hai lượt, phù hợp với trace cho thấy thời gian chờ LLM giả lập chiếm gần toàn bộ request chậm.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Theo dõi RPS cùng p95, p99 và tỷ lệ lỗi để thấy tác động của tải cao và request chậm.
  2. Dùng trace để tìm span chậm hoặc lỗi, rồi đối chiếu `trace_id` với log để xem chi tiết.
  3. Dùng eval với baseline để phát hiện regression chất lượng, kể cả khi các metric hạ tầng vẫn ổn định.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

Thêm synthetic check qua URL public để đo HTTP status và p95 từ phía người dùng. Theo dõi tỷ lệ `5xx` ở Nginx để nhận ra lỗi phát sinh trước khi request đến agent.
