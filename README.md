# MinMessage

A spec-driven, offline-first WebSocket messaging system with clients generated in Python and Kotlin.

---

## What I wrote vs. what the agent generated

| Artifact | Author | Notes |
|---|---|---|
| `Spec.json` | Hand-written | Protocol definition — data models, state machine, wire format. This is the source of truth. |
| `Server/server.py` | Hand-written | Reference server. Never modified by the agent. |
| `generate.json` | Hand-written | Generation config — target list, file lists, build_notes, platform commands, post_generate steps. |
| `.claude/commands/generate.md` | Hand-written | Harness prompt that drives `/generate`. |
| `.claude/commands/regen.md` | Hand-written | Harness prompt that drives `/regen`. |
| `clients/python/client.py` | Agent-generated | Generated from `Spec.json` via `/generate`. |
| `clients/python/README.md` | Agent-generated | Generated from `Spec.json` via `/generate`. |
| `clients/kotlin/src/` | Agent-generated | Generated from `Spec.json` via `/generate`. |
| `clients/kotlin/*.gradle.kts`, `gradle.*`, `gradlew*` | Agent-generated | Build scaffolding generated from `generate.json` build_notes. |
| `clients/kotlin/gradle/wrapper/gradle-wrapper.jar` | Downloaded at generation time | Binary — cannot be generated as text. The post_generate step in `generate.json` downloads it automatically. |
| `clients/kotlin/README.md` | Agent-generated | Generated from `Spec.json` via `/generate`. |


---

## Spec is authoritative

The clients are derived artifacts. The spec defines:
- All message types and their fields (`data_models`)
- The four client states and every valid transition (`state_machine`)
- What triggers each behavior and the exact sequence of steps (`reactive_behaviors`)
- Local storage schemas and their constraints (`local_storage_schemas`)

---

## Two clients, one server

The Python and Kotlin clients are generated from the same spec. They must behave identically at the wire level — same message types, same UUID format, same ack/receipt handshake, same reconnect behavior. You can run both simultaneously and message between them through the server. If they interoperate, the spec is doing its job. If they don't, the spec has a gap.

---

## Regenerating the clients

This project utilizes **Claude Code's custom slash command mechanism** to power its agentic generation harness. By placing prompt-instruction markdown files under `.claude/commands/`, these commands are registered natively in the Claude Code CLI and can be executed by the agent to drive code generation, verification, and tests.

**To regenerate everything from scratch:**

1. Delete `clients/python/` and `clients/kotlin/`
2. Open this repo in Claude Code
3. Run the custom slash command:
   ```
   /generate
   ```

The `/generate` command reads `Spec.json` and `generate.json`, writes every file listed in `targets[].files[]` for each target, then runs the `post_generate` step (downloads `gradle-wrapper.jar` for Kotlin). No manual steps required beyond having network access.

**To repair missing or incomplete files without deleting everything:**

Run the custom slash command:
```
/regen
```

The `/regen` command checks each file against the spec, reports what is MISSING or INCOMPLETE, repairs only those files, and runs build verification.

**To run the automated build and integration check:**

Run the custom slash command:
```
/checker
```

The `/checker` command compiles both client implementations, starts the reference server, runs both client CLI applications as background tasks, exchanges test messages between them, and cleans up.

---

## Running locally

**Start the server:**
```bash
python Server/server.py
```

**Python client:**
```bash
cd clients/python
pip install websockets
python client.py
```

**Kotlin client (Mac/Linux):**
```bash
cd clients/kotlin
./gradlew run --args="<username>"
```

**Kotlin client (Windows):**
```powershell
cd clients\kotlin
.\gradlew.bat run --args="<username>"
```

To message between clients, run the server and two clients with different usernames. From the Python client, type `<recipient> <message>`. From the Kotlin client, type `@<recipient> <message>`.

---

## Repository structure

```
Spec.json                        # Protocol definition (authoritative)
generate.json                    # Generation config (targets, build_notes, post_generate)
Server/server.py                 # Reference server (hand-written, never generated)
clients/python/                  # Python client (agent-generated)
clients/kotlin/                  # Kotlin client (agent-generated)
.claude/commands/generate.md     # /generate harness
.claude/commands/regen.md        # /regen harness
DESIGN.md                        # Design rationale
CLAUDE.md                        # Agent setup reference
```
