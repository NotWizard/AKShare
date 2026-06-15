"""Reusable Plotly chart factories — Terminal Fintech styled.

Every factory applies the design-system CHART_LAYOUT and returns a
``plotly.graph_objects.Figure`` ready to render.
"""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard.config import CHART_LAYOUT, C, PHASE_COLORS, PHASE_LABELS


def _alpha(hex_color: str, opacity: float) -> str:
    """Convert a hex color + opacity to rgba string (Plotly-compatible).

    >>> _alpha('#6366f1', 0.10)
    'rgba(99,102,241,0.1)'
    """
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{opacity})'


def _apply_layout(fig: go.Figure, **overrides) -> go.Figure:
    """Merge CHART_LAYOUT defaults with any overrides.

    The ``title`` key is excluded from defaults — individual charts
    always set their own title before calling this helper.
    """
    defaults = {k: v for k, v in CHART_LAYOUT.items() if k != 'title'}
    layout = {**defaults, **overrides}
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Dual-axis line chart
# ---------------------------------------------------------------------------
def make_dual_axis_line(
    dates, y1, y2,
    y1_name: str, y2_name: str, title: str,
    y1_color: str = C['accent'], y2_color: str = C['up'],
) -> go.Figure:
    """Two lines with independent y-axes, gradient fill under primary."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=dates, y=y1, name=y1_name, mode='lines',
            line=dict(color=y1_color, width=2.5),
            fill='tozeroy',
            fillcolor=_alpha(y1_color, 0.10),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=y2, name=y2_name, mode='lines',
            line=dict(color=y2_color, width=2),
        ),
        secondary_y=True,
    )
    fig.update_layout(
        title=dict(text=title),
        xaxis=dict(rangeslider=dict(visible=False)),
    )
    _apply_layout(fig)
    fig.update_yaxes(
        title_text=y1_name, secondary_y=False,
        tickfont=dict(size=11, color=C['text_3']),
    )
    fig.update_yaxes(
        title_text=y2_name, secondary_y=True,
        tickfont=dict(size=11, color=C['text_3']),
    )
    return fig


# ---------------------------------------------------------------------------
# Stacked / overlapping area chart
# ---------------------------------------------------------------------------
def make_area_chart(
    dates,
    values_dict: dict[str, list],
    title: str,
    colors_dict: dict[str, str] | None = None,
    stack: bool = True,
) -> go.Figure:
    """Stacked or overlapping area chart with semi-transparent fills."""
    default_colors = [C['accent'], C['up'], C['down'], C['warn'], '#a78bfa']
    fig = go.Figure()
    for i, (name, values) in enumerate(values_dict.items()):
        color = (colors_dict or {}).get(name, default_colors[i % len(default_colors)])
        fig.add_trace(go.Scatter(
            x=dates, y=values, name=name, mode='lines',
            fill='tonexty' if stack else 'tozeroy',
            fillcolor=_alpha(color, 0.12),
            line=dict(color=color, width=1.5),
            stackgroup='one' if stack else None,
        ))
    fig.update_layout(title=dict(text=title))
    _apply_layout(fig)
    return fig


# ---------------------------------------------------------------------------
# 4-quadrant scatter (Merrill clock style)
# ---------------------------------------------------------------------------
def make_scatter_quadrant(
    x, y, phases,
    title: str,
    x_label: str = 'GDP同比 (%)',
    y_label: str = 'CPI同比 (%)',
    hline_val: float = 2.0,
    vline_val: float | None = None,
) -> go.Figure:
    """Scatter coloured by phase with cross-hair reference lines."""
    fig = go.Figure()

    unique_phases = sorted(set(phases.dropna())) if hasattr(phases, 'dropna') else sorted(set(phases))
    for phase in unique_phases:
        label = PHASE_LABELS.get(phase, phase)
        color = PHASE_COLORS.get(phase, C['text_3'])
        mask = [p == phase for p in phases]
        fig.add_trace(go.Scatter(
            x=[xi for xi, m in zip(x, mask) if m],
            y=[yi for yi, m in zip(y, mask) if m],
            name=label, mode='markers',
            marker=dict(
                color=color, size=8, opacity=0.85,
                line=dict(color='rgba(255,255,255,0.2)', width=1),
            ),
        ))

    # Reference lines
    line_style = dict(line_dash='dot', line_color=C['text_3'], line_width=1, opacity=0.5)
    if hline_val is not None:
        fig.add_hline(y=hline_val, **line_style)
    if vline_val is not None:
        fig.add_vline(x=vline_val, **line_style)

    fig.update_layout(
        title=dict(text=title),
        xaxis_title=x_label, yaxis_title=y_label,
    )
    _apply_layout(fig)
    return fig


# ---------------------------------------------------------------------------
# Bar + line overlay
# ---------------------------------------------------------------------------
def make_bar_line_combo(
    dates, bars, line,
    bar_name: str, line_name: str, title: str,
    bar_color: str = C['accent'], line_color: str = C['up'],
) -> go.Figure:
    """Bars on primary y, line on secondary y."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=dates, y=bars, name=bar_name,
            marker_color=bar_color, opacity=0.65,
            marker_line_width=0,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=line, name=line_name, mode='lines',
            line=dict(color=line_color, width=2.5),
        ),
        secondary_y=True,
    )
    fig.update_layout(title=dict(text=title), barmode='overlay')
    _apply_layout(fig)
    fig.update_yaxes(title_text=bar_name, secondary_y=False)
    fig.update_yaxes(title_text=line_name, secondary_y=True)
    return fig


# ---------------------------------------------------------------------------
# Utility: add range slider
# ---------------------------------------------------------------------------
def make_range_slider(fig: go.Figure, visible: bool = True) -> go.Figure:
    """Enable the range-slider on the primary x-axis."""
    fig.update_xaxes(
        rangeslider=dict(
            visible=visible,
            bgcolor=C['range_slider'],
            bordercolor=C['border'],
            borderwidth=1,
            thickness=0.08,
        ),
    )
    return fig
