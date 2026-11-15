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
            // The chat follows the finger and starts shrinking towards a blob.
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
            closeTitle: self.presentationData.strings.Common_Close,
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

/// Presented at window level; lets every touch outside the blob through.
final class ChatFloatingBubbleController: ViewController {
    private let context: AccountContext
    private let peerId: EnginePeer.Id
    private var peer: EnginePeer?
    private let theme: PresentationTheme
    private let closeTitle: String
    private var snapshot: UIView?
    private let sourceFrame: CGRect
    private weak var chatNavigationController: NavigationController?

    private var bubbleView: ChatFloatingBubbleView?
    private let closeZoneView = UIView()
    private let closeIconView = UIImageView()
    private let closeOptionButton = UIButton(type: .system)
    private var layoutSize = CGSize()
    private var safeInsets = UIEdgeInsets()
    private var dragStartCenter = CGPoint()
    private var isOverCloseZone = false
    private var isClosing = false
    private var peerDisposable: Disposable?

    private let bubbleSize = CGSize(width: 104.0, height: 78.0)

    init(context: AccountContext, peerId: EnginePeer.Id, peer: EnginePeer?, theme: PresentationTheme, closeTitle: String, snapshot: UIView?, sourceFrame: CGRect, navigationController: NavigationController?) {
        self.context = context
        self.peerId = peerId
        self.peer = peer
        self.theme = theme
        self.closeTitle = closeTitle
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

    /// Bottom center, just above the tab bar.
    private var homeCenter: CGPoint {
        return CGPoint(x: self.layoutSize.width / 2.0, y: self.layoutSize.height - max(self.safeInsets.bottom, 20.0) - 78.0 - self.bubbleSize.height / 2.0)
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

        let finalCenter = self.homeCenter
        bubble.center = finalCenter

        let pan = UIPanGestureRecognizer(target: self, action: #selector(self.bubblePan(_:)))
        bubble.addGestureRecognizer(pan)
        let tap = UITapGestureRecognizer(target: self, action: #selector(self.bubbleTap))
        bubble.addGestureRecognizer(tap)
        let longPress = UILongPressGestureRecognizer(target: self, action: #selector(self.bubbleLongPress(_:)))
        longPress.minimumPressDuration = 0.4
        bubble.addGestureRecognizer(longPress)
        tap.require(toFail: longPress)

        // Close zone at the top while dragging.
        let closeSize: CGFloat = 64.0
        self.closeZoneView.frame = CGRect(x: (self.layoutSize.width - closeSize) / 2.0, y: self.safeInsets.top + 24.0, width: closeSize, height: closeSize)
        self.closeZoneView.backgroundColor = UIColor(white: 0.1, alpha: 0.55)
        self.closeZoneView.layer.cornerRadius = closeSize / 2.0
        self.closeZoneView.alpha = 0.0
        self.closeIconView.image = UIImage(systemName: "xmark", withConfiguration: UIImage.SymbolConfiguration(pointSize: 22.0, weight: .bold))
        self.closeIconView.tintColor = .white
        self.closeIconView.frame = self.closeZoneView.bounds
        self.closeIconView.contentMode = .center
        self.closeZoneView.addSubview(self.closeIconView)
        self.displayNode.view.addSubview(self.closeZoneView)

        // "Close" option shown on long press.
        self.closeOptionButton.setTitle("✕  " + self.closeTitle, for: .normal)
        self.closeOptionButton.titleLabel?.font = UIFont.systemFont(ofSize: 16.0, weight: .semibold)
        self.closeOptionButton.setTitleColor(.white, for: .normal)
        self.closeOptionButton.backgroundColor = UIColor(red: 0.35, green: 0.2, blue: 0.7, alpha: 0.92)
        self.closeOptionButton.sizeToFit()
        self.closeOptionButton.bounds = CGRect(x: 0.0, y: 0.0, width: self.closeOptionButton.bounds.width + 36.0, height: 42.0)
        self.closeOptionButton.layer.cornerRadius = 21.0
        self.closeOptionButton.alpha = 0.0
        self.closeOptionButton.isHidden = true
        self.closeOptionButton.addTarget(self, action: #selector(self.closeOptionPressed), for: .touchUpInside)
        self.displayNode.view.addSubview(self.closeOptionButton)

        self.displayNode.view.addSubview(bubble)
        self.bubbleView = bubble

        // The chat drips down into the blob.
        if let snapshot = self.snapshot {
            self.snapshot = nil
            snapshot.frame = self.sourceFrame
            snapshot.layer.cornerRadius = 40.0
            snapshot.layer.cornerCurve = .continuous
            snapshot.clipsToBounds = true
            self.displayNode.view.insertSubview(snapshot, belowSubview: bubble)
            UIView.animate(withDuration: 0.5, delay: 0.0, usingSpringWithDamping: 0.86, initialSpringVelocity: 0.0, options: [], animations: {
                snapshot.frame = CGRect(x: finalCenter.x - self.bubbleSize.width / 2.0, y: finalCenter.y - self.bubbleSize.height / 2.0, width: self.bubbleSize.width, height: self.bubbleSize.height)
                snapshot.layer.cornerRadius = self.bubbleSize.height / 2.0
            }, completion: { _ in
                snapshot.removeFromSuperview()
            })
            UIView.animate(withDuration: 0.25, delay: 0.22, options: [], animations: {
                snapshot.alpha = 0.0
            }, completion: nil)
        }
        bubble.alpha = 0.0
        bubble.transform = CGAffineTransform(scaleX: 1.6, y: 0.3)
        UIView.animate(withDuration: 0.15, delay: 0.22, options: [], animations: {
            bubble.alpha = 1.0
        }, completion: nil)
        UIView.animate(withDuration: 0.85, delay: 0.22, usingSpringWithDamping: 0.42, initialSpringVelocity: 0.5, options: [.allowUserInteraction], animations: {
            bubble.transform = .identity
        }, completion: nil)
        bubble.animateAvatarIn(delay: 0.36)
        bubble.startMorphing()
    }

    @objc private func bubblePan(_ recognizer: UIPanGestureRecognizer) {
        guard let bubble = self.bubbleView, !self.isClosing else {
            return
        }
        switch recognizer.state {
        case .began:
            self.hideCloseOption()
            self.dragStartCenter = bubble.center
            UIView.animate(withDuration: 0.2, animations: {
                self.closeZoneView.alpha = 1.0
            })
        case .changed:
            let translation = recognizer.translation(in: self.displayNode.view)
            var center = CGPoint(x: self.dragStartCenter.x + translation.x, y: self.dragStartCenter.y + translation.y)
            let closeCenter = self.closeZoneView.center
            let overClose = hypot(center.x - closeCenter.x, center.y - closeCenter.y) < 90.0
            if overClose {
                center = closeCenter
            }
            if overClose != self.isOverCloseZone {
                self.isOverCloseZone = overClose
                UISelectionFeedbackGenerator().selectionChanged()
                UIView.animate(withDuration: 0.25, delay: 0.0, usingSpringWithDamping: 0.6, initialSpringVelocity: 0.0, options: [.beginFromCurrentState], animations: {
                    self.closeZoneView.transform = overClose ? CGAffineTransform(scaleX: 1.25, y: 1.25) : .identity
                }, completion: nil)
            }
            // Stretchy blob: it elongates along the direction of movement and tilts into it.
            let velocity = recognizer.velocity(in: self.displayNode.view)
            let speed = hypot(velocity.x, velocity.y)
            let stretch = min(0.35, speed / 5000.0)
            let angle = speed > 1.0 ? atan2(velocity.y, velocity.x) : 0.0
            bubble.center = center
            bubble.transform = CGAffineTransform(rotationAngle: angle).scaledBy(x: 1.0 + stretch, y: 1.0 - stretch * 0.6).rotated(by: -angle)
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
            // Back home like on a rubber band.
            let velocity = recognizer.velocity(in: self.displayNode.view)
            UIView.animate(withDuration: 0.8, delay: 0.0, usingSpringWithDamping: 0.5, initialSpringVelocity: min(2.5, hypot(velocity.x, velocity.y) / 1200.0), options: [.allowUserInteraction], animations: {
                bubble.center = self.homeCenter
                bubble.transform = .identity
            }, completion: nil)
            bubble.wobble()
        default:
            break
        }
    }

    @objc private func bubbleLongPress(_ recognizer: UILongPressGestureRecognizer) {
        guard recognizer.state == .began, let bubble = self.bubbleView, !self.isClosing else {
            return
        }
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        bubble.wobble()
        let button = self.closeOptionButton
        button.center = CGPoint(x: bubble.center.x, y: bubble.frame.minY - 14.0 - button.bounds.height / 2.0)
        button.isHidden = false
        button.transform = CGAffineTransform(translationX: 0.0, y: 20.0).scaledBy(x: 0.4, y: 0.4)
        UIView.animate(withDuration: 0.45, delay: 0.0, usingSpringWithDamping: 0.62, initialSpringVelocity: 0.0, options: [.allowUserInteraction], animations: {
            button.alpha = 1.0
            button.transform = .identity
        }, completion: nil)
    }

    private func hideCloseOption() {
        let button = self.closeOptionButton
        if button.isHidden {
            return
        }
        UIView.animate(withDuration: 0.18, animations: {
            button.alpha = 0.0
            button.transform = CGAffineTransform(scaleX: 0.6, y: 0.6)
        }, completion: { _ in
            button.isHidden = true
        })
    }

    @objc private func closeOptionPressed() {
        self.hideCloseOption()
        self.close()
    }

    @objc private func bubbleTap() {
        guard let bubble = self.bubbleView, !self.isClosing else {
            return
        }
        if !self.closeOptionButton.isHidden {
            self.hideCloseOption()
            return
        }
        guard let peer = self.peer, let navigationController = self.chatNavigationController else {
            bubble.wobble()
            return
        }
        self.isClosing = true
        UIImpactFeedbackGenerator(style: .light).impactOccurred()

        // The blob splashes open into a full screen wave, and the chat appears out of it.
        let wave = UIView(frame: bubble.frame)
        wave.backgroundColor = UIColor(red: 0.42, green: 0.24, blue: 0.86, alpha: 1.0)
        wave.layer.cornerRadius = bubble.bounds.height / 2.0
        wave.layer.cornerCurve = .continuous
        wave.alpha = 0.0
        self.displayNode.view.insertSubview(wave, belowSubview: bubble)

        let context = self.context
        UIView.animate(withDuration: 0.14, delay: 0.0, options: [.curveEaseOut], animations: {
            bubble.transform = CGAffineTransform(scaleX: 1.25, y: 0.85)
        }, completion: { _ in
            UIView.animate(withDuration: 0.12, animations: {
                wave.alpha = 1.0
                bubble.alpha = 0.0
            })
            UIView.animate(withDuration: 0.42, delay: 0.0, usingSpringWithDamping: 0.85, initialSpringVelocity: 0.0, options: [], animations: {
                wave.frame = CGRect(origin: CGPoint(), size: self.layoutSize)
                wave.layer.cornerRadius = 44.0
            }, completion: { _ in
                context.sharedContext.navigateToChatController(NavigateToChatControllerParams(navigationController: navigationController, context: context, chatLocation: .peer(peer)))
                UIView.animate(withDuration: 0.35, delay: 0.1, options: [.curveEaseOut], animations: {
                    wave.alpha = 0.0
                    wave.transform = CGAffineTransform(scaleX: 1.05, y: 1.05)
                }, completion: { [weak self] _ in
                    self?.dismiss(completion: nil)
                })
            })
        })
    }

    private func close() {
        guard let bubble = self.bubbleView, !self.isClosing else {
            return
        }
        self.isClosing = true
        UIImpactFeedbackGenerator(style: .rigid).impactOccurred()
        UIView.animate(withDuration: 0.12, animations: {
            bubble.transform = CGAffineTransform(scaleX: 1.2, y: 1.2)
        }, completion: { _ in
            UIView.animate(withDuration: 0.25, delay: 0.0, options: [.curveEaseIn], animations: {
                bubble.transform = CGAffineTransform(scaleX: 0.05, y: 0.05)
                bubble.alpha = 0.0
            }, completion: { [weak self] _ in
                self?.dismiss(completion: nil)
            })
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

/// A purple glossy blob that slowly changes its outline, with the chat's avatar inside.
final class ChatFloatingBubbleView: UIView {
    private let context: AccountContext
    private let theme: PresentationTheme
    private let shadowLayer = CAShapeLayer()
    private let materialView = UIView()
    private let materialMask = CAShapeLayer()
    private let blurView = UIVisualEffectView(effect: UIBlurEffect(style: .systemUltraThinMaterialDark))
    private let tintLayer = CAGradientLayer()
    private let rimLayer = CAShapeLayer()
    private let highlightLayer = CAGradientLayer()
    private let avatarContainer = UIView()
    private let avatarNode: AvatarNode
    private var shapes: [CGPath] = []

    private static let purple = UIColor(red: 0.55, green: 0.32, blue: 0.98, alpha: 1.0)

    init(size: CGSize, context: AccountContext, theme: PresentationTheme) {
        self.context = context
        self.theme = theme
        self.avatarNode = AvatarNode(font: avatarPlaceholderFont(size: 20.0))
        super.init(frame: CGRect(origin: CGPoint(), size: size))

        let bounds = self.bounds
        self.shapes = [
            ChatFloatingBubbleView.blobPath(in: bounds, seed: 1),
            ChatFloatingBubbleView.blobPath(in: bounds, seed: 2),
            ChatFloatingBubbleView.blobPath(in: bounds, seed: 3),
            ChatFloatingBubbleView.blobPath(in: bounds, seed: 4),
        ]

        self.shadowLayer.path = self.shapes[0]
        self.shadowLayer.fillColor = ChatFloatingBubbleView.purple.withAlphaComponent(0.55).cgColor
        self.shadowLayer.shadowColor = ChatFloatingBubbleView.purple.cgColor
        self.shadowLayer.shadowOpacity = 0.8
        self.shadowLayer.shadowRadius = 16.0
        self.shadowLayer.shadowOffset = CGSize(width: 0.0, height: 8.0)
        self.layer.addSublayer(self.shadowLayer)

        // Glassy material: blur + purple gradient, cut to the blob outline.
        self.materialView.frame = bounds
        self.materialView.isUserInteractionEnabled = false
        self.blurView.frame = bounds
        self.materialView.addSubview(self.blurView)
        self.tintLayer.frame = bounds
        self.tintLayer.colors = [
            UIColor(red: 0.74, green: 0.56, blue: 1.0, alpha: 0.85).cgColor,
            UIColor(red: 0.52, green: 0.28, blue: 0.96, alpha: 0.82).cgColor,
            UIColor(red: 0.36, green: 0.16, blue: 0.82, alpha: 0.9).cgColor,
        ]
        self.tintLayer.startPoint = CGPoint(x: 0.15, y: 0.0)
        self.tintLayer.endPoint = CGPoint(x: 0.85, y: 1.0)
        self.materialView.layer.addSublayer(self.tintLayer)
        self.materialMask.path = self.shapes[0]
        self.materialView.layer.mask = self.materialMask
        self.addSubview(self.materialView)

        self.rimLayer.path = self.shapes[0]
        self.rimLayer.fillColor = UIColor.clear.cgColor
        self.rimLayer.strokeColor = UIColor.white.withAlphaComponent(0.55).cgColor
        self.rimLayer.lineWidth = 1.5
        self.layer.addSublayer(self.rimLayer)

        let avatarSize: CGFloat = size.height - 22.0
        self.avatarContainer.frame = CGRect(x: (size.width - avatarSize) / 2.0, y: (size.height - avatarSize) / 2.0, width: avatarSize, height: avatarSize)
        self.avatarContainer.layer.cornerRadius = avatarSize / 2.0
        self.avatarContainer.clipsToBounds = true
        self.avatarContainer.isUserInteractionEnabled = false
        self.avatarNode.frame = self.avatarContainer.bounds
        self.avatarContainer.addSubview(self.avatarNode.view)
        self.addSubview(self.avatarContainer)

        self.highlightLayer.type = .radial
        self.highlightLayer.frame = CGRect(x: size.width * 0.12, y: size.height * 0.04, width: size.width * 0.5, height: size.height * 0.34)
        self.highlightLayer.colors = [UIColor.white.withAlphaComponent(0.6).cgColor, UIColor.white.withAlphaComponent(0.0).cgColor]
        self.highlightLayer.startPoint = CGPoint(x: 0.5, y: 0.5)
        self.highlightLayer.endPoint = CGPoint(x: 1.0, y: 1.0)
        self.layer.addSublayer(self.highlightLayer)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    /// A smooth irregular closed outline around a stretched ellipse.
    private static func blobPath(in rect: CGRect, seed: Int) -> CGPath {
        let count = 9
        let center = CGPoint(x: rect.midX, y: rect.midY)
        let radiusX = rect.width / 2.0 - 4.0
        let radiusY = rect.height / 2.0 - 4.0
        var points: [CGPoint] = []
        for index in 0 ..< count {
            let angle = CGFloat(index) / CGFloat(count) * CGFloat.pi * 2.0
            let noise = sin(CGFloat(seed * 7 + index * 13) * 1.37) * 0.5 + sin(CGFloat(seed * 3 + index * 5) * 2.11) * 0.5
            let wobble = 1.0 + noise * 0.075
            points.append(CGPoint(x: center.x + cos(angle) * radiusX * wobble, y: center.y + sin(angle) * radiusY * wobble))
        }
        let path = UIBezierPath()
        path.move(to: points[0])
        for index in 0 ..< count {
            let p0 = points[(index - 1 + count) % count]
            let p1 = points[index]
            let p2 = points[(index + 1) % count]
            let p3 = points[(index + 2) % count]
            let control1 = CGPoint(x: p1.x + (p2.x - p0.x) / 6.0, y: p1.y + (p2.y - p0.y) / 6.0)
            let control2 = CGPoint(x: p2.x - (p3.x - p1.x) / 6.0, y: p2.y - (p3.y - p1.y) / 6.0)
            path.addCurve(to: p2, controlPoint1: control1, controlPoint2: control2)
        }
        path.close()
        return path.cgPath
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

    /// The outline slowly flows between several blob shapes.
    func startMorphing() {
        guard let first = self.shapes.first else {
            return
        }
        let morph = CAKeyframeAnimation(keyPath: "path")
        morph.values = self.shapes + [first]
        morph.duration = 6.0
        morph.repeatCount = .infinity
        morph.calculationMode = .cubic
        for layer in [self.materialMask, self.rimLayer, self.shadowLayer] as [CAShapeLayer] {
            layer.add(morph, forKey: "morph")
        }
    }

    /// The avatar surfaces a moment after the blob.
    func animateAvatarIn(delay: Double) {
        self.avatarContainer.transform = CGAffineTransform(scaleX: 0.4, y: 0.4)
        self.avatarContainer.alpha = 0.0
        UIView.animate(withDuration: 0.6, delay: delay, usingSpringWithDamping: 0.55, initialSpringVelocity: 0.0, options: [.allowUserInteraction], animations: {
            self.avatarContainer.transform = .identity
            self.avatarContainer.alpha = 1.0
        }, completion: nil)
    }

    func wobble() {
        let wobble = CAKeyframeAnimation(keyPath: "transform")
        wobble.values = [
            NSValue(caTransform3D: CATransform3DIdentity),
            NSValue(caTransform3D: CATransform3DMakeScale(1.22, 0.82, 1.0)),
            NSValue(caTransform3D: CATransform3DMakeScale(0.88, 1.12, 1.0)),
            NSValue(caTransform3D: CATransform3DMakeScale(1.08, 0.94, 1.0)),
            NSValue(caTransform3D: CATransform3DMakeScale(0.97, 1.03, 1.0)),
            NSValue(caTransform3D: CATransform3DIdentity),
        ]
        wobble.keyTimes = [0.0, 0.18, 0.4, 0.6, 0.8, 1.0]
        wobble.duration = 0.75
        self.layer.add(wobble, forKey: "wobble")
    }
}
'''

open(root + "/submodules/TelegramUI/Sources/ChatFloatingBubble.swift", "w", encoding="utf-8").write(SWIFT)
print("floating_chat: installed")
