# Graphtyn: changes, overviews and validation

Load this reference when the task edits code, asks for a repository overview or
a persistent report, or produces an architectural or impact claim that must be
checked before it is published.

## Authorized code changes

1. Query `graph_query_intent` with the concrete change before editing.
2. When the package includes `implementation_context`, treat it as the action
   contract:
   - open `read_first` in order and stay within `exploration_budget`;
   - use `source_evidence` to support claims; it supplements, not replaces,
     `implementation_context`, `execution_policy` or the original task;
   - run the first suggested test command that covers `test_files`; do not
     install dependencies during the edit unless the user asked for it;
   - with `do_not_expand=true`, do not grep broadly, list unrelated directories
     or inspect global environments; use at most one exact expansion for a
     named missing obligation;
   - stop when the targeted tests pass and `missing` is empty; report an
     unavailable test runner as a gap instead of provisioning one.
3. When consumers may be affected, run a final `impact` query.

For a Git-aware change, run `graphtyn impact --base HEAD --head HEAD --path <project>`
before risky edits and use the verification plan in `GRAPHTYN_CHANGE_REPORT.md`
afterwards. `graphtyn review --staged` covers the exact staged set.

## Ambiguous relations

List them with `graphtyn review --ambiguities --path <project>`. Record an
accept, reject or correct decision only after checking the source.

## Repository overview

Use `intent: overview` and structure the answer from `project_profile`,
`architecture`, `representative_flows` and `risk_signals`. Read only
`read_first` plus the returned entry points needed to verify the purpose from
documentation or code; do not infer product behavior from directory names.
Explain purpose, technologies, entry points, subsystems, representative flows,
risks and uncertainty. When the user wants a persistent artifact, run
`graphtyn report --path <project> --output GRAPHTYN_REPORT.md`.

## Validate before publishing

For important architectural or impact claims, save the draft and run
`graphtyn validate-answer --answer @draft.md --path <project>`; fix every
unsupported claim before publishing.
