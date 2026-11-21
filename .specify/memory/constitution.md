<!--
Sync Impact Report
- Version change: 2.0.0 -> 2.1.0
- Modified principles: Governance and Development Workflow ownership transferred from the
  upstream author (Patrick) to the repository owner of this fork (or a human reviewer they
  designate). Historical approvals recorded under Patrick's name in evidence remain factual.
- Added sections: none
- Removed sections: none
- Affected normative docs: .specify/memory/constitution.md, AGENTS.md, specs/README.md,
  living reviewer-owned checklist ownership notes, specs/002 runtime-verification golden
  policy approval language, tests/tooling/test_policy_snapshot.py docstring
- Application/API/storage behavior change: none
- Follow-up TODOs: none
-->
# Polymarket Insider Tracker Constitution

## Core Principles

### I. Research and Monitoring Only
The project MUST remain a read-only research and monitoring system. It MUST NOT place, simulate as
real, recommend, or automate trades. Detection output MUST be described as evidence for further
investigation, never proof of illegal conduct or financial advice. The legal and financial
disclaimers in public documentation MUST remain visible unless an approved specification changes
the product boundary. This protects users from mistaking probabilistic signals for established
facts or execution advice.

### II. Truthful, Source-Grounded Contracts
Every public capability, setup instruction, default, threshold, configuration field, and data-source
claim MUST match executable behavior. External integration decisions MUST be grounded in the current
official provider documentation and confirmed with a bounded live-safe smoke test when practical.
Library-only or experimental code MUST NOT be presented as wired production behavior. When an
external service withdraws a capability, the product contract MUST be revised explicitly rather
than relying on an undocumented or obsolete interface.

### III. End-to-End Evidence Over Isolated Coverage
Unit-test count and line coverage are insufficient completion evidence. Every change to the monitoring
path MUST preserve or add deterministic coverage of the applicable flow: ingest a trade, enrich or
profile it, detect and score signals, persist the assessment, and dispatch or safely suppress an
alert. Failure, retry, deduplication, restart, and degraded-dependency behavior MUST be tested at the
level where the contract is observable. The documented clean-checkout quick start and a bounded
live-safe external integration smoke test MUST pass before a release or convergence claim.

### IV. Safe Effects and Durable Research Records
Development, CI, and smoke verification MUST use fakes or dry-run behavior and MUST NOT send a real
Discord or Telegram alert without explicit authorization. Dry runs MUST have no delivery side
effects and MUST NOT poison later real-delivery deduplication state. Signal-bearing risk assessments
are durable research records: their persisted inputs, scores, thresholds, and disposition MUST be
sufficient to explain or replay an evaluation. Persistence failures MUST be observable while never
blocking an otherwise authorized alert attempt.

### V. Compatibility, Reproducibility, and Reviewability
Public Python APIs, CLI flags, environment variables, storage schema, and documented workflows MUST
remain compatible unless an approved specification authorizes a break and supplies a migration path.
Supported Python versions MUST agree across project metadata, the lockfile, CI, and documentation.
All required lint, format, type-check, migration, and test gates MUST be blocking and green, unless
the repository owner approves a time-bounded documented exception. Changes MUST be delivered as
bounded Spec Kit slices and reviewable commits; unrelated refactors are out of scope.

## Product and Operational Boundaries

- The supported product is a Python monitoring pipeline using public Polymarket data, Polygon
  profiling, Redis, PostgreSQL, heuristic or explicitly validated statistical detection, persisted
  assessments, health reporting, and optional Discord or Telegram delivery.
- Trading execution, a web UI, monetization, and unrelated product expansion are prohibited without
  a separately approved specification.
- A roadmap, changelog note, dormant module, or test suite does not by itself make a capability part
  of the implemented product contract. Backtesting or calibration work requires its own approved
  bounded specification; stored assessments may support that future work without implying it exists.
- External integrations MUST be rate-bounded, recover from transient failure where practical, expose
  stale or degraded state, and avoid logging secrets or full credential-bearing URLs.
- Database migrations MUST include a downgrade path and MUST be exercised against the supported
  database driver before release.

## Development Workflow and Quality Gates

1. Brownfield work MUST start from a clean, current upstream baseline and an explicit gap register
   that traces each material promise to code, tests, live evidence, an approved slice, or a documented
   deferral with owner and rationale.
2. Each material slice MUST follow the applicable Spec Kit sequence: specify, clarify, plan,
   reviewer-owned domain requirements-quality checklists, tasks, analyze, human validation,
   implement, and converge. The built-in `checklists/requirements.md` remains the author-owned
   spec-quality checklist.
3. Specifications own what and why; plans own implementation details. Assumptions affecting product
   scope, security, data semantics, compatibility, or user experience MUST be reviewed by the
   repository owner before implementation.
4. Agents MUST leave newly generated reviewer-owned domain checklist items unchecked. Only the
   repository owner or a human reviewer they designate may mark those requirements-quality criteria
   satisfied.
5. Bug fixes and behavior changes MUST begin with a failing regression test when practical. If that
   is infeasible, the plan MUST record why and define equivalent reproducible evidence.
6. Implementation MUST proceed in dependency-ordered, independently reviewable slices. Tests and
   documentation MUST change with the behavior they verify.
7. Before every per-slice Spec Kit command, the intended feature directory MUST be activated
   explicitly. Ignored local pointer state MUST NOT select a slice implicitly on a multi-feature
   branch or fresh clone.
8. Every slice MUST update its owned gap-register entries and record any approved deferral before
   convergence.
9. A pull request may be prepared only after required checks and convergence pass. Verify remote required
   checks at the exact head; do not bypass branch protection. Once independent review
   and required checks pass, merge changes within the authorized task without requesting
   separate human merge approval. After merging, verify the resulting commit/tree and
   main CI before reporting completion.

## Governance

This constitution governs specifications, plans, tasks, implementation, reviews, and release claims.
An amendment requires a documented rationale, the repository owner's approval, an update to affected
Spec Kit artifacts, and a migration or compatibility note when behavior changes. Versions follow
semantic versioning: MAJOR for incompatible governance changes, MINOR for new or materially expanded
principles, and PATCH for non-semantic clarification. Every specification, pull request, and
convergence review MUST record compliance or an explicit approved exception. Unapproved exceptions
are defects and block completion.

**Ownership note (2.1.0):** This fork's living governance is owned by the repository owner (or a
human reviewer they designate). Upstream history and evidence that name Patrick record the original
author's approvals and remain factual; they do not transfer ongoing approval authority.

**Version**: 2.1.0 | **Ratified**: 2026-09-06 | **Last Amended**: 2026-11-18
