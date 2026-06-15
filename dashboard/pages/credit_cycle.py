"""P3 — Credit Cycle (信用周期)."""

import dash
from dash import html, dcc, Input, Output, callback, ctx
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from dashboard.db import load
from dashboard.config import CHART_LAYOUT, PHASE_COLORS, PHASE_LABELS, DB_PATH
from dashboard.components.charts import make_dual_axis_line, make_range_slider
from dashboard.components.controls import make_date_range_selector
from dashboard.components.layout import make_card, make_row

dash.register_page(__name__, path='/credit-cycle', name='信用周期', order=2)

# ---------------------------------------------------------------------------
# Try to load the analysis module
# ---------------------------------------------------------------------------
try:
    from analysis.cycle_credit import classify_credit
    _cc = classify_credit(DB_PATH)
except Exception:
    _cc = None

# Data boundaries
_dm = load('derived_monthly')
MIN_DATE = _dm['date'].min().strftime('%Y-%m-%d')
MAX_DATE = _dm['date'].max().strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _m2_trend_chart(dm, cc_df):
    """M2 growth with trend line, background shaded by easing/tightening."""
    fig = go.Figure()

    # Background shading from credit cycle phases
    if cc_df is not None and len(cc_df) and 'phase' in cc_df.columns:
        phases = cc_df['phase'].tolist()
        dates = cc_df['date'].tolist()
        for i in range(len(dates) - 1):
            phase = phases[i]
            color = PHASE_COLORS.get(phase, '#45475a')
            fig.add_vrect(
                x0=dates[i], x1=dates[i + 1],
                fillcolor=color, opacity=0.08, line_width=0,
                layer='below',
            )

    fig.add_trace(go.Scatter(
        x=dm['date'], y=dm['m2_yoy'], name='M2同比',
        mode='lines', line=dict(color='#1a73e8', width=2),
    ))

    # Trend line if available from analysis
    if cc_df is not None and 'm2_trend' in cc_df.columns:
        # Merge by date
        merged = dm.merge(cc_df[['date', 'm2_trend']], on='date', how='left')
        fig.add_trace(go.Scatter(
            x=merged['date'], y=merged['m2_trend'], name='M2趋势',
            mode='lines', line=dict(color='#f39c12', width=2, dash='dash'),
        ))

    fig.update_layout(
        title=dict(text='M2同比增速与趋势', x=0.5),
        yaxis_title='%',
        **CHART_LAYOUT,
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    return make_range_slider(fig)


def _credit_impulse_chart(cc_df):
    """Credit impulse as bar chart."""
    if cc_df is None or 'credit_impulse' not in cc_df.columns:
        return go.Figure().update_layout(**CHART_LAYOUT, title='信用脉冲 (分析模块未就绪)')

    colors = ['#2ecc71' if v >= 0 else '#e74c3c'
              for v in cc_df['credit_impulse'].fillna(0)]
    fig = go.Figure(go.Bar(
        x=cc_df['date'], y=cc_df['credit_impulse'],
        marker_color=colors,
    ))
    fig.update_layout(
        title=dict(text='信用脉冲', x=0.5),
        **CHART_LAYOUT,
    )
    return make_range_slider(fig)


def _m2_cpi_overlay(dm):
    """M2 vs CPI showing leading relationship."""
    return make_range_slider(make_dual_axis_line(
        dm['date'], dm['m2_yoy'], dm['cpi_yoy'],
        'M2同比', 'CPI同比', 'M2 与 CPI 领先滞后关系',
        y1_color='#1a73e8', y2_color='#e74c3c',
    ))


# ---------------------------------------------------------------------------
# Phase badge
# ---------------------------------------------------------------------------
def _current_phase_badge(cc_df):
    if cc_df is None or not len(cc_df) or 'phase' not in cc_df.columns:
        return html.Div()
    phase = cc_df.iloc[-1]['phase']
    label = PHASE_LABELS.get(phase, phase)
    color = PHASE_COLORS.get(phase, '#888')
    return html.Div(
        style={
            'display': 'inline-flex', 'alignItems': 'center', 'gap': '6px',
            'backgroundColor': '#2d2d44', 'borderRadius': '16px',
            'padding': '6px 16px', 'marginBottom': '16px',
            'border': f'1px solid {color}', 'color': '#cdd6f4',
        },
        children=[
            html.Span(style={
                'width': '10px', 'height': '10px', 'borderRadius': '50%',
                'backgroundColor': color, 'display': 'inline-block',
            }),
            f'当前信用周期: {label}',
        ],
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = html.Div(
    style={'padding': '20px'},
    children=[
        make_date_range_selector(MIN_DATE, MAX_DATE, id_prefix='cc'),
        html.Div(id='cc-phase-badge'),
        make_card(
            [dcc.Graph(id='cc-m2-graph', config={'displayModeBar': False})],
            title='M2同比增速',
        ),
        html.Div(style={'height': '16px'}),
        make_card(
            [dcc.Graph(id='cc-impulse-graph', config={'displayModeBar': False})],
            title='信用脉冲',
        ),
        html.Div(style={'height': '16px'}),
        make_card(
            [dcc.Graph(id='cc-m2cpi-graph', config={'displayModeBar': False})],
            title='M2与CPI领先滞后关系',
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
def _filter_cc(cc_df, start, end):
    if cc_df is None:
        return None
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    return cc_df[(cc_df['date'] >= s) & (cc_df['date'] <= e)]


@callback(
    Output('cc-m2-graph', 'figure'),
    Output('cc-impulse-graph', 'figure'),
    Output('cc-m2cpi-graph', 'figure'),
    Output('cc-phase-badge', 'children'),
    Input('cc-picker', 'start_date'),
    Input('cc-picker', 'end_date'),
)
def update_credit_charts(start_date, end_date):
    dm = load('derived_monthly', start_date=start_date, end_date=end_date)
    cc_filtered = _filter_cc(_cc, start_date, end_date)
    return (
        _m2_trend_chart(dm, cc_filtered),
        _credit_impulse_chart(cc_filtered),
        _m2_cpi_overlay(dm),
        _current_phase_badge(cc_filtered),
    )


@callback(
    Output('cc-picker', 'start_date', allow_duplicate=True),
    Output('cc-picker', 'end_date', allow_duplicate=True),
    Input('cc-btn-5y', 'n_clicks'),
    Input('cc-btn-10y', 'n_clicks'),
    Input('cc-btn-20y', 'n_clicks'),
    Input('cc-btn-all', 'n_clicks'),
    prevent_initial_call=True,
)
def apply_preset(_5y, _10y, _20y, _all):
    trigger = ctx.triggered_id or ''
    if not trigger.startswith('cc-btn-'):
        return dash.no_update, dash.no_update
    preset = trigger.replace('cc-btn-', '')
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
