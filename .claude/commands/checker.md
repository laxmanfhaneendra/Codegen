# Client Connection & Messaging Checker

You are a live integration testing agent. Your job is to start the server, launch both clients in the terminal, and simulate a real two-person conversation to verify everything works end-to-end. Do all of this exclusively through terminal commands — no test files, no temporary scripts.

---

## Step 1 — Check File Structure

1. Read `generate.json` from the workspace root.
2. For each target in `targets[]`, verify every file in `files[]` exists inside `output_dir`.
3. Report any missing files. If critical files are missing, stop and report BLOCKED.

---

## Step 2 — Build / Syntax Verification

Detect the OS (windows or unix). Run build verification commands from `build_verification` in `generate.json`.

- **Python** (run from `clients/python`):
  - Windows: `python -m py_compile client.py`
  - Unix: `python3 -m py_compile client.py`
- **Kotlin** (run from `clients/kotlin`):
  - Windows: `.\gradlew.bat build`
  - Unix: `./gradlew build`

Both must exit with code 0. Report FAIL and stop if either fails.

---

## Step 3 — Live Integration Test

You will act as two users — **alice** (Python client) and **bob** (Kotlin client) — having a real conversation. Launch everything as background tasks and drive them by sending stdin input.

### 3.1 Start the Reference Server

Check if port 8765 is already in use. If not:
- Start as a background task: `python Server/server.py`
- Wait 1–2 seconds, then confirm the task output shows the server is listening.

### 3.2 Launch Python Client as "alice"

- Windows: `python -u clients/python/client.py`
- Unix: `python3 -u clients/python/client.py`

Run as a background task. Wait for the `Chat as: ` prompt, then send:
```
alice
```
Wait for output to confirm alice is connected.

### 3.3 Launch Kotlin Client as "bob"

- Windows: `cmd.exe /c "cd clients\kotlin && .\gradlew.bat -q run"`
- Unix: bash -c `cd clients/kotlin && ./gradlew -q run`

Run as a background task. Wait for the `Chat as: ` prompt, then send:
```
bob
```
Wait for output to confirm bob is connected.

---

### 3.4 Simulated Conversation — Act Like Real Users

Run all of the following in sequence. After each send, wait 1–2 seconds and check the recipient's output. Record PASS or FAIL for each.

**Round 1 — Greeting**
- alice sends to bob: `bob hey, are you there?`
- Verify bob receives: `<- [alice] hey, are you there?`
- bob replies to alice: `@alice yeah! just connected`
- Verify alice receives: `<- [bob] yeah! just connected`

**Round 2 — Normal conversation**
- alice sends: `bob this is the Python client speaking`
- Verify bob receives: `<- [alice] this is the Python client speaking`
- bob replies: `@alice and this is Kotlin on my end`
- Verify alice receives: `<- [bob] and this is Kotlin on my end`

**Round 3 — Longer message**
- alice sends: `bob just making sure longer messages work fine too, no truncation or anything weird`
- Verify bob receives the full message.
- bob replies: `@alice confirmed, got the whole thing`
- Verify alice receives it.

**Round 4 — Status check**
- Send `/status` to both clients and verify each prints `CONNECTED`.

**Round 5 — Offline queue test**
- Disconnect bob by sending `/quit` to his task.
- Wait 1 second.
- alice sends a message to bob while he is offline: `bob are you still around?`
- Verify alice gets no error (message should be queued or sent, server will buffer it).
- Re-launch the Kotlin client as bob (same command as 3.3).
- Wait for bob to reconnect.
- Verify that bob receives the buffered message from alice: `<- [alice] are you still around?`

---

### 3.5 Cleanup

- Send `exit` to alice's task.
- Send `/quit` to bob's task (if still running).
- Stop the server background task.
- Confirm all background tasks have terminated.

---

## Step 4 — Final Report

Print a clean report:

```
File Structure
──────────────
✓ Python client files present
✓ Kotlin client files present

Build & Syntax Check
────────────────────
✓ Python syntax OK
✓ Kotlin build OK

Integration Test — Live Conversation
─────────────────────────────────────
✓ Server started on ws://localhost:8765
✓ alice (Python) connected
✓ bob (Kotlin) connected
✓ Round 1 — Greeting:            alice→bob PASS | bob→alice PASS
✓ Round 2 — Normal exchange:     alice→bob PASS | bob→alice PASS
✓ Round 3 — Long message:        alice→bob PASS | bob→alice PASS
✓ Round 4 — /status check:       alice CONNECTED | bob CONNECTED
✓ Round 5 — Offline queue:       message buffered PASS | delivered on reconnect PASS

Final Status: READY TO TEST
```

If any step fails, replace ✓ with ✗, describe what was expected vs. what was observed, and set Final Status to NEEDS ATTENTION.
