//! End-to-end checks of the job machinery against a real backend.
//!
//! Ignored by default: they need Docker and a built image. Run with
//!
//!     HETERO_GUI_TEST_IMAGE=hetero-sim:gui cargo test -- --ignored --test-threads=1

use crate::backend::{self, Invocation};
use crate::jobs::{self, JobEvent};
use crate::model::RunResult;
use crate::settings::{BackendKind, Settings};
use iced::futures::StreamExt;
use std::path::PathBuf;
use std::time::Duration;

fn settings() -> Settings {
    Settings {
        backend: BackendKind::Docker,
        workspace: PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/..")).canonicalize().unwrap(),
        docker_image: std::env::var("HETERO_GUI_TEST_IMAGE").unwrap_or_else(|_| "hetero-sim:gui".into()),
        mount_sources: false,
        concurrency: 1,
    }
}

#[cfg(target_os = "linux")]
fn assert_owned_by_me(p: &std::path::Path) {
    use std::os::unix::fs::MetadataExt;
    let me = std::fs::metadata(env!("CARGO_MANIFEST_DIR")).unwrap().uid();
    let got = std::fs::metadata(p).unwrap().uid();
    assert_eq!(got, me, "{} is owned by uid {got}, not {me}", p.display());
}

#[tokio::test]
#[ignore]
async fn query_reports_a_ready_pipeline() {
    let out = backend::capture(settings(), Invocation::new("pipeline/gui_query.py").arg("env")).await.unwrap();
    let env: crate::model::EnvReport = serde_json::from_str(out.trim()).unwrap();
    assert!(env.ready, "{env:?}");
}

#[tokio::test]
#[ignore]
async fn run_job_streams_output_and_writes_its_result() {
    let s = settings();
    let rel = "work/gui/e2e/mymatmul.json";
    let _ = std::fs::remove_file(s.workspace.join(rel));
    let inv = Invocation::new("pipeline/run.py").args(["ops/mymatmul", "--cores", "cva6,spatz", "--out", rel]);
    let launch = backend::launch(&s, &inv, 1);
    let events: Vec<JobEvent> =
        tokio::time::timeout(Duration::from_secs(600), jobs::run(s.clone(), launch).collect()).await.unwrap();

    assert!(matches!(events.first(), Some(JobEvent::Started { .. })));
    let lines: Vec<&str> =
        events.iter().filter_map(|e| if let JobEvent::Line(_, l) = e { Some(l.as_str()) } else { None }).collect();
    assert!(lines.iter().any(|l| l.contains("simulate: spatz (2/2)")), "{lines:#?}");
    assert!(matches!(events.last(), Some(JobEvent::Exited(Some(0)))), "{:?}", events.last());

    let RunResult::Isolated(r) = RunResult::parse(&std::fs::read_to_string(s.workspace.join(rel)).unwrap()).unwrap()
    else {
        panic!()
    };
    assert_eq!(r.results.len(), 2);
    assert!(r.results.iter().all(|c| c.status == "ok" && c.cycles.is_some()), "{r:?}");
    #[cfg(target_os = "linux")]
    assert_owned_by_me(&s.workspace.join(rel));
}

#[tokio::test]
#[ignore]
async fn cancel_stops_the_container_and_hands_files_back() {
    let s = settings();
    let out = "work/gui/e2e/cancelled-sweep";
    let dir = s.workspace.join(out);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("designs.json"), r#"[{"SPATZ_NB_LANES": 8}]"#).unwrap();
    let inv = Invocation::new("pipeline/sweep/run.py").args([
        "--models",
        "ops/mnist",
        "--designs",
        &format!("{out}/designs.json"),
        "-o",
        out,
        "--images",
        "16",
        "--progress",
        "json",
    ]);
    let launch = backend::launch(&s, &inv, 2);
    let name = launch.container.clone().unwrap();
    let mut stream = Box::pin(jobs::run(s.clone(), launch.clone()));

    // Wait until the sweep is under way, then cancel.
    let mut pid = None;
    loop {
        match tokio::time::timeout(Duration::from_secs(120), stream.next()).await.unwrap() {
            Some(JobEvent::Started { pid: p }) => pid = p,
            Some(JobEvent::Line(_, l)) if l.contains("\"phase\"") => break,
            Some(JobEvent::Exited(c)) => panic!("exited before it could be cancelled: {c:?}"),
            Some(_) => {}
            None => panic!("stream ended"),
        }
    }
    let t0 = std::time::Instant::now();
    tokio::spawn(backend::cancel(launch, pid));
    let code = loop {
        match tokio::time::timeout(Duration::from_secs(60), stream.next()).await.expect("did not stop within 60 s") {
            Some(JobEvent::Exited(c)) => break c,
            Some(_) => {}
            None => panic!("stream ended without an exit"),
        }
    };
    assert_ne!(code, Some(0));
    assert!(t0.elapsed() < Duration::from_secs(30), "took {:?}", t0.elapsed());

    let ps =
        std::process::Command::new("docker").args(["ps", "-aq", "--filter", &format!("name={name}")]).output().unwrap();
    assert!(String::from_utf8_lossy(&ps.stdout).trim().is_empty(), "container {name} still exists");
    #[cfg(target_os = "linux")]
    for e in walk(&dir) {
        assert_owned_by_me(&e);
    }
}

#[cfg(target_os = "linux")]
fn walk(p: &std::path::Path) -> Vec<PathBuf> {
    let mut out = vec![p.to_path_buf()];
    if p.is_dir() {
        for e in std::fs::read_dir(p).unwrap().flatten() {
            out.extend(walk(&e.path()));
        }
    }
    out
}
