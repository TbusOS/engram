---
name: respond in the user's language
description: match the language of the user's last message
type: feedback
created: 2025-11-25
tags: [communication]
priority: high
---

用用户提问所用的语言回答 —— 中文提问就用中文回答,英文提问就用英文。

**Why:** code-switching on the assistant's side feels condescending
when the user was clearly fluent in the language they chose.

**How to apply:** detect the language of the most recent user turn,
not the conversation history average.
