"""Feature: Live Edits.

1. Text morph on edit: when a message is edited, removed words melt away, kept words glide
   to their new places, new words grow in, and the changes stay highlighted for a moment.
2. Swipe up to edit: drag your own message up and release; it lifts and pours into the input
   field, ready for editing."""
import os
import sys

root = sys.argv[1]


def patch(path, old, new, name):
    full = os.path.join(root, path)
    source = open(full, encoding="utf-8").read()
    if source.count(old) != 1:
        sys.exit("live_edits: anchor not unique/found: " + name + " (" + str(source.count(old)) + ")")
    source = source.replace(old, new, 1)
    open(full, "w", encoding="utf-8").write(source)


def write(path, content):
    full = os.path.join(root, path)
    open(full, "w", encoding="utf-8").write(content)


# ---------------------------------------------------------------------------
# 1. Text morph
# ---------------------------------------------------------------------------

TEXT_NODE = "submodules/TelegramUI/Components/Chat/ChatMessageTextBubbleContentNode/Sources/ChatMessageTextBubbleContentNode.swift"

patch(TEXT_NODE,
      "                            let _ = textApply(InteractiveTextNodeWithEntities.Arguments(\n",
      "                            let liveEditsMorph = LiveEditsMorph.prepare(previousMessage: previousItem?.message, message: item.message, textNode: strongSelf.textNode.textNode, isDraft: hasDraft || hadDraft)\n"
      "                            let _ = textApply(InteractiveTextNodeWithEntities.Arguments(\n",
      "text apply")

patch(TEXT_NODE,
      "                            animation.animator.updateBounds(layer: strongSelf.textNode.textNode.layer, bounds: CGRect(origin: CGPoint(), size: realTextFrame.size), completion: nil)\n",
      "                            animation.animator.updateBounds(layer: strongSelf.textNode.textNode.layer, bounds: CGRect(origin: CGPoint(), size: realTextFrame.size), completion: nil)\n"
      "                            liveEditsMorph?.run(textNode: strongSelf.textNode.textNode, newFrame: realTextFrame, highlightColor: messageTheme.accentTextColor)\n",
      "text frame")

