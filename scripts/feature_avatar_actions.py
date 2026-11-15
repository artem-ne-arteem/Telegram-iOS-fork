"""Feature: Avatar Actions.

Long-press a chat's avatar in the chat list: a vertical glass capsule slides out next
to it with Mute, Voice message, Video call and Call. Slide the finger onto an action
and release, or tap one. No need to open the chat."""
import sys

root = sys.argv[1]

path = root + "/submodules/ChatListUI/Sources/Node/ChatListItem.swift"
source = open(path, encoding="utf-8").read()
old = """        self.contextContainer.activated = { [weak self] gesture, location in
            guard let strongSelf = self, let item = strongSelf.item else {
                return
            }
"""
new = """        self.contextContainer.activated = { [weak self] gesture, location in
            guard let strongSelf = self, let item = strongSelf.item else {
                return
            }
            // Avatar Actions: a long press on the avatar opens quick actions instead of the preview.
            if strongSelf.avatarContainerNode.frame.insetBy(dx: -6.0, dy: -6.0).contains(location), case let .peer(peerData) = item.content, let peer = peerData.peer.peer, peerData.threadInfo == nil {
                presentChatListAvatarActions(context: item.context, peer: peer, avatarView: strongSelf.avatarContainerNode.view, gesture: gesture)
                return
            }
"""
if source.count(old) != 1:
    sys.exit("avatar_actions: activation anchor not found")
source = source.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(source)

