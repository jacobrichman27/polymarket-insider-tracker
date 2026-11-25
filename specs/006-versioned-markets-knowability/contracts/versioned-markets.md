# Contract: Versioned Markets (A1)

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-23

## When writers run

When `ARCHIVE_ENABLED=true`, markets (and knowability-driven market version updates) MAY write even if `ARCHIVE_OUTCOME_REPAIR_ENABLED=false`.

When archive is off, A1 MUST NOT require markets writers or repair health as readiness blockers.

## Append-on-change

- Key: `(condition_id, known_at)`.
- Persist a new version only when attributes or policy/model version change; do not spam identical versions.
- Snapshot read for trade time `t`: latest version with `known_at` ≤ `t`.

## Minimal repair surface

Every markets version used for repair MUST expose a `token_id` → outcome map sufficient to set repaired fields. Richer knowability fields MAY lag but MUST NOT gate shipping repair.

## Non-blocking

Market fetch/persist failures degrade classification/repair workers; they MUST NOT stall the A0 insert path.
