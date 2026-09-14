from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from nicegui import ui

STYLE_DIR = Path(__file__).with_name("styles")
PURPLE = "#7354d8"
PURPLE_LIGHT = "#ded3ff"
SEMANTIC = {"CRITICAL": "#bd3f4b", "HIGH": "#d08022", "MEDIUM": "#4c7ec1", "LOW": "#27835e"}


def compact_euro(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:.0f}K"
    return f"€{value:,.0f}"


def install_design_system() -> None:
    css = "\n".join(
        (STYLE_DIR / name).read_text()
        for name in (
            "tokens.css",
            "animations.css",
            "theme.css",
            "components.css",
            "responsive.css",
            "theme-dark-bronze.css",
        )
    )
    ui.add_css(css, shared=True)
    ui.add_head_html(
        '<script>' + (Path(__file__).with_name("static") / "theme.js").read_text() + '</script>',
        shared=True,
    )
    ui.colors(
        primary="#7354d8",
        secondary="#8b6ce8",
        accent="#5d43b3",
        positive="#18865a",
        negative="#bd3f4b",
        warning="#a85e0a",
        info="#3972c3",
    )


def polish_chart(
    fig: go.Figure, *, height: int = 330, x_title: str | None = None, y_title: str | None = None
) -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 54, "r": 40, "t": 28, "b": 48},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={
            "family": "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
            "color": "#5f596a",
            "size": 13,
        },
        hoverlabel={"bgcolor": "white", "bordercolor": "#ded3ff", "font_color": "#25232a"},
        hovermode="closest",
        bargap=0.28,
        transition={"duration": 420, "easing": "cubic-in-out"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        xaxis={
            "title": x_title,
            "title_font": {"size": 13, "color": "#5f596a"},
            "tickfont": {"size": 12, "color": "#746d80"},
            "gridcolor": "rgba(222,211,255,.55)",
            "zeroline": False,
            "linecolor": "#ded3ef",
            "ticks": "outside",
            "tickcolor": "#ded3ef",
            "automargin": True,
        },
        yaxis={
            "title": y_title,
            "title_font": {"size": 13, "color": "#5f596a"},
            "tickfont": {"size": 12, "color": "#746d80"},
            "gridcolor": "rgba(222,211,255,.6)",
            "zeroline": False,
            "linecolor": "#ded3ef",
            "ticks": "outside",
            "tickcolor": "#ded3ef",
            "automargin": True,
        },
    )
    fig.update_traces(
        marker_line_width=0,
        cliponaxis=False,
        textfont={"size": 12, "color": "#4f485a"},
        selector={"type": "bar"},
    )
    for trace in fig.data:
        if trace.type == "bar" and trace.textposition == "outside":
            values = trace.x if trace.orientation == "h" else trace.y
            numeric = [float(value) for value in values if isinstance(value, (int, float))]
            if numeric and min(numeric) >= 0:
                if trace.orientation == "h":
                    fig.update_xaxes(range=[0, max(numeric) * 1.23])
                else:
                    fig.update_yaxes(range=[0, max(numeric) * 1.18])
    return fig


def chart_header(title: str, description: str) -> None:
    with ui.row().classes("w-full items-start"):
        with ui.column().classes("gap-0"):
            ui.label(title).classes("chart-title")
            ui.label(description).classes("chart-subtitle")
        ui.space()
        ui.button(icon="more_horiz").props(
            f'flat round dense aria-label="More options for {title}"'
        )
