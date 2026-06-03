# Spec-Driven Code Generator

Read the spec file (`spec.json` or `Spec.json`) and the generation config file (`generate.json`), then generate every file listed in `targets[]` of `generate.json`. Each target gets its own folder. Nothing is skipped.

## 1. Locate the Spec and Generation Config

- Use the path from `$ARGUMENTS` if provided to locate the files, otherwise look for the spec file (`spec.json` or `Spec.json`) and the generation config (`generate.json`) in the working directory.
- Read both files. If either is missing, stop and report clearly.

## 2. Read the Generate Targets

Find the `targets[]` array in `generate.json`. Each entry has:
- `language` — target language
- `output_dir` — folder to write all files into (create it if it does not exist)
- `dependencies` — libraries required at runtime
- `files` — list of filenames to generate inside `output_dir`
- `build_notes` — compilation/runtime rules and platform guidelines

If `targets` is absent, infer targets from `meta.description` of the spec.

## 3. Generate Each File

For every entry in `targets[]` of `generate.json`, write every file in its `files` list into its `output_dir`. Apply the rules below.

---

### Source Files

Implement the full client. No stubs, no TODOs.

**Must implement from the spec:**
- `data_models` — one typed model/data class/struct per message; honor every `const`, `pattern`, `format`, `required` constraint.
- `local_storage_schemas` — `primary_key` fields enforce uniqueness; `outbound_queue` survives reconnects; `inbound_history` is checked before any side-effect.
- `state_machine.states` — implemented as native enum or state representations; initial state set from `initial_state`.
- `state_machine.transitions` — guard every event: silently ignore if the current state is not the expected `from` state.
- `state_machine.reactive_behaviors` — implement behavior methods, executing steps in the exact order listed in `sequence`.
- Wire Format and Network Lifecycle — follow the wire format specified in the spec, utilizing the server implementation in `Server/server.py` as a constant reference to build the clients efficiently and guarantee complete wire-format compatibility.
- Language/Platform Rules — strictly follow the runtime libraries, compiler configuration, framework details, and CLI runner implementation details outlined in the target's `build_notes`.

---

### README Files (`README.md`)

Every `README.md` is generated entirely from the spec. Use only what is already in the spec — do not invent content. Include these sections in order:

1. **Title** — `spec.title` + `spec.version`
2. **Overview** — `spec.meta.description`
3. **Installation** — dependency install block derived from the entry's `dependencies` and `build_notes`
4. **Quick Start** — minimal runnable code example showing client instantiation, initialization, connection, and sending a message
5. **State Machine** — ASCII diagram of the states and transitions, then a table: `From | Event | Action | To` (all rows from `state_machine.transitions`)
6. **Message Protocol** — one table per message type from `data_models`; columns `Field | Type | Required | Description`; grouped by direction (Client→Server first, then Server→Client)
7. **Storage Schemas** — one table per schema from `local_storage_schemas`; columns `Field | Type | Primary Key | Notes`
8. **Reactive Behaviors** — one subsection per entry in `state_machine.reactive_behaviors`; each shows the description then a numbered list of its sequence steps

---

## 4. Post-Generate Steps

After all files for a target have been written, check if the target has a `post_generate` key. If it does, detect the current OS and run the platform-appropriate command from within the target's `output_dir`. Report success or failure for each command. A failed `post_generate` command should be reported clearly but must not prevent processing of remaining targets.

## 5. Report

After all files are written, output a summary listing all generated files relative to the workspace root:

```
Generated
─────────
✓ [relative/path/to/generated/file/1]
✓ [relative/path/to/generated/file/2]
...
```
