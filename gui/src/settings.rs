//! What the user configures once: where the checkout is and how to reach the
//! simulator. Stored as TOML in the per-OS config directory.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BackendKind {
    /// A Linux checkout where `./setup.sh` has run: `.venv/bin/python` directly.
    Native,
    /// The `hetero-sim` image, with the workspace's data directories mounted.
    /// The only option on macOS and Windows, since GVSoC builds on Linux only.
    Docker,
}

impl BackendKind {
    pub const ALL: [BackendKind; 2] = [BackendKind::Docker, BackendKind::Native];
}

impl std::fmt::Display for BackendKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            BackendKind::Native => "Native (Linux checkout with setup.sh)",
            BackendKind::Docker => "Docker image",
        })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub backend: BackendKind,
    /// A clone of the hetero-sim repository. With Docker it needs no setup.sh:
    /// only `ops/`, `results/` and `work/` are used from it (plus the sources,
    /// when `mount_sources` is on).
    pub workspace: PathBuf,
    pub docker_image: String,
    /// Mount `pipeline/`, `runtime/` and `targets/` from the workspace over the
    /// image's copies. For an image older than the checkout's Python and C
    /// sources; the compiled GVSoC still comes from the image.
    pub mount_sources: bool,
    /// Jobs run at once. Runs of the same op share a work directory, so the
    /// safe default is one.
    pub concurrency: usize,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            backend: if cfg!(target_os = "linux") && guess_workspace().join(".venv").exists() {
                BackendKind::Native
            } else {
                BackendKind::Docker
            },
            workspace: guess_workspace(),
            docker_image: "hetero-sim".into(),
            mount_sources: false,
            concurrency: 1,
        }
    }
}

/// The repository this binary was started from, if it was started from one
/// (`cargo run` inside `gui/`, or the binary next to a checkout).
fn guess_workspace() -> PathBuf {
    let cwd = std::env::current_dir().unwrap_or_default();
    for cand in cwd.ancestors() {
        if is_workspace(cand) {
            return cand.to_path_buf();
        }
    }
    cwd
}

pub fn is_workspace(p: &Path) -> bool {
    p.join("pipeline").join("run.py").is_file()
}

/// Set by `--config FILE`, for a portable or throwaway configuration.
pub static CONFIG_OVERRIDE: std::sync::OnceLock<PathBuf> = std::sync::OnceLock::new();

fn config_path() -> Option<PathBuf> {
    if let Some(p) = CONFIG_OVERRIDE.get() {
        return Some(p.clone());
    }
    directories::ProjectDirs::from("", "", "hetero-gui").map(|d| d.config_dir().join("settings.toml"))
}

impl Settings {
    pub fn load() -> Settings {
        config_path()
            .and_then(|p| std::fs::read_to_string(p).ok())
            .and_then(|s| toml::from_str(&s).ok())
            .unwrap_or_default()
    }

    pub fn save(&self) -> anyhow::Result<()> {
        let path = config_path().ok_or_else(|| anyhow::anyhow!("no config directory on this system"))?;
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        std::fs::write(path, toml::to_string_pretty(self)?)?;
        Ok(())
    }
}
