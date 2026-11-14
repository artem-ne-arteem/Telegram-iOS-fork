# Telegram iOS fork — Reply from Preview & Swipe through Previews

Unofficial fork of [Telegram-iOS](https://github.com/TelegramMessenger/Telegram-iOS) (GPLv2) with two design concepts for the chat list long-press preview:

### 💬 Reply from Preview
Long-press a chat: between the chat preview and its context menu a separate full-width glass block appears with a message field (attach · text · mic/send). Type and send without opening the chat; the message shows up in the preview and the preview closes. Attach and mic open the full chat.

### 👀 Swipe through Previews
While the preview is open, swipe left/right to flip to the previews of neighbouring chats (up to two above and below in the list), or tap a chat name at the bottom. Each page has its own reply field.

## How it is built
- `.github/workflows/build.yml` clones the official source (newest version compatible with the runner's Xcode), applies the scripts below and builds an IPA.
- `scripts/feature_reply_from_preview.py` — both features (chat list, context menu, keyboard handling).
- `scripts/sideload_fixes.py` — lets a re-signed build start without the App Group entitlement.
- `scripts/refresh_profiles.py`, `scripts/checkout_compatible.py` — build infrastructure.
- Required repository secrets: `TG_API_ID`, `TG_API_HASH` (from my.telegram.org).
- The IPA uses fake codesigning; re-sign it (Sideloadly, ESign, …) to install.

Interactive SwiftUI prototype of the first concept: [ReplyFromPreview](https://github.com/artem-ne-arteem/ReplyFromPreview).
