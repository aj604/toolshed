import unittest
from src.digest.models import Notification, Recipient


class ModelsTest(unittest.TestCase):
    def test_recipient_defaults_to_digest(self):
        self.assertTrue(Recipient("a").digest_enabled)

    def test_notification_fields(self):
        self.assertEqual(Notification("a", "hi").recipient, "a")
