//! How a pipeline command reaches the simulator: natively, or inside the
//! Docker image.
//!
//! Every command runs with the workspace root as its working directory --
//! `/workspace` in the image -- so a workspace-relative path such as
//! `ops/mnist` or `work/gui/runs/x.json` means the same file on both backends,
//! and the GUI reads results straight from the host side of it.

use crate::settings::{BackendKind, Settings};
use std::path::{Path, PathBuf};
use std::process::Stdio;

/// The directories a Docker job mounts from the workspace, always.
const DATA_DIRS: [&str; 3] = ["ops", "results", "work"];
/// Mounted too when `Settings::mount_sources` is on.
const SOURCE_DIRS: [&str; 3] = ["pipeline", "runtime", "targets"];

/// A pipeline script and its arguments, independent of the backend.
#[derive(Debug, Clone, PartialEq)]
pub struct Invocation {
    /// Workspace-relative, e.g. `pipeline/run.py`.
    pub script: String,
    pub args: Vec<String>,
}

impl Invocation {
    pub fn new(script: &str) -> Self {
        Invocation { script: script.into(), args: Vec::new() }
    }

    pub fn arg(mut self, a: impl Into<String>) -> Self {
        self.args.push(a.into());
        self
    }

    pub fn args<I, S>(mut self, it: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<String>,
    {
        self.args.extend(it.into_iter().map(Into::into));
        self
    }

    pub fn flag(self, on: bool, f: &str) -> Self {
        if on { self.arg(f) } else { self }
    }
}

/// A fully resolved process to start.
#[derive(Debug, Clone, PartialEq)]
pub struct Launch {
    pub program: String,
    pub args: Vec<String>,
    pub cwd: PathBuf,
    /// The container name, for a Docker job: what cancelling kills.
    pub container: Option<String>,
}

impl Launch {
    /// A shell-pasteable rendering, for "copy command".
    pub fn display(&self) -> String {
        std::iter::once(self.program.as_str())
            .chain(self.args.iter().map(String::as_str))
            .map(quote)
            .collect::<Vec<_>>()
            .join(" ")
    }
}

fn quote(s: &str) -> String {
    if !s.is_empty() && s.chars().all(|c| c.is_ascii_alphanumeric() || "-_./=:,@+%".contains(c)) {
        s.to_string()
    } else {
        format!("'{}'", s.replace('\'', r"'\''"))
    }
}

/// The wrapper every Docker job runs under.
///
/// The container runs as root -- the image's Python lives under /root, so it
/// cannot run as the host user -- which would leave root-owned files in the
/// host's workspace that the user cannot delete. So it hands them back on the
/// way out, cancelled or not: SIGTERM (what cancel sends) is forwarded to the
/// job, and the chown runs once it has exited.
const DOCKER_WRAPPER: &str = r#"
"$@" &
child=$!
trap 'kill -TERM "$child" 2>/dev/null' TERM INT
wait "$child"; rc=$?
wait "$child" 2>/dev/null
if [ -n "$HES_OWNER" ]; then
  find ops results work ! -user "${HES_OWNER%%:*}" -exec chown -h "$HES_OWNER" {} + 2>/dev/null
fi
exit $rc
"#;

pub fn launch(settings: &Settings, inv: &Invocation, job_id: u64) -> Launch {
    let ws = &settings.workspace;
    match settings.backend {
        BackendKind::Native => Launch {
            program: ws.join(".venv").join("bin").join("python").to_string_lossy().into_owned(),
            args: std::iter::once(inv.script.clone()).chain(inv.args.iter().cloned()).collect(),
            cwd: ws.clone(),
            container: None,
        },
        BackendKind::Docker => {
            let name = format!("hetero-gui-{}-{job_id}", std::process::id());
            let mut args: Vec<String> =
                vec!["run".into(), "--rm".into(), "--name".into(), name.clone(), "-w".into(), "/workspace".into()];
            let mut dirs: Vec<&str> = DATA_DIRS.to_vec();
            if settings.mount_sources {
                dirs.extend(SOURCE_DIRS);
            }
            for d in dirs {
                // --mount rather than -v: it takes Windows paths and paths with
                // spaces or colons without a second parser guessing.
                args.push("--mount".into());
                args.push(format!("type=bind,source={},target=/workspace/{d}", ws.join(d).to_string_lossy()));
            }
            if let Some(owner) = workspace_owner(ws) {
                args.push("-e".into());
                args.push(format!("HES_OWNER={owner}"));
            }
            args.push(settings.docker_image.clone());
            args.extend(["bash".into(), "-c".into(), DOCKER_WRAPPER.into(), "hes-job".into()]);
            args.push("python".into());
            args.push(inv.script.clone());
            args.extend(inv.args.iter().cloned());
            Launch { program: "docker".into(), args, cwd: ws.clone(), container: Some(name) }
        }
    }
}

/// `uid:gid` of the workspace, to hand container output back to. Docker
/// Desktop on macOS and Windows maps ownership itself, so only Linux needs it.
fn workspace_owner(ws: &Path) -> Option<String> {
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::fs::MetadataExt;
        let m = std::fs::metadata(ws).ok()?;
        Some(format!("{}:{}", m.uid(), m.gid()))
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = ws;
        None
    }
}

