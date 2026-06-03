# Spec-Driven Code Generator

Read the spec file, then generate every file listed in `spec.generate[]`. Each target gets its own output directory. Nothing is skipped.

## 0. Detect Platform

Detect the current OS (windows or unix). Then read `spec.platform_commands` to resolve:
- `PYTHON` — the Python executable to use (`platform_commands.python[os]`)
- `GRADLE` — the Gradle wrapper to use (`platform_commands.gradle[os]`)

All subsequent commands use these variables. Never hardcode `python`, `python3`, `gradlew`, or `gradlew.bat` directly.

On unix, after writing `gradlew`, ensure it is executable: `chmod +x gradlew`.

## 1. Locate the Spec

- Use the path from `$ARGUMENTS` if provided, otherwise look for `spec.json` or `Spec.json` in the working directory.
- Read it with the Read tool. If missing, stop and report the error clearly.

## 2. Read the Generate Targets

Find `spec.generate[]`. Each entry declares:
- `language` — target language
- `output_dir` — folder to write all files into (create it if it does not exist)
- `dependencies` — libraries required at runtime
- `files` — list of filenames to generate inside `output_dir`
- `build_notes` — compilation/runtime rules and platform guidelines

If `generate` is absent, infer targets from `spec.meta.description`.

## 3. Generate Each File

For every entry in `generate[]`, write every file in its `files` list into its `output_dir`. Apply the rules below.

---

### Source Files

Implement the full target. No stubs, no TODOs. Every file must be complete and runnable.

**Must implement from the spec:**

- `data_models` — one typed model, data class, or struct per entry; honor every `const`, `pattern`, `format`, and `required` constraint exactly as declared.
- `local_storage_schemas` — `primary_key` fields enforce uniqueness; respect the description and all field-level constraints and notes of each schema definition.
- `state_machine.states` — implemented as a native enum or equivalent; set the initial value from `initial_state`.
- `state_machine.transitions` — guard every event: silently ignore it if the current state does not match the expected `from` state.
- `state_machine.reactive_behaviors` — implement each behavior method, executing its steps in the exact order listed in `sequence`.
- Wire Format and I/O Lifecycle — follow the transport mechanism and wire format declared in `spec.meta` (e.g., `spec.meta.transport`, `spec.meta.wire_format`). If `spec.meta` includes a reference to an existing implementation (such as a `server_reference_note` field pointing to a file path), read and inspect that file as a compatibility anchor for exact protocol behavior.
- Language and Platform Rules — strictly follow all runtime libraries, compiler configuration, framework details, and runner implementation details declared in the target's `build_notes`.

---

### README Files (`README.md`)

Every `README.md` is generated entirely from the spec. Use only what is already in the spec — do not invent content. Include these sections in order:

1. **Title** — `spec.title` + `spec.version`
2. **Overview** — `spec.meta.description`
3. **Installation** — dependency install block derived from the entry's `dependencies` and `build_notes`
4. **Quick Start** — minimal runnable example showing the primary workflow described in the spec for this target (initialization, any required setup, and the core action)
5. **State Machine** — ASCII diagram of states and transitions, then a table: `From | Event | Action | To` (all rows from `state_machine.transitions`)
6. **Data Models** — one table per entry in `data_models`; columns `Field | Type | Required | Description`; grouped by whatever top-level grouping keys exist in `data_models`
7. **Storage Schemas** — one table per schema in `local_storage_schemas`; columns `Field | Type | Primary Key | Notes`
8. **Reactive Behaviors** — one subsection per entry in `state_machine.reactive_behaviors`; each shows the description then a numbered list of its sequence steps

---

## 4. Build Verification

After writing all source files for a target, read `target.build_verification[os]` from the spec and run that command from `output_dir`. Capture the result.

## 5. Report

After all targets are complete, output a summary:

```
Generated
─────────
✓ [relative/path/to/generated/file]
...

Build Verification
──────────────────
✓ [language] — passed
✗ [language] — failed: [reason]
```
