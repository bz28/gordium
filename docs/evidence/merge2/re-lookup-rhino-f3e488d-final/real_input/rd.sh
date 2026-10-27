#!/bin/bash
T=$(python3 -c "import tempfile;print(tempfile.gettempdir())")
rm -f $T/real_read.json
python3 /private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC2/real/../tools/rc.py script /private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC2/real/read2.py
for i in $(seq 1 30); do sleep 1; [ -f $T/real_read.json ] && break; done
sleep 0.5
python3 - <<P
import json
d=json.load(open("$T/real_read.json"))
print(json.dumps({k:d[k] for k in ("count","curves","layers_vis","same_as_before","ids_missing","ids_extra","lot_surveyed","main_building","stated","ground_marked","ui_ground_ids","layers_of","cmp_err") if k in d}), "| Rear:", [i for i in d["check_items"] if i[0]=="Rear yard"], "| n_items", len(d["check_items"]))
P
