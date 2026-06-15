"""P1 — Overview Dashboard (综合概览)."""

import dash
from dash import html, dcc, Input, Output, State, callback, ctx
import plotly.graph_objects as go
from datetime import datetime
from dateutil.relativedelta import relativedelta

from dashboard.db import load
from dashboard.config import CHART_LAYOUT
from dashboard.components.charts import (
    make_dual_axis_line, make_area_chart, make_range_slider,
)
from dashboard.components.controls import make_date_range_selector
from dashboard.components.layout import make_card, make_row

dash.register_page(__name__, path='/', name='综合概览', order=0)

# ---------------------------------------------------------------------------
# Data boundaries
# ---------------------------------------------------------------------------
_dm = load('derived_monthly')
_dq = load('derived_quarterly')
_lev = load('leverage')

MIN_DATE = min(_dm['date'].min(), _dq['date'].min()).strftime('%Y-%m-%d')
MAX_DATE = max(_dm['date'].max(), _dq['date'].max()).strftime('%Y-%m-%d')

# ---------------------------------------------------------------------------
# Try to load analysis signals (graceful fallback)
# ---------------------------------------------------------------------------
try:
    from analysis.signals import compute_signals
    from dashboard.config import DB_PATH
    _signals = compute_signals(DB_PATH)
except Exception:
    _signals = None


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _gdp_chart(dq):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dq['date'], y=dq['gdp_yoy'], name='GDP同比',
        mode='lines+markers', line=dict(color='#1a73e8', width=2),
        marker=dict(size=5),
    ))
    if 'gdp_yoy_smooth' in dq.columns and dq['gdp_yoy_smooth'].notna().any():
        fig.add_trace(go.Scatter(
            x=dq['date'], y=dq['gdp_yoy_smooth'], name='GDP同比(平滑)',
            mode='lines', line=dict(color='#e74c3c', width=2, dash='dash'),
        ))
    fig.update_layout(title=dict(text='GDP同比增长率', x=0.5),
                      yaxis_title='%', **CHART_LAYOUT)
    return make_range_slider(fig)


def _cpi_ppi_chart(dm):
    return make_range_slider(make_dual_axis_line(
        dm['date'], dm['cpi_yoy'], dm['ppi_yoy'],
        'CPI同比', 'PPI同比', 'CPI / PPI 同比走势',
    ))


def _m1_m2_chart(dm):
    return make_range_slider(make_dual_axis_line(
        dm['date'], dm['m1_yoy'], dm['m2_yoy'],
        'M1同比', 'M2同比', 'M1 / M2 同比增速',
        y1_color='#f39c12', y2_color='#1a73e8',
    ))


def _spread_chart(dm):
    return make_range_slider(make_area_chart(
        dm['date'],
        {'M2-M1剪刀差': dm['m2_m1_spread']},
        'M2-M1 剪刀差',
        colors_dict={'M2-M1剪刀差': '#2ecc71'},
        stack=False,
    ))


def _pmi_chart(dm):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dm['date'], y=dm['pmi_official'], name='官方PMI',
        mode='lines', line=dict(color='#1a73e8', width=2),
    ))
    if 'pmi_ma6' in dm.columns and dm['pmi_ma6'].notna().any():
        fig.add_trace(go.Scatter(
            x=dm['date'], y=dm['pmi_ma6'], name='PMI 6月均线',
            mode='lines', line=dict(color='#f39c12', width=1.5, dash='dot'),
        ))
    fig.add_hline(y=50, line_dash='dash', line_color='#e74c3c', opacity=0.6)
    fig.update_layout(title=dict(text='PMI制造业指数', x=0.5), **CHART_LAYOUT)
    return make_range_slider(fig)


def _leverage_chart(lev):
    return make_range_slider(make_area_chart(
        lev['date'],
        {'居民杠杆': lev['household'],
         '非金融企业杠杆': lev['non_fin_corp'],
         '政府杠杆': lev['gov_total']},
        '宏观杠杆率构成 (占GDP比重)',
        colors_dict={'居民杠杆': '#2ecc71',
                     '非金融企业杠杆': '#e74c3c',
                     '政府杠杆': '#1a73e8'},
    ))


