#!/usr/bin/env bash
# usage: run.sh corpus client model
set -u
cd /home/calero/Documentos/docker/PROYECTOS/graphtyn
R=/home/calero/Documentos/docker/graphtyn-benchmark-runs-test3-2026-10-29
B=benchmarks/task_bank_2026-10-28/test3
REPOS=/home/calero/Documentos/docker/graphtyn-benchmark-repos-2026-10-20
corpus=$1; client=$2; model=$3
declare -A EXE=([current]=/home/calero/Documentos/docker/PROYECTOS/graphtyn/.venv/bin/graphtyn [A]=/tmp/claude-1000/-home-calero-Documentos-docker-PROYECTOS-graphtyn/4dacbdad-de83-4a85-a898-f8addb6fb661/scratchpad/bin/graphtyn-A [BCD]=/tmp/claude-1000/-home-calero-Documentos-docker-PROYECTOS-graphtyn/4dacbdad-de83-4a85-a898-f8addb6fb661/scratchpad/bin/graphtyn-BCD)
log=$R/$corpus-$client.log
run() { # variant arm task
  echo "=== $(date -Is) $1 $3 $2 start" >> $log
  .venv/bin/python benchmarks/run_three_client_mcp_comparison.py --protocol $B/${3}_protocol.json --tasks $B/${corpus}_tasks.json --repo $REPOS/$corpus \
    --output-dir $R/$1/$corpus/$3/$client --model $client=$model --client $client --arms $2 --repetitions 1 \
    --graphtyn-executable ${EXE[${1/none/current}]} \
    --timeout 600 --stop-rule targeted --execute >> $log 2>&1
  echo "=== $(date -Is) $1 $3 rc=$?" >> $log
}
for task in $(python3 -c "import json;print(' '.join(t['id'].lower() for t in json.load(open('$B/${corpus}_tasks.json'))['tasks']))"); do
  run none baseline $task
  for v in current A BCD; do run $v graphtyn_hook $task; done
done
echo "=== $(date -Is) DONE" >> $log
