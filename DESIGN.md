# Design Notes

## Core principle: spec as the source of truth

`Spec.json` defines the protocol completely — data models, state machine, storage schemas, reactive behaviors. The server and the generation harness are written by hand; the clients are derived from the spec by an agent.

This has a concrete consequence: **behavior questions are resolved by reading the spec, not the code.** If the Python client and the Kotlin client disagree on something, the spec decides who is wrong.

Adding or changing a feature means editing the spec, then running `/generate` or `/regen`. The clients are not the system — the spec is.

---

## Why spec-driven generation?

The conventional alternative is writing two clients by hand and keeping them in sync manually. That approach tends to diverge — different edge case handling, different reconnect behavior, different message ordering. The spec-driven approach enforces consistency at the source: both clients are produced from the same definitions, so their wire-level behavior is structurally identical.

The two-client setup is also a test of the spec itself. If Python and Kotlin clients can exchange messages through the server, the spec is constraining both implementations correctly. If they fail to interoperate, there is a gap in the spec — not a bug in either client.

---

## Protocol decisions

**Offline-first.** Messages are written to an outbound queue before being sent. If the connection drops while a message is in flight (`PENDING_RECEIPT`), it reverts to `QUEUED` on disconnect and is flushed automatically on reconnect. No message is lost because of a transient connection failure.

**Idempotent delivery.** Every message carries a client-generated UUID. The server issues a receipt when it relays a message; the client deletes the outbound entry on receipt. Inbound messages are deduplicated against `inbound_history` before being delivered to the handler — a re-delivered message is acked but not shown twice.

**State machine, not flags.** The client has four explicit states: `UNINITIALIZED → DISCONNECTED → CONNECTING → CONNECTED`. Transitions are guarded — an event that does not match the current state is a no-op. There are no boolean flags scattered across the class controlling behavior.

**Server is a router, not storage.** The server holds undelivered messages in memory and flushes them when the recipient connects. It is intentionally simple. Durability is a client responsibility, not the server's.

**Auto-reconnect with exponential backoff.** Both clients implement automatic reconnection (1s initial delay, doubles each attempt, capped at 30s, resets on success). This is specified in `generate.json → build_notes`, not in the spec, because it is an implementation detail of the CLI runner rather than part of the protocol.

---

## What the harness does not do

- It does not hard-code language-specific logic or file paths
- It reads all targets from `generate.json`, so adding a new target (e.g. a TypeScript client) requires only adding an entry to `generate.json`
- It does not modify `Spec.json`, `Server/server.py`, or its own harness files
- It does not guess at behavior — every decision in the generated code traces back to a field in the spec or a line in `build_notes`
