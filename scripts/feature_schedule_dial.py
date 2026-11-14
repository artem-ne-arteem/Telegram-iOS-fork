"""Feature: Schedule Dial.

Long-press Send: a glass half-circle dial appears above the send button. The long hand
picks the hour, the short hand the minutes, the bell on top toggles a silent send.
Tapping the clock button schedules the message with Telegram's own scheduled messages."""
import sys

root = sys.argv[1]
path = root + "/submodules/TelegramUI/Sources/Chat/ChatMessageDisplaySendMessageOptions.swift"
source = open(path, encoding="utf-8").read()

old = "func chatMessageDisplaySendMessageOptions(selfController: ChatControllerImpl, node: ASDisplayNode, gesture: ContextGesture) {\n"
new = """func chatMessageDisplaySendMessageOptions(selfController: ChatControllerImpl, node: ASDisplayNode, gesture: ContextGesture) {
    // Schedule Dial: a new message is scheduled from a dial instead of the options menu.
    if selfController.presentationInterfaceState.interfaceState.editMessage == nil, selfController.presentationInterfaceState.subject != .scheduledMessages, selfController.chatLocation.peerId != nil {
        gesture.cancel()
        presentChatScheduleDial(selfController: selfController, sendButton: node)
        return
    }
    chatMessageDisplayDefaultSendMessageOptions(selfController: selfController, node: node, gesture: gesture)
}

private func chatMessageDisplayDefaultSendMessageOptions(selfController: ChatControllerImpl, node: ASDisplayNode, gesture: ContextGesture) {
"""
if source.count(old) != 1:
    sys.exit("schedule_dial: entry point not found")
source = source.replace(old, new, 1)

