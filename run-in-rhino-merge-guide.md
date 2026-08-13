# run-in-rhino merge guide

## Goal

Migrate Tack from the `run-in-rhino` `main`-branch watcher API to the `sync-generator-watcher` API.

This is **not** a fast-forward merge for Tack.

Two old entry points used by Tack disappear on `sync-generator-watcher`:

- `from run_in_rhino import start_server`
- `import rhino_watcher`

The new branch centers these APIs instead:

- `run_in_rhino.server.server(...)`
- `run_in_rhino.server.RunContext`
- `run_in_rhino.orchestration.run_rhino_python_til_done(...)`
- `run_in_rhino.pipe.run_script(...)`
- `run_in_rhino.pipe.run_command(...)`
- `run_in_rhino.rhino_env.client.SocketConnection`
- `run_in_rhino.rhino_env.parasite.OutputParasite`
- `run_in_rhino.rhino_env.env.install_os_environment(...)`

## What breaks in Tack today

### Parent-side pytest files that import `start_server`

- `tests/test_rhino_child_move_updates_offset.py`
- `tests/test_rhino_delete.py`
- `tests/test_rhino_event_traces.py`
- `tests/test_rhino_integration.py`
- `tests/test_rhino_polyline_split.py`
- `tests/test_rhino_polyline_split_without_advanced.py`
- `tests/test_rhino_stress.py`

### Rhino-side test scripts that import `rhino_watcher`

- `tests/rhino/common.py`
- `tests/rhino/polyline_split_collect.py`
- `tests/rhino/polyline_split_setup.py`
- `tests/rhino/polyline_split_undo_collect.py`

### Tack code that still references `rhino_watcher`

- `tack/handlers.py`
- `tack/scheduler.py`
- `commands/tack_add.py`
- `commands/tack_clear.py`
- `commands/tack_hide.py`
- `commands/tack_pause.py`
- `commands/tack_restore.py`
- `commands/tack_resume.py`
- `commands/tack_settings.py`
- `commands/tack_show.py`

### Test that will need expectation changes if we remove old imports

- `tests/test_display_cache.py`

## Important behavior change

Tack debug mode is currently read from `os.environ` at import time in `tack/utils.py`.

That means Rhino-side migrated test scripts must install the watcher environment **before importing Tack modules**.

Use:

```python
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment

connection = SocketConnection()
install_os_environment(connection)
```

Do **not** rely on `install_sticky_environment(...)` alone for Tack debug. It does not populate `os.environ`.

## Recommended migration path

Prefer an **idiomatic migration**, not a compatibility shim.

### Phase 1: replace the Rhino-side helper first

Update `tests/rhino/common.py` so it owns the new connection pattern.

Target shape:

```python
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite


def run_step(name, action, *, send_done=False):
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=send_done):
        print("START {}".format(name))
        data = action()
        if data is not None:
            connection.send_data(data)
        print("PASS {}".format(name))
```

Notes:

- `OutputParasite` already forwards terminal output.
- On exceptions, `OutputParasite` forwards the traceback and sends `quit`.
- For multi-step tests, most helper scripts should **not** send `done`.
- For one-shot tests, the final script should send `done`.

### Phase 2: migrate the easiest parent tests first

These should move best to `run_rhino_python_til_done(...)` and become closest to `../run-in-rhino/demos/example_tests/`:

1. `tests/test_rhino_stress.py`
2. `tests/test_rhino_delete.py`
3. `tests/test_rhino_child_move_updates_offset.py`

Preferred parent shape:

```python
from run_in_rhino.orchestration import run_rhino_python_til_done
from run_in_rhino.server import RunContext

reason, data = run_rhino_python_til_done(
    script_path=SCRIPT,
    context=RunContext(env={"debug": "true"}),
)
assert reason == "done"
```

These simplify the most if setup, action, and cleanup are folded into one Rhino script.

### Phase 3: migrate the command-driven tests to the generator API

These need `server(...)`, `run_script(...)`, and `run_command(...)`:

- `tests/test_rhino_event_traces.py`
- `tests/test_rhino_integration.py`
- `tests/test_rhino_polyline_split.py`
- `tests/test_rhino_polyline_split_without_advanced.py`

Preferred parent shape:

```python
from run_in_rhino.pipe import run_command, run_script
from run_in_rhino.server import RunContext, server

events = server(context=RunContext(env={"debug": "true"}))
try:
    for status, data in events:
        if status == "ready":
            run_script(script_path=SETUP)
        elif status == "data":
            ...
finally:
    events.close()
```

