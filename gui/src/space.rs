//! A sweep's definition: which models, which options, and the design space.
//!
//! The GUI expands the space into explicit design points and hands them to
//! `sweep/run.py --designs`; the driver still prepends the baseline, drops
//! repeats by slug, and records invalid points as infeasible.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub type Design = BTreeMap<String, i64>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum SpaceMode {
    /// Baseline plus each knob moved alone: the screening pass, and the only
    /// points report.py's sensitivity table uses.
    #[default]
    Ofat,
    /// Every combination of the listed values.
    Factorial,
    /// Exactly the points written out, one per line.
    List,
}

impl SpaceMode {
    pub const ALL: [SpaceMode; 3] = [SpaceMode::Ofat, SpaceMode::Factorial, SpaceMode::List];
}

impl std::fmt::Display for SpaceMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            SpaceMode::Ofat => "One factor at a time",
            SpaceMode::Factorial => "Full factorial",
            SpaceMode::List => "Explicit list",
        })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SweepSpec {
    pub name: String,
    /// Op directories, workspace-relative.
    pub models: Vec<String>,
    pub host: String,
    pub power: bool,
    pub images: u32,
    /// KWS only: the cluster running the MFCC front-end.
    pub frontend: Option<String>,
    pub serial: bool,
    /// Main-memory device for every cell (`--dram`), "fixed" for the default.
    pub dram: String,
    pub mode: SpaceMode,
    /// Knob -> values as typed ("2,4,8", hex allowed). Kept as text so a
    /// half-typed field survives a save.
    pub values: BTreeMap<String, String>,
    /// List mode: one design per line, `KNOB=v KNOB=v`.
    pub list: String,
}

impl Default for SweepSpec {
    fn default() -> Self {
        SweepSpec {
            name: "sweep".into(),
            models: vec!["ops/mnist".into(), "ops/kws".into()],
            host: "cva6".into(),
            power: false,
            images: 16,
            frontend: None,
            serial: false,
            dram: "fixed".into(),
            mode: SpaceMode::Ofat,
            values: BTreeMap::new(),
            list: String::new(),
        }
    }
}

/// `2, 4, 0x10` -> [2, 4, 16]: the spellings sweep/run.py's int(v, 0) takes,
/// plus `16k` / `1M` for sizes (the GUI writes plain integers to the driver).
pub fn parse_values(s: &str) -> Result<Vec<i64>, String> {
    s.split([',', ' ', ';'])
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(|v| parse_int(v).ok_or_else(|| format!("{v:?} is not an integer")))
        .collect()
}

pub fn parse_int(v: &str) -> Option<i64> {
    let v = v.replace('_', "");
    let (neg, body) = match v.strip_prefix('-') {
        Some(b) => (true, b.to_string()),
        None => (false, v.clone()),
    };
    let lower = body.to_ascii_lowercase();
    let n = if let Some(h) = lower.strip_prefix("0x") {
        i64::from_str_radix(h, 16).ok()
    } else if let Some(o) = lower.strip_prefix("0o") {
        i64::from_str_radix(o, 8).ok()
    } else if let Some(b) = lower.strip_prefix("0b") {
        i64::from_str_radix(b, 2).ok()
    } else if let Some(k) = lower.strip_suffix('k') {
        k.parse::<i64>().ok().map(|x| x * 1024)
    } else if let Some(m) = lower.strip_suffix('m') {
        m.parse::<i64>().ok().map(|x| x * 1024 * 1024)
    } else {
        lower.parse().ok()
    }?;
    Some(if neg { -n } else { n })
}

/// One `KNOB=v KNOB=v` line of list mode.
fn parse_line(line: &str, known: &[String]) -> Result<Design, String> {
    let mut d = Design::new();
    for tok in line.split([' ', ',', '\t']).filter(|t| !t.is_empty()) {
        let (k, v) = tok.split_once('=').ok_or_else(|| format!("{tok:?}: want KNOB=value"))?;
        let k = k.trim().to_ascii_uppercase();
        if !known.is_empty() && !known.contains(&k) {
            return Err(format!("unknown knob {k}"));
        }
        let v = parse_int(v.trim()).ok_or_else(|| format!("{k}: {v:?} is not an integer"))?;
        d.insert(k, v);
    }
    Ok(d)
}

impl SweepSpec {
    /// Knob -> parsed values, only for knobs with something typed.
    pub fn axes(&self) -> Result<Vec<(String, Vec<i64>)>, String> {
        let mut out = Vec::new();
        for (k, s) in &self.values {
            let vs = parse_values(s).map_err(|e| format!("{k}: {e}"))?;
            if !vs.is_empty() {
                out.push((k.clone(), vs));
            }
        }
        Ok(out)
    }

    /// The design points, without the baseline (the driver adds it) and
    /// without exact repeats. `known` is the knob list, for checking names.
    pub fn expand(&self, known: &[String]) -> Result<Vec<Design>, String> {
        let mut designs: Vec<Design> = match self.mode {
            SpaceMode::Ofat => self
                .axes()?
                .into_iter()
                .flat_map(|(k, vs)| vs.into_iter().map(move |v| Design::from([(k.clone(), v)])))
                .collect(),
            SpaceMode::Factorial => {
                let axes = self.axes()?;
                let mut acc = vec![Design::new()];
                for (k, vs) in axes {
                    acc = acc
                        .into_iter()
                        .flat_map(|d| {
                            let k = k.clone();
                            vs.iter().map(move |v| {
                                let mut d = d.clone();
                                d.insert(k.clone(), *v);
                                d
                            })
                        })
                        .collect();
                }
                acc.retain(|d| !d.is_empty());
                acc
            }
            SpaceMode::List => self
                .list
                .lines()
                .map(|l| l.split('#').next().unwrap_or("").trim())
                .enumerate()
                .filter(|(_, l)| !l.is_empty())
                .map(|(i, l)| parse_line(l, known).map_err(|e| format!("line {}: {e}", i + 1)))
                .collect::<Result<_, _>>()?,
        };
        let mut seen = std::collections::HashSet::new();
        designs.retain(|d| seen.insert(d.clone()));
        Ok(designs)
    }

