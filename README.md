# Telegram iOS fork — Reply from Preview

Unofficial fork of [Telegram-iOS](https://github.com/TelegramMessenger/Telegram-iOS) (GPLv2) with a design concept:
reply to a chat right from its long-press preview, without opening it.

- The workflow clones the official source, applies `patches/*.patch` and builds an IPA.
- Required repository secrets: `TG_API_ID`, `TG_API_HASH` (from my.telegram.org).
- The IPA is signed with fake codesigning; re-sign it (e.g. Sideloadly) to install.

Interactive SwiftUI prototype of the same feature: [ReplyFromPreview](https://github.com/artem-ne-arteem/ReplyFromPreview).
