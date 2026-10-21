// Read-only foreground identity. No AX/System Events, activation or event loop.
import AppKit
import Foundation
import Darwin

guard let application = NSWorkspace.shared.frontmostApplication else {
    FileHandle.standardError.write(Data("No frontmost application\n".utf8))
    exit(2)
}
let result: [String: Any] = [
    "pid": Int(application.processIdentifier),
    "active": application.isActive,
    "bundle_id": application.bundleIdentifier ?? "",
    "name": application.localizedName ?? ""
]
do {
    let bytes = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    FileHandle.standardOutput.write(bytes)
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    FileHandle.standardError.write(Data("Cannot encode foreground identity\n".utf8))
    exit(3)
}
