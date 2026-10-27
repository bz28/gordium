ObjC.import('CoreGraphics');
function run(argv) {
  var x = parseFloat(argv[0]), y = parseFloat(argv[1]);
  var p = $.CGPointMake(x, y);
  var mv = $.CGEventCreateMouseEvent(null, $.kCGEventMouseMoved, p, 0);
  $.CGEventPost($.kCGHIDEventTap, mv);
  delay(0.2);
  var d = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseDown, p, 0);
  $.CGEventPost($.kCGHIDEventTap, d);
  delay(0.08);
  var u = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseUp, p, 0);
  $.CGEventPost($.kCGHIDEventTap, u);
}
