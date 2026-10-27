ObjC.import('CoreGraphics');
function run(argv) {
  var x = parseFloat(argv[0]), y = parseFloat(argv[1]), dy = parseInt(argv[2]);
  $.CGEventPost($.kCGHIDEventTap, $.CGEventCreateMouseEvent(null, $.kCGEventMouseMoved, $.CGPointMake(x, y), 0));
  delay(0.2);
  var e = $.CGEventCreateScrollWheelEvent(null, 0, 1, dy);
  $.CGEventPost($.kCGHIDEventTap, e);
}
