from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Policy:
    """Per-node operator policy. Nothing here is a network-wide rule."""
    name: str = "unnamed swarm index"
    description: str = ""
    # Where rightsholders send notices; published in /v1/node so it is easy to find.
    takedown_contact: str = ""
    # False = only publishers in allowed_publishers may list here.
    open_publish: bool = True
    allowed_publishers: set[str] = field(default_factory=set)
    max_listings_per_publisher: int = 1000
    # Other nodes this node pulls listings from (operator-chosen; none by default).
    peers: list[str] = field(default_factory=list)
    # Other operators' blocklists this node subscribes to (none by default).
    blocklist_subscriptions: list[str] = field(default_factory=list)
    sync_interval: int = 300
    post_rate_per_minute: int = 30
