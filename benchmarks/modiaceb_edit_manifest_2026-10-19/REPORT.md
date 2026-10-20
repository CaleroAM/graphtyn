# modIAceb edit A/B pilot — configurable feature-store manifest

Date: 2026-10-19. Both arms started at commit
`70dc1e8b732ebb08d93e39219a2016f4ef2d8bf8` in separate branches and worktrees.
Model: `opencode/deepseek-v4.1-flash-free`. The task and eight-item rubric were
frozen before either run. Neither arm was retried.

| Metric | Baseline | Graphtyn | Graphtyn delta |
|---|---:|---:|---:|
| Rubric quality | 8/8 | 8/8 | tie |
| Independent targeted tests | 16 passed | 16 passed | tie |
| Total tokens | 1,679,938 | 2,535,043 | +855,105 (+50.90%) |
| Uncached input | 116,684 | 213,199 | +96,515 (+82.71%) |
| Cached input | 1,546,112 | 2,297,984 | +751,872 (+48.63%) |
| Output | 7,859 | 10,752 | +2,893 (+36.81%) |
| Reasoning | 9,283 | 13,108 | +3,825 (+41.20%) |
| Wall time | 192.449 s | 277.267 s | +84.818 s (+44.08%) |
| Tool calls | 48 | 55 | +7 (+14.58%) |
| Provider cost | 0 | 0 | tie; free model |

Both implementations updated the loader, effective cache revision, Docker API
and worker configuration, installation checker, restore checker and tests. The
Graphtyn arm additionally tested cache invalidation after changing the effective
manifest and isolated the new environment variable in the shared fixture. These
are useful robustness improvements, but the frozen rubric was already fully met
by both arms, so they do not change the primary quality score.

The Graphtyn agent made two graph calls as instructed. Its first response was
reported by the agent itself as unrelated, after which it explored locally. The
final impact query did not prevent additional broad exploration. This run gives
no evidence of token savings for this implementation task; it shows materially
higher total and uncached consumption at equal rubric quality.

Limitations: one task, one repository, one free model and one repetition. Cached
input dominates both totals. Monetary cost is zero for this provider and cannot
be inferred from token counts. The client inserted the JSON schema line into
`opencode.json` in both worktrees; it is excluded from grading as a symmetric
harness/client side effect. The result must not be generalized to other tasks,
models or clients without repetitions.
