"""Feature: Floating Chat.

Pull an open chat's title down: the chat shrinks into a glossy jelly bubble with the
avatar inside that floats above Telegram. Drag it around (it sticks to the screen
edges with a jelly wobble), tap it to reopen the chat, drop it on the × to close."""
import sys

root = sys.argv[1]

# 1. Gesture on the chat title.
path = root + "/submodules/TelegramUI/Sources/ChatController.swift"
source = open(path, encoding="utf-8").read()
old = """        self.navigationItem.titleView = self.chatTitleView
        self.chatTitleView?.longTapAction = { [weak self] in
"""
new = """        self.navigationItem.titleView = self.chatTitleView
        // Floating Chat: pull the title down to minimize the chat into a floating bubble.
        if let chatTitleView = self.chatTitleView {
            chatTitleView.addGestureRecognizer(UIPanGestureRecognizer(target: self, action: #selector(self.floatingChatMinimizePan(_:))))
        }
        self.chatTitleView?.longTapAction = { [weak self] in
"""
if source.count(old) != 1:
    sys.exit("floating_chat: title view anchor not found")
source = source.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(source)

# 2. The bubble itself.
SWIFT = r'''import Foundation
import UIKit
import AsyncDisplayKit
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import AccountContext
import AvatarNode

// MARK: - Floating Chat

extension ChatControllerImpl {
    @objc func floatingChatMinimizePan(_ recognizer: UIPanGestureRecognizer) {
        guard case .peer = self.chatLocation else {
            return
        }
        if case .standard(.previewing) = self.presentationInterfaceState.mode {
            return
        }
        let translation = max(0.0, recognizer.translation(in: self.view).y)
        switch recognizer.state {
        case .changed:
            // The chat follows the finger and starts shrinking towards a bubble.
            let progress = min(1.0, translation / 240.0)
            let scale = 1.0 - progress * 0.14
            self.view.transform = CGAffineTransform(translationX: 0.0, y: translation * 0.4).scaledBy(x: scale, y: scale)
        case .ended, .cancelled:
            if recognizer.state == .ended && (translation > 90.0 || recognizer.velocity(in: self.view).y > 700.0) {
                self.minimizeToFloatingBubble()
            } else {
                UIView.animate(withDuration: 0.4, delay: 0.0, usingSpringWithDamping: 0.75, initialSpringVelocity: 0.0, options: [], animations: {
                    self.view.transform = .identity
                }, completion: nil)
            }
        default:
            break
        }
    }

    func minimizeToFloatingBubble() {
        guard case let .peer(peerId) = self.chatLocation, let window = self.view.window else {
            self.view.transform = .identity
            return
        }
        var peer: EnginePeer?
        if let peerView = self.contentData?.state.peerView, let mainPeer = peerView.peers[peerView.peerId] {
            peer = EnginePeer(mainPeer)
        }
        let sourceFrame = self.view.convert(self.view.bounds, to: window)
        let snapshot = self.view.snapshotView(afterScreenUpdates: false)
        let navigationController = self.effectiveNavigationController

        let bubble = ChatFloatingBubbleController(
            context: self.context,
            peerId: peerId,
            peer: peer,
            theme: self.presentationData.theme,
            snapshot: snapshot,
            sourceFrame: sourceFrame,
            navigationController: navigationController
        )
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        self.present(bubble, in: .window(.root))
        self.view.transform = .identity
        navigationController?.filterController(self, animated: false)
    }
}

/// Presented at window level; lets every touch outside the bubble through.
final class ChatFloatingBubbleController: ViewController {
    private let context: AccountContext
    private let peerId: EnginePeer.Id
    private var peer: EnginePeer?
    private let theme: PresentationTheme
    private var snapshot: UIView?
    private let sourceFrame: CGRect
    private weak var chatNavigationController: NavigationController?

    private var bubbleView: ChatFloatingBubbleView?
    private let closeZoneView = UIView()
    private let closeIconView = UIImageView()
    private var layoutSize = CGSize()
    private var safeInsets = UIEdgeInsets()
    private var dragStartCenter = CGPoint()
    private var isOverCloseZone = false
    private var isClosing = false
    private var peerDisposable: Disposable?

    private let bubbleSize: CGFloat = 78.0
    private let edgeMargin: CGFloat = 10.0

    init(context: AccountContext, peerId: EnginePeer.Id, peer: EnginePeer?, theme: PresentationTheme, snapshot: UIView?, sourceFrame: CGRect, navigationController: NavigationController?) {
        self.context = context
        self.peerId = peerId
        self.peer = peer
        self.theme = theme
        self.snapshot = snapshot
        self.sourceFrame = sourceFrame
        self.chatNavigationController = navigationController
        super.init(navigationBarPresentationData: nil)
        self.statusBar.statusBarStyle = .Ignore
    }

    required init(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        self.peerDisposable?.dispose()
    }

    override func loadDisplayNode() {
        self.displayNode = ChatFloatingPassthroughNode()
        self.displayNodeDidLoad()
    }

    override func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        self.layoutSize = layout.size
        self.safeInsets = layout.safeInsets
        self.safeInsets.top = max(self.safeInsets.top, layout.statusBarHeight ?? 0.0)

        if self.bubbleView == nil {
            self.setupBubble()
        }
    }

    private func setupBubble() {
        let bubble = ChatFloatingBubbleView(size: self.bubbleSize, context: self.context, theme: self.theme)
        bubble.setPeer(self.peer)
        if self.peer == nil {
            self.peerDisposable = (self.context.engine.data.get(TelegramEngine.EngineData.Item.Peer.Peer(id: self.peerId))
            |> deliverOnMainQueue).startStrict(next: { [weak self] peer in
                guard let self, let peer else {
                    return
                }
                self.peer = peer
                self.bubbleView?.setPeer(peer)
            })
        }

        let finalCenter = CGPoint(x: self.layoutSize.width - self.edgeMargin - self.bubbleSize / 2.0, y: self.layoutSize.height * 0.32)
        bubble.center = finalCenter

        let pan = UIPanGestureRecognizer(target: self, action: #selector(self.bubblePan(_:)))
        bubble.addGestureRecognizer(pan)
        let tap = UITapGestureRecognizer(target: self, action: #selector(self.bubbleTap))
        bubble.addGestureRecognizer(tap)

        // Close zone at the bottom, visible while dragging.
        let closeSize: CGFloat = 64.0
        self.closeZoneView.frame = CGRect(x: (self.layoutSize.width - closeSize) / 2.0, y: self.layoutSize.height - self.safeInsets.bottom - 40.0 - closeSize, width: closeSize, height: closeSize)
        self.closeZoneView.backgroundColor = UIColor(white: 0.1, alpha: 0.55)
        self.closeZoneView.layer.cornerRadius = closeSize / 2.0
        self.closeZoneView.alpha = 0.0
        self.closeIconView.image = UIImage(systemName: "xmark", withConfiguration: UIImage.SymbolConfiguration(pointSize: 22.0, weight: .bold))
        self.closeIconView.tintColor = .white
        self.closeIconView.frame = self.closeZoneView.bounds
        self.closeIconView.contentMode = .center
        self.closeZoneView.addSubview(self.closeIconView)
        self.displayNode.view.addSubview(self.closeZoneView)

        self.displayNode.view.addSubview(bubble)
        self.bubbleView = bubble

        // The chat shrinks into the bubble.
        if let snapshot = self.snapshot {
            self.snapshot = nil
            snapshot.frame = self.sourceFrame
            snapshot.layer.cornerRadius = 40.0
            snapshot.layer.cornerCurve = .continuous
            snapshot.clipsToBounds = true
            self.displayNode.view.insertSubview(snapshot, belowSubview: bubble)
            UIView.animate(withDuration: 0.5, delay: 0.0, usingSpringWithDamping: 0.88, initialSpringVelocity: 0.0, options: [], animations: {
                snapshot.frame = CGRect(x: finalCenter.x - self.bubbleSize / 2.0, y: finalCenter.y - self.bubbleSize / 2.0, width: self.bubbleSize, height: self.bubbleSize)
                snapshot.layer.cornerRadius = self.bubbleSize * 0.44
            }, completion: { _ in
                snapshot.removeFromSuperview()
            })
            UIView.animate(withDuration: 0.25, delay: 0.25, options: [], animations: {
                snapshot.alpha = 0.0
            }, completion: nil)
        }
        bubble.alpha = 0.0
        bubble.transform = CGAffineTransform(scaleX: 0.3, y: 0.3).rotated(by: -0.4)
        UIView.animate(withDuration: 0.18, delay: 0.22, options: [], animations: {
            bubble.alpha = 1.0
        }, completion: nil)
        UIView.animate(withDuration: 0.8, delay: 0.22, usingSpringWithDamping: 0.48, initialSpringVelocity: 0.6, options: [.allowUserInteraction], animations: {
            bubble.transform = .identity
        }, completion: { _ in
            bubble.startIdleAnimation()
        })
        bubble.animateAvatarIn(delay: 0.38)
    }

    @objc private func bubblePan(_ recognizer: UIPanGestureRecognizer) {
        guard let bubble = self.bubbleView, !self.isClosing else {
            return
        }
        switch recognizer.state {
        case .began:
            self.dragStartCenter = bubble.center
            bubble.stopIdleAnimation()
            UIView.animate(withDuration: 0.2, animations: {
                bubble.transform = CGAffineTransform(scaleX: 1.08, y: 1.08)
                self.closeZoneView.alpha = 1.0
            })
        case .changed:
            let translation = recognizer.translation(in: self.displayNode.view)
            var center = CGPoint(x: self.dragStartCenter.x + translation.x, y: self.dragStartCenter.y + translation.y)
            let closeCenter = self.closeZoneView.center
            let distance = hypot(center.x - closeCenter.x, center.y - closeCenter.y)
            let overClose = distance < 90.0
            if overClose {
                // Snap into the close zone like a magnet.
                center = closeCenter
            }
            if overClose != self.isOverCloseZone {
                self.isOverCloseZone = overClose
                UISelectionFeedbackGenerator().selectionChanged()
                UIView.animate(withDuration: 0.25, delay: 0.0, usingSpringWithDamping: 0.6, initialSpringVelocity: 0.0, options: [.beginFromCurrentState], animations: {
                    self.closeZoneView.transform = overClose ? CGAffineTransform(scaleX: 1.25, y: 1.25) : .identity
                }, completion: nil)
            }
            // Jelly squash in the direction of movement.
            let velocity = recognizer.velocity(in: self.displayNode.view)
            let stretch = min(0.12, hypot(velocity.x, velocity.y) / 12000.0)
            let horizontal = abs(velocity.x) > abs(velocity.y)
            let scaleX = 1.08 + (horizontal ? stretch : -stretch)
            let scaleY = 1.08 + (horizontal ? -stretch : stretch)
            let tilt = max(-0.25, min(0.25, velocity.x / 4000.0))
            bubble.center = center
            bubble.transform = CGAffineTransform(rotationAngle: tilt).scaledBy(x: scaleX, y: scaleY)
        case .ended, .cancelled:
            UIView.animate(withDuration: 0.2, animations: {
                self.closeZoneView.alpha = 0.0
                self.closeZoneView.transform = .identity
            })
            if self.isOverCloseZone {
                self.isOverCloseZone = false
                self.close()
                return
            }
            let velocity = recognizer.velocity(in: self.displayNode.view)
            let projectedX = bubble.center.x + velocity.x * 0.15
            let minX = self.edgeMargin + self.bubbleSize / 2.0
            let maxX = self.layoutSize.width - self.edgeMargin - self.bubbleSize / 2.0
            let targetX = projectedX < self.layoutSize.width / 2.0 ? minX : maxX
            let minY = self.safeInsets.top + self.bubbleSize / 2.0 + 8.0
            let maxY = self.layoutSize.height - self.safeInsets.bottom - self.bubbleSize / 2.0 - 90.0
            let targetY = min(max(bubble.center.y + velocity.y * 0.15, minY), maxY)
            UIView.animate(withDuration: 0.7, delay: 0.0, usingSpringWithDamping: 0.58, initialSpringVelocity: min(2.0, hypot(velocity.x, velocity.y) / 1500.0), options: [.allowUserInteraction], animations: {
                bubble.center = CGPoint(x: targetX, y: targetY)
                bubble.transform = .identity
            }, completion: { _ in
                bubble.startIdleAnimation()
            })
            bubble.wobble()
        default:
            break
        }
    }

    @objc private func bubbleTap() {
        guard let bubble = self.bubbleView, !self.isClosing else {
            return
        }
        guard let peer = self.peer, let navigationController = self.chatNavigationController else {
            bubble.wobble()
            return
        }
        self.isClosing = true
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        bubble.stopIdleAnimation()
        let context = self.context
        // The bubble swells first, then the chat opens out of it.
        UIView.animate(withDuration: 0.16, delay: 0.0, options: [.curveEaseOut], animations: {
            bubble.transform = CGAffineTransform(scaleX: 1.25, y: 1.25)
        }, completion: { _ in
            context.sharedContext.navigateToChatController(NavigateToChatControllerParams(navigationController: navigationController, context: context, chatLocation: .peer(peer)))
            UIView.animate(withDuration: 0.32, delay: 0.0, options: [.curveEaseIn], animations: {
                bubble.transform = CGAffineTransform(scaleX: 3.0, y: 3.0)
                bubble.alpha = 0.0
            }, completion: { [weak self] _ in
                self?.dismiss(completion: nil)
            })
        })
    }

    private func close() {
        guard let bubble = self.bubbleView, !self.isClosing else {
            return
        }
        self.isClosing = true
        UIImpactFeedbackGenerator(style: .rigid).impactOccurred()
        bubble.stopIdleAnimation()
        UIView.animate(withDuration: 0.3, delay: 0.0, options: [.curveEaseIn], animations: {
            bubble.transform = CGAffineTransform(scaleX: 0.1, y: 0.1)
            bubble.alpha = 0.0
        }, completion: { [weak self] _ in
            self?.dismiss(completion: nil)
        })
    }
}

private final class ChatFloatingPassthroughNode: ASDisplayNode {
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        let result = super.hitTest(point, with: event)
        if result === self.view {
            return nil
        }
        return result
    }
}

/// A purple liquid-glass bubble — an oval with stretched corners — with the avatar inside.
final class ChatFloatingBubbleView: UIView {
    private let context: AccountContext
    private let theme: PresentationTheme
    private let glassView: UIVisualEffectView
    private let tintLayer = CAGradientLayer()
    private let rimLayer = CAShapeLayer()
    private let avatarContainer = UIView()
    private let avatarNode: AvatarNode
    private let highlightLayer = CAGradientLayer()

    private static let purple = UIColor(red: 0.55, green: 0.32, blue: 0.98, alpha: 1.0)

    init(size: CGFloat, context: AccountContext, theme: PresentationTheme) {
        self.context = context
        self.theme = theme
        self.avatarNode = AvatarNode(font: avatarPlaceholderFont(size: 22.0))

        var isGlass = false
        if #available(iOS 26.0, *) {
            let glass = UIGlassEffect()
            glass.tintColor = ChatFloatingBubbleView.purple.withAlphaComponent(0.55)
            self.glassView = UIVisualEffectView(effect: glass)
            isGlass = true
        } else {
            self.glassView = UIVisualEffectView(effect: UIBlurEffect(style: .systemUltraThinMaterial))
        }

        super.init(frame: CGRect(x: 0.0, y: 0.0, width: size, height: size))

        let bounds = self.bounds
        // Big continuous corners turn the square into an oval with stretched corners.
        let cornerRadius = size * 0.44
        let shape = UIBezierPath(roundedRect: bounds, cornerRadius: cornerRadius)

        self.layer.shadowColor = ChatFloatingBubbleView.purple.cgColor
        self.layer.shadowOpacity = 0.5
        self.layer.shadowRadius = 16.0
        self.layer.shadowOffset = CGSize(width: 0.0, height: 8.0)
        self.layer.shadowPath = shape.cgPath

        self.glassView.frame = bounds
        self.glassView.layer.cornerRadius = cornerRadius
        self.glassView.layer.cornerCurve = .continuous
        self.glassView.isUserInteractionEnabled = false
        if !isGlass {
            self.glassView.clipsToBounds = true
        }
        self.addSubview(self.glassView)

        if !isGlass {
            // Below iOS 26: a purple tint over the blur imitates the colored glass.
            self.tintLayer.frame = bounds
            self.tintLayer.cornerRadius = cornerRadius
            self.tintLayer.cornerCurve = .continuous
            self.tintLayer.colors = [
                UIColor(red: 0.72, green: 0.55, blue: 1.0, alpha: 0.75).cgColor,
                UIColor(red: 0.45, green: 0.22, blue: 0.92, alpha: 0.85).cgColor,
            ]
            self.tintLayer.startPoint = CGPoint(x: 0.2, y: 0.0)
            self.tintLayer.endPoint = CGPoint(x: 0.8, y: 1.0)
            self.layer.addSublayer(self.tintLayer)

            self.rimLayer.path = UIBezierPath(roundedRect: bounds.insetBy(dx: 1.0, dy: 1.0), cornerRadius: cornerRadius - 1.0).cgPath
            self.rimLayer.fillColor = UIColor.clear.cgColor
            self.rimLayer.strokeColor = UIColor.white.withAlphaComponent(0.5).cgColor
            self.rimLayer.lineWidth = 1.5
            self.layer.addSublayer(self.rimLayer)
        }

        let inset: CGFloat = 9.0
        let avatarSize = size - inset * 2.0
        self.avatarContainer.frame = CGRect(x: inset, y: inset, width: avatarSize, height: avatarSize)
        self.avatarContainer.layer.cornerRadius = avatarSize / 2.0
        self.avatarContainer.clipsToBounds = true
        self.avatarContainer.isUserInteractionEnabled = false
        self.avatarNode.frame = self.avatarContainer.bounds
        self.avatarContainer.addSubview(self.avatarNode.view)
        self.addSubview(self.avatarContainer)

        // A soft specular highlight over the glass.
        self.highlightLayer.type = .radial
        self.highlightLayer.frame = CGRect(x: size * 0.1, y: size * 0.04, width: size * 0.58, height: size * 0.3)
        self.highlightLayer.colors = [UIColor.white.withAlphaComponent(0.55).cgColor, UIColor.white.withAlphaComponent(0.0).cgColor]
        self.highlightLayer.startPoint = CGPoint(x: 0.5, y: 0.5)
        self.highlightLayer.endPoint = CGPoint(x: 1.0, y: 1.0)
        self.layer.addSublayer(self.highlightLayer)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func setPeer(_ peer: EnginePeer?) {
        guard let peer else {
            return
        }
        self.avatarNode.setPeer(
            accountPeerId: self.context.account.peerId,
            postbox: self.context.account.postbox,
            network: self.context.account.network,
            contentSettings: self.context.currentContentSettings.with { $0 },
            theme: self.theme,
            peer: peer,
            synchronousLoad: true,
            displayDimensions: self.avatarContainer.bounds.size
        )
    }

    /// The avatar surfaces a moment after the glass.
    func animateAvatarIn(delay: Double) {
        self.avatarContainer.transform = CGAffineTransform(scaleX: 0.4, y: 0.4)
        self.avatarContainer.alpha = 0.0
        UIView.animate(withDuration: 0.6, delay: delay, usingSpringWithDamping: 0.55, initialSpringVelocity: 0.0, options: [.allowUserInteraction], animations: {
            self.avatarContainer.transform = .identity
            self.avatarContainer.alpha = 1.0
        }, completion: nil)
    }

    func startIdleAnimation() {
        let breathe = CABasicAnimation(keyPath: "transform.scale")
        breathe.fromValue = 1.0
        breathe.toValue = 1.04
        breathe.duration = 1.8
        breathe.autoreverses = true
        breathe.repeatCount = .infinity
        breathe.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        self.avatarContainer.layer.add(breathe, forKey: "breathe")
    }

    func stopIdleAnimation() {
        self.avatarContainer.layer.removeAnimation(forKey: "breathe")
    }

    func wobble() {
        let wobble = CAKeyframeAnimation(keyPath: "transform")
        wobble.values = [
            NSValue(caTransform3D: CATransform3DIdentity),
            NSValue(caTransform3D: CATransform3DMakeScale(1.18, 0.86, 1.0)),
            NSValue(caTransform3D: CATransform3DMakeScale(0.9, 1.1, 1.0)),
            NSValue(caTransform3D: CATransform3DMakeScale(1.06, 0.95, 1.0)),
            NSValue(caTransform3D: CATransform3DMakeScale(0.98, 1.02, 1.0)),
            NSValue(caTransform3D: CATransform3DIdentity),
        ]
        wobble.keyTimes = [0.0, 0.2, 0.42, 0.62, 0.82, 1.0]
        wobble.duration = 0.7
        self.layer.add(wobble, forKey: "wobble")
    }
}
'''

open(root + "/submodules/TelegramUI/Sources/ChatFloatingBubble.swift", "w", encoding="utf-8").write(SWIFT)
print("floating_chat: installed")
