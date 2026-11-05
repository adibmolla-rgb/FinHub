//! FinHub desktop shell.
//!
//! Starts the local Python backend when the app opens and stops it when the app closes.
//!
//! * Installed builds (release): the backend and engine sources ship read-only inside the app's
//!   resources, together with a copy of `uv`. On first launch `uv` downloads a private Python and builds
//!   the backend's environment in the user's app-data folder; later launches reuse it. Engines are
//!   installed into app data too, by the backend, on demand.
//! * Development (debug): uses the repository checkout and the `uv` on PATH.
//!
//! The UI polls the `backend_phase` command to show progress while this happens.

use std::fs::{self, File};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde::Serialize;
use tauri::{Manager, RunEvent};

const BACKEND_ADDR: &str = "127.0.0.1:8765";

#[derive(Clone, Serialize, Default)]
struct Phase {
    /// starting | preparing | launching | running | external | failed
    phase: String,
    detail: String,
    logs_dir: Option<String>,
}

#[derive(Default)]
struct BackendState {
    child: Option<Child>,
    phase: Phase,
}

type Shared = Arc<Mutex<BackendState>>;

struct Layout {
    /// Backend project (pyproject.toml, uv.lock, src/).
    backend_src: PathBuf,
    /// Engine projects (engines/<id>/).
    engines_src: PathBuf,
    /// Where the backend's virtual environment lives.
    backend_env: PathBuf,
    /// Where engine environments live (None = engines/<id>/.venv, the dev layout).
    engine_envs: Option<PathBuf>,
    uv: PathBuf,
    logs: PathBuf,
    /// Installed builds install the data engine automatically on first launch.
    auto_install: bool,
    /// FinHub's writable data folder (agent settings, agent sessions). None = backend default.
    data: Option<PathBuf>,
}

fn backend_running() -> bool {
    TcpStream::connect_timeout(&BACKEND_ADDR.parse().unwrap(), Duration::from_millis(300)).is_ok()
}

fn exe_name(name: &str) -> String {
    if cfg!(windows) { format!("{name}.exe") } else { name.to_string() }
}

fn venv_bin(env: &Path, name: &str) -> PathBuf {
    env.join(if cfg!(windows) { "Scripts" } else { "bin" }).join(exe_name(name))
}

/// On Windows, console programs started from a GUI app open a console window unless told not to.
fn hidden(cmd: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd
}

fn layout(app: &tauri::AppHandle) -> Result<Layout, String> {
    let bundled = !cfg!(debug_assertions) || std::env::var("FINHUB_BUNDLED").as_deref() == Ok("1");
    if !bundled {
        let root = std::env::var("FINHUB_REPO")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."));
        let logs = root.join("app/src-tauri/target/logs");
        return Ok(Layout {
            backend_src: root.join("backend"),
            engines_src: root.join("engines"),
            backend_env: root.join("backend/.venv"),
            engine_envs: None,
            uv: PathBuf::from("uv"),
            logs,
            auto_install: false,
            data: None,
        });
    }
    let resources = app.path().resource_dir().map_err(|e| format!("no resource dir: {e}"))?.join("python");
    let data = app.path().app_local_data_dir().map_err(|e| format!("no app data dir: {e}"))?;
    let exe_dir = std::env::current_exe()
        .map_err(|e| format!("cannot locate FinHub executable: {e}"))?
        .parent()
        .map(Path::to_path_buf)
        .ok_or("executable has no parent folder")?;
    let bundled_uv = exe_dir.join(exe_name("finhub-uv"));
    Ok(Layout {
        backend_src: resources.join("backend"),
        engines_src: resources.join("engines"),
        backend_env: data.join("envs").join("backend"),
        engine_envs: Some(data.join("envs").join("engines")),
        uv: if bundled_uv.exists() { bundled_uv } else { PathBuf::from("uv") },
        logs: data.join("logs"),
        auto_install: true,
        data: Some(data),
    })
}

fn set_phase(state: &Shared, phase: &str, detail: impl Into<String>, logs: &Path) {
    let detail = detail.into();
    log::info!("backend: {phase} — {detail}");
    state.lock().unwrap().phase = Phase {
        phase: phase.into(),
        detail,
        logs_dir: Some(logs.display().to_string()),
    };
}

