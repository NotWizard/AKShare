"""P2 — Merrill Lynch Investment Clock (美林投资时钟)."""

import dash
from dash import html, dcc, Input, Output, callback, ctx
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from dashboard.db import load
from dashboard.config import C, CHART_LAYOUT, PHASE_COLORS, PHASE_LABELS, DB_PATH
from dashboard.components.charts import (
    _apply_layout, make_scatter_quadrant, make_range_slider, make_phase_timeline,
    empty_dark_fig,
)
from dashboard.components.controls import make_date_range_selector
from dashboard.components.layout import make_card, make_row, make_graph_card

dash.register_page(__name__, path='/merrill-clock', name='美林时钟', order=1)

# ---------------------------------------------------------------------------
# Try to load the analysis module
# ---------------------------------------------------------------------------
try:
    from analysis.cycle_merrill import classify_merrill
    _mc = classify_merrill(DB_PATH)
except Exception:
    _mc = None

# Data boundaries
_dq = load('derived_quarterly')
MIN_DATE = _dq['date'].min().strftime('%Y-%m-%d')
MAX_DATE = _dq['date'].max().strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _quadrant_chart(dq, mc_df):
    """4-quadrant scatter: X=GDP同比, Y=CPI同比, coloured by phase."""
    if mc_df is not None and len(mc_df):
        phases = mc_df['phase'].tolist()
        x = mc_df['gdp_yoy'].tolist()
        y = mc_df['cpi_yoy'].tolist()
    else:
        phases = ['recovery'] * len(dq)
        x = dq['gdp_yoy'].tolist()
        y = dq['cpi_yoy'].tolist()

    # GDP trend line as vertical reference
    gdp_trend = pd.Series(x).mean() if x else 0.0

    fig = make_scatter_quadrant(
        x, y, phases,
        x_label='GDP同比 (%)', y_label='CPI同比 (%)',
        hline_val=2.0, vline_val=gdp_trend,
    )

    # Highlight the most recent point
    if x and y:
        fig.add_trace(go.Scatter(
            x=[x[-1]], y=[y[-1]],
            name='当前', mode='markers',
            marker=dict(color=C['warn'], size=16, symbol='star',
                        line=dict(color='rgba(15,23,42,0.25)', width=1.5)),
            hovertemplate='<b>当前</b>: GDP %{x:.2f}% / CPI %{y:.2f}%<extra></extra>',
        ))

    fig.update_layout(height=500)
    _apply_layout(fig)
    return fig


def _phase_pie(mc_df):
    """Pie chart of time spent in each phase."""
    if mc_df is None or not len(mc_df):
        return go.Figure().update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title='暂无数据')

    counts = mc_df['phase'].value_counts()
    labels = [PHASE_LABELS.get(p, p) for p in counts.index]
    colors = [PHASE_COLORS.get(p, '#888') for p in counts.index]

    fig = go.Figure(go.Pie(
        labels=labels, values=counts.values,
        marker=dict(colors=colors),
        textinfo='label+percent',
        hole=0.4,
        hovertemplate='<b>%{label}</b>: %{value} 期 (%{percent})<extra></extra>',
    ))
    fig.update_layout(
        showlegend=False,
        hovermode='closest',
    )
    _apply_layout(fig)
    return fig


def _timeline_chart(mc_df):
    """Horizontal bar timeline showing phase transitions."""
    if mc_df is None or not len(mc_df):
        return go.Figure().update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title='暂无数据')

    fig = make_phase_timeline(
        mc_df['date'].tolist(),
        mc_df['phase'].tolist(),
        PHASE_COLORS,
        PHASE_LABELS,
    )
    return make_range_slider(fig)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div(
    style={'padding': '20px'},
    children=[
        make_date_range_selector(MIN_DATE, MAX_DATE, id_prefix='mc'),
        make_row(
            make_graph_card(
                '美林时钟四象限', 'mc-quadrant-graph',
                tip='横轴为 GDP 同比增速，纵轴为 CPI 同比增速；按增长/通胀高低划分复苏、过热、滞胀、衰退四个象限。'
            ),
            make_graph_card(
                '阶段分布', 'mc-pie-graph',
                tip='统计历史样本中四个阶段出现的时长占比，帮助判断当前周期所处的位置。'
            ),
        ),
        make_graph_card(
            '周期阶段时间线', 'mc-timeline-graph',
            tip='按年份展示经济周期阶段的演变，颜色对应复苏、过热、滞胀、衰退四个阶段。'
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
def _filter_mc(mc_df, start, end):
    if mc_df is None:
        return None
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    return mc_df[(mc_df['date'] >= s) & (mc_df['date'] <= e)]


@callback(
    Output('mc-quadrant-graph', 'figure'),
    Output('mc-pie-graph', 'figure'),
    Output('mc-timeline-graph', 'figure'),
    Input('mc-picker', 'start_date'),
    Input('mc-picker', 'end_date'),
)
def update_merrill_charts(start_date, end_date):
    dq = load('derived_quarterly', start_date=start_date, end_date=end_date)
    mc_filtered = _filter_mc(_mc, start_date, end_date)
    return (
        _quadrant_chart(dq, mc_filtered),
        _phase_pie(mc_filtered),
        _timeline_chart(mc_filtered),
    )


@callback(
    Output('mc-picker', 'start_date', allow_duplicate=True),
    Output('mc-picker', 'end_date', allow_duplicate=True),
    Input('mc-btn-5y', 'n_clicks'),
    Input('mc-btn-10y', 'n_clicks'),
    Input('mc-btn-20y', 'n_clicks'),
    Input('mc-btn-all', 'n_clicks'),
    prevent_initial_call=True,
)
def apply_preset(_5y, _10y, _20y, _all):
    trigger = ctx.triggered_id or ''
    if not trigger.startswith('mc-btn-'):
        return dash.no_update, dash.no_update
    preset = trigger.replace('mc-btn-', '')
    max_dt = datetime.strptime(MAX_DATE, '%Y-%m-%d')
    end = MAX_DATE
    if preset == '5y':
        start = (max_dt - relativedelta(years=5)).strftime('%Y-%m-%d')
    elif preset == '10y':
        start = (max_dt - relativedelta(years=10)).strftime('%Y-%m-%d')
    elif preset == '20y':
        start = (max_dt - relativedelta(years=20)).strftime('%Y-%m-%d')
    else:
        start = MIN_DATE
    return start, end
