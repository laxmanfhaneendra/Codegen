# MinimalMessagingProtocolSpec 1.0.0

## Overview

Cross-platform specification for robust offline-first point-to-point messaging.

## Installation

Requires **JDK 17+** and internet access to download the Gradle wrapper on first run.

```bash
# Unix
./gradlew build

# Windows
gradlew.bat build
```

## Quick Start

```bash
# Unix – run the CLI
./gradlew run --args="alice"

# Windows
gradlew.bat run --args="alice"
```

Once running, type commands at the prompt:

```
alice> @bob Hello, Bob!
alice> /status
alice> /quit
```

## State Machine

```
 ┌───────────────┐
 │ UNINITIALIZED │
 └──────┬────────┘
        │ INITIALIZE
        ▼
 ┌──────────────┐
 │ DISCONNECTED │◄──────────────────────┐
 └──────┬───────┘                       │
        │ NETWORK_AVAILABLE             │ SOCKET_CLOSE
        ▼                               │
 ┌────────────┐                  ┌──────┴───────┐
 │ CONNECTING │──SOCKET_OPEN────►│  CONNECTED   │
 └────────────┘                  └──────────────┘
```

| From          | Event             | Action                                                                   | To           |
|---------------|-------------------|--------------------------------------------------------------------------|--------------|
| UNINITIALIZED | INITIALIZE        | Set username, initialize local storage engines                           | DISCONNECTED |
| DISCONNECTED  | NETWORK_AVAILABLE | Initiate WebSocket connection attempt                                    | CONNECTING   |
| CONNECTING    | SOCKET_OPEN       | Transmit 'connect' payload immediately. Transition to live system state. | CONNECTED    |
| CONNECTED     | SOCKET_CLOSE      | Revert all PENDING_RECEIPT outbound messages back to QUEUED.             | DISCONNECTED |

## Message Protocol

### Client → Server

#### `connect`

Sent by client immediately upon establishing connection to authenticate identity.

| Field    | Type   | Required | Description                           |
|----------|--------|----------|---------------------------------------|
| type     | string | Yes      | Constant: `"connect"`                 |
| username | string | Yes      | Pattern: `^[a-zA-Z0-9_-]{1,32}$`     |

#### `send_msg`

Dispatched by client to transmit a text message to a specific peer.

| Field  | Type   | Required | Description                                                                 |
|--------|--------|----------|-----------------------------------------------------------------------------|
| type   | string | Yes      | Constant: `"send_msg"`                                                      |
| msg_id | string | Yes      | UUID v4. Client-generated unique ID for tracking lifecycle and deduplication. |
| to     | string | Yes      | Username of target recipient.                                               |
| body   | string | Yes      | Text payload content.                                                       |

#### `ack`

Sent by client confirming a message has been received. Authorizes server to purge it from its offline buffer.

| Field  | Type   | Required | Description           |
|--------|--------|----------|-----------------------|
| type   | string | Yes      | Constant: `"ack"`     |
| msg_id | string | Yes      | UUID v4.              |

### Server → Client

#### `msg`

Inbound message pushed by the server, either in real-time or as a flushed buffer entry.

| Field  | Type   | Required | Description           |
|--------|--------|----------|-----------------------|
| type   | string | Yes      | Constant: `"msg"`     |
| msg_id | string | Yes      | UUID v4.              |
| from   | string | Yes      | Sender username.      |
| body   | string | Yes      | Text payload content. |

#### `receipt`

Server confirmation acknowledging receipt of a sent message. Signals client to remove the entry from its local outbound queue.

| Field  | Type   | Required | Description             |
|--------|--------|----------|-------------------------|
| type   | string | Yes      | Constant: `"receipt"`   |
| msg_id | string | Yes      | UUID v4.                |

## Storage Schemas

### `outbound_queue`

Persistent transactional log for queuing messages while offline. Implemented as `ConcurrentHashMap<String, OutboundEntry>` keyed by `msg_id`.

| Field      | Type    | Primary Key | Notes                                              |
|------------|---------|-------------|----------------------------------------------------|
| msg_id     | string  | Yes         | Uniqueness enforced; UUID v4.                      |
| to         | string  | No          | Recipient username.                                |
| body       | string  | No          |                                                    |
| status     | string  | No          | Enum: `QUEUED` or `PENDING_RECEIPT`. Tracks delivery state. |
| created_at | string  | No          | ISO-8601 UTC (`Instant.now().toString()`). Used for FIFO ordering. |

### `inbound_history`

Idempotent-safe log to prevent duplicate rendering from network retries. Implemented as `Collections.newSetFromMap(ConcurrentHashMap())`.

| Field     | Type    | Primary Key | Notes                         |
|-----------|---------|-------------|-------------------------------|
| msg_id    | string  | Yes         | Uniqueness enforced; UUID v4. |
| from      | string  | No          | Sender username.              |
| body      | string  | No          |                               |
| timestamp | integer | No          | Unix epoch milliseconds.      |

## Reactive Behaviors

### ON_CONNECTED

Triggered automatically when shifting into CONNECTED state.

1. Scan outbound_queue for all entries.
2. For each item: transmit raw 'send_msg' JSON frame to socket.

### ON_USER_ACTION_SEND

Triggered when a user hits send in the interface.

1. Generate cryptographically secure v4 UUID as msg_id.
2. Insert into outbound_queue with status = QUEUED.
3. If state == CONNECTED: dispatch 'send_msg' frame immediately. Else: remain in queue.

### ON_RECEIVE_RECEIPT

Triggered when server responds with type: 'receipt'.

1. Match receipt.msg_id against entries in outbound_queue.
2. Delete the matched record from outbound_queue completely.

### ON_RECEIVE_MSG

Triggered when server pushes an inbound type: 'msg'.

1. Check inbound_history for pre-existing msg_id.
2. If NOT present: write to inbound_history, dispatch to message handler.
3. Always: send immediate raw 'ack' JSON frame back to server containing msg_id.
