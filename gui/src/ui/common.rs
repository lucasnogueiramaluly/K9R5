//! Small view helpers shared by the tabs.

use iced::widget::{Column, button, column, container, row, text};
use iced::{Color, Element, Font, Length, Theme};

/// Status colours legible on both themes: the palette's own success and
/// danger are tuned for button backgrounds, too dark for text on dark.
#[derive(Clone, Copy)]
pub enum Tone {
    Good,
    Bad,
    Warn,
    Info,
    Muted,
}

pub fn tone(t: &Theme, k: Tone) -> Color {
    let dark = t.extended_palette().is_dark;
    let pick = |d: [f32; 3], l: [f32; 3]| {
        let c = if dark { d } else { l };
        Color::from_rgb(c[0], c[1], c[2])
    };
    match k {
        Tone::Good => pick([0.40, 0.82, 0.55], [0.08, 0.50, 0.25]),
        Tone::Bad => pick([0.96, 0.45, 0.45], [0.75, 0.12, 0.12]),
        Tone::Warn => pick([0.95, 0.75, 0.35], [0.62, 0.42, 0.02]),
        Tone::Info => pick([0.55, 0.65, 1.0], [0.20, 0.30, 0.80]),
        Tone::Muted => {
            let mut c = t.extended_palette().background.base.text;
            c.a = 0.62;
            c
        }
    }
}

fn toned<'a>(s: impl text::IntoFragment<'a>, k: Tone) -> text::Text<'a> {
    text(s).style(move |t: &Theme| text::Style { color: Some(tone(t, k)) })
}

pub fn section<'a, M: 'a>(title: &'a str, body: impl Into<Element<'a, M>>) -> Element<'a, M> {
    container(column![text(title).size(16), body.into()].spacing(8))
        .padding(12)
        .width(Length::Fill)
        .style(container::bordered_box)
        .into()
}

pub fn mono<'a>(s: impl text::IntoFragment<'a>) -> text::Text<'a> {
    text(s).font(Font::MONOSPACE).size(12)
}

pub fn muted<'a>(s: impl text::IntoFragment<'a>) -> text::Text<'a> {
    toned(s, Tone::Muted).size(12)
}

pub fn error<'a>(s: impl text::IntoFragment<'a>) -> text::Text<'a> {
    toned(s, Tone::Bad).size(13)
}

pub fn warn<'a>(s: impl text::IntoFragment<'a>) -> text::Text<'a> {
    toned(s, Tone::Warn).size(13)
}

pub fn ok<'a>(s: impl text::IntoFragment<'a>) -> text::Text<'a> {
    toned(s, Tone::Good).size(13)
}

/// A status word coloured by what it means.
pub fn status<'a>(s: &str) -> text::Text<'a> {
    let k = match s {
        "ok" | "done" => Tone::Good,
        "running" | "queued" => Tone::Info,
        "invalid" | "cancelled" | "killed" => Tone::Warn,
        _ => Tone::Bad,
    };
    toned(s.to_string(), k).size(13)
}

pub fn labelled<'a, M: 'a>(label: &'a str, w: impl Into<Element<'a, M>>) -> Element<'a, M> {
    row![text(label).size(13).width(Length::Fixed(120.0)), w.into()].spacing(8).align_y(iced::Center).into()
}

pub fn small_button<'a, M: Clone + 'a>(label: &'a str, on: Option<M>) -> button::Button<'a, M> {
    button(text(label).size(13)).padding([4, 10]).on_press_maybe(on)
}

/// A column of lines, for a list of reasons or messages.
pub fn lines<'a, M: 'a>(items: impl IntoIterator<Item = Element<'a, M>>) -> Column<'a, M> {
    Column::with_children(items).spacing(2)
}