Notes:

- This is the pattern used by `../run-in-rhino/demos/example_tests/test_rhino_end_command_move.py`.
- The parent test becomes more event-driven.
- The server generator must be closed in `finally`.
- If helper scripts send `done` too early, the whole parent loop ends too early.

### Phase 4: remove direct `rhino_watcher` imports from Rhino test scripts

After `tests/rhino/common.py` is updated, migrate these to use the shared helper or direct `SocketConnection` calls:

- `tests/rhino/common.py`
- `tests/rhino/polyline_split_collect.py`
- `tests/rhino/polyline_split_setup.py`
- `tests/rhino/polyline_split_undo_collect.py`

Best outcome:

- `common.py` hides most watcher details
- scripts call `run_step(...)` or a small shared send-data helper
- top-level Rhino scripts stop importing watcher transport code directly

### Phase 5: decide whether to migrate Tack command/debug code now or later

The tests can be migrated without immediately rewriting every Tack command entry point.

However, a full merge should eventually replace `rhino_watcher` usage in:

- `tack/handlers.py`
- `tack/scheduler.py`
- `commands/tack_add.py`
- `commands/tack_clear.py`
- `commands/tack_hide.py`
- `commands/tack_pause.py`
- `commands/tack_restore.py`
- `commands/tack_resume.py`
- `commands/tack_settings.py`
- `commands/tack_show.py`

The cleanest way is to add a small Tack-local watcher helper that wraps:

- optional `SocketConnection()` setup
- `install_os_environment(...)`
- `OutputParasite(...)`
- optional `send_done()` / `send_quit()` calls

That avoids scattering `run_in_rhino.rhino_env.*` imports everywhere.

### Phase 6: update the AST/source-inspection test

If the old imports are removed from command files, update `tests/test_display_cache.py`.

Today it asserts that commands lazily import `rhino_watcher`.

After migration it should instead assert one of these:

- commands lazily import a Tack-local watcher helper, or
- commands lazily import `run_in_rhino.rhino_env.*`

## What will actually simplify

## Biggest simplification wins

- One-shot Rhino tests can become much more like `demos/example_tests/test_rhino_box.py`.
- `tests/test_rhino_stress.py` is the strongest candidate.
- `tests/test_rhino_delete.py` and `tests/test_rhino_child_move_updates_offset.py` can also simplify if their setup and cleanup move into a single Rhino script.

## Smaller simplification wins

- The command-driven tests can become more uniform.
- They can look more like `demos/example_tests/test_rhino_end_command_move.py`.
- They will usually become **clearer**, but not always **shorter**.

## What will not simplify automatically

If Tack keeps its current many-file setup/collect/cleanup structure, the new API does not magically reduce test count or script count.

The tests become more like the demos only if we also consolidate flows.

## Suggested order of work

1. `tests/rhino/common.py` — 30 to 45 minutes
2. `tests/test_rhino_stress.py` — 20 to 30 minutes
3. `tests/test_rhino_delete.py` — 20 to 30 minutes
4. `tests/test_rhino_child_move_updates_offset.py` — 20 to 30 minutes
5. `tests/test_rhino_polyline_split.py` and `tests/test_rhino_polyline_split_without_advanced.py` — 45 to 75 minutes
6. `tests/test_rhino_event_traces.py` — 45 to 75 minutes
7. `tests/test_rhino_integration.py` — 45 to 75 minutes
8. command/debug helper cleanup plus `tests/test_display_cache.py` — 45 to 60 minutes

Total expected migration time: **4 to 7 hours**.

## Optional shortcut

If the goal is only to get Tack green quickly after the merge, add a compatibility layer instead of rewriting everything immediately.

That shortcut would reintroduce:

- a `start_server` wrapper around `server(...)`
- a small `rhino_watcher`-compatible shim exposing the old helper names

That is lower-risk in the short term, but it keeps Tack tied to the old mental model.

## Definition of done

The migration is complete when all of these are true:

- parent pytest files no longer import `start_server`
- Rhino-side test scripts no longer import `rhino_watcher`
- Tack debug behavior still works in watched Rhino runs
- `tests/test_display_cache.py` matches the new lazy-import story
- command-driven tests use the generator/event loop pattern
- one-shot tests use `run_rhino_python_til_done(...)` where practical
