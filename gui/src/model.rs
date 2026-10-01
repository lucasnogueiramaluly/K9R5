//! The JSON the pipeline writes, as Rust types.
//!
//! Lenient on purpose: every field that a failed or older run may leave out is
//! optional or defaulted, so an odd file shows what it has instead of failing
//! to load.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::BTreeMap;

// --- gui_query.py ------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct EnvReport {
    pub python: String,
    pub have: BTreeMap<String, bool>,
    pub ready: bool,
    pub build_key: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct OpInfo {
    pub name: String,
    /// What to pass to the drivers, workspace-relative.
    pub arg: String,
    /// "workspace" or "deeploy".
    pub source: String,
    pub app: Option<String>,
    #[serde(default)]
    pub has_inputs: bool,
}

#[derive(Debug, Clone, Deserialize)]
pub struct OpsList {
    pub ops: Vec<OpInfo>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TensorInfo {
    pub name: String,
    pub dtype: String,
    pub shape: Vec<Value>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Inspect {
    #[serde(default)]
    pub inputs: Vec<TensorInfo>,
    #[serde(default)]
    pub outputs: Vec<TensorInfo>,
    #[serde(default)]
    pub nodes: usize,
    /// Insertion-ordered (most frequent first) thanks to `preserve_order`.
    #[serde(default)]
    pub op_types: Map<String, Value>,
    #[serde(default)]
    pub initializers: usize,
    pub app: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Knobs {
    /// Knob -> baseline, in design.py's order.
    pub defaults: Map<String, Value>,
    pub build_time: Vec<String>,
    pub ofat: Map<String, Value>,
}

impl Knobs {
    pub fn default_of(&self, knob: &str) -> Option<i64> {
        self.defaults.get(knob).and_then(Value::as_i64)
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct DesignCheck {
    pub slug: Option<String>,
    #[serde(default)]
    pub reasons: Vec<String>,
    #[serde(default)]
    pub needs_build: bool,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Validation {
    pub designs: Vec<DesignCheck>,
}

// --- run.py ------------------------------------------------------------------

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct Cache {
    pub cache: String,
    #[serde(default)]
    pub accesses: u64,
    #[serde(default)]
    pub misses: u64,
    pub hit_rate: Option<f64>,
    #[serde(default)]
    pub latency_cycles: u64,
    pub dynamic_pj: Option<f64>,
}

impl Cache {
    pub fn hit_rate(&self) -> Option<f64> {
        self.hit_rate.or_else(|| (self.accesses > 0).then(|| 1.0 - self.misses as f64 / self.accesses as f64))
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct CoreResult {
    pub core: String,
    pub status: String,
    pub cycles: Option<u64>,
    pub maxdiff: Option<f64>,
    pub sim_wall_s: Option<f64>,
    #[serde(default)]
    pub caches: Vec<Cache>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct IsolatedResult {
    pub op: String,
    #[serde(default)]
    pub memory: String,
    #[serde(default)]
    pub spatz_kernels: String,
    /// Main-memory device (`--dram`); absent for the fixed-latency model.
    #[serde(default)]
    pub dram: String,
    pub results: Vec<CoreResult>,
}

impl IsolatedResult {
    pub fn baseline(&self) -> Option<u64> {
        self.results.iter().find(|r| r.core == "cva6").and_then(|r| r.cycles)
    }
}

// --- run_hetero.py -----------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct NodeMap {
    pub node: String,
    pub op: String,
    pub engine: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Mapping {
    pub pin: Option<String>,
    #[serde(default = "default_host")]
    pub host: String,
    #[serde(default)]
    pub nodes: Vec<NodeMap>,
    pub frontend: Option<String>,
    #[serde(default)]
    pub serial: bool,
}

fn default_host() -> String {
    "cva6".into()
}

#[derive(Debug, Clone, Deserialize)]
pub struct HeteroRun {
    pub status: String,
    pub wall_s: Option<f64>,
    pub cycles: Option<u64>,
    pub cycles_per_image: Option<u64>,
    pub cycles_per_clip: Option<u64>,
    pub accuracy: Option<f64>,
    pub maxdiff: Option<f64>,
    pub offload_failures: Option<u64>,
    #[serde(default)]
    pub per_engine_cycles: BTreeMap<String, u64>,
    #[serde(default)]
    pub caches: Vec<Cache>,
    #[serde(default)]
    pub log_tail: Vec<String>,
}

impl HeteroRun {
    /// The figure to compare on: per sample for an application, else total.
    pub fn headline(&self) -> Option<(u64, &'static str)> {
        self.cycles_per_image
            .map(|c| (c, "cycles/image"))
            .or(self.cycles_per_clip.map(|c| (c, "cycles/clip")))
            .or(self.cycles.map(|c| (c, "cycles")))
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct HeteroResult {
    pub op: String,
    pub mapping: Mapping,
    pub result: HeteroRun,
}

impl HeteroResult {
    pub fn variant(&self) -> String {
        let mut s = format!(
            "{} host, {}",
            self.mapping.host,
            self.mapping.pin.as_deref().map_or("mapped".to_string(), |p| format!("pinned {p}"))
        );
        if let Some(fe) = &self.mapping.frontend {
            s += &format!(", fe {fe}");
        }
        if self.mapping.serial {
            s += ", serial";
        }
        s
    }
}

/// Either kind of result file, told apart by shape.
#[derive(Debug, Clone)]
pub enum RunResult {
    Isolated(IsolatedResult),
    Hetero(Box<HeteroResult>),
}

impl RunResult {
    pub fn parse(text: &str) -> Result<RunResult, String> {
        let v: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
        if v.get("results").is_some() {
            serde_json::from_value(v).map(RunResult::Isolated).map_err(|e| e.to_string())
        } else if v.get("mapping").is_some() {
            serde_json::from_value(v).map(|h| RunResult::Hetero(Box::new(h))).map_err(|e| e.to_string())
        } else {
            Err("neither a run.py nor a run_hetero.py result".into())
        }
    }
}

// --- sweep -------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SweepRow {
    pub design_slug: String,
    #[serde(default)]
    pub design: Map<String, Value>,
    pub model: String,
    #[serde(default)]
    pub host: String,
    pub status: String,
    #[serde(default)]
    pub reasons: Vec<String>,
    pub cycles: Option<u64>,
    pub cycles_per_image: Option<u64>,
    pub cycles_per_clip: Option<u64>,
    pub accuracy: Option<f64>,
    pub wall_s: Option<f64>,
    pub area_au: Option<f64>,
    pub cache_dynamic_pj: Option<f64>,
}

impl SweepRow {
    /// Same precedence as report.py's cycles_of.
    pub fn cycles(&self) -> Option<u64> {
        self.cycles_per_image.or(self.cycles_per_clip).or(self.cycles).filter(|c| *c > 0)
    }

    /// The knobs this row moved away from the given baseline.
    pub fn diff(&self, baseline: &Map<String, Value>) -> Vec<(String, i64)> {
        self.design
            .iter()
            .filter(|(k, v)| baseline.get(*k) != Some(*v))
            .filter_map(|(k, v)| v.as_i64().map(|v| (k.clone(), v)))
            .collect()
    }
}

pub fn parse_jsonl(text: &str) -> Vec<SweepRow> {
    text.lines().filter(|l| !l.trim().is_empty()).filter_map(|l| serde_json::from_str(l).ok()).collect()
}

/// One line of `sweep/run.py --progress json`.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "event", rename_all = "lowercase")]
pub enum SweepEvent {
    Start { total: usize },
    Cell { index: usize, cell: String },
    Phase { phase: String },
    Row { done: usize, total: usize, eta_s: Option<f64>, row: Box<SweepRow> },
    Done { done: usize, total: usize },
}

// --- report.py --json --------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct SensPoint {
    pub value: i64,
    pub cycles: u64,
    pub pct: f64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SensKnob {
    pub knob: String,
    pub base_value: Value,
    pub points: Vec<SensPoint>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Sensitivity {
    pub model: String,
    pub base_cycles: u64,
    pub knobs: Vec<SensKnob>,
    #[serde(default)]
    pub flat: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct FrontPoint {
    pub key: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Pareto {
    pub objectives: Vec<String>,
    pub points: usize,
    pub front: Vec<FrontPoint>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Robustness {
    pub perturb: f64,
    pub sourced: bool,
    #[serde(default)]
    pub front: usize,
    #[serde(default)]
    pub stable: Vec<String>,
    #[serde(default)]
    pub lost: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Report {
    #[serde(default)]
    pub sensitivity: Vec<Sensitivity>,
    pub pareto: Option<Pareto>,
    pub robustness: Option<Robustness>,
}

// --- formatting --------------------------------------------------------------

/// 863 -> "863", 119037 -> "119.0k", 1860000 -> "1.86M", as the README writes them.
pub fn fmt_cycles(c: u64) -> String {
    let f = c as f64;
    if c < 10_000 {
        c.to_string()
    } else if c < 1_000_000 {
        format!("{:.1}k", f / 1e3)
    } else if c < 1_000_000_000 {
        format!("{:.2}M", f / 1e6)
    } else {
        format!("{:.2}G", f / 1e9)
    }
}

/// Knob values read best as sizes when they are sizes.
pub fn fmt_knob_value(knob: &str, v: i64) -> String {
    if knob.ends_with("_SIZE") && v >= 1024 && v % 1024 == 0 {
        if v % (1024 * 1024) == 0 { format!("{}M", v / (1024 * 1024)) } else { format!("{}K", v / 1024) }
    } else {
        v.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/..");

    fn read(rel: &str) -> String {
        std::fs::read_to_string(format!("{ROOT}/{rel}")).unwrap()
    }

    #[test]
    fn parses_committed_isolated_result() {
        let RunResult::Isolated(r) = RunResult::parse(&read("results/Kernels_FP32_MatMul.json")).unwrap() else {
            panic!("wrong kind")
        };
        assert_eq!(r.op, "Kernels_FP32_MatMul");
        assert_eq!(r.baseline(), Some(119037));
        let spatz = r.results.iter().find(|c| c.core == "spatz").unwrap();
        assert_eq!(spatz.cycles, Some(6815));
        assert_eq!(r.results[0].caches.len(), 3);
    }

    #[test]
    fn parses_committed_hetero_results() {
        let RunResult::Hetero(r) = RunResult::parse(&read("results/mnist-hetero.json")).unwrap() else {
            panic!("wrong kind")
        };
        assert_eq!(r.result.headline(), Some((572820, "cycles/image")));
        assert_eq!(r.mapping.nodes[0].engine, "spatz");
        assert_eq!(r.variant(), "cva6 host, mapped");
        let RunResult::Hetero(k) = RunResult::parse(&read("results/kws-hetero-serial.json")).unwrap() else {
            panic!("wrong kind")
        };
        assert!(k.result.headline().unwrap().1 == "cycles/clip");
    }

    #[test]
    fn every_committed_result_parses() {
        for e in std::fs::read_dir(format!("{ROOT}/results")).unwrap() {
            let p = e.unwrap().path();
            if p.extension().is_some_and(|x| x == "json") {
                RunResult::parse(&std::fs::read_to_string(&p).unwrap())
                    .unwrap_or_else(|e| panic!("{}: {e}", p.display()));
            }
        }
    }

    #[test]
    fn parses_sweep_rows_and_events() {
        let rows = parse_jsonl(include_str!("../tests/fixtures/sweep.jsonl"));
        assert_eq!(rows.len(), 24);
        assert_eq!(rows[0].design_slug, "baseline");
        assert_eq!(rows[0].cycles(), Some(576078));
        let diff = rows[1].diff(&rows[0].design);
        assert_eq!(diff, vec![("HOST_NB_LANES".to_string(), 2)]);

        let e: SweepEvent = serde_json::from_str(r#"{"event": "phase", "index": 0, "phase": "calibrating"}"#).unwrap();
        assert!(matches!(e, SweepEvent::Phase { phase, .. } if phase == "calibrating"));
        let line = format!(
            r#"{{"event": "row", "done": 1, "total": 3, "eta_s": null, "row": {}}}"#,
            include_str!("../tests/fixtures/sweep.jsonl").lines().next().unwrap()
        );
        let e: SweepEvent = serde_json::from_str(&line).unwrap();
        assert!(matches!(e, SweepEvent::Row { done: 1, .. }));
    }

    #[test]
    fn formats_like_the_readme() {
        assert_eq!(fmt_cycles(863), "863");
        assert_eq!(fmt_cycles(119037), "119.0k");
        assert_eq!(fmt_cycles(1_860_000), "1.86M");
        assert_eq!(fmt_knob_value("L2_SIZE", 2048 * 1024), "2M");
        assert_eq!(fmt_knob_value("TCDM_SIZE", 0x10000), "64K");
        assert_eq!(fmt_knob_value("SPATZ_NB_LANES", 8), "8");
    }
}
