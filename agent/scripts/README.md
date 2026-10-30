# scripts — setup and helpers

| Script | Purpose |
|---|---|
| `setup_wsl.ps1` | one-click WSL + HDL toolchain setup (iverilog, yosys, nextpnr) |
| `register_wsl_finish.ps1` | finishes the WSL install after a reboot |
| `board_ui.bat` | starts the board web UI on 127.0.0.1:8790 |

The chip gate needs the WSL toolchain; `setup_wsl.ps1` is the supported
way to get it.
