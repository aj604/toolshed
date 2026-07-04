"""HTTP client for the export service."""

RETRIES_503 = 2   # retry twice on 503, then raise

def fetch(url):
    ...
