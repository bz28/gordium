#!/bin/bash
osascript -l JavaScript <<'A'
var se = Application('System Events');
var p = se.processes.byName('Rhinoceros');
var w = p.windows.byName('TabPanelDockBarFloatingForm()');
var els = w.entireContents();
var out = [];
for (var i = 0; i < els.length; i++) {
  try { if (els[i].role() == 'AXCheckBox') out.push(els[i].name() + '=' + els[i].value()); } catch (e) {}
}
'ticks: ' + out.join(' | ');
A
