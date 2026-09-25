# Project Rules & Guidelines

## 1. Do Not Output Raw Code Diffs in Chat
- **Never output raw git diff blocks (e.g., ````diff ... ```` with `+` and `-` lines) in chat messages.**
- The user reviews changes directly in the IDE's diff/preview interface.
- Provide clear, concise explanations of what changed along with clickable file links (e.g., `[filename](file:///path/to/file)`).

## 2. Code Review & Finalization
- Keep changes pending review so the user can inspect, accept, or reject each change individually in the IDE.
- Never declare a task finalized until the user has reviewed and accepted the changes.

## 3. No Static Data Usage
- Our application must not use hardcoded or static mock display data; all data must be dynamic from live services, tools, or SQLite.
