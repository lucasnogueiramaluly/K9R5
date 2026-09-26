//! Settings: the workspace, the backend, and a check that it can run.

use super::common::*;
use crate::settings::{BackendKind, Settings};
use iced::widget::{button, checkbox, column, pick_list, radio, row, text, text_input};
use iced::{Element, Length};
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub enum Msg {
    Backend(BackendKind),
    Workspace(String),
    Browse,
    Browsed(Option<PathBuf>),
    Image(String),
    MountSources(bool),
    Concurrency(usize),
    Apply,
    Revert,
    Check,
    Checked(Vec<(String, Result<String, String>)>),
}

pub fn view<'a>(
    draft: &'a Settings,
    applied: &'a Settings,
    check: &'a [(String, Result<String, String>)],
    checking: bool,
) -> Element<'a, Msg> {
    let backend = column(
        BackendKind::ALL
            .iter()
            .map(|&k| radio(k.to_string(), k, Some(draft.backend), Msg::Backend).size(16).text_size(14).into()),
    )
    .spacing(6);
    let native_note = if cfg!(target_os = "linux") {
        "Native needs ./setup.sh to have run in the workspace (deps/, toolchains/, .venv/)."
    } else {
        "Native is Linux-only: GVSoC, Deeploy and the toolchain are built for Linux. Use Docker here."
    };
    let mut form = column![
        labelled(
            "Workspace",
            row![
                text_input("path to a hetero-sim clone", &draft.workspace.to_string_lossy())
                    .on_input(Msg::Workspace)
                    .width(Length::Fill),
                small_button("Browse…", Some(Msg::Browse)),
            ]
            .spacing(8)
        ),
        labelled("Backend", backend),
        labelled("", muted(native_note)),
    ]
    .spacing(10);
    if draft.backend == BackendKind::Docker {
        form = form
            .push(labelled("Image", text_input("hetero-sim", &draft.docker_image).on_input(Msg::Image).width(Length::Fixed(260.0))))
            .push(labelled(
                "",
                checkbox(draft.mount_sources)
                    .label("Mount pipeline/, runtime/ and targets/ from the workspace")
                    .on_toggle(Msg::MountSources),
            ))
            .push(labelled(
                "",
                muted("For an image older than the checkout's Python and C sources. GVSoC itself is compiled into the image, so a C++ model change still needs an image rebuild."),
            ));
    }
    form = form.push(labelled(
        "Parallel jobs",
        row![
            pick_list([1usize, 2, 3, 4], Some(draft.concurrency), Msg::Concurrency).text_size(13),
            muted("Runs of the same op share a work directory; keep 1 unless the jobs are for different ops."),
        ]
        .spacing(8)
        .align_y(iced::Center),
    ));
    let dirty = draft != applied;
    form = form.push(
        row![
            button(text("Apply").size(14)).style(button::primary).on_press_maybe(dirty.then_some(Msg::Apply)),
            small_button("Revert", dirty.then_some(Msg::Revert)),
            small_button(if checking { "Checking…" } else { "Check environment" }, (!checking).then_some(Msg::Check)),
        ]
        .spacing(8),
    );

    let mut results = column![].spacing(4);
    for (what, r) in check {
        results = results.push(match r {
            Ok(s) => row![
                ok("✓").width(Length::Fixed(18.0)),
                text(what.clone()).size(13).width(Length::Fixed(160.0)),
                text(s.clone()).size(13)
            ]
            .spacing(6),
            Err(e) => row![
                error("✗").width(Length::Fixed(18.0)),
                text(what.clone()).size(13).width(Length::Fixed(160.0)),
                error(e.clone())
            ]
            .spacing(6),
        });
    }
    column![section("Settings", form), section("Environment", results)].spacing(12).into()
}