/// The directories a Docker mount needs must exist, or Docker refuses to start.
pub fn prepare_workspace(settings: &Settings) -> std::io::Result<()> {
    if settings.backend == BackendKind::Docker {
        for d in DATA_DIRS {
            std::fs::create_dir_all(settings.workspace.join(d))?;
        }
    }
    std::fs::create_dir_all(settings.workspace.join("work").join("gui"))
}

pub fn command(l: &Launch) -> tokio::process::Command {
    let mut c = tokio::process::Command::new(&l.program);
    c.args(&l.args)
        .current_dir(&l.cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("PYTHONUNBUFFERED", "1")
        .kill_on_drop(false);
    #[cfg(unix)]
    {
        // Its own process group, so cancelling a native job takes GVSoC and
        // the compilers with it rather than only the Python driver.
        c.process_group(0);
    }
    #[cfg(windows)]
    {
        // No console window flashing up for every docker invocation.
        c.creation_flags(0x0800_0000);
    }
    c
}

/// Run to completion and return stdout; for the quick JSON queries.
pub async fn capture(settings: Settings, inv: Invocation) -> Result<String, String> {
    prepare_workspace(&settings).map_err(|e| e.to_string())?;
    let l = launch(&settings, &inv, next_query_id());
    let out = command(&l).output().await.map_err(|e| format!("could not start {}: {e}", l.program))?;
    let stdout = String::from_utf8_lossy(&out.stdout).into_owned();
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        // gui_query prints {"error": ...} on failure; prefer that.
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(stdout.trim())
            && let Some(e) = v.get("error").and_then(|e| e.as_str())
        {
            return Err(e.to_string());
        }
        let tail: String =
            stderr.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\n");
        return Err(format!("{} exited with {}\n{tail}", inv.script, out.status));
    }
    Ok(stdout)
}

fn next_query_id() -> u64 {
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(1_000_000);
    N.fetch_add(1, Ordering::Relaxed)
}

/// Stop a running job. Docker: SIGTERM to the container, which the wrapper
/// forwards, then a hard kill if it is still there. Native: the process group.
pub async fn cancel(l: Launch, pid: Option<u32>) {
    if let Some(name) = l.container {
        let _ = tokio::process::Command::new("docker").args(["kill", "--signal", "TERM", &name]).output().await;
        tokio::time::sleep(std::time::Duration::from_secs(10)).await;
        let _ = tokio::process::Command::new("docker").args(["kill", &name]).output().await;
    } else if let Some(pid) = pid {
        #[cfg(unix)]
        unsafe {
            libc::killpg(pid as libc::pid_t, libc::SIGTERM);
        }
        #[cfg(not(unix))]
        {
            let _ =
                tokio::process::Command::new("taskkill").args(["/T", "/F", "/PID", &pid.to_string()]).output().await;
        }
    }
}

