"""P2 — Merrill Lynch Investment Clock (美林投资时钟)."""

import dash
from dash import html, dcc, Input, Output, callback, ctx
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from dashboard.db import load
from dashboard.config import CHART_LAYOUT, PHASE_COLORS, PHASE_LABELS, DB_PATH
from dashboard.components.charts import make_scatter_quadrant, make_range_slider
from dashboard.components.controls import make_date_range_selector
from dashboard.components.layout import make_card, make_row

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
        title='美林时钟四象限图',
        x_label='GDP同比 (%)', y_label='CPI同比 (%)',
        hline_val=2.0, vline_val=gdp_trend,
    )

    # Highlight the most recent point
    if x and y:
        fig.add_trace(go.Scatter(
            x=[x[-1]], y=[y[-1]],
            name='当前', mode='markers',
            marker=dict(color='#f39c12', size=16, symbol='star',
                        line=dict(color='white', width=2)),
        ))

    fig.update_layout(height=500)
    return fig


def _phase_pie(mc_df):
    """Pie chart of time spent in each phase."""
    if mc_df is None or not len(mc_df):
        return go.Figure().update_layout(**CHART_LAYOUT, title='暂无数据')

    counts = mc_df['phase'].value_counts()
    labels = [PHASE_LABELS.get(p, p) for p in counts.index]
    colors = [PHASE_COLORS.get(p, '#888') for p in counts.index]

    fig = go.Figure(go.Pie(
        labels=labels, values=counts.values,
        marker=dict(colors=colors),
        textinfo='label+percent',
        hole=0.4,
    ))
    fig.update_layout(
        title=dict(text='各阶段时间分布', x=0.5),
        **CHART_LAYOUT,
        showlegend=False,
    )
    return fig


def _timeline_chart(mc_df):
    """Horizontal bar timeline showing phase transitions."""
    if mc_df is None or not len(mc_df):
        return go.Figure().update_layout(**CHART_LAYOUT, title='暂无数据')

    fig = go.Figure()
    dates = mc_df['date'].tolist()
    phases = mc_df['phase'].tolist()

    # Plot as colored segments
    for i, (d, phase) in enumerate(zip(dates, phases)):
        label = PHASE_LABELS.get(phase, phase)
        color = PHASE_COLORS.get(phase, '#888')
        fig.add_trace(go.Bar(
            x=[d], y=[1], name=label if i == 0 else '',
            marker_color=color, showlegend=(i == 0),
            width=7776000,  # ~1 quarter in ms (90 days)
        ))

    # Deduplicate legend
    seen = set()
    fig.for_each_trace(lambda t: t.update(showlegend=False)
                       if t.name in seen else seen.add(t.name))

    fig.update_layout(
        title=dict(text='经济周期阶段时间线', x=0.5),
        barmode='stack',
        yaxis=dict(showticklabels=False, title=''),
        **CHART_LAYOUT,
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
            make_card(
                [dcc.Graph(id='mc-quadrant-graph', config={'displayModeBar': False})],
                title='美林时钟四象限',
            ),
            make_card(
                [dcc.Graph(id='mc-pie-graph', config={'displayModeBar': False})],
                title='阶段分布',
            ),
        ),
        make_card(
            [dcc.Graph(id='mc-timeline-graph', config={'displayModeBar': False})],
            title='周期阶段时间线',
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
