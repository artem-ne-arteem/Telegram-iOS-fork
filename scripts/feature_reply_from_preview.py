"""Feature: Reply from Preview.

Long-press a chat in the chat list: between the chat preview and its context menu a
separate glass block appears with a message field (attach, text, mic/send). The
message is sent with TelegramEngine without opening the chat."""
import sys

root = sys.argv[1]

ITEM = r'''import Foundation
import UIKit
import AsyncDisplayKit
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import AccountContext
import ContextUI

/// Reply from Preview: a message field shown as its own glass block between a chat
/// preview and its context menu, so a chat can be answered without opening it.
final class ChatListPreviewReplyItem: ContextMenuCustomItem {
    let context: AccountContext
    let peerId: EnginePeer.Id
    let openChat: () -> Void

    init(context: AccountContext, peerId: EnginePeer.Id, openChat: @escaping () -> Void) {
        self.context = context
        self.peerId = peerId
        self.openChat = openChat
    }

    func node(presentationData: PresentationData, getController: @escaping () -> ContextControllerProtocol?, actionSelected: @escaping (ContextMenuActionResult) -> Void) -> ContextMenuCustomNode {
        return ChatListPreviewReplyItemNode(item: self, presentationData: presentationData, getController: getController)
    }
}

private final class ChatListPreviewReplyItemNode: ASDisplayNode, ContextMenuCustomNode, UITextFieldDelegate {
    private let item: ChatListPreviewReplyItem
    private var presentationData: PresentationData
    private let getController: () -> ContextControllerProtocol?

    private let attachButton: UIButton
    private let textField: UITextField
    private let actionButton: UIButton
    private var isSending = false

    var needsSeparator: Bool {
        return false
    }

    var needsPadding: Bool {
        return false
    }

    init(item: ChatListPreviewReplyItem, presentationData: PresentationData, getController: @escaping () -> ContextControllerProtocol?) {
        self.item = item
        self.presentationData = presentationData
        self.getController = getController
        self.attachButton = UIButton(type: .system)
        self.textField = UITextField()
        self.actionButton = UIButton(type: .system)

        super.init()
    }

    override func didLoad() {
        super.didLoad()

        self.attachButton.addTarget(self, action: #selector(self.attachPressed), for: .touchUpInside)
        self.view.addSubview(self.attachButton)

        self.textField.font = UIFont.systemFont(ofSize: 17.0)
        self.textField.returnKeyType = .send
        self.textField.enablesReturnKeyAutomatically = true
        self.textField.delegate = self
        self.textField.addTarget(self, action: #selector(self.textChanged), for: .editingChanged)
        self.view.addSubview(self.textField)

        self.actionButton.addTarget(self, action: #selector(self.actionPressed), for: .touchUpInside)
        self.view.addSubview(self.actionButton)

        self.updateTheme(presentationData: self.presentationData)
    }

    func updateLayout(constrainedWidth: CGFloat, constrainedHeight: CGFloat) -> (CGSize, (CGSize, ContainedViewLayoutTransition) -> Void) {
        let size = CGSize(width: min(constrainedWidth, 340.0), height: 52.0)
        return (size, { [weak self] size, _ in
            self?.layoutContents(size: size)
        })
    }

    private func layoutContents(size: CGSize) {
        let buttonSize: CGFloat = 44.0
        let buttonY = floor((size.height - buttonSize) / 2.0)
        self.attachButton.frame = CGRect(x: 6.0, y: buttonY, width: buttonSize, height: buttonSize)
        self.actionButton.frame = CGRect(x: size.width - 6.0 - buttonSize, y: buttonY, width: buttonSize, height: buttonSize)
        let textX = self.attachButton.frame.maxX + 2.0
        self.textField.frame = CGRect(x: textX, y: 0.0, width: max(0.0, self.actionButton.frame.minX - 2.0 - textX), height: size.height)
    }

    func updateTheme(presentationData: PresentationData) {
        self.presentationData = presentationData
        let menuTheme = presentationData.theme.contextMenu
        self.attachButton.tintColor = menuTheme.primaryColor
        self.textField.textColor = menuTheme.primaryColor
        self.textField.tintColor = presentationData.theme.list.itemAccentColor
        self.textField.attributedPlaceholder = NSAttributedString(
            string: presentationData.strings.Conversation_InputTextPlaceholder,
            attributes: [.foregroundColor: menuTheme.secondaryColor, .font: UIFont.systemFont(ofSize: 17.0)]
        )
        self.updateButtons()
    }

    func canBeHighlighted() -> Bool {
        return false
    }

    func updateIsHighlighted(isHighlighted: Bool) {
    }

    func performAction() {
    }

    private var hasText: Bool {
        return !(self.textField.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func updateButtons() {
        let configuration = UIImage.SymbolConfiguration(pointSize: 20.0, weight: .regular)
        self.attachButton.setImage(UIImage(systemName: "paperclip", withConfiguration: configuration), for: .normal)
        if self.hasText {
            self.actionButton.setImage(UIImage(systemName: "arrow.up.circle.fill", withConfiguration: UIImage.SymbolConfiguration(pointSize: 30.0, weight: .regular)), for: .normal)
            self.actionButton.tintColor = self.presentationData.theme.list.itemAccentColor
        } else {
            self.actionButton.setImage(UIImage(systemName: "mic", withConfiguration: configuration), for: .normal)
            self.actionButton.tintColor = self.presentationData.theme.contextMenu.primaryColor
        }
    }

    @objc private func textChanged() {
        self.updateButtons()
    }

    @objc private func attachPressed() {
        self.openChat()
    }

    @objc private func actionPressed() {
        if self.hasText {
            self.send()
        } else {
            self.openChat()
        }
    }

    func textFieldShouldReturn(_ textField: UITextField) -> Bool {
        self.send()
        return false
    }

    private func openChat() {
        let openChat = self.item.openChat
        self.textField.resignFirstResponder()
        if let controller = self.getController() {
            controller.dismiss(completion: {
                openChat()
            })
        } else {
            openChat()
        }
    }

    private func send() {
        let text = (self.textField.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty || self.isSending {
            return
        }
        self.isSending = true
        self.textField.text = nil
        self.updateButtons()

        let _ = self.item.context.engine.messages.enqueueOutgoingMessage(to: self.item.peerId, replyTo: nil, content: .text(text, [])).startStandalone()

        // Leave the preview on screen for a moment so the sent message shows up in it.
        Queue.mainQueue().after(0.8, { [weak self] in
            guard let self else {
                return
            }
            self.textField.resignFirstResponder()
            self.getController()?.dismiss(completion: nil)
        })
    }
}
'''