/// A human summary of whether the backend can run anything, for Settings.
pub async fn check(settings: Settings) -> Vec<(String, Result<String, String>)> {
    let mut out = Vec::new();
    let ws = &settings.workspace;
    out.push((
        "Workspace".into(),
        if crate::settings::is_workspace(ws) {
            Ok(ws.display().to_string())
        } else {
            Err(format!("{} has no pipeline/run.py -- point this at a hetero-sim clone", ws.display()))
        },
    ));
    if settings.backend == BackendKind::Docker {
        let v =
            tokio::process::Command::new("docker").args(["version", "--format", "{{.Server.Version}}"]).output().await;
        out.push((
            "Docker daemon".into(),
            match v {
                Ok(o) if o.status.success() => Ok(format!("server {}", String::from_utf8_lossy(&o.stdout).trim())),
                Ok(o) => Err(String::from_utf8_lossy(&o.stderr).trim().to_string()),
                Err(e) => Err(format!("docker not found: {e}")),
            },
        ));
        let img = tokio::process::Command::new("docker")
            .args(["image", "inspect", "--format", "{{.Created}}", &settings.docker_image])
            .output()
            .await;
        out.push((
            format!("Image {}", settings.docker_image),
            match img {
                Ok(o) if o.status.success() => Ok(format!("built {}", String::from_utf8_lossy(&o.stdout).trim())),
                _ => Err("not found -- run `docker build -t hetero-sim .` in the workspace".into()),
            },
        ));
    }
    out.push((
        "Pipeline".into(),
        match capture(settings.clone(), Invocation::new("pipeline/gui_query.py").arg("env")).await {
            Ok(s) => match serde_json::from_str::<crate::model::EnvReport>(&s) {
                Ok(e) if e.ready => Ok(format!("ready (Python {}, build {})", e.python, e.build_key)),
                Ok(e) => Err(format!(
                    "missing: {}",
                    e.have.iter().filter(|(_, v)| !**v).map(|(k, _)| k.as_str()).collect::<Vec<_>>().join(", ")
                )),
                Err(err) => Err(format!("unexpected answer: {err}")),
            },
            Err(e) => Err(if e.contains("gui_query.py") && e.contains("No such file") {
                format!("{e}\nThe image predates the GUI helpers: rebuild it, or enable \"mount sources\".")
            } else {
                e
            }),
        },
    ));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn settings(kind: BackendKind, ws: &str) -> Settings {
        Settings { backend: kind, workspace: PathBuf::from(ws), ..Settings::default() }
    }

    #[test]
    fn native_runs_the_venv_python_in_the_workspace() {
        let l = launch(&settings(BackendKind::Native, "/src/hs"), &Invocation::new("pipeline/run.py").arg("ops/x"), 1);
        assert_eq!(PathBuf::from(&l.program), PathBuf::from("/src/hs/.venv/bin/python"));
        assert_eq!(l.args, vec!["pipeline/run.py", "ops/x"]);
        assert_eq!(l.cwd, PathBuf::from("/src/hs"));
        assert!(l.container.is_none());
    }

    #[test]
    fn docker_mounts_data_dirs_and_keeps_paths_relative() {
        let mut s = settings(BackendKind::Docker, "/home/me/my ws");
        s.docker_image = "hetero-sim:gui".into();
        let l = launch(&s, &Invocation::new("pipeline/run.py").arg("ops/x").arg("--out").arg("work/gui/r.json"), 7);
        assert_eq!(l.program, "docker");
        let a = l.args.join("\n");
        for d in DATA_DIRS {
            assert!(a.contains(&format!("type=bind,source=/home/me/my ws/{d},target=/workspace/{d}")), "{a}");
        }
        assert!(!a.contains("target=/workspace/pipeline"));
        let img = l.args.iter().position(|x| x == "hetero-sim:gui").unwrap();
        assert_eq!(&l.args[img + 1..img + 3], ["bash", "-c"]);
        assert_eq!(&l.args[l.args.len() - 5..], ["python", "pipeline/run.py", "ops/x", "--out", "work/gui/r.json"]);
        assert!(l.container.unwrap().ends_with("-7"));
    }

    #[test]
    fn docker_mount_sources_adds_source_dirs() {
        let mut s = settings(BackendKind::Docker, "/w");
        s.mount_sources = true;
        let a = launch(&s, &Invocation::new("pipeline/gui_query.py"), 1).args.join("\n");
        for d in SOURCE_DIRS {
            assert!(a.contains(&format!("target=/workspace/{d}")));
        }
    }

    #[test]
    fn windows_workspace_path_goes_into_the_mount_verbatim() {
        let s = settings(BackendKind::Docker, r"C:\Users\me\hetero-sim");
        let a = launch(&s, &Invocation::new("pipeline/gui_query.py"), 1).args.join("\n");
        // Path::join uses the host separator, so only check the prefix survives
        // unmangled (no -v colon splitting to worry about with --mount).
        assert!(a.contains(r"type=bind,source=C:\Users\me\hetero-sim"), "{a}");
    }

    #[test]
    fn display_quotes_what_needs_it() {
        let l = Launch {
            program: "docker".into(),
            args: vec!["a b".into(), "it's".into(), "x=1".into()],
            cwd: PathBuf::new(),
            container: None,
        };
        assert_eq!(l.display(), r"docker 'a b' 'it'\''s' x=1");
    }
}
