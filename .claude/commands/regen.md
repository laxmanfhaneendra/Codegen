You are a regeneration agent. Your job is to detect missing and incomplete generated files, then regenerate only what is damaged.

## Step 1 — Read Both Config Files and Detect Platform

Detect OS (windows or unix).

Look for the spec file: `Spec.json` or `spec.json` in the working directory. Read it. Extract:
- `state_machine.states` — expected state names
- `state_machine.reactive_behaviors` — expected behavior names (keys)
- `data_models` — all message type names across all groups
- `local_storage_schemas` — all schema names
- `meta.server_reference_note` — locate and read the referenced server file as a wire-format compatibility anchor

Look for the generation config: `generate.json` in the same directory. Read it. Extract:
- `targets[]` — output_dir, files[], language, build_notes, build_verification, dependencies
- `platform_commands` — resolve for current OS:
  - `PYTHON` = `platform_commands.python[os]`
  - `GRADLE` = `platform_commands.gradle[os]`

Use `PYTHON` and `GRADLE` in all commands below. Never hardcode `python`, `python3`, `gradlew`, or `gradlew.bat` directly.

## Step 2 — Detect Missing Files

For every target in `generate.json`'s `targets[]`, attempt to read each file in `files[]` from `output_dir`. Mark any unreadable file as **MISSING**.

## Step 3 — Validate Existing Files

Read each existing file and check it against the spec. Mark as **INCOMPLETE** if any expected element is absent.

**Primary client implementation file** (identified by `build_notes`):
- All state names from `spec.state_machine.states` are present
- All behavior names from `spec.state_machine.reactive_behaviors` keys are implemented
- All message type names from `spec.data_models` (across all groups) are handled
- All schema names from `spec.local_storage_schemas` are referenced
- Storage and concurrency requirements described in `build_notes` are present

**Entry point file** (identified by the ENTRY POINT or MAIN CLI LOOP section in `build_notes`):
- File is non-empty
- Main function or entry symbol declared in `build_notes` is present
- CLI commands described in `build_notes` are handled

**README.md**:
- All 8 sections present: Title, Overview, Installation, Quick Start, State Machine, Data Models, Storage Schemas, Reactive Behaviors

**Build and config files** (all non-source, non-README files in `files[]`):
- File is non-empty
- Contains key identifiers declared in `build_notes` for that file

## Step 4 — Report

```
Scan Results
────────────
MISSING     [output_dir/file]     (file does not exist)
INCOMPLETE  [output_dir/file]     (missing: [element names])
OK          [output_dir/file]
```

If everything is OK, report and stop.

## Step 5 — Regenerate Damaged Files Only

For each MISSING or INCOMPLETE file, regenerate from scratch using the spec and server reference.

Before regenerating an INCOMPLETE file, re-read its current content to stay consistent with any intact sibling files in the same target.

**Source files**: complete implementations, no stubs. Follow `build_notes` exactly. Implement all elements from `state_machine`, `data_models`, and `local_storage_schemas`.

**README.md** sections in order:
1. Title — `spec.title` + `spec.version`
2. Overview — `spec.meta.description`
3. Installation — from `dependencies` and `build_notes`
4. Quick Start — minimal runnable example
5. State Machine — ASCII diagram + transitions table (`From | Event | Action | To`)
6. Data Models — one table per entry (`Field | Type | Required | Description`)
7. Storage Schemas — one table per schema (`Field | Type | Primary Key | Notes`)
8. Reactive Behaviors — one subsection per behavior; description + numbered sequence steps

## Step 5.5 — Pre-Generate Scaffolding & Post-Generate Steps

- **Pre-Generate**: If any files for a target were marked as **MISSING**, check if the target has a `pre_generate` key. If it does, detect the current OS (windows or unix) and run the platform-appropriate command from within the target's `output_dir` to bootstrap the project scaffolding before writing the regenerated files.
- **Post-Generate**: After regenerating any files, check if the target has a `post_generate` key. If it does, detect the current OS and run the platform-appropriate command from within the target's `output_dir`. Report success or failure.

## Step 6 — Verification

Run all three checks for every target, whether or not files were regenerated.

**1. Syntax / compile check — always run, never skip**
Run `target.build_verification[os]` from the generation config unconditionally for every target, even if no files were regenerated. Do not skip because of a cached build — always invoke and capture the exit code.

**2. Import / instantiation smoke test**
Verify the client class can be loaded and instantiated without errors:
- Python: `{PYTHON} -c "from <module> import <ClientClass>; c = <ClientClass>(); print('OK')"`
- Compiled languages: a successful build implicitly covers this; no separate step needed

**3. Live connection test**
Attempt to connect to the server declared in `spec.meta` (default `ws://localhost:8765`):
- Start the server if it is not already running (use the file referenced in `spec.meta.server_reference_note`)
- Python: `{PYTHON} -c "import asyncio; from client import MessagingClient; c = MessagingClient(); c.initialize('_regen_probe'); asyncio.run(c.connect()); asyncio.run(c.disconnect()); print('connection OK')"`
- Compiled languages: skip if the binary requires interactive input and no non-interactive mode exists
- If the server cannot be started or the port is unavailable, mark as SKIPPED (not FAILED) and note the reason

## Step 7 — Final Report

```
Regenerated
───────────
✓ [output_dir/file]   (was MISSING)
✓ [output_dir/file]   (was INCOMPLETE — restored: [element names])

Verification
────────────
✓ [language] — syntax OK
✓ [language] — import/instantiation OK
✓ [language] — live connection OK
✗ [language] — live connection SKIPPED: server not reachable on ws://localhost:8765
```
