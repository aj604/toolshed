from dataclasses import dataclass


@dataclass(frozen=True)
class Notification:
    recipient: str
    body: str


@dataclass(frozen=True)
class Recipient:
    id: str
    digest_enabled: bool = True