source += r'''

// MARK: - Schedule Dial

private func presentChatScheduleDial(selfController: ChatControllerImpl, sendButton: ASDisplayNode) {
    guard let window = selfController.view.window else {
        return
    }
    let sendButtonFrame = sendButton.view.convert(sendButton.view.bounds, to: window)
    let theme = selfController.presentationData.theme
    let dial = ChatScheduleDialView(
        frame: window.bounds,
        sendButtonFrame: sendButtonFrame,
        accentColor: theme.list.itemAccentColor,
        primaryColor: theme.list.itemPrimaryTextColor,
        isDark: theme.overallDarkAppearance
    )
    dial.onSchedule = { [weak selfController] timestamp, silent in
        guard let selfController else {
            return
        }
        selfController.chatDisplayNode.sendCurrentMessage(silentPosting: silent, scheduleTime: timestamp, completion: { [weak selfController] in
            guard let selfController else {
                return
            }
            selfController.updateChatPresentationInterfaceState(animated: true, interactive: false, saveInterfaceState: true, {
                $0.updatedInterfaceState { $0.withUpdatedReplyMessageSubject(nil).withUpdatedSendMessageEffect(nil).withUpdatedPostSuggestionState(nil).withUpdatedForwardMessageIds(nil).withUpdatedForwardOptionsState(nil).withUpdatedComposeInputState(ChatTextInputState(inputText: NSAttributedString(string: ""))) }
            })
        })
    }
    window.addSubview(dial)
    dial.animateIn()
}

/// A half-circle dial above the send button: the long hand is the hour, the short hand
/// the minutes, the bell on top switches between a normal and a silent send.
private final class ChatScheduleDialView: UIView {
    private enum Hand {
        case hour
        case minute
    }

    var onSchedule: ((Int32, Bool) -> Void)?

    private let accentColor: UIColor
    private let primaryColor: UIColor
    private let sendButtonFrame: CGRect
    private let radius: CGFloat = 150.0
    private let hourHandLength: CGFloat = 118.0
    private let minuteHandLength: CGFloat = 82.0
    private let pivot: CGPoint

    private let dimView = UIView()
    private let contentView = UIView()
    private let panelView: UIVisualEffectView
    private let ticksLayer = CAShapeLayer()
    private let hourHand = UIView()
    private let minuteHand = UIView()
    private let hubView = UIView()
    private let timeLabel = UILabel()
    private let dayLabel = UILabel()
    private let bellBackground: UIVisualEffectView
    private let bellButton = UIButton(type: .system)
    private let confirmButton = UIButton(type: .system)
    private let selectionFeedback = UISelectionFeedbackGenerator()

    private var hour: Int
    private var minute: Int
    private var silent = false
    private var activeHand: Hand?
    private var isDismissing = false

    init(frame: CGRect, sendButtonFrame: CGRect, accentColor: UIColor, primaryColor: UIColor, isDark: Bool) {
        self.sendButtonFrame = sendButtonFrame
        self.accentColor = accentColor
        self.primaryColor = primaryColor

        let hubRadius: CGFloat = 38.0
        let pivotX = min(max(sendButtonFrame.midX, 150.0 + 12.0), frame.width - 150.0 - 12.0)
        self.pivot = CGPoint(x: pivotX, y: sendButtonFrame.minY - 14.0 - hubRadius)

        if #available(iOS 26.0, *) {
            self.panelView = UIVisualEffectView(effect: UIGlassEffect())
            self.bellBackground = UIVisualEffectView(effect: UIGlassEffect())
        } else {
            self.panelView = UIVisualEffectView(effect: UIBlurEffect(style: isDark ? .systemThickMaterialDark : .systemThickMaterialLight))
            self.bellBackground = UIVisualEffectView(effect: UIBlurEffect(style: isDark ? .systemThickMaterialDark : .systemThickMaterialLight))
        }

        // Start one hour from now, rounded to five minutes.
        let start = Date().addingTimeInterval(3600.0)
        let calendar = Calendar.current
        self.hour = calendar.component(.hour, from: start)
        self.minute = (calendar.component(.minute, from: start) / 5) * 5

        super.init(frame: frame)

        self.dimView.frame = self.bounds
        self.dimView.backgroundColor = UIColor(white: 0.0, alpha: 0.25)
        self.dimView.alpha = 0.0
        self.addSubview(self.dimView)

        self.contentView.frame = self.bounds
        self.addSubview(self.contentView)

        // Glass half-circle.
        let radius = self.radius
        self.panelView.frame = CGRect(x: self.pivot.x - radius, y: self.pivot.y - radius, width: radius * 2.0, height: radius)
        let panelShape = CAShapeLayer()
        panelShape.path = UIBezierPath(arcCenter: CGPoint(x: radius, y: radius), radius: radius, startAngle: CGFloat.pi, endAngle: 0.0, clockwise: true).cgPath
        self.panelView.layer.mask = panelShape
        self.contentView.addSubview(self.panelView)

        // Hour ticks and labels along the arc.
        let ticksPath = UIBezierPath()
        for index in 0 ... 23 {
            let angle = self.angle(forHour: index)
            let isMajor = index % 6 == 0 || index == 23
            let outer = self.point(angle: angle, distance: radius - 6.0)
            let inner = self.point(angle: angle, distance: radius - (isMajor ? 18.0 : 12.0))
            ticksPath.move(to: inner)
            ticksPath.addLine(to: outer)
            if isMajor {
                let label = UILabel()
                label.text = "\(index)"
                label.font = UIFont.systemFont(ofSize: 12.0, weight: .semibold)
                label.textColor = primaryColor.withAlphaComponent(0.6)
                label.sizeToFit()
                label.center = self.point(angle: angle, distance: radius - 32.0)
                self.contentView.addSubview(label)
            }
        }
        self.ticksLayer.path = ticksPath.cgPath
        self.ticksLayer.strokeColor = primaryColor.withAlphaComponent(0.35).cgColor
        self.ticksLayer.lineWidth = 2.0
        self.ticksLayer.lineCap = .round
        self.contentView.layer.addSublayer(self.ticksLayer)

        // Hands: the long one is the hour, the short one the minutes.
        self.setupHand(self.hourHand, length: self.hourHandLength, width: 7.0, color: accentColor)
        self.setupHand(self.minuteHand, length: self.minuteHandLength, width: 5.0, color: primaryColor.withAlphaComponent(0.75))

        // Hub with the selected time.
        self.hubView.frame = CGRect(x: self.pivot.x - hubRadius, y: self.pivot.y - hubRadius, width: hubRadius * 2.0, height: hubRadius * 2.0)
        self.hubView.backgroundColor = accentColor
        self.hubView.layer.cornerRadius = hubRadius
        self.contentView.addSubview(self.hubView)

        self.timeLabel.font = UIFont.monospacedDigitSystemFont(ofSize: 19.0, weight: .bold)
        self.timeLabel.textColor = .white
        self.timeLabel.textAlignment = .center
        self.timeLabel.frame = CGRect(x: 0.0, y: 17.0, width: hubRadius * 2.0, height: 24.0)
        self.hubView.addSubview(self.timeLabel)

        self.dayLabel.font = UIFont.systemFont(ofSize: 11.0, weight: .medium)
        self.dayLabel.textColor = UIColor.white.withAlphaComponent(0.85)
        self.dayLabel.textAlignment = .center
        self.dayLabel.frame = CGRect(x: 4.0, y: 41.0, width: hubRadius * 2.0 - 8.0, height: 15.0)
        self.dayLabel.adjustsFontSizeToFitWidth = true
        self.hubView.addSubview(self.dayLabel)

        // Bell on top of the arc.
        let bellSize: CGFloat = 46.0
        self.bellBackground.frame = CGRect(x: self.pivot.x - bellSize / 2.0, y: self.pivot.y - radius - bellSize / 2.0, width: bellSize, height: bellSize)
        self.bellBackground.layer.cornerRadius = bellSize / 2.0
        self.bellBackground.clipsToBounds = true
        self.contentView.addSubview(self.bellBackground)
        self.bellButton.frame = self.bellBackground.frame
        self.bellButton.addTarget(self, action: #selector(self.bellPressed), for: .touchUpInside)
        self.contentView.addSubview(self.bellButton)

        // The send button turns into a "schedule" button.
        self.confirmButton.frame = sendButtonFrame.insetBy(dx: -4.0, dy: -4.0)
        self.confirmButton.backgroundColor = accentColor
        self.confirmButton.layer.cornerRadius = self.confirmButton.frame.height / 2.0
        self.confirmButton.tintColor = .white
        self.confirmButton.setImage(UIImage(systemName: "clock.fill", withConfiguration: UIImage.SymbolConfiguration(pointSize: 18.0, weight: .semibold)), for: .normal)
        self.confirmButton.addTarget(self, action: #selector(self.confirmPressed), for: .touchUpInside)
        self.contentView.addSubview(self.confirmButton)

        self.updateBell()
        self.updateHands(animated: false)
        self.selectionFeedback.prepare()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func setupHand(_ hand: UIView, length: CGFloat, width: CGFloat, color: UIColor) {
        hand.backgroundColor = color
        hand.layer.cornerRadius = width / 2.0
        hand.layer.anchorPoint = CGPoint(x: 0.5, y: 1.0)
        hand.bounds = CGRect(x: 0.0, y: 0.0, width: width, height: length)
        hand.center = self.pivot
        self.contentView.addSubview(hand)
    }

    // Angles are measured from the right (0) to the left (pi) over the top.
    private func angle(forHour hour: Int) -> CGFloat {
        return CGFloat.pi - CGFloat(hour) / 23.0 * CGFloat.pi
    }

    private func angle(forMinute minute: Int) -> CGFloat {
        return CGFloat.pi - CGFloat(minute) / 55.0 * CGFloat.pi
    }

    private func point(angle: CGFloat, distance: CGFloat) -> CGPoint {
        return CGPoint(x: self.pivot.x + cos(angle) * distance, y: self.pivot.y - sin(angle) * distance)
    }

    private func targetDate() -> Date {
        let calendar = Calendar.current
        let now = Date()
        var date = calendar.date(bySettingHour: self.hour, minute: self.minute, second: 0, of: now) ?? now
        if date.timeIntervalSince(now) < 60.0 {
            date = calendar.date(byAdding: .day, value: 1, to: date) ?? date
        }
        return date
    }

    private func updateHands(animated: Bool) {
        let apply = {
            self.hourHand.transform = CGAffineTransform(rotationAngle: CGFloat.pi / 2.0 - self.angle(forHour: self.hour))
            self.minuteHand.transform = CGAffineTransform(rotationAngle: CGFloat.pi / 2.0 - self.angle(forMinute: self.minute))
        }
        if animated {
            UIView.animate(withDuration: 0.25, delay: 0.0, usingSpringWithDamping: 0.7, initialSpringVelocity: 0.0, options: [.beginFromCurrentState, .allowUserInteraction], animations: apply, completion: nil)
        } else {
            apply()
        }

        self.timeLabel.text = String(format: "%02d:%02d", self.hour, self.minute)
        let formatter = DateFormatter()
        formatter.doesRelativeDateFormatting = true
        formatter.dateStyle = .medium
        formatter.timeStyle = .none
        self.dayLabel.text = formatter.string(from: self.targetDate())
    }

    private func updateBell() {
        let name = self.silent ? "bell.slash.fill" : "bell.fill"
        self.bellButton.setImage(UIImage(systemName: name, withConfiguration: UIImage.SymbolConfiguration(pointSize: 18.0, weight: .semibold)), for: .normal)
        self.bellButton.tintColor = self.silent ? self.primaryColor.withAlphaComponent(0.55) : self.accentColor
    }

    @objc private func bellPressed() {
        self.silent = !self.silent
        self.updateBell()
        self.selectionFeedback.selectionChanged()
        self.bellButton.transform = CGAffineTransform(scaleX: 0.8, y: 0.8)
        UIView.animate(withDuration: 0.35, delay: 0.0, usingSpringWithDamping: 0.5, initialSpringVelocity: 0.0, options: [], animations: {
            self.bellButton.transform = .identity
        }, completion: nil)
    }

    @objc private func confirmPressed() {
        let timestamp = Int32(self.targetDate().timeIntervalSince1970)
        let silent = self.silent
        let onSchedule = self.onSchedule
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        self.dismiss(completion: {
            onSchedule?(timestamp, silent)
        })
    }

    // MARK: Dragging the hands

    private func handleTouch(at location: CGPoint, began: Bool) {
        let dx = location.x - self.pivot.x
        let dy = self.pivot.y - location.y
        var angle = atan2(max(dy, 0.0), dx)
        angle = min(max(angle, 0.0), CGFloat.pi)
        let fraction = (CGFloat.pi - angle) / CGFloat.pi

        if began {
            let distance = sqrt(dx * dx + dy * dy)
            self.activeHand = distance > (self.hourHandLength + self.minuteHandLength) / 2.0 ? .hour : .minute
        }
        guard let activeHand = self.activeHand else {
            return
        }
        switch activeHand {
        case .hour:
            let value = Int((fraction * 23.0).rounded())
            if value != self.hour {
                self.hour = value
                self.selectionFeedback.selectionChanged()
                self.updateHands(animated: true)
            }
        case .minute:
            let value = Int((fraction * 11.0).rounded()) * 5
            if value != self.minute {
                self.minute = value
                self.selectionFeedback.selectionChanged()
                self.updateHands(animated: true)
            }
        }
    }

    private func isOnDial(_ location: CGPoint) -> Bool {
        let dx = location.x - self.pivot.x
        let dy = location.y - self.pivot.y
        return sqrt(dx * dx + dy * dy) <= self.radius + 16.0 && location.y <= self.pivot.y + 40.0
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let location = touches.first?.location(in: self) else {
            return
        }
        if self.isOnDial(location) {
            self.handleTouch(at: location, began: true)
        } else {
            self.activeHand = nil
            self.dismiss(completion: {})
        }
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let location = touches.first?.location(in: self) else {
            return
        }
        self.handleTouch(at: location, began: false)
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        self.activeHand = nil
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        self.activeHand = nil
    }

    // MARK: Appearance

    private var collapsedTransform: CGAffineTransform {
        return CGAffineTransform(translationX: self.sendButtonFrame.midX - self.pivot.x, y: self.sendButtonFrame.midY - self.pivot.y).scaledBy(x: 0.2, y: 0.2)
    }

    func animateIn() {
        self.contentView.transform = self.collapsedTransform
        self.contentView.alpha = 0.0
        self.hourHand.transform = CGAffineTransform(rotationAngle: -CGFloat.pi / 2.0)
        self.minuteHand.transform = CGAffineTransform(rotationAngle: -CGFloat.pi / 2.0)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()

        UIView.animate(withDuration: 0.2, animations: {
            self.dimView.alpha = 1.0
            self.contentView.alpha = 1.0
        })
        UIView.animate(withDuration: 0.5, delay: 0.0, usingSpringWithDamping: 0.75, initialSpringVelocity: 0.0, options: [], animations: {
            self.contentView.transform = .identity
        }, completion: nil)
        UIView.animate(withDuration: 0.7, delay: 0.1, usingSpringWithDamping: 0.6, initialSpringVelocity: 0.0, options: [], animations: {
            self.hourHand.transform = CGAffineTransform(rotationAngle: CGFloat.pi / 2.0 - self.angle(forHour: self.hour))
            self.minuteHand.transform = CGAffineTransform(rotationAngle: CGFloat.pi / 2.0 - self.angle(forMinute: self.minute))
        }, completion: nil)
    }

    private func dismiss(completion: @escaping () -> Void) {
        if self.isDismissing {
            return
        }
        self.isDismissing = true
        self.isUserInteractionEnabled = false
        UIView.animate(withDuration: 0.25, delay: 0.0, options: [.curveEaseIn], animations: {
            self.contentView.transform = self.collapsedTransform
            self.contentView.alpha = 0.0
            self.dimView.alpha = 0.0
        }, completion: { _ in
            self.removeFromSuperview()
            completion()
        })
    }
}
'''

open(path, "w", encoding="utf-8").write(source)
print("schedule_dial: send options patched")
