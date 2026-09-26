//! Long-running pipeline commands: a FIFO queue, each job's live log, and
//! what to do with its output when it finishes.

use crate::backend::{self, Invocation, Launch};
use crate::settings::Settings;
use iced::futures::{SinkExt, Stream};
use std::collections::VecDeque;
use std::time::Instant;
use tokio::io::{AsyncBufReadExt, BufReader};

const LOG_LINES: usize = 4000;

/// What a finished job feeds back into.
#[derive(Debug, Clone, PartialEq)]
pub enum JobKind {
    /// make_op / mnist.py / kws.py: refresh the op list afterwards.
    MakeOp,
    /// A run.py or run_hetero.py run writing its result here (workspace-relative).
    Run { out: String },
    /// A sweep writing into this directory (workspace-relative).
    Sweep { out: String },
}

#[derive(Debug, Clone, PartialEq)]
pub enum JobStatus {
    Queued,
    Running,
    Finished(Option<i32>),
    Failed(String),
    Cancelled,
}

impl JobStatus {
    pub fn is_active(&self) -> bool {
        matches!(self, JobStatus::Queued | JobStatus::Running)
    }

    pub fn label(&self) -> String {
        match self {
            JobStatus::Queued => "queued".into(),
            JobStatus::Running => "running".into(),
            JobStatus::Finished(Some(0)) => "done".into(),
            JobStatus::Finished(Some(c)) => format!("exit {c}"),
            JobStatus::Finished(None) => "killed".into(),
            JobStatus::Failed(_) => "failed to start".into(),
            JobStatus::Cancelled => "cancelled".into(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Job {
    pub id: u64,
    pub title: String,
    pub kind: JobKind,
    pub invocation: Invocation,
    pub launch: Option<Launch>,
    pub status: JobStatus,
    pub pid: Option<u32>,
    pub log: VecDeque<String>,
    pub started: Option<Instant>,
    pub ended: Option<Instant>,
    /// (done, total) when the job reports it.
    pub progress: Option<(usize, usize)>,
    /// What it is doing right now, when it says.
    pub phase: String,
}

impl Job {
    pub fn new(id: u64, title: String, kind: JobKind, invocation: Invocation) -> Job {
        Job {
            id,
            title,
            kind,
            invocation,
            launch: None,
            status: JobStatus::Queued,
            pid: None,
            log: VecDeque::new(),
            started: None,
            ended: None,
            progress: None,
            phase: String::new(),
        }
    }

    pub fn push_line(&mut self, line: String) {
        if self.log.len() == LOG_LINES {
            self.log.pop_front();
        }
        self.log.push_back(line);
    }

    pub fn elapsed(&self) -> Option<std::time::Duration> {
        self.started.map(|s| self.ended.unwrap_or_else(Instant::now) - s)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Channel {
    Stdout,
    Stderr,
}

#[derive(Debug, Clone)]
pub enum JobEvent {
    Started { pid: Option<u32> },
    Line(Channel, String),
    Exited(Option<i32>),
    SpawnFailed(String),
}

/// Start `launch` and stream what it prints, then its exit code.
pub fn run(settings: Settings, launch: Launch) -> impl Stream<Item = JobEvent> {
    iced::stream::channel(256, async move |mut tx| {
        if let Err(e) = backend::prepare_workspace(&settings) {
            let _ = tx.send(JobEvent::SpawnFailed(format!("preparing the workspace: {e}"))).await;
            return;
        }
        let mut child = match backend::command(&launch).spawn() {
            Ok(c) => c,
            Err(e) => {
                let _ = tx.send(JobEvent::SpawnFailed(format!("could not start {}: {e}", launch.program))).await;
                return;
            }
        };
        let _ = tx.send(JobEvent::Started { pid: child.id() }).await;

        let stdout = child.stdout.take().map(|s| BufReader::new(s).lines());
        let stderr = child.stderr.take().map(|s| BufReader::new(s).lines());
        let (mut out, mut err) = (stdout.unwrap(), stderr.unwrap());
        let (mut out_open, mut err_open) = (true, true);
        while out_open || err_open {
            tokio::select! {
                l = out.next_line(), if out_open => match l {
                    Ok(Some(l)) => { let _ = tx.send(JobEvent::Line(Channel::Stdout, l)).await; }
                    _ => out_open = false,
                },
                l = err.next_line(), if err_open => match l {
                    Ok(Some(l)) => { let _ = tx.send(JobEvent::Line(Channel::Stderr, l)).await; }
                    _ => err_open = false,
                },
            }
        }
        let code = child.wait().await.ok().and_then(|s| s.code());
        let _ = tx.send(JobEvent::Exited(code)).await;
    })
}

/// The `[i/n]` style counters run.py and make_op print, as progress.
pub fn parse_progress(line: &str) -> Option<(usize, usize)> {
    // run.py: "[2/3] build + [3/3] simulate: spatz (2/4)" -- the trailing
    // (i/n) is the core counter, the one that moves.
    let tail = line.rsplit_once('(').map(|(_, t)| t)?;
    let (a, b) = tail.trim_end_matches(')').split_once('/')?;
    Some((a.trim().parse().ok()?, b.trim().parse().ok()?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn progress_from_run_py_lines() {
        assert_eq!(parse_progress("[2/3] build + [3/3] simulate: spatz (2/4)"), Some((2, 4)));
        assert_eq!(parse_progress("[1/3] Deeploy: MatMul/network.onnx -> C  (work/x/gen)"), None);
        assert_eq!(parse_progress("plain line"), None);
    }

    #[test]
    fn log_is_bounded() {
        let mut j = Job::new(1, "t".into(), JobKind::MakeOp, Invocation::new("x"));
        for i in 0..LOG_LINES + 10 {
            j.push_line(i.to_string());
        }
        assert_eq!(j.log.len(), LOG_LINES);
        assert_eq!(j.log.front().unwrap(), "10");
    }
}
