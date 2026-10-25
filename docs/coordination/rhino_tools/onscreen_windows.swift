// Lists Rhino's on-screen windows: "<window id>\t<title>\t<width>x<height>" (owner name contains "Rhino").
import CoreGraphics
import Foundation

let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] ?? []
for w in info {
    let owner = w[kCGWindowOwnerName as String] as? String ?? ""
    guard owner.contains("Rhino") else { continue }
    let id = w[kCGWindowNumber as String] as? Int ?? 0
    let name = w[kCGWindowName as String] as? String ?? ""
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    let width = b["Width"] as? Double ?? 0, height = b["Height"] as? Double ?? 0
    if width > 50 && height > 50 { print("\(id)\t\(name)\t\(Int(width))x\(Int(height))") }
}