fn log_file(logs: &Path, name: &str) -> Stdio {
    match File::create(logs.join(name)) {
        Ok(f) => Stdio::from(f),
        Err(_) => Stdio::null(),
    }
}

/// Prepare the environment and start the backend. Runs on a background thread so the window opens
/// immediately; progress goes into `state` for the UI.
fn start_backend(app: tauri::AppHandle, state: Shared) {
    let fallback_logs = PathBuf::from(".");
    if backend_running() {
        set_phase(&state, "external", "A backend is already running on 127.0.0.1:8765; using it.", &fallback_logs);
        return;
    }
    let l = match layout(&app) {
        Ok(l) => l,
        Err(e) => return set_phase(&state, "failed", e, &fallback_logs),
    };
    let _ = fs::create_dir_all(&l.logs);

    set_phase(
        &state,
        "preparing",
        "Setting up FinHub's Python environment. The first launch downloads Python and takes a minute or two.",
        &l.logs,
    );
    let mut sync = Command::new(&l.uv);
    sync.args(["sync", "--frozen", "--no-dev", "--no-editable", "--project"])
        .arg(&l.backend_src)
        .env("UV_PROJECT_ENVIRONMENT", &l.backend_env)
        .stdout(log_file(&l.logs, "backend-setup.log"))
        .stderr(log_file(&l.logs, "backend-setup.err.log"));
    match hidden(&mut sync).status() {
        Ok(s) if s.success() => {}
        Ok(s) => {
            return set_phase(&state, "failed", format!("Setting up Python failed (uv exited with {s}). See backend-setup.err.log."), &l.logs);
        }
        Err(e) => {
            return set_phase(&state, "failed", format!("Could not run uv ({}): {e}", l.uv.display()), &l.logs);
        }
    }

    set_phase(&state, "launching", "Starting the backend…", &l.logs);
    let entry = venv_bin(&l.backend_env, "finhub-backend");
    let mut cmd = Command::new(&entry);
    cmd.current_dir(&l.logs)
        .env("FINHUB_PARENT_PID", std::process::id().to_string())
        .env("FINHUB_ENGINES_DIR", &l.engines_src)
        .env("FINHUB_UV", &l.uv)
        .stdout(log_file(&l.logs, "backend.log"))
        .stderr(log_file(&l.logs, "backend.err.log"));
    if let Some(envs) = &l.engine_envs {
        cmd.env("FINHUB_ENGINE_ENVS_DIR", envs);
    }
    if l.auto_install {
        cmd.env("FINHUB_AUTO_INSTALL", "1");
    }
    if let Some(data) = &l.data {
        cmd.env("FINHUB_DATA_DIR", data);
    }
    match hidden(&mut cmd).spawn() {
        Ok(child) => {
            log::info!("started backend (pid {}) from {}", child.id(), entry.display());
            state.lock().unwrap().child = Some(child);
        }
        Err(e) => return set_phase(&state, "failed", format!("Could not start {}: {e}", entry.display()), &l.logs),
    }

    for _ in 0..120 {
        if backend_running() {
            return set_phase(&state, "running", "Backend running.", &l.logs);
        }
        let exited = state.lock().unwrap().child.as_mut().and_then(|c| c.try_wait().ok().flatten());
        if let Some(status) = exited {
            return set_phase(&state, "failed", format!("The backend exited ({status}). See backend.err.log."), &l.logs);
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    set_phase(&state, "failed", "The backend did not start listening within 60 seconds. See backend.err.log.", &l.logs);
}

fn stop_backend(state: &Shared) {
    if let Some(mut child) = state.lock().unwrap().child.take() {
        let _ = child.kill();
        let _ = child.wait();
        log::info!("stopped backend");
    }
}

#[tauri::command]
fn backend_phase(state: tauri::State<'_, Shared>) -> Phase {
    state.lock().unwrap().phase.clone()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let shared: Shared = Arc::new(Mutex::new(BackendState {
        child: None,
        phase: Phase { phase: "starting".into(), detail: "Starting…".into(), logs_dir: None },
    }));

    let app = tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .manage(shared.clone())
        .invoke_handler(tauri::generate_handler![backend_phase])
        .setup(move |app| {
            let handle = app.handle().clone();
            let state = shared.clone();
            std::thread::spawn(move || start_backend(handle, state));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building FinHub");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_backend(&handle.state::<Shared>());
        }
    });
}
