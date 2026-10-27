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
