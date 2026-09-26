//! Jobs: the queue, each job's live log, cancel and "copy command".

use super::common::*;
use crate::jobs::{Job, JobStatus};
use iced::widget::{button, column, container, progress_bar, row, scrollable, text};
use iced::{Element, Length};

/// Lines of a log shown at once; the job keeps more.
const SHOWN: usize = 600;

#[derive(Debug, Clone)]
pub enum Msg {
    Select(u64),
    Cancel(u64),
    Copy(u64),
    ClearFinished,
}

pub fn view<'a>(jobs: &'a [Job], selected: Option<u64>) -> Element<'a, Msg> {
    let list = jobs.iter().rev().map(|j| {
        let secs = j.elapsed().map(|d| d.as_secs()).unwrap_or(0);
        let mut c = column![
            row![text(&j.title).size(13).width(Length::Fill), status(&j.status.label())].spacing(8),
            muted(if j.phase.is_empty() {
                format!("{}m{:02}s", secs / 60, secs % 60)
            } else {
                format!("{}m{:02}s · {}", secs / 60, secs % 60, j.phase)
            }),
        ]
        .spacing(2);
        if let (JobStatus::Running, Some((d, t))) = (&j.status, j.progress) {
            c = c.push(progress_bar(0.0..=t.max(1) as f32, d as f32).girth(4));
        }
        button(c)
            .width(Length::Fill)
            .padding(6)
            .style(if selected == Some(j.id) { button::secondary } else { button::text })
            .on_press(Msg::Select(j.id))
            .into()
    });
    let left = column![
        row![
            text("Queue").size(16).width(Length::Fill),
            small_button("Clear finished", jobs.iter().any(|j| !j.status.is_active()).then_some(Msg::ClearFinished)),
        ]
        .align_y(iced::Center),
        scrollable(lines(list).spacing(4)).height(Length::Fill),
    ]
    .spacing(8);

    let right: Element<'a, Msg> = match selected.and_then(|id| jobs.iter().find(|j| j.id == id)) {
        None => muted("Select a job to see its output.").into(),
        Some(j) => {
            let skip = j.log.len().saturating_sub(SHOWN);
            let log: String = j.log.iter().skip(skip).map(String::as_str).collect::<Vec<_>>().join("\n");
            let mut head = column![
                row![
                    text(&j.title).size(15).width(Length::Fill),
                    small_button("Copy command", j.launch.as_ref().map(|_| Msg::Copy(j.id))),
                    button(text("Cancel").size(13))
                        .padding([4, 10])
                        .style(button::danger)
                        .on_press_maybe(j.status.is_active().then_some(Msg::Cancel(j.id))),
                ]
                .spacing(8)
                .align_y(iced::Center),
            ]
            .spacing(6);
            if let Some(l) = &j.launch {
                head = head.push(mono(l.display()).size(11));
            }
            if let JobStatus::Failed(e) = &j.status {
                head = head.push(error(e.as_str()));
            }
            if skip > 0 {
                head = head.push(muted(format!("… {skip} earlier lines not shown")));
            }
            column![
                head,
                container(scrollable(mono(log).width(Length::Fill)).anchor_bottom().height(Length::Fill))
                    .padding(8)
                    .style(container::rounded_box)
                    .height(Length::Fill),
            ]
            .spacing(8)
            .into()
        }
    };
    row![container(left).width(Length::FillPortion(2)), container(right).width(Length::FillPortion(5))]
        .spacing(16)
        .into()
}
