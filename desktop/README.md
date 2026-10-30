# Coal Desktop

A native desktop client for Coal — a real window, not a terminal.

Built with **Rust** (Tauri v2 + WebView2 shell) and **Go** (launcher /
preflight). The UI is a single static page, so there is no Node build step.

```
desktop/
  ui/index.html            the interface (no bundler, no npm)
  src-tauri/               Rust shell: spawns the agent, streams its events
  launcher/                Go launcher: checks prerequisites, starts the app
  make_icon.py             generates the app icon
  build.cmd                icon -> Rust -> Go, in one command
```

The launcher finds the agent at `../agent` (override with `COAL_DIR`).

## What it does

- **Command input** — type what you want; it goes to the agent over stdin.
- **Live thinking** — the model's reasoning streams into a dim, collapsible block.
- **Tool trace** — every tool call with its arguments and output, click to expand.
- **Artifacts rail** — any PNG the agent produces (schematic, die map, 3D
  package, generated image) appears as a thumbnail; click to enlarge.
- **Keyboard** — `Ctrl+T` toggle thinking, `Ctrl+O` toggle tool output,
  `Ctrl+L` clear, `Enter` send, `Shift+Enter` newline.

## How it connects

The window does **not** call the model directly. It owns a child process:

```
Tauri (Rust)  ──spawn──►  py -3.15 coal.py --json-repl
      ▲                          │
      └──── JSON events ─────────┘   (ready / start / thinking / token /
                                      tool / answer / done / error)
```

That is the same protocol the terminal UI uses, so both clients stay in sync.

## Build

```powershell
# icon (once)
py -3.15 desktop\make_icon.py

# Rust shell  (first build downloads Tauri; several minutes)
cd desktop\src-tauri
cargo build --release

# Go launcher
cd ..\launcher
go build -o coal-launcher.exe .
```

## Run

```powershell
.\desktop\coal-launcher.exe
```

No environment variables needed. The launcher resolves the API key from:

1. `NEBIUS_API_KEY` in the environment, or
2. `%USERPROFILE%\.coal\nebius.key` — one line, no quotes

If a key is found it configures Nebius automatically:

```
[i] provider : nebius
[i] endpoint : https://api.studio.nebius.com/v1
[i] model    : nvidia/nemotron-3-super-120b-a12b
```

With no key it falls back to the local model and says so.

The launcher also verifies Python, finds the agent directory, and sets
`COAL_NO_35B=1` so the 19.7 GB model is never loaded. If
`coal-desktop.exe` is not next to it, it looks in
`src-tauri/target/{debug,release}`.

## Why Rust for the shell

The shell only has to own a process and forward lines. Rust gives a small,
dependency-light binary with no runtime to install, and Tauri uses the
WebView2 runtime already present on Windows.

## Why Go for the launcher

One static executable that fails loudly with a readable message when Python,
the agent directory, or the key is missing — instead of opening an empty
window and looking broken.
