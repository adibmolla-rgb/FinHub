//! FinHub desktop shell.
//!
//! On launch it starts the local backend (a Python service that fronts the data, agent and simulator
//! engines) unless one is already running, and stops it again when the window closes.

use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};

const BACKEND_ADDR: &str = "127.0.0.1:8765";

struct Backend(Mutex<Option<Child>>);

fn backend_running() -> bool {
    TcpStream::connect_timeout(&BACKEND_ADDR.parse().unwrap(), Duration::from_millis(300)).is_ok()
}

/// Where the backend source lives. `FINHUB_BACKEND_DIR` overrides it; otherwise use the repo layout.
fn backend_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("FINHUB_BACKEND_DIR") {
        return PathBuf::from(dir);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../backend")
}

/// The backend's own interpreter entry point inside its virtual environment.
fn backend_entry(dir: &Path) -> PathBuf {
    if cfg!(windows) {
        dir.join(".venv/Scripts/finhub-backend.exe")
    } else {
        dir.join(".venv/bin/finhub-backend")
    }
}

/// Start the backend. The environment is prepared with `uv sync`, then the backend executable is run
/// directly (not through `uv run`, whose extra wrapper process would survive a kill and leave Python
/// orphaned). The backend also receives our PID and exits by itself if this app disappears.
///
/// Bundling a self-managed Python runtime for installed builds is the next milestone; until then this
/// requires `uv` on PATH (https://docs.astral.sh/uv/).
fn spawn_backend() -> Option<Child> {
    if backend_running() {
        log::info!("backend already running on {BACKEND_ADDR}; reusing it");
        return None;
    }
    let dir = backend_dir();
    match Command::new("uv").args(["sync", "--quiet"]).current_dir(&dir).status() {
        Ok(status) if status.success() => {}
        Ok(status) => log::warn!("`uv sync` exited with {status}; trying to start the backend anyway"),
        Err(err) => log::warn!("could not run `uv sync` ({err}); trying to start the backend anyway"),
    }
    let entry = backend_entry(&dir);
    match Command::new(&entry)
        .current_dir(&dir)
        .env("FINHUB_PARENT_PID", std::process::id().to_string())
        .spawn()
    {
        Ok(child) => {
            log::info!("started backend (pid {}) from {}", child.id(), entry.display());
            Some(child)
        }
        Err(err) => {
            log::error!("could not start backend {}: {err}", entry.display());
            None
        }
    }
}

fn stop_backend(handle: &tauri::AppHandle) {
    if let Some(mut child) = handle.state::<Backend>().0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
        log::info!("stopped backend");
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .setup(|app| {
            app.manage(Backend(Mutex::new(spawn_backend())));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building FinHub");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_backend(handle);
        }
    });
}