# ---------------------------------------------------------------------------
# Signals badges
# ---------------------------------------------------------------------------
def _signals_section() -> html.Div:
    if _signals is None:
        return html.Div()
    badges = []
    score = _signals.get('composite_score')
    if score is not None:
        color = '#2ecc71' if score > 0 else '#e74c3c' if score < 0 else '#f39c12'
        badges.append(html.Span(
            style={
                'display': 'inline-flex', 'alignItems': 'center', 'gap': '6px',
                'backgroundColor': '#2d2d44', 'borderRadius': '16px',
                'padding': '6px 16px', 'marginRight': '10px',
                'border': f'1px solid {color}', 'color': '#cdd6f4',
            },
            children=[
                html.Span(style={
                    'width': '10px', 'height': '10px', 'borderRadius': '50%',
                    'backgroundColor': color, 'display': 'inline-block',
                }),
                f'综合信号: {score:.1f}',
            ],
        ))
    return html.Div(style={'marginTop': '16px'}, children=badges)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def _card_with_graph(title, graph_id):
    return make_card(
        [dcc.Graph(id=graph_id, config={'displayModeBar': False})],
        title=title,
    )


layout = html.Div(
    style={'padding': '20px'},
    children=[
        make_date_range_selector(MIN_DATE, MAX_DATE, id_prefix='ov'),
        # Row 1 — GDP & CPI/PPI
        make_row(
            _card_with_graph('GDP同比增长率', 'ov-gdp-graph'),
            _card_with_graph('CPI / PPI 同比走势', 'ov-cpi-graph'),
        ),
        # Row 2 — M1/M2 & Spread
        make_row(
            _card_with_graph('M1 / M2 同比增速', 'ov-m1m2-graph'),
            _card_with_graph('M2-M1 剪刀差', 'ov-spread-graph'),
        ),
        # Row 3 — PMI & Leverage
        make_row(
            _card_with_graph('PMI制造业指数', 'ov-pmi-graph'),
            _card_with_graph('宏观杠杆率', 'ov-lev-graph'),
        ),
        # Signals
        _signals_section(),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output('ov-gdp-graph', 'figure'),
    Output('ov-cpi-graph', 'figure'),
    Output('ov-m1m2-graph', 'figure'),
    Output('ov-spread-graph', 'figure'),
    Output('ov-pmi-graph', 'figure'),
    Output('ov-lev-graph', 'figure'),
    Input('ov-picker', 'start_date'),
    Input('ov-picker', 'end_date'),
)
def update_overview_charts(start_date, end_date):
    dm = load('derived_monthly', start_date=start_date, end_date=end_date)
    dq = load('derived_quarterly', start_date=start_date, end_date=end_date)
    lev = load('leverage', start_date=start_date, end_date=end_date)

    empty = go.Figure().update_layout(**CHART_LAYOUT, title='暂无数据')
    return (
        _gdp_chart(dq) if len(dq) else empty,
        _cpi_ppi_chart(dm) if len(dm) else empty,
        _m1_m2_chart(dm) if len(dm) else empty,
        _spread_chart(dm) if len(dm) else empty,
        _pmi_chart(dm) if len(dm) else empty,
        _leverage_chart(lev) if len(lev) else empty,
    )


@callback(
    Output('ov-picker', 'start_date', allow_duplicate=True),
    Output('ov-picker', 'end_date', allow_duplicate=True),
    Input('ov-btn-5y', 'n_clicks'),
    Input('ov-btn-10y', 'n_clicks'),
    Input('ov-btn-20y', 'n_clicks'),
    Input('ov-btn-all', 'n_clicks'),
    prevent_initial_call=True,
)
def apply_preset(_5y, _10y, _20y, _all):
    trigger = ctx.triggered_id or ''
    if not trigger.startswith('ov-btn-'):
        return dash.no_update, dash.no_update
    preset = trigger.replace('ov-btn-', '')
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
