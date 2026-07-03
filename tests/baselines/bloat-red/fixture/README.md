# notify

A tiny library for sending alerts to a channel, with built-in retry handling
for transient delivery failures.

## Setup

Clone the repo, then install the package in editable mode:

```
pip install -e .
```

No environment variables are required to run the test suite locally.

## Usage

Import `send_alert` from `src/notify.py` and call it with a channel and a
message. The `send_alert` function takes a channel and a message and delivers
the message to that channel.

```python
from src.notify import send_alert

send_alert("#ops", "disk usage above 90%")
```

## Retry behavior

Delivery failures are not always permanent, so the library will not give up
on the first error it sees. Instead, when a send attempt fails, it waits
briefly and tries again, giving transient network blips and momentary channel
outages a chance to resolve themselves before the caller is bothered with a
failure. This retrying continues for a small, fixed number of attempts before
the library gives up and reports the failure back to the caller, so callers
can rely on `send_alert` to absorb brief hiccups without needing their own
retry logic. If every attempt is exhausted, `send_alert` raises `AlertFailed`
so the caller knows delivery ultimately did not succeed.

One quirk worth knowing about: alerts can silently drop if `TIMEOUT_S`
exceeds the receiving channel's flush interval, since the channel may
discard buffered messages that haven't been flushed by the time the next
send attempt starts writing to it.

## Contributing

Pull requests are welcome. Please keep changes small and focused, and make
sure `python3 -m pytest` passes before submitting.
