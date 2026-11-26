# Spec Kit Feature Workspace

This brownfield effort intentionally keeps several proposed feature directories on one review branch.
GitHub Spec Kit v1.0.4 decouples a feature directory from the Git branch, but its local
`.specify/feature.json` pointer is ignored and can select the wrong feature after another command runs.

## Activate One Slice Explicitly

Before every per-feature Spec Kit command, set the intended directory explicitly in the command environment:

```bash
SPECIFY_FEATURE_DIRECTORY=specs/002-reproducible-runtime <speckit command>
# After it exists:
SPECIFY_FEATURE_DIRECTORY=specs/006-versioned-markets-knowability <speckit command>
```

Replace the value for the active slice. Never rely on the ignored pointer when reviewing or executing a
different feature, and never run two feature-writing commands concurrently in the same checkout.

Proposed execution order:

1. `002-reproducible-runtime`
2. `001-supported-trade-ingestion`
3. `003-safe-observable-operation`
4. `004-truthful-detection-contract`
5. `005-research-trade-archive` (Phase A0 tape — **implemented**; activate only for A0 follow-ups)
6. `006-versioned-markets-knowability` (Phase A1 — **implemented/verified** 2026-11-25; G-044–G-046 Closed; activate this path only for A1 follow-ups)
7. `007-featured-enrichment` (Phase B — proposed)
8. `008-labels-resolutions` (Phase C — proposed)
9. `009-archive-retention` (Phase D — proposed)

Numeric prefixes record creation order, not dependency order. Archive phases A0–D and the
prerequisite 001/003 contract amendments are sequenced in
[`docs/research-archive-roadmap.md`](../docs/research-archive-roadmap.md) and
[`Data.md`](../Data.md). Until a listed directory exists, do not point
`SPECIFY_FEATURE_DIRECTORY` at it. When authoring or implementing `005-…` (or later archive
slices), set the env var to that exact path on every Spec Kit command—never the ignored
`.specify/feature.json` pointer, and never a leftover `001`/`002`/`003`/`004` value from a
prior session.

Before implementing an archive slice, register its owned gaps in
[`audit/gap-register.md`](audit/gap-register.md) (and keep them updated through converge).

## Checklist Ownership

- `checklists/requirements.md` is the built-in author-owned specification-quality checklist created by
  `$speckit-specify` and maintained by `$speckit-clarify`.
- Other `checklists/<domain>.md` files are reviewer-owned requirements-quality checklists generated later by
  `$speckit-checklist` from the approved review focus.
- Agents leave new reviewer-owned checklist items unchecked. The repository owner of this fork (or a human
  reviewer they designate) owns the `[x]` decision. Checked items mean the written requirements passed
  review, not that code is complete. Upstream evidence that names Patrick records original ownership
  and past approvals only.

## Required Per-Slice Order

Use individual skills in this order:

1. specify
2. clarify
3. plan
4. reviewer-owned domain checklist
5. tasks
6. analyze
7. human validation
8. implement
9. converge

Do not use the bundled legacy workflow as a shortcut because it omits required intermediate gates. Each
slice must update its owned entries in `audit/gap-register.md` before convergence.
