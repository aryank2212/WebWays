# Licensing

This repository contains several components with different licenses, chosen deliberately:

| path | license | why |
|---|---|---|
| `core/` | GPL-3.0-or-later ([core/LICENSE](core/LICENSE)) | the client |
| `ui/` | GPL-3.0-or-later ([ui/LICENSE](ui/LICENSE)) | the client |
| `indexer/` | AGPL-3.0-or-later ([indexer/LICENSE](indexer/LICENSE)) | hosted forks of an index node must stay open |
| `protocol/` | Apache-2.0 ([protocol/LICENSE](protocol/LICENSE)) | anyone may implement the listing format |
| `docs/`, `scripts/`, root files | GPL-3.0-or-later unless a file says otherwise | |

Third-party code bundled in the UI (MIT/ISC) is listed with its notices in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Contributions are accepted under the license of the directory they
touch (see [CONTRIBUTING.md](CONTRIBUTING.md)).
