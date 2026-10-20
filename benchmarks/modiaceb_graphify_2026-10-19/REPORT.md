# Graphify comparison on modIAceb

Graphify 0.9.92 was installed in an isolated virtual environment. No Graphify
skill, hook or project instruction was installed, and it was never registered
under a Graphtyn MCP alias. A local code-only graph was built from the frozen
modIAceb commit: 2,112 nodes and 5,608 edges.

Graphify's own benchmark reports a 105,600-word corpus (~140,800 estimated
tokens), ~1,617 tokens per query and `87.1x` reduction. That is a corpus versus
retrieved-subgraph estimate, not measured agent-session usage.

## Question C1

| Condition | Quality | Total tokens | Uncached input | Cached input | Time | Calls |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 6/6 | 540,504 | 75,265 | 459,904 | 109.409 s | 18 |
| Graphtyn | 6/6 | 662,919 | 74,350 | 578,432 | 150.466 s | 25 |
| Graphify | 6/6 | 437,058 | 75,612 | 355,200 | 67.386 s | 25 |

For this question Graphify used 19.14% fewer total tokens and 38.41% less time
than baseline. It used 34.07% fewer tokens than Graphtyn. Its uncached input was
approximately equal to baseline; the saving came mainly from fewer cached input
tokens. The agent called `graph_stats` and `query_graph`, received a broad
truncated subgraph, then verified locally.

## Edit task

| Condition | Quality | Total tokens | Uncached input | Cached input | Time | Calls |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 8/8 | 1,679,938 | 116,684 | 1,546,112 | 192.449 s | 48 |
| Graphtyn | 8/8 | 2,535,043 | 213,199 | 2,297,984 | 277.267 s | 55 |
| Graphify | 8/8 | 2,998,493 | 246,146 | 2,729,856 | 377.325 s | 72 |

Graphify passed 17 targeted tests on independent verification. It changed all
required consumers and added fixture isolation. At equal rubric quality, it used
78.49% more total tokens and 96.06% more time than baseline, and 18.28% more
tokens than Graphtyn. It made ten Graphify calls and continued broad local
exploration and test execution.

## Interpretation

Graphify can reduce session consumption when a compact query replaces repeated
repository reads, as happened on C1. It does not guarantee that result. For the
implementation task, graph retrieval was additional work rather than a
replacement for source inspection, editing and tests. The internal `87.1x`
metric and end-to-end totals answer different questions and must not be quoted
as interchangeable savings.

This remains one repository, one model, one task of each kind and one repetition.
Provider cost was zero in all three conditions because the selected OpenCode
model was free; token totals measure usage, not money charged.
