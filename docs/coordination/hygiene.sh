#!/bin/zsh
# Coordinator hygiene check: every test process, its age, CPU, folder; flags anything over 45 min or in a
# finished lane's folder. Run on every agent notification and before starting work. Kill orphans' children first.
echo "load: $(uptime | sed 's/.*averages: //')  memory free: $(memory_pressure | tail -1 | grep -o '[0-9]*%')"
for p in $(pgrep -f "pytest -q"); do
  par=$(ps -o ppid= -p $p | tr -d ' '); pargs=$(ps -o args= -p $par 2>/dev/null)
  [[ "$pargs" == *"pytest -q"* ]] && continue   # xdist worker: counted under its parent
  et=$(ps -o etime= -p $p | tr -d ' '); cwd=$(lsof -a -p $p -d cwd -Fn 2>/dev/null | grep ^n | sed 's|.*scratchpad/||')
  w=$(pgrep -P $p | wc -l | tr -d ' '); mins=$(echo $et | awk -F'[-:]' '{if(NF==4)print $1*1440+$2*60+$3; else if(NF==3)print $1*60+$2; else print $1}')
  flag=""; (( mins > 45 )) && flag="  <-- OVER 45 MIN"
  echo "pid $p  age $et  workers $w  folder $cwd$flag"
done
pgrep -x caffeinate >/dev/null && echo "caffeinate: on" || echo "caffeinate: OFF"
# Agents: minutes since each background agent's transcript last changed. A "running" agent quiet for over 30 min is stalled.
T=/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/tasks
# Only the coordinator's own lanes, listed one id per line in scratchpad/watch.txt (reviewers and sceptics are not listed).
now=$(date +%s); for id in $(cat ${T%/tasks}/scratchpad/watch.txt 2>/dev/null); do f=$T/$id.output; [[ -f $f ]] || continue; m=$(( (now - $(stat -f %m $f)) / 60 )); (( m < 720 )) && echo "agent $(basename $f .output | cut -c1-8): quiet ${m} min"; done
echo "disk: $(df -h / | tail -1 | awk '{print $4}') free; scratch $(du -sh ${T%/tasks}/scratchpad 2>/dev/null | cut -f1); worktrees $(git -C /Users/benzhao/Documents/Gordium worktree list | wc -l | tr -d ' ')"
