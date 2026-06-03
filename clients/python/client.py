import asyncio
import json
import logging
import uuid
from enum import Enum
from typing import Callable, Dict, Optional, Set

import websockets

logger = logging.getLogger(__name__)


# ── State Machine ──────────────────────────────────────────────────────────────

class State(Enum):
    UNINITIALIZED = "UNINITIALIZED"
    DISCONNECTED  = "DISCONNECTED"
    CONNECTING    = "CONNECTING"
    CONNECTED     = "CONNECTED"


# ── Local Storage Models ───────────────────────────────────────────────────────

class OutboundEntry:
    """Single record for outbound_queue storage schema."""
    __slots__ = ("msg_id", "to", "body", "status", "created_at")

    def __init__(self, msg_id: str, to: str, body: str) -> None:
        from datetime import datetime, timezone
        self.msg_id: str     = msg_id
        self.to: str         = to
        self.body: str       = body
        self.status: str     = "QUEUED"
        self.created_at: str = datetime.now(timezone.utc).isoformat()


# ── MessagingClient ────────────────────────────────────────────────────────────

class MessagingClient:
    """
    Offline-first point-to-point messaging client.

    Wire format: JSON over WebSocket (ws://).
    State machine: UNINITIALIZED → DISCONNECTED → CONNECTING → CONNECTED.
    """

    def __init__(self, on_message: Callable[[str, str], None]) -> None:
        self._on_message = on_message

        # State machine
        self._state: State = State.UNINITIALIZED

        # Identity / connection
        self._username: Optional[str] = None
        self._ws_url: Optional[str]   = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None

        # Local storage
        self._outbound_queue: Dict[str, OutboundEntry] = {}  # primary_key: msg_id
        self._inbound_history: Set[str] = set()              # primary_key: msg_id

        # Auto-reconnect
        self._auto_reconnect: bool  = False
        self._reconnect_delay: float = 1.0

    # ── State Machine Transitions ──────────────────────────────────────────────

    def initialize(self, username: str, ws_url: str) -> None:
        """
        Event INITIALIZE (UNINITIALIZED → DISCONNECTED).
        Sets username and initialises local storage engines.
        Silently ignored if not in UNINITIALIZED state.
        """
        if self._state != State.UNINITIALIZED:
            return
        self._username        = username
        self._ws_url          = ws_url
        self._outbound_queue  = {}
        self._inbound_history = set()
        self._auto_reconnect  = True
        self._reconnect_delay = 1.0
        self._state           = State.DISCONNECTED
        logger.debug("State → DISCONNECTED")

    async def connect(self) -> None:
        """
        Event NETWORK_AVAILABLE (DISCONNECTED → CONNECTING → CONNECTED).
        Silently ignored if not in DISCONNECTED state.
        """
        if self._state != State.DISCONNECTED:
            return
        self._state = State.CONNECTING
        logger.debug("State → CONNECTING")

        try:
            ws = await websockets.connect(self._ws_url)
        except Exception as exc:
            logger.warning("Connection attempt failed: %s", exc)
            self._state = State.DISCONNECTED
            return

        self._ws = ws

        # Event SOCKET_OPEN (CONNECTING → CONNECTED)
        self._state           = State.CONNECTED
        self._reconnect_delay = 1.0
        logger.debug("State → CONNECTED")

        # Transmit 'connect' payload immediately
        await self._send_raw({"type": "connect", "username": self._username})

        # Reactive behavior: ON_CONNECTED
        await self._on_connected()

        # Start receive loop (detached)
        asyncio.ensure_future(self._recv_loop())

    async def disconnect(self) -> None:
        """Graceful shutdown; disables auto-reconnect."""
        self._auto_reconnect = False
        if self._ws is not None:
            await self._ws.close()
        self._ws    = None
        self._state = State.DISCONNECTED

    @property
    def state(self) -> State:
        return self._state

    # ── Reactive Behaviors ─────────────────────────────────────────────────────

    async def _on_connected(self) -> None:
        """
        ON_CONNECTED: Flush every entry in outbound_queue to the socket (FIFO).
        Steps:
          1. Scan outbound_queue for all entries.
          2. For each item: transmit raw 'send_msg' JSON frame to socket.
        """
        entries = sorted(self._outbound_queue.values(), key=lambda e: e.created_at)
        for entry in entries:
            await self._send_raw({
                "type":   "send_msg",
                "msg_id": entry.msg_id,
                "to":     entry.to,
                "body":   entry.body,
            })
            entry.status = "PENDING_RECEIPT"

    async def send_message(self, to: str, body: str) -> None:
        """
        ON_USER_ACTION_SEND: User hit send.
        Steps:
          1. Generate cryptographically secure v4 UUID as msg_id.
          2. Insert into outbound_queue with status = QUEUED.
          3. If CONNECTED: dispatch 'send_msg' frame immediately. Else: remain in queue.
        """
        msg_id = str(uuid.uuid4())
        entry  = OutboundEntry(msg_id, to, body)
        self._outbound_queue[msg_id] = entry

        if self._state == State.CONNECTED:
            await self._send_raw({
                "type":   "send_msg",
                "msg_id": msg_id,
                "to":     to,
                "body":   body,
            })
            entry.status = "PENDING_RECEIPT"

    async def _on_receive_receipt(self, frame: dict) -> None:
        """
        ON_RECEIVE_RECEIPT: Server confirmed delivery.
        Steps:
          1. Match receipt.msg_id against entries in outbound_queue.
          2. Delete the matched record from outbound_queue completely.
        """
        msg_id = frame.get("msg_id")
        if msg_id and msg_id in self._outbound_queue:
            del self._outbound_queue[msg_id]

    async def _on_receive_msg(self, frame: dict) -> None:
        """
        ON_RECEIVE_MSG: Server pushed an inbound message.
        Steps:
          1. Check inbound_history for pre-existing msg_id.
          2. If NOT present: write to inbound_history, dispatch to message handler.
          3. Always: send immediate raw 'ack' JSON frame back to server containing msg_id.
        """
        msg_id    = frame.get("msg_id")
        from_user = frame.get("from")
        body      = frame.get("body")

        if msg_id not in self._inbound_history:
            self._inbound_history.add(msg_id)
            self._on_message(from_user, body)

        # Always ack regardless of dedup result
        await self._send_raw({"type": "ack", "msg_id": msg_id})

    # ── Internal Helpers ───────────────────────────────────────────────────────

    async def _send_raw(self, frame: dict) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps(frame))
            except Exception as exc:
                logger.warning("Send failed: %s", exc)

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON frame; ignoring.")
                    continue
                frame_type = frame.get("type")
                if frame_type == "msg":
                    await self._on_receive_msg(frame)
                elif frame_type == "receipt":
                    await self._on_receive_receipt(frame)
        except Exception as exc:
            logger.warning("Receive loop ended: %s", exc)
        finally:
            # Event SOCKET_CLOSE (CONNECTED → DISCONNECTED)
            # Revert all PENDING_RECEIPT outbound messages back to QUEUED
            for entry in self._outbound_queue.values():
                if entry.status == "PENDING_RECEIPT":
                    entry.status = "QUEUED"

            if self._state in (State.CONNECTED, State.CONNECTING):
                self._state = State.DISCONNECTED
                logger.debug("State → DISCONNECTED")

            self._ws = None

            if self._auto_reconnect:
                asyncio.ensure_future(self._do_reconnect())

    async def _do_reconnect(self) -> None:
        while self._auto_reconnect and self._state == State.DISCONNECTED:
            logger.warning("Reconnecting in %.0fs…", self._reconnect_delay)
            await asyncio.sleep(self._reconnect_delay)
            if not self._auto_reconnect:
                break
            await self.connect()
            if self._state == State.CONNECTED:
                self._reconnect_delay = 1.0
                break
            self._reconnect_delay = min(self._reconnect_delay * 2, 30.0)


# ── Entry Point ────────────────────────────────────────────────────────────────

async def _main() -> None:
    import sys  # noqa: F401 – used implicitly by logging setup
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    loop     = asyncio.get_event_loop()
    username = (await loop.run_in_executor(None, input, "Chat as: ")).strip()

    def on_message(from_user: str, body: str) -> None:
        print(f"\n<- [{from_user}] {body}")
        print(f"{username}> ", end="", flush=True)

    client = MessagingClient(on_message=on_message)
    client.initialize(username, "ws://localhost:8765")
    await client.connect()

    print(f"Connected as '{username}'. Type '<recipient> <message>' or 'exit'/'quit' to quit.")

    while True:
        try:
            line = await loop.run_in_executor(None, input, f"{username}> ")
        except EOFError:
            break
        line = line.strip()
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            await client.disconnect()
            break
        parts = line.split(" ", 1)
        if len(parts) < 2:
            print("Usage: <recipient> <message>")
            continue
        recipient, message = parts[0], parts[1]
        await client.send_message(recipient, message)


if __name__ == "__main__":
    import sys  # noqa: F401
    asyncio.run(_main())
