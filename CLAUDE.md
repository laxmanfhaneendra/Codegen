# Agent Setup

## Commands

| Command | What it does |
|---|---|
| `/generate` | Reads `Spec.json` + `generate.json`, generates every file listed in `targets[].files[]`, then runs `post_generate` steps |
| `/regen` | Detects missing or incomplete generated files and regenerates only those; always runs build verification at the end |

## What is hand-written vs. agent-generated

**Hand-written (do not modify or regenerate):**
- `Spec.json` — protocol definition, the source of truth
- `Server/server.py` — reference server implementation
- `generate.json` — generation config (targets, file lists, build_notes, platform commands, post_generate)
- `.claude/commands/generate.md` — the `/generate` harness
- `.claude/commands/regen.md` — the `/regen` harness
- `CLAUDE.md`, `DESIGN.md`, `README.md` — project documentation

**Agent-generated (safe to delete and regenerate):**
- `clients/python/` — all files
- `clients/kotlin/` — all files
- `clients/kotlin/gradle/wrapper/gradle-wrapper.jar` — binary, downloaded by post_generate step (not written by the agent)

## How `/generate` works

1. Reads `Spec.json` and `generate.json`
2. For each entry in `targets[]`, writes every file in `files[]` into `output_dir`
3. Source files implement the full spec — no stubs, no TODOs
4. After writing all files for a target, runs the `post_generate` command for the current OS
5. Reports all generated files

The spec is the prompt. The agent does not infer behavior from existing code — if you want different behavior, change the spec and regenerate.

## How `/regen` works

1. Reads `Spec.json` and `generate.json`, detects OS
2. For each target, checks each file in `files[]` for existence and completeness against the spec
3. Reports MISSING / INCOMPLETE / OK for every file
4. Regenerates only damaged files
5. Runs `post_generate` if any binary artifact (e.g. `gradle-wrapper.jar`) is absent
6. Runs `build_verification` for every target unconditionally
7. Attempts a live connection test against the server

## post_generate step

`gradle-wrapper.jar` is a binary that cannot be generated as text. `generate.json` includes a `post_generate` key on the Kotlin target with platform-specific download commands:

- **Windows:** `Invoke-WebRequest` via PowerShell
- **Unix/Mac:** `curl` + `chmod +x gradlew`

This runs automatically at the end of `/generate` and `/regen`. It requires network access.

## Platform commands

Resolved from `generate.json → platform_commands` based on detected OS. Never hardcoded.

| Platform | Python | Gradle |
|---|---|---|
| Windows | `python` | `.\gradlew.bat` |
| Unix/Mac | `python3` | `./gradlew` |
