# helpers (source me)
L=/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC2/real
shot(){ screencapture -x $L/shots3/$1.png; sips -Z 1200 $L/shots3/$1.png >/dev/null; }
st(){ echo "[$1]"; $L/rd.sh; $L/ticks.sh; }
clk(){ osascript -e "tell application \"System Events\" to click at {$1, $2}" >/dev/null; }
undo(){ osascript -e 'tell application "System Events" to keystroke "z" using command down'; }
front(){ osascript -e 'tell application "System Events" to name of first process whose frontmost is true'; }
typ(){ osascript -e "tell application \"System Events\" to keystroke \"$1\"" -e 'tell application "System Events" to key code 36'; }
mclick(){ osascript -l JavaScript /private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC2/real/mclick.js $1 $2; }
