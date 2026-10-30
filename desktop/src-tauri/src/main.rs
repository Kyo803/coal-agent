// ROX N desktop shell.
//
// A native window (Tauri + WebView2) that talks to the Python agent over the
// same JSON REPL the terminal UI uses. The Rust side owns the child process
// and forwards its newline-delimited events to the webview.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{Arc, Mutex};

use base64::Engine;
use tauri::{Emitter, Manager};

struct Agent {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
}

type Shared = Arc<Mutex<Agent>>;

/// Where the Python agent lives. ROX_DIR wins; otherwise resolve relative to
/// this crate (desktop/src-tauri -> ../../lm_track/rox_chat).
fn rox_dir() -> std::path::PathBuf {
    if let Ok(d) = std::env::var("ROX_DIR") {
        return std::path::PathBuf::from(d);
    }
    let here = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.join("..").join("..").join("lm_track").join("rox_chat")
}

fn spawn_agent(app: tauri::AppHandle, shared: Shared) {
    let dir = rox_dir();

    // Prefer the py launcher; fall back to python.
    let mut cmd = Command::new("py");
    cmd.args(["-3.15", "-u", "rox.py", "--json-repl"]);

    let mut child = match cmd
        .current_dir(&dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("ROX_NO_35B", "1")
        .env("PYTHONUNBUFFERED", "1")
        .spawn()
    {
        Ok(c) => c,
        Err(_) => {
            let mut cmd2 = Command::new("python");
            cmd2.args(["-u", "rox.py", "--json-repl"]);
            match cmd2
                .current_dir(&dir)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .env("ROX_NO_35B", "1")
                .env("PYTHONUNBUFFERED", "1")
                .spawn()
            {
                Ok(c) => c,
                Err(e) => {
                    let _ = app.emit(
                        "agent-error",
                        format!("could not start the agent in {}: {e}", dir.display()),
                    );
                    return;
                }
            }
        }
    };

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let stdin = child.stdin.take();
    {
        let mut g = shared.lock().unwrap();
        g.child = Some(child);
        g.stdin = stdin;
    }

    if let Some(out) = stdout {
        let app2 = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(out).lines().map_while(Result::ok) {
                let _ = app2.emit("agent", line);
            }
            let _ = app2.emit("agent-exit", "");
        });
    }
    if let Some(err) = stderr {
        let app3 = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                let _ = app3.emit("agent-stderr", line);
            }
        });
    }
}

fn write_line(shared: &tauri::State<'_, Shared>, value: serde_json::Value)
    -> Result<(), String>
{
    let mut g = shared.lock().map_err(|e| e.to_string())?;
    match g.stdin.as_mut() {
        Some(stdin) => {
            writeln!(stdin, "{value}").map_err(|e| e.to_string())?;
            stdin.flush().map_err(|e| e.to_string())?;
            Ok(())
        }
        None => Err("agent is not running".into()),
    }
}

#[tauri::command]
fn send_command(shared: tauri::State<'_, Shared>, text: String) -> Result<(), String> {
    write_line(&shared, serde_json::json!({ "prompt": text }))
}

/// Answer a pending tool approval.
#[tauri::command]
fn send_confirm(shared: tauri::State<'_, Shared>, allow: bool) -> Result<(), String> {
    write_line(&shared, serde_json::json!({ "confirm": allow }))
}

/// Invoke a tool directly (cmd/powershell/file ops) without going through the
/// model. Approval still goes through the normal confirm flow.
#[tauri::command]
fn send_tool(shared: tauri::State<'_, Shared>, tool: String,
             args: serde_json::Value) -> Result<(), String> {
    write_line(&shared, serde_json::json!({ "tool": tool, "args": args }))
}

#[tauri::command]
fn restart_agent(app: tauri::AppHandle, shared: tauri::State<'_, Shared>) -> Result<(), String> {
    {
        let mut g = shared.lock().map_err(|e| e.to_string())?;
        if let Some(mut c) = g.child.take() {
            let _ = c.kill();
        }
        g.stdin = None;
    }
    spawn_agent(app, shared.inner().clone());
    Ok(())
}

/// Read a local PNG and return it as a data URL so the webview can show it.
#[tauri::command]
fn read_image(path: String) -> Result<String, String> {
    let bytes = std::fs::read(&path).map_err(|e| e.to_string())?;
    let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
    Ok(format!("data:image/png;base64,{b64}"))
}

fn main() {
    let shared: Shared = Arc::new(Mutex::new(Agent {
        child: None,
        stdin: None,
    }));

    tauri::Builder::default()
        .manage(shared)
        .invoke_handler(tauri::generate_handler![
            send_command,
            send_confirm,
            send_tool,
            restart_agent,
            read_image
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            let sh = app.state::<Shared>().inner().clone();
            spawn_agent(handle, sh);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running ROX N");
}
