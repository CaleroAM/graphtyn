# Quality/context v2 — focused real-repository regression

Date: 2026-08-22. Model: `opencode/x-preview-f-free`. Graphtyn was rerun after retrieval/compaction changes; the same-day Gra…ify 0.9.48 and baseline runs from `real_repos_current_2026-08-22` are reused as comparators. This is a focused regression check, not a fresh full-matrix statistical benchmark.

## Changes under test

- Spanish security/session concepts expand to concrete operations (`TimestampSigner`, `unsign`, `BadSignature`, `b64encode`, flags).
- Explicit component/file evidence outranks unrelated lexical matches.
- Exceptions are first-class `catch` operations.
- Signatures and repeated owner metadata are compacted.
- Imports are emitted only when dependencies are requested.
- Zero consumers/interfaces are emitted as explicit negative evidence.
- Short mid-sentence responses become `INCOMPLETE`; optional retry accumulates both attempts' cost.

## Results

| Task | Variant | Quality | Tokens | Time | Calls |
|---|---|---:|---:|---:|---:|
| signed-session-flow | Graphtyn v2 | **1.0000** | **8,155** | 80.4 s | 1 |
| signed-session-flow | Graphtyn previous | 0.0000 | 4,540 | 65.5 s | 1 |
| signed-session-flow | Gra…ify | 0.5000 | 28,094 | 250.9 s | 27 |
| signed-session-flow | Baseline | 0.1667 | 11,112 | 270.9 s | 15 |
| auction-service | Graphtyn v2 | **0.6667** | **6,307** | 36.9 s | 1 |
| auction-service | Graphtyn previous | 0.5833 | 11,325 | 64.8 s | 4 |
| auction-service | Gra…ify | 0.5000 | 13,493 | 121.8 s | 12 |
| auction-service | Baseline | 0.8333 | 29,196 | 270.7 s | 15 |

Across these two focused tasks, Graphtyn v2 averaged **0.8334 quality**, **7,231 tokens**, **58.6 seconds**, and one tool call. The matching Gra…ify results averaged 0.5000 quality and 20,793.5 tokens. This is **65.2% fewer tokens** with a +0.3334 quality delta. The matching baseline averaged 0.5000 quality and 20,154 tokens.

The session response now covers 6/6 facts and finished normally without retry. Its token count increased because the previous 393-character answer was incomplete; the new complete answer still used 71.0% fewer tokens than Gra…ify. AuctionService improved quality while reducing Graphtyn's previous tokens by 44.3%.

## Conservative caveat

The auction answer explicitly states “cero relaciones de tipo implementa” and “cero relaciones entrantes de llama/usa”, but the pre-existing regex grader does not accept those phrasings for its no-interface/no-consumer facts. The recorded 0.6667 score is intentionally not adjusted after observing the answer. Provider nondeterminism and the two-task sample prevent a general superiority claim.
