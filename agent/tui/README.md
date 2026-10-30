# tui — terminal user interface

OpenCode-style Go TUI (bubbletea). Talks to `coal.py --json-repl`.

```powershell
go build -o coal-tui.exe .
.\coal-tui.exe
```

`coal-tui.cmd` builds on first run. `demo.cmd` in the agent root sets the
Nebius key and `COAL_NO_35B`, then launches this.
