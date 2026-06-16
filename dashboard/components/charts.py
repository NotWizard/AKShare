"""Reusable Plotly chart factories — Terminal Fintech styled.

Every factory applies the design-system CHART_LAYOUT and returns a
``plotly.graph_objects.Figure`` ready to render.
"""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard.config import CHART_LAYOUT, CHART_DEFAULTS, C, PHASE_COLORS, PHASE_LABELS


# ---------------------------------------------------------------------------
# Hover templates — keep numerical labels concise and unit-aware
# ---------------------------------------------------------------------------
HOVER_PCT = '<b>%{fullData.name}</b>: %{y:.2f}%<extra></extra>'
HOVER_PP  = '<b>%{fullData.name}</b>: %{y:+.2f}pp<extra></extra>'
HOVER_IDX = '<b>%{fullData.name}</b>: %{y:.1f}<extra></extra>'


def _alpha(hex_color: str, opacity: float) -> str:
    """Convert a hex color + opacity to rgba string (Plotly-compatible).

    >>> _alpha('#6366f1', 0.10)
    'rgba(99,102,241,0.1)'
    """
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{opacity})'


def _apply_layout(fig: go.Figure, **overrides) -> go.Figure:
    """Apply CHART_LAYOUT base + CHART_DEFAULTS (axis/legend/hover).

    CHART_DEFAULTS keys are skipped if the caller already provides them
    in ``overrides``, so pages can freely set their own legend/axis.
    """
    layout = {**CHART_LAYOUT}
    for key, val in CHART_DEFAULTS.items():
        if key not in overrides:
            layout[key] = val
    layout.update(overrides)
    fig.update_layout(**layout)
    return fig


def add_phase_background(
    fig: go.Figure,
    dates,
    phases,
    color_map: dict,
    opacity: float = 0.08,
) -> go.Figure:
    """Shade the chart background by consecutive same-phase segments.

    Merging adjacent same-phase rows into a single ``add_vrect`` keeps the
    figure JSON small and the SVG tree manageable on long monthly series.
    """
    dates = list(dates)
    phases = list(phases)
    n = len(dates)
    if n == 0:
        return fig

    seg_start = dates[0]
    cur = phases[0]

    for i in range(1, n):
        if phases[i] != cur:
            color = color_map.get(cur)
            if color:
                fig.add_vrect(
                    x0=seg_start, x1=dates[i],
                    fillcolor=color, opacity=opacity,
                    line_width=0, layer='below',
                )
            seg_start = dates[i]
            cur = phases[i]

    color = color_map.get(cur)
    if color:
        fig.add_vrect(
            x0=seg_start, x1=dates[-1],
            fillcolor=color, opacity=opacity,
            line_width=0, layer='below',
        )
    return fig


def make_phase_timeline(
    dates,
    phases,
    color_map: dict,
    label_map: dict,
    title: str = '',
) -> go.Figure:
    """Phase timeline as merged-segment Bar chart.

    Groups consecutive same-phase rows into one bar per segment, then
    bins all segments by phase into a single trace per phase. Result:
    at most ``len(unique_phases)`` traces (typically 4) instead of one
    trace per row, eliminating O(N) trace overhead.
    """
    import pandas as _pd
    fig = go.Figure()
    if not len(dates):
        return fig

    ds = [_pd.Timestamp(d) for d in dates]
    ps = list(phases)
    n = len(ds)

    # Build segments
    segs = []  # (start, end, phase)
    seg_start = ds[0]
    cur = ps[0]
    for i in range(1, n):
        if ps[i] != cur:
            segs.append((seg_start, ds[i], cur))
            seg_start = ds[i]
            cur = ps[i]
    # Extend last segment by one step (use last delta or 30d default)
    last_step = (ds[-1] - ds[-2]) if n >= 2 else _pd.Timedelta(days=30)
    segs.append((seg_start, ds[-1] + last_step, cur))

    # Group by phase to minimize trace count
    groups: dict = {}
    for s, e, ph in segs:
        g = groups.setdefault(ph, {'x': [], 'width': [], 'cd': []})
        mid = s + (e - s) / 2
        g['x'].append(mid)
        g['width'].append((e - s).total_seconds() * 1000)
        g['cd'].append(
            f'{s.strftime("%Y-%m")} ~ {e.strftime("%Y-%m")}：'
            f'{label_map.get(ph, ph)}'
        )

    for ph, g in groups.items():
        fig.add_trace(go.Bar(
            x=g['x'], y=[1] * len(g['x']),
            width=g['width'],
            name=label_map.get(ph, ph),
            marker_color=color_map.get(ph, '#888'),
            customdata=g['cd'],
            hovertemplate='%{customdata}<extra></extra>',
        ))

    fig.update_layout(
        title=dict(text=title, x=0.5),
        barmode='overlay',
        yaxis=dict(showticklabels=False, title='', range=[0, 1]),
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    _apply_layout(fig)
    return fig


# ---------------------------------------------------------------------------
# Dual-axis line chart
# ---------------------------------------------------------------------------
def make_dual_axis_line(
    dates, y1, y2,
    y1_name: str, y2_name: str, title: str,
    y1_color: str = C['accent'], y2_color: str = C['up'],
    y1_hover: str = HOVER_PCT, y2_hover: str = HOVER_PCT,
) -> go.Figure:
    """Two lines with independent y-axes, gradient fill under primary."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=dates, y=y1, name=y1_name, mode='lines',
            line=dict(color=y1_color, width=2.5),
            fill='tozeroy',
            fillcolor=_alpha(y1_color, 0.10),
            hovertemplate=y1_hover,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=y2, name=y2_name, mode='lines',
            line=dict(color=y2_color, width=2),
            hovertemplate=y2_hover,
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
        gridcolor=C['grid'],
        zerolinecolor=C['grid_hi'],
        zerolinewidth=1,
        showspikes=True, spikemode='across', spikesnap='cursor',
        spikethickness=0.8, spikedash='dot',
        spikecolor='rgba(148,163,184,0.35)',
    )
    fig.update_yaxes(
        title_text=y2_name, secondary_y=True,
        tickfont=dict(size=11, color=C['text_3']),
        gridcolor='rgba(0,0,0,0)',  # hide secondary grid to avoid double lines
        zerolinecolor=C['grid_hi'],
        zerolinewidth=1,
        showgrid=False,
        showspikes=False,
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
    hovertemplate: str = HOVER_PCT,
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
            hovertemplate=hovertemplate,
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
            hovertemplate=(
                '<b>' + label + '</b><br>'
                + x_label + ': %{x:.2f}<br>'
                + y_label + ': %{y:.2f}<extra></extra>'
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
    # Quadrant scatter: closest hover; spike crosshair would be misleading.
    _apply_layout(fig, hovermode='closest')
    fig.update_xaxes(showspikes=False)
    fig.update_yaxes(showspikes=False)
    return fig


# ---------------------------------------------------------------------------
# Bar + line overlay
# ---------------------------------------------------------------------------
def make_bar_line_combo(
    dates, bars, line,
    bar_name: str, line_name: str, title: str,
    bar_color: str = C['accent'], line_color: str = C['up'],
    bar_hover: str = HOVER_PCT, line_hover: str = HOVER_PCT,
) -> go.Figure:
    """Bars on primary y, line on secondary y."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=dates, y=bars, name=bar_name,
            marker_color=bar_color, opacity=0.65,
            marker_line_width=0,
            hovertemplate=bar_hover,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=line, name=line_name, mode='lines',
            line=dict(color=line_color, width=2.5),
            hovertemplate=line_hover,
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
