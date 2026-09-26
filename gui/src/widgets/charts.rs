//! The two charts the GUI needs, drawn on an iced canvas: horizontal bars
//! (cycles per core, % change per knob) and a scatter (the Pareto plot).

use iced::mouse;
use iced::widget::canvas::{self, Frame, Geometry, Path, Stroke, Text};
use iced::{Color, Element, Length, Pixels, Point, Rectangle, Renderer, Size, Theme, alignment};

const ROW: f32 = 24.0;
const LABEL_W: f32 = 190.0;
const VALUE_W: f32 = 110.0;
const TEXT: f32 = 13.0;

fn text(content: impl Into<String>, at: Point, color: Color, align_x: alignment::Horizontal) -> Text {
    Text {
        content: content.into(),
        position: at,
        color,
        size: Pixels(TEXT),
        align_x: align_x.into(),
        align_y: alignment::Vertical::Center,
        ..Text::default()
    }
}

#[derive(Debug, Clone)]
pub struct Bar {
    pub label: String,
    pub value: f64,
    /// Shown right of the bar instead of the raw value.
    pub shown: String,
    pub highlight: bool,
    /// Drawn in the warning colour and without a length (failed runs).
    pub missing: bool,
}

/// Horizontal bars, one per row. Negative values grow left from a zero axis,
/// which is what a "% vs baseline" chart needs.
#[derive(Debug, Clone)]
pub struct BarChart {
    pub bars: Vec<Bar>,
    pub log: bool,
}

impl BarChart {
    pub fn view<'a, M: 'a>(self) -> Element<'a, M> {
        let h = self.bars.len() as f32 * ROW + 8.0;
        canvas::Canvas::new(self).width(Length::Fill).height(Length::Fixed(h)).into()
    }

    /// Log bars start a decade below the smallest value rather than at 1,
    /// so a 10x gap between two cores reads as one, not as a sliver.
    fn scale(&self, v: f64, floor: f64) -> f64 {
        if self.log { v.max(1.0).log10() - floor } else { v }
    }

    fn log_floor(&self) -> f64 {
        let min = self.bars.iter().filter(|b| !b.missing && b.value > 0.0).map(|b| b.value).fold(f64::MAX, f64::min);
        if self.log && min < f64::MAX { (min.log10() - 0.3).floor().max(0.0) } else { 0.0 }
    }
}

impl<M> canvas::Program<M> for BarChart {
    type State = ();

    fn draw(&self, _: &(), renderer: &Renderer, theme: &Theme, bounds: Rectangle, _: mouse::Cursor) -> Vec<Geometry> {
        let mut f = Frame::new(renderer, bounds.size());
        let p = theme.extended_palette();
        let fg = p.background.base.text;
        let muted = p.background.strong.color;

        let floor = self.log_floor();
        let vals: Vec<f64> = self.bars.iter().filter(|b| !b.missing).map(|b| self.scale(b.value, floor)).collect();
        let max = vals.iter().cloned().fold(0.0_f64, f64::max);
        let min = vals.iter().cloned().fold(0.0_f64, f64::min);
        let span = (max - min).max(f64::EPSILON);
        let plot_x = LABEL_W;
        let plot_w = (bounds.width - LABEL_W - VALUE_W).max(40.0);
        let zero_x = plot_x + ((0.0 - min) / span) as f32 * plot_w;

        for (i, b) in self.bars.iter().enumerate() {
            let y = 4.0 + i as f32 * ROW;
            let mid = y + ROW / 2.0;
            f.fill_text(text(&b.label, Point::new(LABEL_W - 8.0, mid), fg, alignment::Horizontal::Right));
            if b.missing {
                f.fill_text(text(
                    &b.shown,
                    Point::new(plot_x + 4.0, mid),
                    p.warning.base.color,
                    alignment::Horizontal::Left,
                ));
                continue;
            }
            let v = self.scale(b.value, floor);
            let x = plot_x + ((v - min) / span) as f32 * plot_w;
            let (left, right) = if x >= zero_x { (zero_x, x) } else { (x, zero_x) };
            let color = if b.highlight {
                p.success.base.color
            } else if b.value < 0.0 {
                p.primary.weak.color
            } else {
                p.primary.base.color
            };
            f.fill_rectangle(Point::new(left, y + 4.0), Size::new((right - left).max(1.0), ROW - 8.0), color);
            f.fill_text(text(&b.shown, Point::new(plot_x + plot_w + 8.0, mid), fg, alignment::Horizontal::Left));
        }
        if min < 0.0 {
            let axis = Path::line(Point::new(zero_x, 0.0), Point::new(zero_x, bounds.height));
            f.stroke(&axis, Stroke::default().with_color(muted).with_width(1.0));
        }
        vec![f.into_geometry()]
    }
}

