import unittest
from src.digest.batcher import plan_sends
from src.digest.models import Notification, Recipient


class BatcherTest(unittest.TestCase):
    def test_batches_by_recipient(self):
        ns = [Notification("a", "1"), Notification("b", "2"), Notification("a", "3")]
        digests, immediate = plan_sends(ns, [Recipient("a"), Recipient("b")])
        self.assertEqual(sorted((r, len(b)) for r, b in digests), [("a", 2), ("b", 1)])
        self.assertEqual(immediate, [])

    def test_digest_disabled_is_immediate(self):
        ns = [Notification("a", "1")]
        digests, immediate = plan_sends(ns, [Recipient("a", digest_enabled=False)])
        self.assertEqual(digests, [])
        self.assertEqual(immediate, ns)

    def test_large_batch_splits(self):
        ns = [Notification("a", str(i)) for i in range(120)]
        digests, _ = plan_sends(ns, [Recipient("a")])
        self.assertTrue(len(digests) > 1)
