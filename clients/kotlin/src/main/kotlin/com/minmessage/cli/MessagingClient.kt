package com.minmessage.cli

import io.ktor.client.*
import io.ktor.client.engine.okhttp.*
import io.ktor.client.plugins.websocket.*
import io.ktor.websocket.*
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.time.Instant
import java.util.*
import java.util.concurrent.ConcurrentHashMap

// ── State Machine ──────────────────────────────────────────────────────────────

enum class State {
    UNINITIALIZED, DISCONNECTED, CONNECTING, CONNECTED
}

// ── Local Storage Models ───────────────────────────────────────────────────────

data class OutboundEntry(
    val msgId: String,
    val to: String,
    val body: String,
    @Volatile var status: String = "QUEUED",
    val createdAt: String = Instant.now().toString()
)

// ── MessagingClient ────────────────────────────────────────────────────────────

class MessagingClient(
    private val onMessage: (fromUser: String, body: String) -> Unit
) {
    // State machine
    @Volatile private var state: State = State.UNINITIALIZED

    // Identity / connection
    private var username: String = ""
    private var wsUrl: String    = ""

    // Local storage
    private val outboundQueue: ConcurrentHashMap<String, OutboundEntry> =
        ConcurrentHashMap()
    private val inboundHistory: MutableSet<String> =
        Collections.newSetFromMap(ConcurrentHashMap())

    // Auto-reconnect
    @Volatile var autoReconnect: Boolean = false
    @Volatile var reconnectDelayMs: Long = 1_000L
    var reconnectJob: Job? = null

    // Coroutine scope for background work
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // Serializes concurrent socket writes
    private val sendMutex = Mutex()

    // Current live WebSocket session (null when disconnected)
    @Volatile private var session: DefaultClientWebSocketSession? = null

    private val httpClient = HttpClient(OkHttp) {
        install(WebSockets)
    }

    // ── State Machine Transitions ──────────────────────────────────────────────

    /**
     * Event INITIALIZE (UNINITIALIZED → DISCONNECTED).
     * Sets username and initialises in-memory storage engines.
     * Silently ignored if not in UNINITIALIZED state.
     */
    fun initialize(username: String, wsUrl: String) {
        if (state != State.UNINITIALIZED) return
        this.username     = username
        this.wsUrl        = wsUrl
        outboundQueue.clear()
        inboundHistory.clear()
        autoReconnect     = true
        reconnectDelayMs  = 1_000L
        state             = State.DISCONNECTED
    }

    /**
     * Event NETWORK_AVAILABLE (DISCONNECTED → CONNECTING → CONNECTED).
     * Suspends for the lifetime of the WebSocket session.
     * Designed to be launched via [scope.launch].
     * Silently ignored if not in DISCONNECTED state.
     */
    suspend fun connect() {
        if (state != State.DISCONNECTED) return
        state = State.CONNECTING

        try {
            httpClient.webSocket(wsUrl) {
                session = this

                // Event SOCKET_OPEN (CONNECTING → CONNECTED)
                state            = State.CONNECTED
                reconnectDelayMs = 1_000L

                // Transmit 'connect' payload immediately
                sendRaw(
                    JSONObject()
                        .put("type", "connect")
                        .put("username", username)
                        .toString()
                )

                // Reactive behavior: ON_CONNECTED – flush outbound queue
                onConnected()

                // Receive loop
                try {
                    for (frame in incoming) {
                        if (frame is Frame.Text) {
                            handleFrame(frame.readText())
                        }
                    }
                } catch (_: Exception) {
                    // connection ended normally or with an error
                } finally {
                    // Event SOCKET_CLOSE (CONNECTED → DISCONNECTED)
                    // Revert all PENDING_RECEIPT outbound messages back to QUEUED
                    outboundQueue.values.forEach { entry ->
                        if (entry.status == "PENDING_RECEIPT") entry.status = "QUEUED"
                    }
                    if (state == State.CONNECTED || state == State.CONNECTING) {
                        state = State.DISCONNECTED
                    }
                    session = null
                    if (autoReconnect && reconnectJob?.isActive != true) {
                        reconnectJob = scope.launch { doReconnect() }
                    }
                }
            }
        } catch (_: Exception) {
            // Could not establish the connection at all
            if (state == State.CONNECTING) state = State.DISCONNECTED
            session = null
            if (autoReconnect && reconnectJob?.isActive != true) {
                reconnectJob = scope.launch { doReconnect() }
            }
        }
    }

    /**
     * Graceful shutdown; disables auto-reconnect and closes the session.
     */
    fun disconnect() {
        autoReconnect = false
        reconnectJob?.cancel()
        reconnectJob = null
        runBlocking {
            session?.close()
        }
        session = null
        state   = State.DISCONNECTED
    }

    fun getState(): State = state

    // ── Reactive Behaviors ─────────────────────────────────────────────────────

    /**
     * ON_CONNECTED:
     * 1. Scan outbound_queue for all entries.
     * 2. For each item: transmit raw 'send_msg' JSON frame to socket.
     */
    private suspend fun onConnected() {
        val entries = outboundQueue.values.sortedBy { it.createdAt }
        for (entry in entries) {
            sendRaw(
                JSONObject()
                    .put("type",   "send_msg")
                    .put("msg_id", entry.msgId)
                    .put("to",     entry.to)
                    .put("body",   entry.body)
                    .toString()
            )
            entry.status = "PENDING_RECEIPT"
        }
    }

    /**
     * ON_USER_ACTION_SEND:
     * 1. Generate cryptographically secure v4 UUID as msg_id.
     * 2. Insert into outbound_queue with status = QUEUED.
     * 3. If CONNECTED: dispatch 'send_msg' frame immediately. Else: remain in queue.
     */
    suspend fun sendMessage(to: String, body: String) {
        val msgId = UUID.randomUUID().toString()
        val entry = OutboundEntry(msgId = msgId, to = to, body = body, status = "QUEUED")
        outboundQueue[msgId] = entry

        if (state == State.CONNECTED) {
            sendRaw(
                JSONObject()
                    .put("type",   "send_msg")
                    .put("msg_id", msgId)
                    .put("to",     to)
                    .put("body",   body)
                    .toString()
            )
            entry.status = "PENDING_RECEIPT"
        }
    }

    /**
     * ON_RECEIVE_RECEIPT:
     * 1. Match receipt.msg_id against entries in outbound_queue.
     * 2. Delete the matched record from outbound_queue completely.
     */
    private fun onReceiveReceipt(frame: JSONObject) {
        val msgId = frame.optString("msg_id")
        if (msgId.isNotEmpty()) {
            outboundQueue.remove(msgId)
        }
    }

    /**
     * ON_RECEIVE_MSG:
     * 1. Check inbound_history for pre-existing msg_id.
     * 2. If NOT present: write to inbound_history, dispatch to message handler.
     * 3. Always: send immediate raw 'ack' JSON frame back to server containing msg_id.
     */
    private suspend fun onReceiveMsg(frame: JSONObject) {
        val msgId    = frame.optString("msg_id")
        val fromUser = frame.optString("from")
        val body     = frame.optString("body")

        if (inboundHistory.add(msgId)) {
            onMessage(fromUser, body)
        }

        // Always ack regardless of dedup result
        sendRaw(JSONObject().put("type", "ack").put("msg_id", msgId).toString())
    }

    // ── Internal Helpers ───────────────────────────────────────────────────────

    private suspend fun sendRaw(text: String) {
        sendMutex.withLock {
            session?.send(Frame.Text(text))
        }
    }

    private suspend fun handleFrame(text: String) {
        val frame = try {
            JSONObject(text)
        } catch (_: Exception) {
            return
        }
        when (frame.optString("type")) {
            "msg"     -> onReceiveMsg(frame)
            "receipt" -> onReceiveReceipt(frame)
        }
    }

    private suspend fun doReconnect() {
        while (autoReconnect && state == State.DISCONNECTED) {
            System.err.println("Reconnecting in ${reconnectDelayMs}ms…")
            delay(reconnectDelayMs)
            if (!autoReconnect) break
            connect()
            if (state == State.CONNECTED) {
                reconnectDelayMs = 1_000L
                break
            }
            reconnectDelayMs = minOf(reconnectDelayMs * 2, 30_000L)
        }
    }
}
