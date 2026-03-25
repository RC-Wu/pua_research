# CatfishResearch Capability Provider Ledger

This document defines the provider capability ledger used by the Catfish router. The implementation lives in `assets/router/catfish_capability_ledger.json`, while this file describes the contract and why each field matters.

## Goal

The ledger is a small capability memory. It answers one question:

When two providers are technically eligible, which one should receive the next task given what recent routing history says about task type, difficulty, reasoning depth, and parent-node value?

## Compatibility Contract

The schema is designed to stay compatible with a future `Capability.md` view. Every ledger row can be rendered into a Markdown table or bullet block without losing meaning because the core fields are already explicit:

| field | meaning |
| --- | --- |
| `providerId` | stable provider key from the registry |
| `taskCategory` | task family such as `research`, `builder`, `summary`, `review` |
| `difficulty` | `low`, `medium`, or `high` |
| `reasoningTier` | `quick`, `balanced`, or `deep` |
| `reasoningLength` | `short`, `medium`, or `long` |
| `parentScore` | normalized importance score inherited from the parent node |
| `recency` | date or timestamp for freshness weighting |
| `confidence` | trust in the observation, from `0.0` to `1.0` |
| `routingEffect` | qualitative routing action such as `prefer`, `penalize`, or `block` |
| `scoreDelta` | numeric weight applied when the row matches a future task |

That is the minimal set needed to drive routing and also keep a future Markdown ledger human-readable.

## How Scoring Works

For each provider, the evaluator checks every ledger entry for that provider and computes a weighted contribution:

1. Match quality
   The router compares current task category, difficulty, reasoning tier, reasoning length, and parent score against the stored entry.
2. Freshness
   Newer entries weigh more than old entries.
3. Confidence
   Higher-confidence entries move the score more.
4. Routing effect
   `prefer` reinforces the provider, `penalize` drags it down, and `block` makes the negative signal stronger.

The result is added to the provider’s health-weighted base score.

## Why Parent Score Is Stored Per Entry

Parent score is not global metadata. It is part of the observation itself.

Example:

- a provider may be excellent for deep work when a parent node already has score `0.9`
- the same provider may be wasteful for exploratory branches with score `0.2`

By storing `parentScore` in each row instead of only at evaluation time, the ledger preserves the context of why the provider was good or bad. That is the signal used to steer future routing.

## Current 2026-03-25 Entries

The shipped ledger reflects current reality:

- `ucloud-modelverse`
  - positive entries for `research`, `builder`, and `summary`
  - strongest boost on high-score deep research because the provider is currently healthy and verified
- `smartaipro`
  - negative entries, including a hard `block` for deep research
  - kept in the ledger so recovery is a state flip, not a schema rewrite
- `molus`
  - negative entries for the same quota-exhaustion reason

## Updating The Ledger

When a provider’s capability changes, append or revise an entry instead of rewriting the routing logic.

Recommended update rule:

1. update the dated health snapshot if reachability or quota changed
2. add a new ledger row for the observed task pattern
3. set `confidence` according to how directly the outcome was verified
4. set `routingEffect`
5. choose `scoreDelta` to reflect how much that observation should move future routing

The router then consumes the new state automatically.
