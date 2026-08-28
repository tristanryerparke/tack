# Tack Agent Instructions

## Interactive Rhino watcher sessions

When testing Tack interactively, run the watcher directly in the agent terminal:

```bash
uv run rhino-watch commands/tack_add.py --debug
```

Use persistent mode only when handler output is needed after setup completes:

```bash
uv run rhino-watch commands/tack_add.py --debug --nostop
```

- Keep this foreground command as the sole live output channel. Do not use `nohup`, background processes, Terminal.app, PID files, log files, or `tail`.
- Do not intentionally start a second watcher while one is running. Startup automatically stops an existing `rhino-watch` listener on port `8765`, but refuses to kill an unrelated process.
- In default mode, `end` and `quit` stop the watcher. With `--nostop`, `end` keeps it open while `quit` still stops it.
- Let the command end from its lifecycle message, or stop the agent terminal command only when the user asks. Then inspect the command output together with the user. It is rare to use either the --nostop so only use it in the specific situation where non-script triggered code needs it output observed in the original session. Using it unessecarily can cause scripts to hang when they don't need to.
- Do not claim an interactive Rhino result until the user has completed the requested Rhino action and the foreground output has been observed.
- When creating new demos for tack things, always use the OutputParasite from run-in-rhino so the original shell can see the output. 