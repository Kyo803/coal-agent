# ROX N — Linux Sandbox (Phase 1)

ROX N now has an isolated Linux world it fully controls: **WSL2 Ubuntu
24.04** with root, the internet, and a full toolchain. The Windows host is
sealed off from inside it. This is the security boundary that lets ROX N
run *any* Linux command, install *anything*, clone repos, and build
projects without artificial ceilings.

## Layout

| Thing | Value |
|---|---|
| Distro | `Ubuntu-24.04` (backing store moved to `D:\ROX_N_SANDBOX\Ubuntu-24.04`) |
| Memory cap | `~/.wslconfig` -> `[wsl2] memory=6GB, processors=6, swap=2GB` (global to all WSL distros, incl. Docker) |
| Isolation | `/etc/wsl.conf`: `[automount] enabled=false`, `[interop] enabled=false, appendWindowsPath=false`, `[boot] systemd=true` |
| User | `rox` (uid 1001), NOPASSWD sudo (`/etc/sudoers.d/rox`), default user |
| Workdir | `/home/rox/work`; transfer dir `/home/rox/shared` |
| Open ports | none; host FS and Windows exes unreachable from inside |

Toolchain installed: gcc/g++/clang, make, cmake, pkg-config, python3 (+pip,
venv, dev), Node 22 (`node`/`npm`, corepack), git, curl/wget, jq, ripgrep,
tree, tmux, htop, sqlite3, iverilog 12, verilator 5, gtkwave.

## Package (`sandbox/`)

```
sandbox/base.py       low-level `wsl bash -s` bridge + distro list/terminate
sandbox/exec.py       shell / check / which / version
sandbox/fs.py         read / write / append / edit / mkdir / move / copy / rm / stat
sandbox/session.py    start / stop / restart / ensure / status
sandbox/health.py     OS info + tool versions + free RAM
sandbox/pkg.py        apt / pip / npm installs
sandbox/toolchain.py  per-stack detect+install (node/web/python/cpp/hdl/rust/go/db/tools)
sandbox/governor.py   host free RAM, .wslconfig memory cap get/set, wsl shutdown
```

Facade: `from sandbox import sb; sb.shell("ls -la"); sb.write(path, text)`.

The bridge pipes a bash script to `wsl -d Ubuntu-24.04 -u <user> -- bash -s`
(stdin), so there are no Windows/quote-escaping problems and **no automount
is needed**. Files cross the boundary by value (base64).

## Tools (`tools/handlers_sandbox.py`, category `sandbox`)

`sandbox_run`, `sandbox_write`, `sandbox_read`, `sandbox_edit`,
`sandbox_list`, `sandbox_move`, `sandbox_delete`, `sandbox_pkg`,
`sandbox_toolchain`, `sandbox_info`, `sandbox_upload`, `sandbox_download`.

- Registered in `tools/specs.py`; category `sandbox` enabled in
  `tools/permissions.py` DEFAULT and in `config.json` `tools.enabled`.
- All sandbox tools are in `tools.auto_allow` (no prompt): the sandbox is
  the boundary, so commands inside it are ROX N's to run.
- `tools/shell_gate.py`: `wsl` moved from Tier-2 to Tier-0 (allowed).
- `tools/intent.py`: a top-priority rule routes anything mentioning
  sandbox/linux/ubuntu/wsl/apt/bash-script to `sandbox_run`.
- `tools/exec.py`: handler time limit raised 90s -> 600s (installs/builds);
  `sandbox` is first in the tool-exposure priority.

## Config keys

`config.json` `model`: Phase 0 keys (context 16384, flash_attn, kv q8_0,
cache_reuse, draft/spec — disabled). `tools`: updated `enabled` +
`sandbox_*` in `auto_allow`.

## Verified

- `python -c "import sandbox; sandbox.sb.shell('uname -a')"` -> Ubuntu.
- Handlers end-to-end: run/write/read/python3/list/info/toolchain/upload/
  download all OK.
- Live agent: `rox.py --say "...sandbox... hello.sh ... run it"` ->
  ROX N called `sandbox_run`, created `/home/rox/work/hello.sh`, chmod +x,
  ran it, and reported `ROX SANDBOX OK`.
- Regressions: test_tools 145, test_security 16, test_chip 9, test_board 31.

## Notes / caveats

- `~/.wslconfig` `memory=6GB` is **global** (also caps Docker Desktop's WSL
  VM). Raise it before heavy sandbox builds: `sandbox.governor.set_wsl_memory`
  + `wsl --shutdown`.
- `--cache-reuse` is auto-disabled by llama.cpp while the vision `mmproj`
  is loaded.
- Old backing store at `C:\...\AppData\Local\wsl\{5df6e1f7...}` removed.