write("submodules/TelegramUI/Components/Chat/ChatMessageTextBubbleContentNode/Sources/LiveEditsMorph.swift", r'''import Foundation
import UIKit
import Display
import TelegramCore
import InteractiveTextComponent

/// Live Edits: animates a message's text from its previous version to the edited one.
/// The old rendering is cut into word fragments that melt away (removed words) or glide
/// to their new place (kept words); new words grow in through a mask on the real text,
/// and get a short marker highlight.
final class LiveEditsMorph {
    private struct Word {
        let text: String
        let range: NSRange
    }

    private let oldWords: [Word]
    private let oldRects: [[CGRect]]
    private let oldImage: CGImage
    private let oldSize: CGSize
    private let oldFrame: CGRect

    private init(oldWords: [Word], oldRects: [[CGRect]], oldImage: CGImage, oldSize: CGSize, oldFrame: CGRect) {
        self.oldWords = oldWords
        self.oldRects = oldRects
        self.oldImage = oldImage
        self.oldSize = oldSize
        self.oldFrame = oldFrame
    }

    private static func editDate(_ message: EngineRawMessage) -> Int32? {
        for attribute in message.attributes {
            if let attribute = attribute as? EditedMessageAttribute {
                return attribute.date
            }
        }
        return nil
    }

    private static func words(in string: String) -> [Word] {
        let nsString = string as NSString
        var result: [Word] = []
        var start: Int?
        let length = nsString.length
        var index = 0
        while index < length {
            let character = nsString.character(at: index)
            let isSpace = character == 0x20 || character == 0x0A || character == 0x09 || character == 0x0D || character == 0xA0
            if isSpace {
                if let startValue = start {
                    let range = NSRange(location: startValue, length: index - startValue)
                    result.append(Word(text: nsString.substring(with: range), range: range))
                    start = nil
                }
            } else if start == nil {
                start = index
            }
            index += 1
        }
        if let startValue = start, startValue < length {
            let range = NSRange(location: startValue, length: length - startValue)
            result.append(Word(text: nsString.substring(with: range), range: range))
        }
        return result
    }

    private static func rects(for words: [Word], textNode: InteractiveTextNode) -> [[CGRect]] {
        return words.map { word in
            return textNode.rangeRects(in: word.range)?.rects.filter { $0.width > 0.5 && $0.height > 0.5 } ?? []
        }
    }

    static func prepare(previousMessage: EngineRawMessage?, message: EngineRawMessage, textNode: InteractiveTextNode, isDraft: Bool) -> LiveEditsMorph? {
        guard !isDraft, let previousMessage, previousMessage.id == message.id else {
            return nil
        }
        guard let newEditDate = editDate(message), newEditDate != editDate(previousMessage) else {
            return nil
        }
        guard previousMessage.text != message.text, textNode.view.window != nil else {
            return nil
        }
        guard let oldString = textNode.cachedLayout?.attributedString?.string, !oldString.isEmpty else {
            return nil
        }
        let size = textNode.bounds.size
        guard size.width > 1.0, size.height > 1.0, size.height < 1600.0 else {
            return nil
        }
        let oldWords = words(in: oldString)
        guard !oldWords.isEmpty, oldWords.count < 400 else {
            return nil
        }
        let format = UIGraphicsImageRendererFormat()
        format.opaque = false
        let image = UIGraphicsImageRenderer(size: size, format: format).image { context in
            textNode.layer.render(in: context.cgContext)
        }
        guard let cgImage = image.cgImage else {
            return nil
        }
        return LiveEditsMorph(oldWords: oldWords, oldRects: rects(for: oldWords, textNode: textNode), oldImage: cgImage, oldSize: size, oldFrame: textNode.frame)
    }

    /// Longest common subsequence of words: pairs (oldIndex, newIndex) of words that stay.
    private static func matches(_ old: [Word], _ new: [Word]) -> [(Int, Int)] {
        let n = old.count
        let m = new.count
        if n == 0 || m == 0 {
            return []
        }
        var table = Array(repeating: Array(repeating: 0, count: m + 1), count: n + 1)
        for i in stride(from: n - 1, through: 0, by: -1) {
            for j in stride(from: m - 1, through: 0, by: -1) {
                if old[i].text == new[j].text {
                    table[i][j] = table[i + 1][j + 1] + 1
                } else {
                    table[i][j] = max(table[i + 1][j], table[i][j + 1])
                }
            }
        }
        var result: [(Int, Int)] = []
        var i = 0
        var j = 0
        while i < n && j < m {
            if old[i].text == new[j].text {
                result.append((i, j))
                i += 1
                j += 1
            } else if table[i + 1][j] >= table[i][j + 1] {
                i += 1
            } else {
                j += 1
            }
        }
        return result
    }

    private func fragment(rect: CGRect, scale: CGFloat) -> CALayer {
        let padded = rect.insetBy(dx: -1.5, dy: -2.0).intersection(CGRect(origin: CGPoint(), size: self.oldSize))
        let layer = CALayer()
        layer.contents = self.oldImage
        layer.contentsScale = scale
        layer.contentsRect = CGRect(
            x: padded.minX / self.oldSize.width,
            y: padded.minY / self.oldSize.height,
            width: padded.width / self.oldSize.width,
            height: padded.height / self.oldSize.height
        )
        layer.frame = padded
        return layer
    }

    func run(textNode: InteractiveTextNode, newFrame: CGRect, highlightColor: UIColor) {
        guard let container = textNode.view.superview else {
            return
        }
        guard let newString = textNode.cachedLayout?.attributedString?.string else {
            return
        }
        let newWords = LiveEditsMorph.words(in: newString)
        guard newWords.count < 400 else {
            return
        }
        let newRects = LiveEditsMorph.rects(for: newWords, textNode: textNode)
        let pairs = LiveEditsMorph.matches(self.oldWords, newWords)
        var keptOld = Set<Int>()
        var keptNew = Set<Int>()
        for (i, j) in pairs {
            keptOld.insert(i)
            keptNew.insert(j)
        }

        // Clean up a morph that is still running on this node.
        for sublayer in container.layer.sublayers ?? [] where sublayer.name == "LiveEditsMorph" {
            sublayer.removeFromSuperlayer()
        }
        textNode.layer.mask = nil

        let scale = UIScreenScale
        let spring = CASpringAnimation(keyPath: "position")
        let springDuration = 0.55

        // Overlay in the container, aligned with the new text frame.
        let overlay = CALayer()
        overlay.name = "LiveEditsMorph"
        overlay.frame = newFrame
        container.layer.insertSublayer(overlay, above: textNode.layer)
        let oldOffset = CGPoint(x: self.oldFrame.minX - newFrame.minX, y: self.oldFrame.minY - newFrame.minY)

        // Kept words glide from their old place to the new one.
        for (i, j) in pairs {
            let fromRects = self.oldRects[i]
            let toRects = newRects[j]
            guard !fromRects.isEmpty else {
                continue
            }
            for (k, fromRect) in fromRects.enumerated() {
                let layer = self.fragment(rect: fromRect, scale: scale)
                let fromPosition = CGPoint(x: layer.position.x + oldOffset.x, y: layer.position.y + oldOffset.y)
                var toPosition = fromPosition
                if k < toRects.count {
                    let toRect = toRects[k]
                    toPosition = CGPoint(x: fromPosition.x - oldOffset.x + (toRect.minX - fromRect.minX), y: fromPosition.y - oldOffset.y + (toRect.minY - fromRect.minY))
                }
                layer.position = toPosition
                overlay.addSublayer(layer)
                let animation = spring.copy() as! CASpringAnimation
                animation.fromValue = NSValue(cgPoint: fromPosition)
                animation.toValue = NSValue(cgPoint: toPosition)
                animation.damping = 18.0
                animation.stiffness = 170.0
                animation.mass = 1.0
                animation.duration = springDuration
                layer.add(animation, forKey: "position")
            }
        }

        // Removed words melt: shrink, drift up and fade.
        for (i, fromRects) in self.oldRects.enumerated() where !keptOld.contains(i) {
            for fromRect in fromRects {
                let layer = self.fragment(rect: fromRect, scale: scale)
                layer.position = CGPoint(x: layer.position.x + oldOffset.x, y: layer.position.y + oldOffset.y)
                overlay.addSublayer(layer)
                layer.opacity = 0.0
                layer.transform = CATransform3DConcat(CATransform3DMakeScale(0.35, 0.35, 1.0), CATransform3DMakeTranslation(0.0, -8.0, 0.0))
                let group = CAAnimationGroup()
                let fade = CABasicAnimation(keyPath: "opacity")
                fade.fromValue = 1.0
                fade.toValue = 0.0
                let shrink = CABasicAnimation(keyPath: "transform")
                shrink.fromValue = NSValue(caTransform3D: CATransform3DIdentity)
                shrink.toValue = NSValue(caTransform3D: layer.transform)
                group.animations = [fade, shrink]
                group.duration = 0.32
                group.timingFunction = CAMediaTimingFunction(name: .easeIn)
                layer.add(group, forKey: "melt")
            }
        }

        // The real (new) text is masked: kept words stay hidden while their fragments fly,
        // new words grow in from their centers.
        let mask = CALayer()
        mask.frame = CGRect(origin: CGPoint(), size: newFrame.size)
        var addedRects: [CGRect] = []
        for (j, rects) in newRects.enumerated() where !keptNew.contains(j) {
            for rect in rects {
                let padded = rect.insetBy(dx: -2.0, dy: -3.0)
                addedRects.append(rect)
                let piece = CALayer()
                piece.backgroundColor = UIColor.white.cgColor
                piece.frame = padded
                mask.addSublayer(piece)
                let grow = CASpringAnimation(keyPath: "transform.scale")
                grow.fromValue = 0.05
                grow.toValue = 1.0
                grow.damping = 12.0
                grow.stiffness = 220.0
                grow.duration = 0.6
                grow.beginTime = CACurrentMediaTime() + 0.14
                grow.fillMode = .backwards
                piece.add(grow, forKey: "grow")
                let appear = CABasicAnimation(keyPath: "opacity")
                appear.fromValue = 0.0
                appear.toValue = 1.0
                appear.duration = 0.25
                appear.beginTime = CACurrentMediaTime() + 0.14
                appear.fillMode = .backwards
                piece.add(appear, forKey: "appear")
            }
        }
        textNode.layer.mask = mask

        // New words also grow (scale) visually: the text inside the revealed area is scaled by
        // the mask reveal, so add a soft marker behind them that stays for a moment.
        let marker = CALayer()
        marker.name = "LiveEditsMorph"
        marker.frame = newFrame
        container.layer.insertSublayer(marker, below: textNode.layer)
        for rect in addedRects {
            let piece = CALayer()
            piece.backgroundColor = highlightColor.withAlphaComponent(0.22).cgColor
            piece.cornerRadius = 4.0
            piece.frame = rect.insetBy(dx: -2.0, dy: 0.5)
            marker.addSublayer(piece)
        }
        marker.opacity = 0.0
        let markerIn = CABasicAnimation(keyPath: "opacity")
        markerIn.fromValue = 0.0
        markerIn.toValue = 1.0
        markerIn.duration = 0.3
        markerIn.beginTime = CACurrentMediaTime() + 0.3
        markerIn.fillMode = .both
        markerIn.isRemovedOnCompletion = false
        marker.add(markerIn, forKey: "in")

        DispatchQueue.main.asyncAfter(deadline: .now() + springDuration) { [weak textNode, weak overlay] in
            if let textNode, textNode.layer.mask === mask {
                textNode.layer.mask = nil
            }
            overlay?.removeFromSuperlayer()
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) { [weak marker] in
            guard let marker else {
                return
            }
            marker.removeAnimation(forKey: "in")
            marker.opacity = 0.0
            let fade = CABasicAnimation(keyPath: "opacity")
            fade.fromValue = 1.0
            fade.toValue = 0.0
            fade.duration = 0.6
            marker.add(fade, forKey: "out")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak marker] in
                marker?.removeFromSuperlayer()
            }
        }
    }
}
''')

