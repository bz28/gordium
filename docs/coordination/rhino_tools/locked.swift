import CoreGraphics
import Foundation

if let d = CGSessionCopyCurrentDictionary() as? [String: Any] {
    print("locked:", d["CGSSessionScreenIsLocked"] ?? "no key (unlocked)")
    print("on console:", d["kCGSSessionOnConsoleKey"] ?? "?")
} else {
    print("no session")
}
