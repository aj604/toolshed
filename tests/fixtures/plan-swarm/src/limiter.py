"""Token-bucket rate limiter (design: docs/plans/2026-05-01-rate-limiter-design.md)."""

MAX_REQUESTS_PER_MIN = 120
BURST = 20


class TokenBucket:
    def __init__(self, rate=MAX_REQUESTS_PER_MIN, burst=BURST):
        self.rate = rate
        self.burst = burst
        self.tokens = burst

    def allow(self):
        if self.tokens > 0:
            self.tokens -= 1
            return True
        return False
