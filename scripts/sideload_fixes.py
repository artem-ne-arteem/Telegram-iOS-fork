"""Make Telegram start when it is re-signed for sideloading (Sideloadly, ESign...).

Re-signed builds usually lose the App Group and keychain group entitlements.
Telegram then gets nil from containerURL(...) and crashes on `try!` during launch,
which looks like a black screen. We fall back to the app's own Documents folder."""
import sys

path = sys.argv[1] + "/submodules/TelegramUI/Sources/AppDelegate.swift"
source = open(path, encoding="utf-8").read()


def replace_once(old, new):
    global source
    if old not in source:
        sys.exit(f"sideload_fixes: pattern not found:\n{old}")
    source = source.replace(old, new, 1)


replace_once(
    "        precondition(!testIsLaunched)\n        testIsLaunched = true\n",
    "        precondition(!testIsLaunched)\n        testIsLaunched = true\n"
    "        FileManager.tg_installSideloadAppGroupFallback()\n",
)
replace_once("try! PasscodeEnvironment.shared.configure(", "try? PasscodeEnvironment.shared.configure(")

source += '''

// MARK: - Sideload compatibility (fork)

extension FileManager {
    /// After the swap below this name points to the system implementation.
    @objc dynamic func tg_sideloadContainerURL(forSecurityApplicationGroupIdentifier groupIdentifier: String) -> URL? {
        if let url = self.tg_sideloadContainerURL(forSecurityApplicationGroupIdentifier: groupIdentifier) {
            return url
        }
        guard let documents = self.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return nil
        }
        let fallback = documents.appendingPathComponent("AppGroup-\\(groupIdentifier)", isDirectory: true)
        try? self.createDirectory(at: fallback, withIntermediateDirectories: true, attributes: nil)
        return fallback
    }

    static func tg_installSideloadAppGroupFallback() {
        guard let original = class_getInstanceMethod(FileManager.self, #selector(FileManager.containerURL(forSecurityApplicationGroupIdentifier:))),
              let replacement = class_getInstanceMethod(FileManager.self, #selector(FileManager.tg_sideloadContainerURL(forSecurityApplicationGroupIdentifier:))) else {
            return
        }
        method_exchangeImplementations(original, replacement)
    }
}
'''

open(path, "w", encoding="utf-8").write(source)
print("sideload_fixes: AppDelegate patched")
