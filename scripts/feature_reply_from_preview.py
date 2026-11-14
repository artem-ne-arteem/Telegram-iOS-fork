"""Features: Reply from Preview + Swipe through Previews.

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
final class ChatListPreviewReplyItem: ContextMenuFullWidthCustomItem {
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

        // A tap anywhere on the bar focuses the field.
        self.view.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(self.barTapped)))

        self.updateTheme(presentationData: self.presentationData)
    }

    func updateLayout(constrainedWidth: CGFloat, constrainedHeight: CGFloat) -> (CGSize, (CGSize, ContainedViewLayoutTransition) -> Void) {
        // Same width as the chat preview above it.
        let size = CGSize(width: max(240.0, constrainedWidth - 32.0), height: 52.0)
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

    @objc private func barTapped() {
        self.textField.becomeFirstResponder()
    }

    func textFieldDidBeginEditing(_ textField: UITextField) {
        // Context menus are drawn above the keyboard; move this one below it while typing.
        self.getController()?.overlayWantsToBeBelowKeyboardUpdated(transition: .animated(duration: 0.3, curve: .spring))
    }

    func textFieldDidEndEditing(_ textField: UITextField) {
        self.getController()?.overlayWantsToBeBelowKeyboardUpdated(transition: .animated(duration: 0.3, curve: .spring))
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



def patch(relative_path, replacements, append=None):
    file_path = root + "/" + relative_path
    text = open(file_path, encoding="utf-8").read()
    for old, new in replacements:
        count = text.count(old)
        if count != 1:
            sys.exit(f"reply_from_preview: expected 1 match in {relative_path}, found {count}:\n{old}")
        text = text.replace(old, new, 1)
    if append:
        text += append
    open(file_path, "w", encoding="utf-8").write(text)


# ContextUI: a custom menu item may ask for the full screen width.
patch("submodules/ContextUI/Sources/ContextController.swift", [], append="""

/// A custom context menu item laid out at the full width of the screen
/// instead of the standard context menu width.
public protocol ContextMenuFullWidthCustomItem: ContextMenuCustomItem {
}
""")

# Actions list: don't clamp full-width custom items to the standard menu width.
patch("submodules/TelegramUI/Components/ContextControllerImpl/Sources/ContextControllerActionsStackNode.swift", [
    ("""private final class ContextControllerActionsListCustomItemNode: ASDisplayNode, ContextControllerActionsListItemNode {
""", """private final class ContextControllerActionsListCustomItemNode: ASDisplayNode, ContextControllerActionsListItemNode {
    var wantsFullScreenWidth: Bool {
        return self.item is ContextMenuFullWidthCustomItem
    }

"""),
    ("""                let itemNodeLayout = item.node.update(
                    presentationData: presentationData,
                    constrainedSize: CGSize(width: standardMaxWidth, height: constrainedSize.height)
                )""", """                var itemConstrainedWidth = standardMaxWidth
                if let customItemNode = item.node as? ContextControllerActionsListCustomItemNode, customItemNode.wantsFullScreenWidth {
                    itemConstrainedWidth = constrainedSize.width
                }
                let itemNodeLayout = item.node.update(
                    presentationData: presentationData,
                    constrainedSize: CGSize(width: itemConstrainedWidth, height: constrainedSize.height)
                )"""),
])

# Presentation: center a wide block, go below the keyboard and lift content while typing.
patch("submodules/TelegramUI/Components/ContextControllerImpl/Sources/ContextControllerExtractedPresentationNode.swift", [
    ("""                } else {
                    additionalActionsFrame = CGRect(origin: actionsFrame.origin, size: additionalActionsSize)
                    actionsFrame = actionsFrame.offsetBy(dx: 0.0, dy: additionalActionsSize.height + 10.0)
                }""", """                } else {
                    additionalActionsFrame = CGRect(origin: actionsFrame.origin, size: additionalActionsSize)
                    if additionalActionsSize.width > actionsFrame.width {
                        // A full-width block is centered under the content.
                        additionalActionsFrame.origin.x = floor((layout.size.width - additionalActionsSize.width) / 2.0)
                    }
                    actionsFrame = actionsFrame.offsetBy(dx: 0.0, dy: additionalActionsSize.height + 10.0)
                }"""),
    ("""            transition.updateFrame(node: self.additionalActionsStackNode, frame: additionalActionsFrame.offsetBy(dx: -combinedActionsFrame.minX, dy: -combinedActionsFrame.minY), beginWithCurrentState: true)
