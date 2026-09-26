//! Models & ops: what can be run, what is in it, and adding more.

use super::common::*;
use super::{Ctx, NewJob, Out, query, valid_name};
use crate::backend::Invocation;
use crate::jobs::JobKind;
use crate::model::Inspect;
use iced::widget::{button, checkbox, column, container, row, scrollable, text, text_input};
use iced::{Element, Length, Task};
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct State {
    filter: String,
    show_deeploy: bool,
    selected: Option<String>,
    inspect: Option<Result<Inspect, String>>,
    inspecting: bool,
    model: Option<PathBuf>,
    inputs: Option<PathBuf>,
    random: bool,
    seed: String,
    name: String,
    import_error: Option<String>,
    mnist_images: String,
    mnist_epochs: String,
    mnist_reuse: bool,
    kws_clips: String,
    kws_reuse: bool,
}

impl Default for State {
    fn default() -> Self {
        State {
            filter: String::new(),
            show_deeploy: false,
            selected: None,
            inspect: None,
            inspecting: false,
            model: None,
            inputs: None,
            random: true,
            seed: "0".into(),
            name: String::new(),
            import_error: None,
            mnist_images: "64".into(),
            mnist_epochs: "4".into(),
            mnist_reuse: true,
            kws_clips: "16".into(),
            kws_reuse: true,
        }
    }
}

#[derive(Debug, Clone)]
pub enum Msg {
    Refresh,
    Filter(String),
    ShowDeeploy(bool),
    Select(String),
    Inspected(String, Result<Inspect, String>),
    PickModel,
    ModelPicked(Option<PathBuf>),
    PickInputs,
    InputsPicked(Option<PathBuf>),
    ClearInputs,
    Random(bool),
    Seed(String),
    Name(String),
    Import,
    MnistImages(String),
    MnistEpochs(String),
    MnistReuse(bool),
    RegenMnist,
    KwsClips(String),
    KwsReuse(bool),
    RegenKws,
}

