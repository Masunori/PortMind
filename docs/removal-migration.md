# Removal migration

This document tracks temporary compatibility layers while the platform moves to an
HTTP-only client boundary. Contract fixtures currently target demo-client integration
API version `v1` (`/integration/v1`).

| Compatibility layer | Runtime reachable | Removal milestone |
| --- | --- | --- |
| `LocalDemoGateway` | Removed | Complete |
| Operational services and APIs | Removed | Complete |
| Embedded simulator | Removed | Complete |
| Document/candidate workflow | Removed | Complete |

Decision recorded 2026-08-27: this repository has no production data. Legacy document,
candidate, operational-model, and simulator records are disposable and require no data
conversion before their tables are dropped. Schema migrations still preserve a clean,
deterministic upgrade path, but they do not copy legacy records into evidence or signals.

The live demo client used for contract verification is available at
`http://localhost:8100/integration/v1` and identifies its API as version `1.0.0`.