open(root + "/submodules/ChatListUI/Sources/ChatListPreviewReplyItem.swift", "w", encoding="utf-8").write(ITEM)

path = root + "/submodules/ChatListUI/Sources/ChatListController.swift"
source = open(path, encoding="utf-8").read()
old = '''let contextController = makeContextController(context: strongSelf.context, presentationData: strongSelf.presentationData, source: source, items: chatContextMenuItems(context: strongSelf.context, peerId: peer.peerId, promoInfo: promoInfo, source: .chatList(filter: strongSelf.chatListDisplayNode.mainContainerNode.currentItemNode.chatListFilter), chatListController: strongSelf, joined: joined) |> map { ContextController.Items(content: .list($0)) }, gesture: gesture)'''
new = '''// Reply from Preview: a message field between the preview and the menu.
                        let canReplyFromPreview: Bool
                        if case let .channel(channel) = peer.peer, case .broadcast = channel.info {
                            canReplyFromPreview = false
                        } else {
                            canReplyFromPreview = true
                        }
                        let replyFromPreviewItem = ChatListPreviewReplyItem(context: strongSelf.context, peerId: peer.peerId, openChat: { [weak strongSelf] in
                            guard let strongSelf, let navigationController = strongSelf.navigationController as? NavigationController, let targetPeer = peer.peer else {
                                return
                            }
                            strongSelf.context.sharedContext.navigateToChatController(NavigateToChatControllerParams(navigationController: navigationController, context: strongSelf.context, chatLocation: .peer(targetPeer)))
                        })
                        let contextController = makeContextController(context: strongSelf.context, presentationData: strongSelf.presentationData, source: source, items: chatContextMenuItems(context: strongSelf.context, peerId: peer.peerId, promoInfo: promoInfo, source: .chatList(filter: strongSelf.chatListDisplayNode.mainContainerNode.currentItemNode.chatListFilter), chatListController: strongSelf, joined: joined) |> map { items -> ContextController.Items in
                            if canReplyFromPreview {
                                return ContextController.Items(content: .twoLists(items, [.custom(replyFromPreviewItem, false)]))
                            } else {
                                return ContextController.Items(content: .list(items))
                            }
                        }, gesture: gesture)'''
count = source.count(old)
if count != 1:
    sys.exit(f"reply_from_preview: expected 1 match in ChatListController, found {count}")
source = source.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(source)
print("reply_from_preview: preview reply item installed")
