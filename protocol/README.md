# webways-protocol

Apache-2.0. The signed listing and rating format shared by the daemon and index nodes.

```python
from webways_protocol import Identity, sign_listing, verify_listing

ident = Identity.load_or_create("publisher.key")            # ed25519; file mode 0600
doc = sign_listing(ident, infohash="ab"*20, title="Big Buck Bunny", license="CC-BY-3.0", tags=["film"])
listing_id = verify_listing(doc)                            # raises ProtocolError if anything is off
```

Format and rules: [../docs/listing-spec.md](../docs/listing-spec.md). Tests: `protocol/tests` (22).
Public API: `Identity`, `sign_listing`, `verify_listing`, `validate_listing`, `listing_id`, `supersedes`,
`sign_rating`, `verify_rating`, `canonical`, `ProtocolError`.
