#!/bin/bash
# usage: bash lane.sh <client> <model> <ceiling>
# Per repetition and task: Graphtyn main (7ab006a, PR #68), c213b37 (tokens) and a41fcb6 (final), arm order rotated per repetition.
cd /home/calero/Documentos/docker/PROYECTOS/graphtyn || exit 1
O=/home/calero/Documentos/docker/graphtyn-benchmark-runs-quality-2026-11-17; B=$O/bench-def
R=/home/calero/Documentos/docker/graphtyn-benchmark-repos-2026-11-17-quality
client=$1; model=$2; ceiling=$3; total=0
run() {  # <variant> <corpus> <task>
  local variant=$1 corpus=$2 task=$3 name; name=$(echo "$3" | tr A-Z a-z)
  local log=$O/logs/$client-$variant-$name-r$rep.log; mkdir -p $O/logs
  .venv/bin/python benchmarks/run_three_client_mcp_comparison.py --protocol $B/protocols/$name.json \
    --tasks $B/${corpus}_tasks.json --repo "$R/$corpus" --output-dir "$O/$client/$variant/$name" \
    --model "$client=$model" --client "$client" --arms graphtyn --repetitions 3 --repetition $rep \
    --graphtyn-executable "$O/graphtyn-$variant" --stop-rule targeted --timeout 900 \
    --initial-tokens "$total" --total-token-ceiling "$ceiling" --skip-complete --execute > "$log" 2>&1
  local rc=$? t; t=$(grep -o 'total_tokens=[0-9]*' "$log" | tail -1 | cut -d= -f2); [ -n "$t" ] && total=$t
  echo "$(date -Is) $client $variant $name r$rep rc=$rc cumulative=$total"
  if [ $rc -ne 0 ]; then tail -3 "$log" | cut -c1-300; fi
  if [ "$total" -ge "$ceiling" ]; then echo "CEILING $client $total"; exit 3; fi
}
for rep in 1 2 3; do
  case $rep in 1) order="main tokens final" ;; 2) order="tokens final main" ;; 3) order="final main tokens" ;; esac
  for spec in winston:Q_WINSTON_GET_LEVEL_VALUE_IMPACT marshmallow:Q_MARSHMALLOW_IS_AWARE_IMPACT \
              monolog:Q_MONOLOG_UNWRAP_FORMATTER_IMPACT logrus:Q_LOGRUS_PREFIX_FIELD_CLASHES_IMPACT \
              winston:Q_WINSTON_GET_ALL_INFO_IMPACT marshmallow:Q_MARSHMALLOW_CALLABLE_OR_RAISE_IMPACT \
              monolog:Q_MONOLOG_CANONICALIZE_PATH_IMPACT logrus:Q_LOGRUS_GET_PACKAGE_NAME_IMPACT; do
    corpus=${spec%%:*}; task=${spec##*:}
    for variant in $order; do run "$variant" "$corpus" "$task"; done
  done
done
echo "DONE $client total=$total"
