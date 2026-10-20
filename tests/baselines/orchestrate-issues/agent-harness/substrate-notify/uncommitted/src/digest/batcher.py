from collections import defaultdict

MAX_BATCH = 50


def plan_sends(notifications, recipients):
    """Return (digests, immediate).

    digests: list of (recipient_id, [notifications]) batches, each at most MAX_BATCH long.
    immediate: notifications for recipients with digest disabled, in arrival order.
    """
    by_id = {r.id: r for r in recipients}
    grouped = defaultdict(list)
    immediate = []
    for n in notifications:
        r = by_id.get(n.recipient)
        if r is not None and not r.digest_enabled:
            immediate.append(n)
            continue
        grouped[n.recipient].append(n)
    digests = []
    for rid, items in grouped.items():
        for i in range(0, len(items), MAX_BATCH):
            digests.append((rid, items[i:i + MAX_BATCH]))
    return digests, immediate