# ---------------------------------------------------------------------------
# 2. Swipe up to edit (bubble side)
# ---------------------------------------------------------------------------

BUBBLE = "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"

patch(BUBBLE,
      "        let replyRecognizer = ChatSwipeToReplyRecognizer(target: self, action: #selector(self.swipeToReplyGesture(_:)))\n",
      """        let liveEditsRecognizer = LiveEditsSwipeUpRecognizer(target: self, action: #selector(self.liveEditsSwipeUpGesture(_:)))
        liveEditsRecognizer.canBegin = { [weak self] in
            return self?.liveEditsCanSwipeUp() ?? false
        }
        self.view.addGestureRecognizer(liveEditsRecognizer)

        let replyRecognizer = ChatSwipeToReplyRecognizer(target: self, action: #selector(self.swipeToReplyGesture(_:)))
""",
      "bubble recognizer")

patch(BUBBLE,
      "    private var playedSwipeToReplyHaptic = false\n",
      """    private var liveEditsIndicator: LiveEditsSwipeIndicatorView?
    private var liveEditsFeedback: HapticFeedback?
    private var liveEditsPlayedHaptic = false

    private func liveEditsCanSwipeUp() -> Bool {
        guard let item = self.item, self.selectionNode == nil else {
            return false
        }
        if item.content.effectivelyIncoming(item.context.account.peerId, associatedData: item.associatedData) {
            return false
        }
        if item.message.id.namespace != Namespaces.Message.Cloud {
            return false
        }
        if !item.controllerInteraction.canEditMessageRichText(item.message) {
            return false
        }
        // Only at the bottom of the chat, where pulling up would not scroll anything anyway.
        var current: ASDisplayNode? = self.supernode
        while let node = current {
            if let listView = node as? ListView {
                if case let .known(offset) = listView.visibleContentOffset(), offset < 40.0 {
                    return true
                }
                return false
            }
            current = node.supernode
        }
        return false
    }

    @objc private func liveEditsSwipeUpGesture(_ recognizer: UIPanGestureRecognizer) {
        let threshold: CGFloat = 64.0
        let raw = max(0.0, -recognizer.translation(in: self.view).y)
        let banded: CGFloat
        if raw < threshold {
            banded = raw
        } else {
            banded = threshold + (1.0 - 1.0 / ((raw - threshold) * 0.4 / 100.0 + 1.0)) * 100.0
        }
        switch recognizer.state {
        case .began:
            self.liveEditsPlayedHaptic = false
            self.liveEditsFeedback = HapticFeedback()
            self.liveEditsFeedback?.prepareImpact()
            self.item?.controllerInteraction.cancelInteractiveKeyboardGestures()
            if self.liveEditsIndicator == nil, let item = self.item {
                let indicator = LiveEditsSwipeIndicatorView(
                    fillColor: selectDateFillStaticColor(theme: item.presentationData.theme.theme, wallpaper: item.presentationData.theme.wallpaper),
                    foregroundColor: bubbleVariableColor(variableColor: item.presentationData.theme.theme.chat.message.shareButtonForegroundColor, wallpaper: item.presentationData.theme.wallpaper)
                )
                let bubbleFrame = self.backgroundNode.frame
                indicator.center = CGPoint(x: bubbleFrame.minX - 26.0, y: bubbleFrame.maxY - 18.0)
                self.view.addSubview(indicator)
                self.liveEditsIndicator = indicator
            }
        case .changed:
            var bounds = self.bounds
            bounds.origin.y = banded
            self.bounds = bounds
            var shadowBounds = self.shadowNode.bounds
            shadowBounds.origin.y = banded
            self.shadowNode.bounds = shadowBounds
            let progress = min(1.0, raw / threshold)
            if let indicator = self.liveEditsIndicator {
                indicator.update(progress: progress)
                // Keep the pencil near where the bubble was, so it is revealed under it.
                indicator.transform = CGAffineTransform(translationX: 0.0, y: banded * 0.6)
            }
            if progress >= 1.0 && !self.liveEditsPlayedHaptic {
                self.liveEditsPlayedHaptic = true
                self.liveEditsFeedback?.impact(.medium)
            }
        case .ended, .cancelled:
            self.liveEditsFeedback = nil
            let triggered = recognizer.state == .ended && raw >= threshold
            if triggered, let item = self.item {
                let bubbleFrame = self.backgroundNode.frame
                if let window = self.view.window, let snapshot = self.view.resizableSnapshotView(from: bubbleFrame.offsetBy(dx: 0.0, dy: 0.0), afterScreenUpdates: false, withCapInsets: .zero) {
                    let rect = self.view.convert(bubbleFrame, to: window)
                    NotificationCenter.default.post(name: Notification.Name("TGLiveEditsSwipeUp"), object: nil, userInfo: [
                        "messageId": item.message.id,
                        "snapshot": snapshot,
                        "rect": NSValue(cgRect: rect)
                    ])
                }
                // Leave a ghost of the bubble behind while it pours into the field.
                self.layer.opacity = 0.35
                self.layer.animateAlpha(from: 0.0, to: 0.35, duration: 0.15)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { [weak self] in
                    guard let self else {
                        return
                    }
                    self.layer.opacity = 1.0
                    self.layer.animateAlpha(from: 0.35, to: 1.0, duration: 0.35)
                }
            }
            var bounds = self.bounds
            let previousBounds = bounds
            bounds.origin.y = 0.0
            self.bounds = bounds
            var shadowBounds = self.shadowNode.bounds
            let previousShadowBounds = shadowBounds
            shadowBounds.origin.y = 0.0
            self.shadowNode.bounds = shadowBounds
            self.layer.animateBounds(from: previousBounds, to: bounds, duration: triggered ? 0.2 : 0.35, timingFunction: kCAMediaTimingFunctionSpring)
            self.shadowNode.layer.animateBounds(from: previousShadowBounds, to: shadowBounds, duration: triggered ? 0.2 : 0.35, timingFunction: kCAMediaTimingFunctionSpring)
            if let indicator = self.liveEditsIndicator {
                self.liveEditsIndicator = nil
                UIView.animate(withDuration: 0.25, animations: {
                    indicator.alpha = 0.0
                    indicator.transform = CGAffineTransform(scaleX: 0.3, y: 0.3)
                }, completion: { _ in
                    indicator.removeFromSuperview()
                })
            }
        default:
            break
        }
    }

    private var playedSwipeToReplyHaptic = false
""",
      "bubble handler")