#[derive(Debug, Clone)]
pub struct Point2 {
    pub x: f64,
    pub y: f64,
    pub label: String,
    pub emphasis: bool,
}

/// x/y scatter with axes, emphasised points drawn larger and joined in x
/// order (a Pareto front), and the nearest point's label under the cursor.
#[derive(Debug, Clone)]
pub struct Scatter {
    pub points: Vec<Point2>,
    pub x_label: String,
    pub y_label: String,
    pub log_x: bool,
}

impl Scatter {
    pub fn view<'a, M: 'a>(self, height: f32) -> Element<'a, M> {
        canvas::Canvas::new(self).width(Length::Fill).height(Length::Fixed(height)).into()
    }
}

const PAD_L: f32 = 70.0;
const PAD_B: f32 = 36.0;
const PAD_T: f32 = 12.0;
const PAD_R: f32 = 16.0;

impl<M> canvas::Program<M> for Scatter {
    type State = ();

    fn draw(
        &self,
        _: &(),
        renderer: &Renderer,
        theme: &Theme,
        bounds: Rectangle,
        cursor: mouse::Cursor,
    ) -> Vec<Geometry> {
        let mut f = Frame::new(renderer, bounds.size());
        let p = theme.extended_palette();
        let fg = p.background.base.text;
        let muted = p.background.strong.color;
        if self.points.is_empty() {
            f.fill_text(text(
                "no points",
                Point::new(bounds.width / 2.0, bounds.height / 2.0),
                fg,
                alignment::Horizontal::Center,
            ));
            return vec![f.into_geometry()];
        }
        let tx = |x: f64| if self.log_x { x.max(1.0).log10() } else { x };
        let (mut x0, mut x1, mut y0, mut y1) = (f64::MAX, f64::MIN, f64::MAX, f64::MIN);
        for pt in &self.points {
            x0 = x0.min(tx(pt.x));
            x1 = x1.max(tx(pt.x));
            y0 = y0.min(pt.y);
            y1 = y1.max(pt.y);
        }
        // Some air around the data, and a usable span when it is one point.
        let (dx, dy) = ((x1 - x0).max(x1.abs() * 0.1).max(1e-9), (y1 - y0).max(y1.abs() * 0.1).max(1e-9));
        let (x0, x1, y0, y1) = (x0 - dx * 0.05, x1 + dx * 0.05, y0 - dy * 0.05, y1 + dy * 0.05);
        let w = bounds.width - PAD_L - PAD_R;
        let h = bounds.height - PAD_T - PAD_B;
        let to_screen = |x: f64, y: f64| {
            Point::new(PAD_L + ((tx(x) - x0) / (x1 - x0)) as f32 * w, PAD_T + h - ((y - y0) / (y1 - y0)) as f32 * h)
        };

        let axes = Path::new(|b| {
            b.move_to(Point::new(PAD_L, PAD_T));
            b.line_to(Point::new(PAD_L, PAD_T + h));
            b.line_to(Point::new(PAD_L + w, PAD_T + h));
        });
        f.stroke(&axes, Stroke::default().with_color(muted).with_width(1.0));
        for i in 0..=4 {
            let t = i as f64 / 4.0;
            let xv = x0 + (x1 - x0) * t;
            let xv = if self.log_x { 10f64.powf(xv) } else { xv };
            let yv = y0 + (y1 - y0) * t;
            let sx = PAD_L + w * t as f32;
            let sy = PAD_T + h - h * t as f32;
            // End ticks align inwards so they are not clipped at the edges.
            let ax = match i {
                0 => alignment::Horizontal::Left,
                4 => alignment::Horizontal::Right,
                _ => alignment::Horizontal::Center,
            };
            f.fill_text(text(short(xv), Point::new(sx, PAD_T + h + 12.0), fg, ax));
            f.fill_text(text(short(yv), Point::new(PAD_L - 6.0, sy), fg, alignment::Horizontal::Right));
        }
        f.fill_text(text(
            &self.x_label,
            Point::new(PAD_L + w / 2.0, bounds.height - 8.0),
            fg,
            alignment::Horizontal::Center,
        ));
        let dim = Color { a: 0.7, ..fg };
        f.fill_text(text(&self.y_label, Point::new(PAD_L + 6.0, PAD_T + 4.0), dim, alignment::Horizontal::Left));

        let mut front: Vec<&Point2> = self.points.iter().filter(|p| p.emphasis).collect();
        front.sort_by(|a, b| a.x.total_cmp(&b.x));
        if front.len() > 1 {
            let line = Path::new(|b| {
                b.move_to(to_screen(front[0].x, front[0].y));
                for q in &front[1..] {
                    b.line_to(to_screen(q.x, q.y));
                }
            });
            f.stroke(&line, Stroke::default().with_color(p.success.weak.color).with_width(1.5));
        }
        for pt in &self.points {
            let s = to_screen(pt.x, pt.y);
            let (r, c) = if pt.emphasis { (5.0, p.success.base.color) } else { (3.5, p.primary.base.color) };
            f.fill(&Path::circle(s, r), c);
        }

        if let Some(pos) = cursor.position_in(bounds) {
            let near = self
                .points
                .iter()
                .map(|pt| (pt, to_screen(pt.x, pt.y).distance(pos)))
                .filter(|(_, d)| *d < 12.0)
                .min_by(|a, b| a.1.total_cmp(&b.1));
            if let Some((pt, _)) = near {
                let s = to_screen(pt.x, pt.y);
                f.stroke(&Path::circle(s, 8.0), Stroke::default().with_color(fg).with_width(1.0));
                let label = format!("{}  ({}, {})", pt.label, short(pt.x), short(pt.y));
                let right = s.x > bounds.width * 0.6;
                let at = Point::new(if right { s.x - 12.0 } else { s.x + 12.0 }, (s.y - 14.0).max(PAD_T + 6.0));
                let est_w = label.chars().count() as f32 * 7.0 + 8.0;
                let bx = if right { at.x - est_w + 4.0 } else { at.x - 4.0 };
                f.fill_rectangle(Point::new(bx, at.y - 10.0), Size::new(est_w, 20.0), p.background.weak.color);
                let ax = if right { alignment::Horizontal::Right } else { alignment::Horizontal::Left };
                f.fill_text(text(label, at, fg, ax));
            }
        }
        vec![f.into_geometry()]
    }

    fn mouse_interaction(&self, _: &(), bounds: Rectangle, cursor: mouse::Cursor) -> mouse::Interaction {
        if cursor.is_over(bounds) { mouse::Interaction::Crosshair } else { mouse::Interaction::default() }
    }

    fn update(
        &self,
        _: &mut (),
        event: &canvas::Event,
        bounds: Rectangle,
        cursor: mouse::Cursor,
    ) -> Option<canvas::Action<M>> {
        // Redraw on movement, so the hover label follows the cursor.
        match event {
            canvas::Event::Mouse(mouse::Event::CursorMoved { .. }) if cursor.is_over(bounds) => {
                Some(canvas::Action::request_redraw())
            }
            _ => None,
        }
    }
}

/// Axis-tick formatting: 1234567 -> 1.23M.
pub fn short(v: f64) -> String {
    let a = v.abs();
    if a >= 1e9 {
        format!("{:.2}G", v / 1e9)
    } else if a >= 1e6 {
        format!("{:.2}M", v / 1e6)
    } else if a >= 1e4 {
        format!("{:.1}k", v / 1e3)
    } else if a >= 100.0 || v.fract() == 0.0 {
        format!("{v:.0}")
    } else {
        format!("{v:.2}")
    }
}