SWIFT = r'''import Foundation
import UIKit
import AsyncDisplayKit
import Display
import SwiftSignalKit
import TelegramCore
import AccountContext

// MARK: - Avatar Actions

func presentChatListAvatarActions(context: AccountContext, peer: EnginePeer, avatarView: UIView, gesture: ContextGesture) {
    guard let window = avatarView.window, let mainWindow = context.sharedContext.mainWindow else {
        gesture.cancel()
        return
    }
    let presentationData = context.sharedContext.currentPresentationData.with { $0 }
    let avatarFrame = avatarView.convert(avatarView.bounds, to: window)

    var actions: [ChatListAvatarAction] = [.mute, .voice]
    if case let .user(user) = peer, user.botInfo == nil, peer.id != context.account.peerId {
        actions.append(.video)
        actions.append(.call)
    }

    let controller = ChatListAvatarActionsController(
        avatarFrame: avatarFrame,
        actions: actions,
        accentColor: presentationData.theme.list.itemAccentColor,
        isDark: presentationData.theme.overallDarkAppearance,
        perform: { action in
            switch action {
            case .mute:
                let _ = context.engine.peers.togglePeerMuted(peerId: peer.id, threadId: nil).startStandalone()
            case .voice:
                if let navigationController = mainWindow.viewController as? NavigationController {
                    context.sharedContext.navigateToChatController(NavigateToChatControllerParams(navigationController: navigationController, context: context, chatLocation: .peer(peer)))
                }
            case .video, .call:
                if let callManager = context.sharedContext.callManager {
                    let _ = callManager.requestCall(context: context, peerId: peer.id, isVideo: action == .video, endCurrentIfAny: false)
                }
            }
        }
    )

    gesture.externalUpdated = { [weak controller] view, point in
        guard let view, let window = view.window else {
            return
        }
        controller?.fingerMoved(to: view.convert(point, to: window))
    }
    gesture.externalEnded = { [weak controller] viewAndPoint in
        guard let viewAndPoint, let view = viewAndPoint.0, let window = view.window else {
            controller?.fingerLifted(at: nil)
            return
        }
        controller?.fingerLifted(at: view.convert(viewAndPoint.1, to: window))
    }

    mainWindow.present(controller, on: .root)
}

enum ChatListAvatarAction {
    case mute
    case voice
    case video
    case call

    var iconName: String {
        switch self {
        case .mute:
            return "speaker.slash.fill"
        case .voice:
            return "mic.fill"
        case .video:
            return "video.fill"
        case .call:
            return "phone.fill"
        }
    }
}

/// A full-screen overlay with a vertical glass capsule of actions next to the avatar.
final class ChatListAvatarActionsController: ViewController {
    private let avatarFrame: CGRect
    private let actions: [ChatListAvatarAction]
    private let accentColor: UIColor
    private let isDark: Bool
    private let perform: (ChatListAvatarAction) -> Void

    private var capsuleView: UIVisualEffectView?
    private var buttons: [UIButton] = []
    private let highlightView = UIView()
    private var highlightedIndex: Int?
    private var isDismissing = false
    private let selectionFeedback = UISelectionFeedbackGenerator()

    private let capsuleWidth: CGFloat = 50.0
    private let itemHeight: CGFloat = 40.0

    init(avatarFrame: CGRect, actions: [ChatListAvatarAction], accentColor: UIColor, isDark: Bool, perform: @escaping (ChatListAvatarAction) -> Void) {
        self.avatarFrame = avatarFrame
        self.actions = actions
        self.accentColor = accentColor
        self.isDark = isDark
        self.perform = perform
        super.init(navigationBarPresentationData: nil)
        self.statusBar.statusBarStyle = .Ignore
    }

    required init(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func loadDisplayNode() {
        self.displayNode = ASDisplayNode()
        self.displayNodeDidLoad()
        self.displayNode.view.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(self.backgroundTapped)))
    }

    override func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        if self.capsuleView == nil {
            self.setupCapsule(layoutSize: layout.size)
        }
    }

    private var capsuleFrame: CGRect {
        let height = CGFloat(self.actions.count) * self.itemHeight + 12.0
        // Right next to the avatar, starting a bit below its top, like a drop of glass.
        return CGRect(x: self.avatarFrame.maxX + 8.0, y: self.avatarFrame.minY + 14.0, width: self.capsuleWidth, height: height)
    }

    private func setupCapsule(layoutSize: CGSize) {
        var frame = self.capsuleFrame
        if frame.maxY > layoutSize.height - 100.0 {
            // Near the bottom the capsule grows upwards instead.
            frame.origin.y = self.avatarFrame.maxY - 14.0 - frame.height
        }

        let effect: UIVisualEffect
        if #available(iOS 26.0, *) {
            effect = UIGlassEffect()
        } else {
            effect = UIBlurEffect(style: self.isDark ? .systemThickMaterialDark : .systemThickMaterialLight)
        }
        let capsule = UIVisualEffectView(effect: effect)
        capsule.frame = frame
        capsule.layer.cornerRadius = self.capsuleWidth / 2.0
        capsule.layer.cornerCurve = .continuous
        if #available(iOS 26.0, *) {
        } else {
            capsule.clipsToBounds = true
        }
        capsule.layer.shadowColor = UIColor.black.cgColor
        capsule.layer.shadowOpacity = 0.12
        capsule.layer.shadowRadius = 14.0
        capsule.layer.shadowOffset = CGSize(width: 0.0, height: 6.0)

        self.highlightView.backgroundColor = self.accentColor.withAlphaComponent(0.15)
        self.highlightView.layer.cornerRadius = (self.capsuleWidth - 8.0) / 2.0
        self.highlightView.alpha = 0.0
        capsule.contentView.addSubview(self.highlightView)

        for (index, action) in self.actions.enumerated() {
            let button = UIButton(type: .system)
            button.frame = CGRect(x: 0.0, y: 6.0 + CGFloat(index) * self.itemHeight, width: self.capsuleWidth, height: self.itemHeight)
            button.setImage(UIImage(systemName: action.iconName, withConfiguration: UIImage.SymbolConfiguration(pointSize: 21.0, weight: .medium)), for: .normal)
            button.tintColor = self.accentColor
            button.tag = index
            button.addTarget(self, action: #selector(self.buttonPressed(_:)), for: .touchUpInside)
            capsule.contentView.addSubview(button)
            self.buttons.append(button)
        }

        self.displayNode.view.addSubview(capsule)
        self.capsuleView = capsule
        self.animateIn(capsule: capsule)
        self.selectionFeedback.prepare()
    }

    private func animateIn(capsule: UIVisualEffectView) {
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        // The capsule pours out of the avatar edge and stretches down.
        let finalFrame = capsule.frame
        let growsUp = finalFrame.minY < self.avatarFrame.minY
        capsule.frame = CGRect(x: self.avatarFrame.maxX - 6.0, y: growsUp ? finalFrame.maxY - self.capsuleWidth : finalFrame.minY, width: self.capsuleWidth, height: self.capsuleWidth)
        capsule.alpha = 0.0
        capsule.transform = CGAffineTransform(scaleX: 0.5, y: 0.5)
        for button in self.buttons {
            button.alpha = 0.0
            button.transform = CGAffineTransform(scaleX: 0.3, y: 0.3)
        }
        UIView.animate(withDuration: 0.12, animations: {
            capsule.alpha = 1.0
        })
        UIView.animate(withDuration: 0.55, delay: 0.0, usingSpringWithDamping: 0.68, initialSpringVelocity: 0.0, options: [.allowUserInteraction], animations: {
            capsule.transform = .identity
            capsule.frame = finalFrame
        }, completion: nil)
        let order = growsUp ? Array(self.buttons.reversed()) : self.buttons
        for (index, button) in order.enumerated() {
            UIView.animate(withDuration: 0.45, delay: 0.06 + Double(index) * 0.05, usingSpringWithDamping: 0.6, initialSpringVelocity: 0.0, options: [.allowUserInteraction], animations: {
                button.alpha = 1.0
                button.transform = .identity
            }, completion: nil)
        }
    }

    // MARK: Finger tracking (the long press continues on the capsule)

    private func index(at windowPoint: CGPoint) -> Int? {
        guard let capsule = self.capsuleView else {
            return nil
        }
        let local = capsule.convert(windowPoint, from: nil)
        guard capsule.bounds.insetBy(dx: -24.0, dy: -8.0).contains(local) else {
            return nil
        }
        for (index, button) in self.buttons.enumerated() where button.frame.insetBy(dx: -24.0, dy: 0.0).contains(local) {
            return index
        }
        return nil
    }

    func fingerMoved(to windowPoint: CGPoint) {
        self.setHighlighted(self.index(at: windowPoint))
    }

    func fingerLifted(at windowPoint: CGPoint?) {
        if let windowPoint, let index = self.index(at: windowPoint) {
            self.select(index: index)
        } else {
            // Released elsewhere: the capsule stays open for a tap.
            self.setHighlighted(nil)
        }
    }

    private func setHighlighted(_ index: Int?) {
        if index == self.highlightedIndex {
            return
        }
        self.highlightedIndex = index
        if index != nil {
            self.selectionFeedback.selectionChanged()
        }
        UIView.animate(withDuration: 0.25, delay: 0.0, usingSpringWithDamping: 0.7, initialSpringVelocity: 0.0, options: [.beginFromCurrentState, .allowUserInteraction], animations: {
            for (buttonIndex, button) in self.buttons.enumerated() {
                button.transform = buttonIndex == index ? CGAffineTransform(scaleX: 1.22, y: 1.22) : .identity
            }
            if let index {
                let frame = self.buttons[index].frame.insetBy(dx: 4.0, dy: 0.0)
                self.highlightView.frame = frame
                self.highlightView.alpha = 1.0
            } else {
                self.highlightView.alpha = 0.0
            }
        }, completion: nil)
    }

    @objc private func buttonPressed(_ sender: UIButton) {
        self.select(index: sender.tag)
    }

    private func select(index: Int) {
        guard !self.isDismissing, index < self.actions.count else {
            return
        }
        let action = self.actions[index]
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        let button = self.buttons[index]
        UIView.animate(withDuration: 0.12, animations: {
            button.transform = CGAffineTransform(scaleX: 1.4, y: 1.4)
        }, completion: { _ in
            self.dismissCapsule(completion: { [perform = self.perform] in
                perform(action)
            })
        })
    }

    @objc private func backgroundTapped() {
        self.dismissCapsule(completion: {})
    }

    private func dismissCapsule(completion: @escaping () -> Void) {
        guard !self.isDismissing, let capsule = self.capsuleView else {
            return
        }
        self.isDismissing = true
        UIView.animate(withDuration: 0.22, delay: 0.0, options: [.curveEaseIn], animations: {
            capsule.alpha = 0.0
            capsule.transform = CGAffineTransform(scaleX: 0.6, y: 0.6)
        }, completion: { [weak self] _ in
            completion()
            self?.dismiss(completion: nil)
        })
    }
}
'''
open(root + "/submodules/ChatListUI/Sources/ChatListAvatarActions.swift", "w", encoding="utf-8").write(SWIFT)
print("avatar_actions: installed")
