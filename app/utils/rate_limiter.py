import time
from collections import defaultdict, deque

class RateLimiter:
    """In-memory sliding window rate limiter and parameter metric tracker.
    Tracks request frequencies and aggregates cumulative parameter values over a sliding time window."""

    def __init__(self, window_seconds: int = 300):
        self.window = window_seconds
        self.calls = defaultdict(deque)          # Tracks call timestamps for rate limiting (60s window)
        self.metric_values = defaultdict(deque)  # Tracks (timestamp, value) tuples for cumulative metrics (5m window)

    def record_and_count(self, agent_id: str, tool: str) -> int:
        """Records a call and returns the number of calls in the last 60 seconds."""
        key = f"{agent_id}:{tool}"
        now = time.time()
        dq = self.calls[key]
        dq.append(now)
        # slide window to keep last 60 seconds
        while dq and dq[0] < now - 60:
            dq.popleft()
        return len(dq)

    def record_and_sum_metric(self, agent_id: str, metric_name: str, value: float) -> float:
        """Records a numeric metric value and returns the sliding window sum over window_seconds (default 5m)."""
        key = f"{agent_id}:{metric_name}"
        now = time.time()
        dq = self.metric_values[key]
        dq.append((now, value))
        # slide window to keep last window_seconds
        while dq and dq[0][0] < now - self.window:
            dq.popleft()
        return sum(item[1] for item in dq)