async fn pick(filter: (&'static str, &'static [&'static str])) -> Option<PathBuf> {
    rfd::AsyncFileDialog::new().add_filter(filter.0, filter.1).pick_file().await.map(|h| h.path().to_path_buf())
}

impl State {
    pub fn update(&mut self, msg: Msg, ctx: &Ctx) -> Out<Msg> {
        match msg {
            Msg::Refresh => return Out { refresh_ops: true, ..Out::none() },
            Msg::Filter(s) => self.filter = s,
            Msg::ShowDeeploy(b) => self.show_deeploy = b,
            Msg::Select(arg) => {
                self.selected = Some(arg.clone());
                self.inspect = None;
                self.inspecting = true;
                let s = ctx.settings.clone();
                return Out::task(Task::perform(query(s, vec!["inspect".into(), arg.clone()]), move |r| {
                    Msg::Inspected(arg.clone(), r)
                }));
            }
            Msg::Inspected(arg, r) => {
                if self.selected.as_deref() == Some(arg.as_str()) {
                    self.inspect = Some(r);
                    self.inspecting = false;
                }
            }
            Msg::PickModel => return Out::task(Task::perform(pick(("ONNX model", &["onnx"])), Msg::ModelPicked)),
            Msg::ModelPicked(p) => {
                if let Some(p) = p {
                    if self.name.is_empty() {
                        self.name = p
                            .file_stem()
                            .map(|s| {
                                s.to_string_lossy()
                                    .chars()
                                    .map(|c| if c.is_ascii_alphanumeric() || c == '-' { c } else { '_' })
                                    .collect()
                            })
                            .unwrap_or_default();
                    }
                    self.model = Some(p);
                }
            }
            Msg::PickInputs => return Out::task(Task::perform(pick(("NumPy archive", &["npz"])), Msg::InputsPicked)),
            Msg::InputsPicked(p) => {
                if p.is_some() {
                    self.inputs = p;
                    self.random = false;
                }
            }
            Msg::ClearInputs => {
                self.inputs = None;
                self.random = true;
            }
            Msg::Random(b) => self.random = b,
            Msg::Seed(s) => self.seed = s,
            Msg::Name(s) => self.name = s,
            Msg::Import => match self.import(ctx) {
                Ok(job) => {
                    self.import_error = None;
                    return Out::jobs(vec![job]);
                }
                Err(e) => self.import_error = Some(e),
            },
            Msg::MnistImages(s) => self.mnist_images = s,
            Msg::MnistEpochs(s) => self.mnist_epochs = s,
            Msg::MnistReuse(b) => self.mnist_reuse = b,
            Msg::KwsClips(s) => self.kws_clips = s,
            Msg::KwsReuse(b) => self.kws_reuse = b,
            Msg::RegenMnist => {
                let (Ok(images), Ok(epochs)) = (self.mnist_images.parse::<u32>(), self.mnist_epochs.parse::<u32>())
                else {
                    return Out::toast("MNIST: images and epochs must be whole numbers");
                };
                let inv = Invocation::new("pipeline/mnist.py")
                    .arg("--images")
                    .arg(images.to_string())
                    .arg("--epochs")
                    .arg(epochs.to_string())
                    .flag(self.mnist_reuse, "--reuse");
                return Out::jobs(vec![NewJob {
                    title: format!("Regenerate ops/mnist ({images} images)"),
                    kind: JobKind::MakeOp,
                    inv,
                }]);
            }
            Msg::RegenKws => {
                let Ok(clips) = self.kws_clips.parse::<u32>() else {
                    return Out::toast("KWS: clips must be a whole number");
                };
                let inv = Invocation::new("pipeline/kws.py")
                    .arg("--clips")
                    .arg(clips.to_string())
                    .flag(self.kws_reuse, "--reuse");
                return Out::jobs(vec![NewJob {
                    title: format!("Regenerate ops/kws ({clips} clips)"),
                    kind: JobKind::MakeOp,
                    inv,
                }]);
            }
        }
        Out::none()
    }

    /// Stage the chosen files inside the workspace, where both backends can
    /// see them, and build the make_op.py job.
    fn import(&self, ctx: &Ctx) -> Result<NewJob, String> {
        let model = self.model.as_ref().ok_or("choose an .onnx file first")?;
        if !valid_name(&self.name) {
            return Err("name: letters, digits, '-' and '_' only".into());
        }
        let ws = &ctx.settings.workspace;
        if ws.join("ops").join(&self.name).exists() {
            return Err(format!("ops/{} already exists; pick another name", self.name));
        }
        let stage_rel = format!("work/gui/incoming/{}", self.name);
        let stage = ws.join(&stage_rel);
        std::fs::create_dir_all(&stage).map_err(|e| format!("{}: {e}", stage.display()))?;
        std::fs::copy(model, stage.join("model.onnx")).map_err(|e| format!("copying the model: {e}"))?;
        let mut inv = Invocation::new("pipeline/make_op.py").arg(format!("{stage_rel}/model.onnx"));
        match (&self.inputs, self.random) {
            (Some(inp), false) => {
                std::fs::copy(inp, stage.join("inputs.npz")).map_err(|e| format!("copying the inputs: {e}"))?;
                inv = inv.arg(format!("{stage_rel}/inputs.npz"));
            }
            _ => {
                let seed: u64 = self.seed.trim().parse().map_err(|_| "seed must be a whole number")?;
                inv = inv.arg("--random").arg("--seed").arg(seed.to_string());
            }
        }
        inv = inv.arg("-o").arg(format!("ops/{}", self.name));
        Ok(NewJob { title: format!("Import ops/{}", self.name), kind: JobKind::MakeOp, inv })
    }

    pub fn view<'a>(&'a self, ctx: &Ctx<'a>, loading: bool, list_error: Option<&'a str>) -> Element<'a, Msg> {
        let f = self.filter.to_ascii_lowercase();
        let list = ctx
            .ops
            .iter()
            .filter(|o| self.show_deeploy || o.source == "workspace")
            .filter(|o| f.is_empty() || o.name.to_ascii_lowercase().contains(&f))
            .map(|o| {
                let badge = match (&o.app, o.source.as_str()) {
                    (Some(app), _) => format!("app: {app}"),
                    (None, "deeploy") => "deeploy test".to_string(),
                    _ => "op".to_string(),
                };
                let selected = self.selected.as_deref() == Some(o.arg.as_str());
                button(row![text(&o.name).size(14).width(Length::Fill), muted(badge)].spacing(8))
                    .width(Length::Fill)
                    .padding([4, 8])
                    .style(if selected { button::primary } else { button::text })
                    .on_press(Msg::Select(o.arg.clone()))
                    .into()
            });
        let mut left = column![
            row![
                text_input("filter", &self.filter).on_input(Msg::Filter).width(Length::Fill),
                small_button("Refresh", Some(Msg::Refresh)),
            ]
            .spacing(6),
            checkbox(self.show_deeploy).label("Show Deeploy kernel tests").on_toggle(Msg::ShowDeeploy),
        ]
        .spacing(8);
        if loading {
            left = left.push(muted("loading…"));
        }
        if let Some(e) = list_error {
            left = left.push(error(e));
        }
        left = left.push(scrollable(lines(list)).height(Length::Fill));

        let detail: Element<'a, Msg> = match (&self.selected, &self.inspect) {
            (None, _) => muted("Select an op to see its graph.").into(),
            (Some(_), None) => muted(if self.inspecting { "reading the graph…" } else { "" }).into(),
            (Some(_), Some(Err(e))) => error(e.as_str()).into(),
            (Some(arg), Some(Ok(i))) => inspect_view(arg, i),
        };

        let import = section(
            "Import an ONNX model",
            column![
                labelled(
                    "Model",
                    row![
                        small_button("Choose .onnx…", Some(Msg::PickModel)),
                        mono(self.model.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "none".into())),
                    ]
                    .spacing(8)
                    .align_y(iced::Center)
                ),
                labelled(
                    "Inputs",
                    row![
                        small_button("Choose inputs.npz…", Some(Msg::PickInputs)),
                        mono(self.inputs.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "none".into())),
                        small_button("Clear", self.inputs.as_ref().map(|_| Msg::ClearInputs)),
                    ]
                    .spacing(8)
                    .align_y(iced::Center)
                ),
                labelled(
                    "",
                    row![
                        checkbox(self.random).label("Random inputs, seed").on_toggle(Msg::Random),
                        text_input("0", &self.seed).on_input(Msg::Seed).width(Length::Fixed(80.0)),
                    ]
                    .spacing(8)
                    .align_y(iced::Center)
                ),
                labelled("Name", text_input("myop", &self.name).on_input(Msg::Name).width(Length::Fixed(240.0))),
                row![
                    button(text("Import to ops/").size(14)).style(button::primary).on_press(Msg::Import),
                    muted("Expected outputs are computed with onnxruntime (pipeline/make_op.py)."),
                ]
                .spacing(12)
                .align_y(iced::Center),
            ]
            .push(self.import_error.as_deref().map(error))
            .spacing(8),
        );

        let apps = section(
            "Regenerate application ops",
            column![
                row![
                    text("MNIST").width(Length::Fixed(60.0)),
                    text("images"),
                    text_input("64", &self.mnist_images).on_input(Msg::MnistImages).width(Length::Fixed(70.0)),
                    text("epochs"),
                    text_input("4", &self.mnist_epochs).on_input(Msg::MnistEpochs).width(Length::Fixed(60.0)),
                    checkbox(self.mnist_reuse).label("reuse trained weights").on_toggle(Msg::MnistReuse),
                    small_button("Regenerate", Some(Msg::RegenMnist)),
                ]
                .spacing(8)
                .align_y(iced::Center),
                row![
                    text("KWS").width(Length::Fixed(60.0)),
                    text("clips"),
                    text_input("16", &self.kws_clips).on_input(Msg::KwsClips).width(Length::Fixed(70.0)),
                    checkbox(self.kws_reuse).label("reuse trained weights").on_toggle(Msg::KwsReuse),
                    small_button("Regenerate", Some(Msg::RegenKws)),
                ]
                .spacing(8)
                .align_y(iced::Center),
                muted("Training downloads the dataset on first use, so the container needs network access."),
            ]
            .spacing(8),
        );

        row![
            container(left).width(Length::FillPortion(2)),
            scrollable(
                column![section("Graph", detail), import, apps]
                    .spacing(12)
                    .padding(iced::Padding { right: 12.0, ..Default::default() })
            )
            .width(Length::FillPortion(3)),
        ]
        .spacing(16)
        .into()
    }
}

fn inspect_view<'a>(arg: &'a str, i: &'a Inspect) -> Element<'a, Msg> {
    let tensors = |ts: &'a [crate::model::TensorInfo]| {
        lines(ts.iter().map(|t| {
            let shape: Vec<String> = t.shape.iter().map(|d| d.to_string().trim_matches('"').to_string()).collect();
            mono(format!("{}  {}[{}]", t.name, t.dtype, shape.join("×"))).into()
        }))
    };
    let ops = i.op_types.iter().map(|(k, v)| format!("{k} ×{v}")).collect::<Vec<_>>().join(", ");
    column![
        mono(arg),
        row![text("Inputs").size(13).width(Length::Fixed(80.0)), tensors(&i.inputs)].spacing(8),
        row![text("Outputs").size(13).width(Length::Fixed(80.0)), tensors(&i.outputs)].spacing(8),
        row![
            text("Nodes").size(13).width(Length::Fixed(80.0)),
            text(format!("{} ({} initializers): {ops}", i.nodes, i.initializers)).size(13)
        ]
        .spacing(8),
    ]
    .push(
        i.app
            .as_ref()
            .map(|a| muted(format!("Application op ({a}): runs with its own evaluation host program on the SoC."))),
    )
    .spacing(6)
    .into()
}
