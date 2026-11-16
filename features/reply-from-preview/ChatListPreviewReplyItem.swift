import Foundation
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

        self.textField.font = UIFont.systemFont(ofSize: 16.0)
        self.textField.returnKeyType = .send
        self.textField.enablesReturnKeyAutomatically = true
        self.textField.delegate = self
        self.textField.addTarget(self, action: #selector(self.textChanged), for: .editingChanged)
        self.view.addSubview(self.textField)

        self.actionButton.addTarget(self, action: #selector(self.actionPressed), for: .touchUpInside)
        self.view.addSubview(self.actionButton)

        // A tap anywhere on the bar focuses the field.
        self.view.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(self.barTapped)))

        // Context menus are drawn above the keyboard. Move this one below it right away:
        // doing it on the first tap re-parents the view and the field loses focus.
        DispatchQueue.main.async { [weak self] in
            self?.getController()?.overlayWantsToBeBelowKeyboardUpdated(transition: .immediate)
        }

        self.updateTheme(presentationData: self.presentationData)
    }

    func updateLayout(constrainedWidth: CGFloat, constrainedHeight: CGFloat) -> (CGSize, (CGSize, ContainedViewLayoutTransition) -> Void) {
        // Same width as the chat preview above it.
        let size = CGSize(width: max(240.0, constrainedWidth - 32.0), height: 44.0)
        return (size, { [weak self] size, _ in
            self?.layoutContents(size: size)
        })
    }

    private func layoutContents(size: CGSize) {
        let buttonSize: CGFloat = 40.0
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
            attributes: [.foregroundColor: menuTheme.secondaryColor, .font: UIFont.systemFont(ofSize: 16.0)]
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
        let configuration = UIImage.SymbolConfiguration(pointSize: 18.0, weight: .regular)
        self.attachButton.setImage(UIImage(systemName: "paperclip", withConfiguration: configuration), for: .normal)
        if self.hasText {
            self.actionButton.setImage(UIImage(systemName: "arrow.up.circle.fill", withConfiguration: UIImage.SymbolConfiguration(pointSize: 27.0, weight: .regular)), for: .normal)
            self.actionButton.tintColor = self.presentationData.theme.list.itemAccentColor
        } else {
            self.actionButton.setImage(UIImage(systemName: "mic", withConfiguration: configuration), for: .normal)
            self.actionButton.tintColor = self.presentationData.theme.contextMenu.primaryColor
        }
    }

    /// The text turns into an outgoing bubble and flies from the field into the preview above.
    private func animateSentMessage(text: String, landed: @escaping () -> Void) {
        guard let window = self.view.window else {
            landed()
            return
        }
        let theme = self.presentationData.theme
        let bubbleColor = theme.chat.message.outgoing.bubble.withWallpaper.fill.first ?? theme.list.itemAccentColor

        let label = UILabel()
        label.text = text
        label.font = UIFont.systemFont(ofSize: 17.0)
        label.textColor = theme.chat.message.outgoing.primaryTextColor
        label.numberOfLines = 1
        let maxTextWidth = self.view.bounds.width * 0.7
        let textSize = label.sizeThatFits(CGSize(width: maxTextWidth, height: 100.0))
        let bubbleSize = CGSize(width: min(maxTextWidth, ceil(textSize.width)) + 24.0, height: 36.0)

        let bubble = UIView(frame: CGRect(origin: CGPoint(), size: bubbleSize))
        bubble.backgroundColor = bubbleColor
        bubble.layer.cornerRadius = 18.0
        bubble.layer.cornerCurve = .continuous
        label.frame = CGRect(x: 12.0, y: floor((bubbleSize.height - textSize.height) / 2.0), width: bubbleSize.width - 24.0, height: ceil(textSize.height))
        bubble.addSubview(label)

        let fieldFrame = self.textField.convert(self.textField.bounds, to: window)
        bubble.center = CGPoint(x: fieldFrame.minX + bubbleSize.width / 2.0, y: fieldFrame.midY)
        bubble.transform = CGAffineTransform(scaleX: 0.85, y: 0.85)
        bubble.alpha = 0.0
        window.addSubview(bubble)

        // Bottom-right corner of the chat preview, right above this block.
        let barFrame = self.view.convert(self.view.bounds, to: window)
        let target = CGPoint(x: barFrame.maxX - 14.0 - bubbleSize.width / 2.0, y: barFrame.minY - 18.0 - bubbleSize.height / 2.0)

        UIView.animate(withDuration: 0.12, animations: {
            bubble.alpha = 1.0
        })
        UIView.animate(withDuration: 0.45, delay: 0.0, usingSpringWithDamping: 0.85, initialSpringVelocity: 0.3, options: [.curveEaseOut], animations: {
            bubble.center = target
            bubble.transform = .identity
        }, completion: { _ in
            landed()
            UIView.animate(withDuration: 0.2, delay: 0.25, options: [], animations: {
                bubble.alpha = 0.0
            }, completion: { _ in
                bubble.removeFromSuperview()
            })
        })

        self.actionButton.transform = CGAffineTransform(scaleX: 0.8, y: 0.8)
        UIView.animate(withDuration: 0.4, delay: 0.0, usingSpringWithDamping: 0.5, initialSpringVelocity: 0.0, options: [], animations: {
            self.actionButton.transform = .identity
        }, completion: nil)
    }

    @objc private func barTapped() {
        self.textField.becomeFirstResponder()
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

        let item = self.item
        self.animateSentMessage(text: text, landed: { [weak self] in
            // Send exactly when the bubble lands, so the real message replaces it.
            let _ = item.context.engine.messages.enqueueOutgoingMessage(to: item.peerId, replyTo: nil, content: .text(text, [])).startStandalone()
            self?.scheduleDismissAfterSend()
        })
    }

    private func scheduleDismissAfterSend() {
        // Leave the preview on screen for a moment so the sent message shows up in it.
        Queue.mainQueue().after(0.9, { [weak self] in
            guard let self else {
                return
            }
            self.textField.resignFirstResponder()
            self.getController()?.dismiss(completion: nil)
        })
    }
}