    /// Number of (design, model) cells the driver will run, baseline included.
    pub fn cells(&self, designs: usize) -> usize {
        (designs + 1) * self.models.len()
    }

    /// `sweep/run.py` arguments for this spec. `out` and `designs_file` are
    /// workspace-relative.
    pub fn invocation(&self, out: &str, designs_file: &str) -> crate::backend::Invocation {
        let mut inv = crate::backend::Invocation::new("pipeline/sweep/run.py")
            .arg("--models")
            .args(self.models.iter().cloned())
            .arg("--designs")
            .arg(designs_file)
            .arg("-o")
            .arg(out)
            .arg("--host")
            .arg(self.host.clone())
            .arg("--images")
            .arg(self.images.to_string())
            .arg("--progress")
            .arg("json")
            .flag(self.power, "--power")
            .flag(self.serial, "--serial");
        if let Some(fe) = &self.frontend {
            inv = inv.arg("--frontend").arg(fe.clone());
        }
        if !self.dram.is_empty() && self.dram != "fixed" {
            inv = inv.arg("--dram").arg(self.dram.clone());
        }
        inv
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec(mode: SpaceMode, vals: &[(&str, &str)]) -> SweepSpec {
        SweepSpec {
            mode,
            values: vals.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect(),
            ..SweepSpec::default()
        }
    }

    #[test]
    fn values_accept_python_int_spellings() {
        assert_eq!(parse_values("2, 4,8").unwrap(), vec![2, 4, 8]);
        assert_eq!(parse_values("0x10000 0x40000").unwrap(), vec![65536, 262144]);
        assert_eq!(parse_values("16k,1M").unwrap(), vec![16384, 1 << 20]);
        assert!(parse_values("4, four").is_err());
        assert!(parse_values("").unwrap().is_empty());
    }

    #[test]
    fn ofat_moves_one_knob_per_point() {
        let s = spec(SpaceMode::Ofat, &[("SPATZ_NB_LANES", "2,8"), ("L2_WAYS", "4,16"), ("TCDM_SIZE", "")]);
        let d = s.expand(&[]).unwrap();
        assert_eq!(d.len(), 4);
        assert!(d.iter().all(|x| x.len() == 1));
        assert_eq!(s.cells(d.len()), 10); // (4 + baseline) x mnist, kws
    }

    #[test]
    fn factorial_is_the_cartesian_product() {
        let s = spec(SpaceMode::Factorial, &[("SPATZ_NB_LANES", "2,4,8"), ("SPATZ_NB_CORE", "5,9")]);
        let d = s.expand(&[]).unwrap();
        assert_eq!(d.len(), 6);
        assert!(d.iter().all(|x| x.len() == 2));
        assert!(d.contains(&Design::from([("SPATZ_NB_LANES".into(), 8), ("SPATZ_NB_CORE".into(), 5)])));
    }

    #[test]
    fn list_mode_parses_lines_and_checks_knobs() {
        let mut s = spec(SpaceMode::List, &[]);
        s.list = "SPATZ_NB_LANES=8 spatz_nb_core=17\n# comment\n\nL2_SIZE=0x100000  # trailing\nSPATZ_NB_LANES=8 SPATZ_NB_CORE=17".into();
        let known: Vec<String> = ["SPATZ_NB_LANES", "SPATZ_NB_CORE", "L2_SIZE"].map(String::from).to_vec();
        let d = s.expand(&known).unwrap();
        assert_eq!(d.len(), 2, "duplicate line dropped");
        assert_eq!(d[1]["L2_SIZE"], 1 << 20);
        s.list = "SPATZ_LANES=8".into();
        assert!(s.expand(&known).unwrap_err().contains("unknown knob"));
    }

    #[test]
    fn invocation_carries_the_options() {
        let mut s = SweepSpec { frontend: Some("spatz".into()), serial: true, ..SweepSpec::default() };
        s.power = true;
        let inv = s.invocation("work/gui/sweeps/x", "work/gui/sweeps/x/designs.json");
        let a = inv.args.join(" ");
        assert_eq!(inv.script, "pipeline/sweep/run.py");
        assert!(
            a.starts_with("--models ops/mnist ops/kws --designs work/gui/sweeps/x/designs.json -o work/gui/sweeps/x")
        );
        assert!(
            a.contains("--progress json")
                && a.contains("--power")
                && a.contains("--serial")
                && a.contains("--frontend spatz")
        );
    }

    #[test]
    fn invocation_carries_the_main_memory_only_when_set() {
        let fixed = SweepSpec::default().invocation("o", "d.json");
        assert!(!fixed.args.iter().any(|a| a == "--dram"));
        let s = SweepSpec { dram: "lpddr5".into(), ..SweepSpec::default() };
        assert!(s.invocation("o", "d.json").args.join(" ").contains("--dram lpddr5"));
        // A spec saved before the field existed loads as the fixed-latency model.
        let old: SweepSpec = toml::from_str("name = \"x\"").unwrap();
        assert_eq!(old.dram, "fixed");
    }

    #[test]
    fn spec_round_trips_through_toml() {
        let s = spec(SpaceMode::Factorial, &[("SPATZ_NB_LANES", "2,8")]);
        let t = toml::to_string_pretty(&s).unwrap();
        assert_eq!(toml::from_str::<SweepSpec>(&t).unwrap(), s);
    }
}