write("submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/LiveEditsSwipeUp.swift", r'''import Foundation
import UIKit

/// Vertical pan that only begins on a clear upward drag; while it is deciding, the chat list's
/// scrolling waits for it, so it never fights with scrolling.
final class LiveEditsSwipeUpRecognizer: UIPanGestureRecognizer, UIGestureRecognizerDelegate {
    var canBegin: (() -> Bool)?

    override init(target: Any?, action: Selector?) {
        super.init(target: target, action: action)
        self.delegate = self
        self.maximumNumberOfTouches = 1
    }

    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        let velocity = self.velocity(in: self.view)
        guard velocity.y < -40.0, abs(velocity.y) > abs(velocity.x) * 1.6 else {
            return false
        }
        return self.canBegin?() ?? false
    }

    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldBeRequiredToFailBy otherGestureRecognizer: UIGestureRecognizer) -> Bool {
        return otherGestureRecognizer.view is UIScrollView
    }

    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
        return false
    }
}

/// The round pencil badge revealed under the bubble while it is pulled up.
final class LiveEditsSwipeIndicatorView: UIView {
    private let iconView = UIImageView()
    private let ringLayer = CAShapeLayer()

    init(fillColor: UIColor, foregroundColor: UIColor) {
        super.init(frame: CGRect(x: 0.0, y: 0.0, width: 34.0, height: 34.0))
        self.backgroundColor = fillColor
        self.layer.cornerRadius = 17.0
        self.isUserInteractionEnabled = false

        self.ringLayer.path = UIBezierPath(arcCenter: CGPoint(x: 17.0, y: 17.0), radius: 15.5, startAngle: -.pi / 2.0, endAngle: .pi * 1.5, clockwise: true).cgPath
        self.ringLayer.fillColor = UIColor.clear.cgColor
        self.ringLayer.strokeColor = foregroundColor.cgColor
        self.ringLayer.lineWidth = 1.5
        self.ringLayer.lineCap = .round
        self.ringLayer.strokeEnd = 0.0
        self.layer.addSublayer(self.ringLayer)

        let configuration = UIImage.SymbolConfiguration(pointSize: 15.0, weight: .semibold)
        self.iconView.image = UIImage(systemName: "pencil", withConfiguration: configuration)?.withRenderingMode(.alwaysTemplate)
        self.iconView.tintColor = foregroundColor
        self.iconView.contentMode = .center
        self.iconView.frame = self.bounds
        self.addSubview(self.iconView)

        self.update(progress: 0.0)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func update(progress: CGFloat) {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        self.ringLayer.strokeEnd = progress
        CATransaction.commit()
        let scale = 0.45 + 0.55 * progress
        self.iconView.transform = CGAffineTransform(scaleX: scale, y: scale).rotated(by: (1.0 - progress) * -0.6)
        self.alpha = min(1.0, progress * 1.6)
    }
}
''')

