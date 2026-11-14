"""Feature: Reply from Preview.

Long-press a chat in the chat list -> the preview (a ChatController in
.standard(.previewing) mode hosted by a ContextController) now shows the regular
message input panel, so you can answer without opening the chat. Sending, the
keyboard, stickers and voice messages reuse Telegram's own input panel."""
import sys

path = sys.argv[1] + "/submodules/TelegramUI/Sources/ChatControllerNode.swift"
source = open(path, encoding="utf-8").read()


def replace_once(old, new):
    global source
    count = source.count(old)
    if count != 1:
        sys.exit(f"reply_from_preview: expected 1 match, found {count}:\n{old}")
    source = source.replace(old, new, 1)


# 1. Keep the text input panel in preview mode (other panels stay hidden).
replace_once(
    "if let inputPanelNode = inputPanelNodes.primary, !previewing {",
    "if let inputPanelNode = inputPanelNodes.primary, !previewing || inputPanelNode is ChatTextInputPanelNode {",
)

# 2. Let touches reach the input panel inside the preview.
replace_once(
    """        switch self.chatPresentationInterfaceState.mode {
        case .standard(.previewing):
            if let subject = self.controller?.subject, case let .messageOptions(_, _, info) = subject, case .reply = info {""",
    """        switch self.chatPresentationInterfaceState.mode {
        case .standard(.previewing):
            // Reply from Preview: the input panel inside a chat preview is interactive.
            if let inputPanelNode = self.inputPanelNode as? ChatTextInputPanelNode, inputPanelNode.supernode != nil {
                if let result = inputPanelNode.view.hitTest(self.view.convert(point, to: inputPanelNode.view), with: event) {
                    return result
                }
            }
            if let inputNode = self.inputNode, let result = inputNode.view.hitTest(self.view.convert(point, to: inputNode.view), with: event) {
                return result
            }
            if let subject = self.controller?.subject, case let .messageOptions(_, _, info) = subject, case .reply = info {""",
)

# 3. Tapping the input panel must not open the full chat; a tap elsewhere first hides the keyboard.
replace_once(
    """            if case .standard(.previewing) = self.chatPresentationInterfaceState.mode {
                self.controller?.animateFromPreviewing()
            } else {
                self.dismissInput(view: self.view, location: recognizer.location(in: self.contentContainerNode.view))
            }""",
    """            if case .standard(.previewing) = self.chatPresentationInterfaceState.mode {
                if let inputPanelNode = self.inputPanelNode as? ChatTextInputPanelNode {
                    if inputPanelNode.view.bounds.contains(recognizer.location(in: inputPanelNode.view)) {
                        return
                    }
                    if inputPanelNode.isFocused {
                        self.dismissInput(view: self.view, location: recognizer.location(in: self.contentContainerNode.view))
                        return
                    }
                }
                self.controller?.animateFromPreviewing()
            } else {
                self.dismissInput(view: self.view, location: recognizer.location(in: self.contentContainerNode.view))
            }""",
)

open(path, "w", encoding="utf-8").write(source)
print("reply_from_preview: ChatControllerNode patched")