""", """            transition.updateFrame(node: self.additionalActionsStackNode, frame: additionalActionsFrame.offsetBy(dx: -combinedActionsFrame.minX, dy: -combinedActionsFrame.minY), beginWithCurrentState: true)

            // Keep a focused text field inside the menu above the keyboard.
            var keyboardLift: CGFloat = 0.0
            if let inputHeight = layout.inputHeight, inputHeight > 0.0, additionalActionsSize.height > 0.0, contextMenuViewContainsFirstResponder(self.actionsContainerNode.view) {
                let fieldBottom = self.scrollNode.view.convert(CGPoint(x: 0.0, y: additionalActionsFrame.maxY + additionalVisibleOffsetY), to: self.view).y
                let maxFieldBottom = layout.size.height - inputHeight - 10.0
                if fieldBottom > maxFieldBottom {
                    keyboardLift = fieldBottom - maxFieldBottom
                }
            }
            transition.updateSublayerTransformOffset(layer: self.scrollNode.layer, offset: CGPoint(x: 0.0, y: -keyboardLift))
"""),
    ("""    func wantsDisplayBelowKeyboard() -> Bool {
        if let reactionContextNode = self.reactionContextNode {""", """    func wantsDisplayBelowKeyboard() -> Bool {
        if contextMenuViewContainsFirstResponder(self.actionsContainerNode.view) {
            return true
        }
        if let reactionContextNode = self.reactionContextNode {"""),
], append="""

private func contextMenuViewContainsFirstResponder(_ view: UIView) -> Bool {
    if view.isFirstResponder {
        return true
    }
    for subview in view.subviews {
        if contextMenuViewContainsFirstResponder(subview) {
            return true
        }
    }
    return false
}
""")

path = root + "/submodules/ChatListUI/Sources/ChatListController.swift"
source = open(path, encoding="utf-8").read()
old = """let contextController = makeContextController(context: strongSelf.context, presentationData: strongSelf.presentationData, source: source, items: chatContextMenuItems(context: strongSelf.context, peerId: peer.peerId, promoInfo: promoInfo, source: .chatList(filter: strongSelf.chatListDisplayNode.mainContainerNode.currentItemNode.chatListFilter), chatListController: strongSelf, joined: joined) |> map { ContextController.Items(content: .list($0)) }, gesture: gesture)"""
new = """let chatListFilter = strongSelf.chatListDisplayNode.mainContainerNode.currentItemNode.chatListFilter

                        // Reply from Preview: every preview gets a message field between it and its menu.
                        let makePreviewItems: (EnginePeer.Id, EnginePeer?, Bool, Bool) -> Signal<ContextController.Items, NoError> = { [weak strongSelf] itemPeerId, targetPeer, joinedValue, isMainPreview in
                            guard let strongSelf else {
                                return .single(ContextController.Items(content: .list([])))
                            }
                            let canReply: Bool
                            if case let .channel(channel) = targetPeer, case .broadcast = channel.info {
                                canReply = false
                            } else {
                                canReply = true
                            }
                            let replyItem = ChatListPreviewReplyItem(context: strongSelf.context, peerId: itemPeerId, openChat: { [weak strongSelf] in
                                guard let strongSelf, let navigationController = strongSelf.navigationController as? NavigationController, let targetPeer else {
                                    return
                                }
                                strongSelf.context.sharedContext.navigateToChatController(NavigateToChatControllerParams(navigationController: navigationController, context: strongSelf.context, chatLocation: .peer(targetPeer)))
                            })
                            return chatContextMenuItems(context: strongSelf.context, peerId: itemPeerId, promoInfo: isMainPreview ? promoInfo : nil, source: .chatList(filter: chatListFilter), chatListController: strongSelf, joined: joinedValue)
                            |> map { items -> ContextController.Items in
                                if canReply {
                                    return ContextController.Items(content: .twoLists(items, [.custom(replyItem, false)]))
                                } else {
                                    return ContextController.Items(content: .list(items))
                                }
                            }
                        }

                        var previewSources: [ContextController.Source] = [ContextController.Source(
                            id: AnyHashable(peer.peerId),
                            title: peer.peer?.compactDisplayTitle ?? "",
                            source: source,
                            items: makePreviewItems(peer.peerId, peer.peer, joined, true)
                        )]

                        // Swipe through Previews: neighbouring chats become extra pages of the same
                        // context menu, so you can flip left/right through them without letting go.
                        var isCommunityPreview = false
                        if case .community = peer.peer {
                            isCommunityPreview = true
                        }
                        if case .controller = source, !isCommunityPreview {
                            var rows: [(peerData: ChatListItemContent.PeerData, node: ChatListItemNode)] = []
                            strongSelf.chatListDisplayNode.mainContainerNode.currentItemNode.forEachItemNode { itemNode in
                                guard let itemNode = itemNode as? ChatListItemNode, let rowItem = itemNode.item, case let .peer(rowData) = rowItem.content, let rowPeer = rowData.peer.peer else {
                                    return
                                }
                                if case .community = rowPeer {
                                    return
                                }
                                if case let .channel(channel) = rowPeer, channel.isForumOrMonoForum {
                                    return
                                }
                                if rowData.displayAsTopicList || rowPeer.id == strongSelf.context.account.peerId {
                                    return
                                }
                                rows.append((rowData, itemNode))
                            }
                            rows.sort(by: { $0.node.frame.minY < $1.node.frame.minY })

                            if let currentIndex = rows.firstIndex(where: { $0.peerData.peer.peerId == peer.peerId }) {
                                let lowerBound = max(0, currentIndex - 2)
                                let upperBound = min(rows.count - 1, currentIndex + 2)
                                var orderedSources: [ContextController.Source] = []
                                for index in lowerBound ... upperBound {
                                    if index == currentIndex {
                                        orderedSources.append(previewSources[0])
                                        continue
                                    }
                                    let row = rows[index]
                                    let rowPeerId = row.peerData.peer.peerId
                                    let rowChatController = strongSelf.context.sharedContext.makeChatController(context: strongSelf.context, chatLocation: .peer(id: rowPeerId), subject: nil, botStart: nil, mode: .standard(.previewing), params: nil)
                                    rowChatController.customNavigationController = strongSelf.navigationController as? NavigationController
                                    rowChatController.canReadHistory.set(false)
                                    rowChatController.dismissPreviewing = { animateIn in
                                        return dismissPreviewingImpl?(animateIn) ?? {}
                                    }
                                    orderedSources.append(ContextController.Source(
                                        id: AnyHashable(rowPeerId),
                                        title: row.peerData.peer.peer?.compactDisplayTitle ?? "",
                                        source: .controller(ContextControllerContentSourceImpl(controller: rowChatController, sourceNode: row.node.contextContainer, navigationController: strongSelf.navigationController as? NavigationController)),
                                        items: makePreviewItems(rowPeerId, row.peerData.peer.peer, false, false)
                                    ))
                                }
                                previewSources = orderedSources
                            }
                        }

                        let contextController = makeContextController(context: strongSelf.context, presentationData: strongSelf.presentationData, configuration: ContextController.Configuration(sources: previewSources, initialId: AnyHashable(peer.peerId)), gesture: gesture)"""
count = source.count(old)
if count != 1:
    sys.exit(f"reply_from_preview: expected 1 match in ChatListController, found {count}")
source = source.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(source)
print("reply_from_preview + swipe_through_previews: chat list preview patched")
