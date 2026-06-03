import asyncio
import json
import logging
from collections import defaultdict

import websockets

# Setup clean logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("BridgeServer")

# --- In-Memory State ---
# Active connections: { username: WebSocketServerProtocol }
ACTIVE_CONNECTIONS = {}
# Offline message mailboxes: { username: [ {msg_id, from, body} ] }
OFFLINE_QUEUES = defaultdict(list)


async def send_frame(websocket, frame_dict):
    """Helper to safely send JSON frames to a client."""
    try:
        await websocket.send(json.dumps(frame_dict))
    except Exception as e:
        logger.error(f"Error sending frame: {e}")


async def flush_offline_messages(username, websocket):
    """Delivers all pending offline messages to a newly reconnected user."""
    if username in OFFLINE_QUEUES and OFFLINE_QUEUES[username]:
        pending_count = len(OFFLINE_QUEUES[username])
        logger.info(
            f"Flushing {pending_count} offline message(s) to '{username}'"
        )

        # Send all queued messages. Note: We do NOT delete them yet.
        # They are deleted only when the client sends back an 'ack' frame.
        for msg in list(OFFLINE_QUEUES[username]):
            await send_frame(
                websocket,
                {
                    "type": "msg",
                    "msg_id": msg["msg_id"],
                    "from": msg["from"],
                    "body": msg["body"],
                },
            )


async def handle_client(websocket):
    """Main client connection lifecycle handler."""
    authenticated_user = None
    logger.info("New raw connection established. Awaiting authentication...")

    try:
        async for message in websocket:
            try:
                frame = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("Received malformed non-JSON frame. Ignoring.")
                continue

            frame_type = frame.get("type")

            # 1. HANDLE CONNECT / LOGIN
            if frame_type == "connect":
                username = frame.get("username", "").strip()
                if not username:
                    continue

                authenticated_user = username
                ACTIVE_CONNECTIONS[username] = websocket
                logger.info(f"User '{username}' is now ONLINE.")

                # Immediately flush messages missed while offline
                await flush_offline_messages(username, websocket)

            # 2. HANDLE MESSAGE SENDING
            elif frame_type == "send_msg":
                if not authenticated_user:
                    logger.warning("Unauthenticated send_msg attempt.")
                    continue

                msg_id = frame.get("msg_id")
                recipient = frame.get("to")
                body = frame.get("body")

                logger.info(
                    f"Message from '{authenticated_user}' to '{recipient}': {body}"
                )

                # Construct the payload
                msg_payload = {
                    "msg_id": msg_id,
                    "from": authenticated_user,
                    "body": body,
                }

                # Send immediate receipt back to the sender so they can clear their offline queue
                await send_frame(websocket, {"type": "receipt", "msg_id": msg_id})

                # Route the message
                if (
                    recipient in ACTIVE_CONNECTIONS
                    and ACTIVE_CONNECTIONS[recipient]
                ):
                    # Recipient is online, send directly
                    recipient_ws = ACTIVE_CONNECTIONS[recipient]
                    await send_frame(
                        recipient_ws,
                        {
                            "type": "msg",
                            "msg_id": msg_id,
                            "from": authenticated_user,
                            "body": body,
                        },
                    )
                else:
                    # Recipient is offline, queue it up
                    logger.info(
                        f"Recipient '{recipient}' is OFFLINE. Queuing message."
                    )
                    OFFLINE_QUEUES[recipient].append(msg_payload)

            # 3. HANDLE CLIENT ACKNOWLEDGEMENTS
            elif frame_type == "ack":
                if not authenticated_user:
                    continue

                msg_id = frame.get("msg_id")
                # Remove message from the offline queue if it was delivered post-reconnection
                if authenticated_user in OFFLINE_QUEUES:
                    OFFLINE_QUEUES[authenticated_user] = [
                        m
                        for m in OFFLINE_QUEUES[authenticated_user]
                        if m["msg_id"] != msg_id
                    ]
                logger.info(
                    f"Message {msg_id} acknowledged by '{authenticated_user}' and cleared from server state."
                )

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Clean up connection state on disconnect
        if authenticated_user:
            logger.info(f"User '{authenticated_user}' went OFFLINE.")
            if ACTIVE_CONNECTIONS.get(authenticated_user) == websocket:
                del ACTIVE_CONNECTIONS[authenticated_user]


async def main():
    host = "localhost"
    port = 8765
    logger.info(f"Starting Bridge Server on ws://{host}:{port}")
    async with websockets.serve(handle_client, host, port):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user.")