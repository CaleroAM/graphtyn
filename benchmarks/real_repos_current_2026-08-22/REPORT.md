# Real-repository comparison — 2026-08-22

## Protocol

- Repositories: a real Python/ASGI framework (`398e5a3`) and a real turn-based Unity/C# game (`c002fb1`). Exact repository identities remain in the machine-readable artifacts for reproducibility.
- Competitors: Graphtyn current worktree, Gra…ify `0.9.48`, and OpenCode without either graph.
- Model: `opencode/x-preview-f-free` for every run.
- Four paired tasks with the same prompt and pre-existing atomic ground truth.
- Graph variants could use only their MCP. Baseline could read/search locally. All variants were read-only.
- Quality is pattern-based fact coverage minus explicit forbidden claims. It does not measure prose style.

## Observed agent results

| Variant | Runs | Total tokens | Mean tokens | Mean time | Tool calls | Mean quality | Factual errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Graphtyn | 4/4 | 40,118 | 10,029.5 | 62.6 s | 9 | 0.5458 | 0 |
| Gra…ify | 4/4 | 63,797 | 15,949.3 | 165.3 s | 78 | 0.6375 | 0 |
| Baseline | 4/4 | 77,841 | 19,460.3 | 194.6 s | 42 | 0.7000 | 0 |

Graphtyn used **37.12% fewer tokens**, **62.16% less time**, and **88.46% fewer tool calls** than Gra…ify. However, its mean quality was **0.0917 lower**. Against baseline it used 48.46% fewer tokens and 67.86% less time, with quality 0.1542 lower.

## Per-task evidence

| Task | Variant | Quality | Tokens | Time | Calls |
|---|---|---:|---:|---:|---:|
| signed-session-flow | Graphtyn | 0.0000 | 4,540 | 65.5 s | 1 |
| signed-session-flow | Gra…ify | 0.5000 | 28,094 | 250.9 s | 27 |
| signed-session-flow | Baseline | 0.1667 | 11,112 | 270.9 s | 15 |
| router-dispatch-flow | Graphtyn | 1.0000 | 15,453 | 62.5 s | 2 |
| router-dispatch-flow | Gra…ify | 0.7500 | 14,218 | 217.8 s | 32 |
| router-dispatch-flow | Baseline | 1.0000 | 19,270 | 110.4 s | 7 |
| selection-impact | Graphtyn | 0.6000 | 8,800 | 57.5 s | 2 |
| selection-impact | Gra…ify | 0.8000 | 7,992 | 70.8 s | 7 |
| selection-impact | Baseline | 0.8000 | 18,263 | 126.5 s | 5 |
| auction-service | Graphtyn | 0.5833 | 11,325 | 64.8 s | 4 |
| auction-service | Gra…ify | 0.5000 | 13,493 | 121.8 s | 12 |
| auction-service | Baseline | 0.8333 | 29,196 | 270.7 s | 15 |

## Incomplete-response sensitivity

The Graphtyn `signed-session-flow` answer ended mid-section after 393 characters even though OpenCode emitted `SUCCESS`. Counting it is the conservative primary result. Excluding that entire paired task from all variants leaves three complete comparisons:

| Variant | Mean tokens | Mean quality |
|---|---:|---:|
| Graphtyn | 11,859.3 | 0.7278 |
| Gra…ify | 11,901.0 | 0.6833 |
| Baseline | 22,243.0 | 0.8778 |

On complete responses, Graphtyn and Gra…ify had essentially equal token cost; Graphtyn quality was 0.0445 higher. Baseline remained highest quality but used 87.6% more tokens than Graphtyn.

## Structural and new-feature checks

- Graphtyn indexed the Python/ASGI repository in 0.538 s: 638 nodes, 1,194 edges, no dangling/duplicate edges, but 58.82% of resolved calls were ambiguous.
- Graphtyn indexed the Unity/C# repository in 2.068 s: 1,881 nodes, 4,323 edges, zero ambiguous calls, but 133 duplicate edges were detected.
- Gra…ify's regenerated graphs contained 955/2,046 nodes/edges for Python/ASGI and 2,294/3,880 for Unity/C#.
- Gra…ify's own synthetic benchmark estimated 10,081 and 10,848 tokens per query. Those estimates are recorded but not mixed with observed OpenCode token usage.
- The new Graphtyn global registry successfully combined both real repositories: 2,519 namespaced nodes and 5,517 intra-repository edges before cross-project hints. Querying `Session` returned evidence from both projects without ID collisions.

## Honest conclusion

The current implementation demonstrates a real efficiency advantage over Gra…ify when all runs are counted, but not quality parity. The most urgent problems are response-completeness detection, Python/ASGI call ambiguity, and duplicate Unity/C# edges. With the incomplete run removed, the comparison is favorable to Graphtyn against Gra…ify, but four tasks are too few for a superiority claim.