# ---------------------------------------------------------------------------
# 2b. Swipe up to edit (chat controller side)
# ---------------------------------------------------------------------------

patch("submodules/TelegramUI/Sources/ChatController.swift",
      "        self.loadDisplayNodeImpl()\n        self.galleryPresentationContext.view = self.view\n",
      "        self.loadDisplayNodeImpl()\n"
      "        NotificationCenter.default.addObserver(self, selector: #selector(self.liveEditsHandleSwipeUp(_:)), name: Notification.Name(\"TGLiveEditsSwipeUp\"), object: nil)\n"
      "        self.galleryPresentationContext.view = self.view\n",
      "controller observer")

write("submodules/TelegramUI/Sources/ChatLiveEdits.swift", r'''import Foundation
import UIKit
import Display
import TelegramCore

extension ChatControllerImpl {
    /// Live Edits: a bubble was swiped up. Start editing it and pour its snapshot into the field.
    @objc func liveEditsHandleSwipeUp(_ notification: Notification) {
        guard let info = notification.userInfo, let messageId = info["messageId"] as? EngineMessage.Id else {
            return
        }
        guard self.isNodeLoaded, let window = self.view.window else {
            return
        }
        guard self.chatDisplayNode.historyNode.messageInCurrentHistoryView(messageId) != nil else {
            return
        }
        self.interfaceInteraction?.setupEditMessage(messageId, { _ in })

        guard let snapshot = info["snapshot"] as? UIView, let rectValue = info["rect"] as? NSValue else {
            return
        }
        let sourceRect = rectValue.cgRectValue
        snapshot.frame = sourceRect
        snapshot.layer.cornerRadius = 18.0
        snapshot.clipsToBounds = true
        window.addSubview(snapshot)

        var targetRect = CGRect(x: 16.0, y: window.bounds.height - 90.0, width: window.bounds.width - 32.0, height: 40.0)
        if let panel = self.chatDisplayNode.textInputPanelNode, panel.view.window != nil {
            let panelRect = panel.view.convert(panel.bounds, to: window)
            targetRect = CGRect(x: panelRect.minX + 52.0, y: panelRect.minY + 6.0, width: max(80.0, panelRect.width - 104.0), height: max(36.0, min(panelRect.height - 12.0, sourceRect.height)))
        }

        // Pour: the bubble first squashes a little, then flows down and spreads into the field.
        UIView.animateKeyframes(withDuration: 0.55, delay: 0.0, options: [.calculationModeCubic], animations: {
            UIView.addKeyframe(withRelativeStartTime: 0.0, relativeDuration: 0.25) {
                snapshot.transform = CGAffineTransform(scaleX: 0.94, y: 1.06)
            }
            UIView.addKeyframe(withRelativeStartTime: 0.2, relativeDuration: 0.8) {
                snapshot.transform = .identity
                snapshot.frame = targetRect
                snapshot.layer.cornerRadius = targetRect.height / 2.0
            }
            UIView.addKeyframe(withRelativeStartTime: 0.6, relativeDuration: 0.4) {
                snapshot.alpha = 0.0
            }
        }, completion: { _ in
            snapshot.removeFromSuperview()
        })
    }
}
''')

print("live_edits: applied")
