# Graphtyn 0.8.0 — release and comparative validation

**Release target:** `346bc6b949b63cfcf459e576741b862bbff782c4` (`main`, tag `v0.8.0`).  
**Competitor tested:** `graphifyy 0.9.58`, installed in a separate Python environment.  
**Test date:** 2026-09-11, America/Mexico_City.

## Release verification

- Local full suite: **313 passed, 2 skipped** in 90.60 seconds on Python 3.13.13.
- The CI run on the merge commit passed all required jobs: Python 3.10–3.13, Windows portability, browser, package, security and Docker. The release workflow also waits for CI on the exact tag commit before creating assets.
- `graphtyn --version` returned `0.8.0` from a clean virtual environment.
- The 36-task benchmark manifest validated: six repositories, six technology groups and 108 planned cells, with no protocol errors. The complete 108-cell agent run was **not** performed.
- Memory retrieval stability test: 285 synthetic queries (270 positive, 15 negative), Recall@5/10 **1.000**, MRR **0.9889**, attribution **1.000**, negative accuracy **1.000**, estimated mean **643 tokens/query**, mean latency **30.739 ms**, p95 **36.984 ms**. This does not measure topic extraction from real conversations.

## Structural indexing against Graphify

Both indexers used deterministic, local AST/code-only modes on identical source revisions. Graphify community clustering and all model-based document extraction were disabled. Node and edge schemas differ, so counts show output size, **not relative accuracy**.

| Repository and pinned revision | Graphtyn nodes / edges | Graphify 0.9.58 nodes / edges |
|---|---:|---:|
| Graphtyn repository (`346bc6b`) | 1,382 / 3,616 | 1,440 / 4,896 |
| Starlette (`398e5a3430eb1ddd33e1d48d766efe41426e231f`) | 1,641 / 4,578 | 2,259 / 8,013 |
| go-chi (`735ae2b87f8c733d616e809ae86e0985c1bc3350`) | 493 / 1,184 | 575 / 1,663 |

On the Graphtyn repository, its own structural benchmark measured 100% edge validity, zero dangling/duplicate edges, 116/1,810 ambiguous calls (6.41%), a 9.9386 s first scan and a 1.6462 s warm scan (6.04×). Graphify's extraction time and accuracy were not measured with the same metric in this run.

## Small retrieval-and-answer pilot

Four fixed tasks were drawn from the existing Starlette and go-chi task sets (two per repository). Each used one query and one answer from the same local `qwen2.5-coder:3b` model, temperature 0, with one repetition. The three contexts were retrieved by Graphtyn, Graphify, or ordinary `rg` search; answers were scored against 24 predefined atomic facts using the task's regular-expression rubric.

| Context source | Facts matched | Mean strict score | Mean model tokens | Mean retrieval time |
|---|---:|---:|---:|---:|
| Graphtyn | 3/24 | 0.125 | 4,336 | 2.019 s |
| Graphify | 0/24 | 0.000 | 1,273 | 0.344 s |
| No graph (`rg`) | 0/24 | 0.000 | 3,034 | 0.055 s |

This small pilot is **diagnostic, not a statistically valid ranking**: it has four tasks, one model run per cell, no confidence interval and a small model. All three variants missed most required facts; several answers also omitted required source-and-line citations. These results do not support a claim that Graphtyn beats Graphify. The raw answers and per-fact scores are in `graphtyn_graphify_head2head_0.8.0.json`.

## Limits still open

- The full 36-task/108-cell comparison and repeated runs remain pending.
- The memory benchmark is synthetic; real-session topic segmentation and recovery were not evaluated here.
- Multi-gigabyte histories, sustained load, and long-running upgrades/restores have not been validated.
- PyPI publishing remains disabled. Graphtyn 0.8.0 is distributed from GitHub Releases.

Reproduction inputs are the task manifests under `benchmarks/`, the repository revisions listed above, and local `graphifyy 0.9.58`. The release CI run and assets are linked from <https://github.com/CaleroAM/graphtyn/releases/tag/v0.8.0>.
