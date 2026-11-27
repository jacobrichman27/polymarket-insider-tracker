# Knowability golden case schema

One JSON object per line in `golden.v1.jsonl`. Blank lines and `#` comments are ignored.

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Stable slug (`ou-point-total-001`) |
| `question` | yes | Exact market title |
| `expected_regime` | yes | `no_private_edge` \| `private_edge_possible` \| `unknown` |
| `expected_path` | yes | `title_rule` \| `model` \| `unknown` |
| `family` | no | Research tag (`price`, `sports`, …) |
| `series_slug` | no | Optional series id passed to Decisions |
| `market_json` | no | Frozen evidence fields (`resolutionSource`, `description`) |
| `recorded_regime` | no | Offline Decisions stub regime (defaults to `expected_regime`) |
| `recorded_confidence` | no | Optional stub confidence in `[0, 1]` |
| `rationale` | no | One-line human why |
| `source` | no | Audit window / seed note |
| `set_version` | no | Defaults to `knowability.golden.v1` |
| `status` | no | `active` (default) or `provisional` |
| `min_policy` | no | Floor policy stamp this case assumes |
| `min_prompt` | no | Floor prompt stamp this case assumes |

**Offline mode** runs title-rule then a fixed Decisions stub (`recorded_regime`).  
**Live mode** (`--live`) calls the real Decisions API; never part of `verify.py` / CI.
