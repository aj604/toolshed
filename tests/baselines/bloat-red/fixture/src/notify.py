"""Send alerts to a channel, retrying on failure."""

MAX_RETRIES = 3
TIMEOUT_S = 10


def send_alert(channel, msg):
    """Deliver msg to channel; raises AlertFailed after MAX_RETRIES attempts."""
    ...
