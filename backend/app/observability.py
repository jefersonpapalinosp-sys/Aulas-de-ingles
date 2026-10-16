"""Métricas agregadas por processo, sem rótulos ou conteúdo de alunos."""

import threading
import time
from dataclasses import dataclass

LATENCY_BUCKETS_MS = (50, 100, 250, 500, 1000, 2500, 5000)


@dataclass(frozen=True)
class RequestMetricsSnapshot:
    process_uptime_seconds: int
    requests_total: int
    responses_5xx_total: int
    duration_ms_sum: float
    duration_ms_max: float
    latency_buckets: dict[str, int]


class RequestMetrics:
    """Contadores de cardinalidade fixa para cada processo da API."""

    def __init__(self) -> None:
        self._started = time.monotonic()
        self._lock = threading.Lock()
        self._requests = 0
        self._responses_5xx = 0
        self._duration_sum = 0.0
        self._duration_max = 0.0
        self._buckets = {value: 0 for value in LATENCY_BUCKETS_MS}
        self._infinite = 0

    def record(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._requests += 1
            self._responses_5xx += int(status_code >= 500)
            self._duration_sum += duration_ms
            self._duration_max = max(self._duration_max, duration_ms)
            self._infinite += 1
            for boundary in LATENCY_BUCKETS_MS:
                if duration_ms <= boundary:
                    self._buckets[boundary] += 1

    def snapshot(self) -> RequestMetricsSnapshot:
        with self._lock:
            buckets = {str(boundary): self._buckets[boundary] for boundary in LATENCY_BUCKETS_MS}
            buckets["+Inf"] = self._infinite
            return RequestMetricsSnapshot(
                process_uptime_seconds=max(0, int(time.monotonic() - self._started)),
                requests_total=self._requests,
                responses_5xx_total=self._responses_5xx,
                duration_ms_sum=round(self._duration_sum, 3),
                duration_ms_max=round(self._duration_max, 3),
                latency_buckets=buckets,
            )


request_metrics = RequestMetrics()
