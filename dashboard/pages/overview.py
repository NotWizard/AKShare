"""P1 — Overview Dashboard (综合概览)."""

import dash
from dash import html, dcc, Input, Output, callback, ctx
import plotly.graph_objects as go
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from dashboard.db import load
from dashboard.config import CHART_LAYOUT, C, DB_PATH, FONT
from dashboard.components.charts import (
    make_dual_axis_line, make_area_chart, make_range_slider, _alpha,
)
from dashboard.components.controls import make_date_range_selector
from dashboard.components.layout import make_card, make_row, make_metric_tile, make_section

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
# Analysis signals (graceful fallback)
# ---------------------------------------------------------------------------
try:
    from analysis.signals import compute_signals
    _signals = compute_signals(DB_PATH)
except Exception:
    _signals = None


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _gdp_chart(dq):
    fig = go.Figure()
    if len(dq) and 'gdp_yoy' in dq.columns:
        fig.add_trace(go.Scatter(
            x=dq['date'], y=dq['gdp_yoy'], name='GDP同比',
            mode='lines+markers',
            line=dict(color=C['accent'], width=2.5),
            marker=dict(size=5, color=C['accent']),
            fill='tozeroy', fillcolor=_alpha(C['accent'], 0.10),
        ))
    if 'gdp_yoy_smooth' in dq.columns and dq['gdp_yoy_smooth'].notna().any():
        fig.add_trace(go.Scatter(
            x=dq['date'], y=dq['gdp_yoy_smooth'], name='趋势(4Q均线)',
            mode='lines',
            line=dict(color=C['warn'], width=2, dash='dot'),
        ))
    fig.add_hline(y=0, line_dash='solid', line_color=C['grid_hi'], line_width=1)
    fig.update_layout(title=dict(text='GDP 同比增长率'), yaxis_title='%')
    fig.update_layout(**CHART_LAYOUT)
    return make_range_slider(fig)


def _cpi_ppi_chart(dm):
    return make_range_slider(make_dual_axis_line(
        dm['date'], dm['cpi_yoy'], dm['ppi_yoy'],
        'CPI同比', 'PPI同比', 'CPI / PPI 同比走势',
        y1_color=C['warn'], y2_color=C['info'],
    ))


def _m1_m2_chart(dm):
    return make_range_slider(make_dual_axis_line(
        dm['date'], dm['m1_yoy'], dm['m2_yoy'],
        'M1同比', 'M2同比', 'M1 / M2 同比增速',
        y1_color=C['up'], y2_color=C['accent'],
    ))


def _spread_chart(dm):
    """M2-M1 spread with positive/negative coloring."""
    spread = dm['m2_m1_spread']
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dm['date'], y=spread, name='M2-M1 剪刀差',
        mode='lines',
        line=dict(color=C['accent'], width=2),
        fill='tozeroy',
        fillcolor=_alpha(C['accent'], 0.15),
    ))
    fig.add_hline(y=0, line_dash='solid', line_color=C['grid_hi'], line_width=1)
    fig.update_layout(title=dict(text='M2-M1 剪刀差'), yaxis_title='pp')
    fig.update_layout(**CHART_LAYOUT)
    return make_range_slider(fig)


def _pmi_chart(dm):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dm['date'], y=dm['pmi_official'], name='官方PMI',
        mode='lines', line=dict(color=C['accent'], width=2.5),
        fill='tozeroy', fillcolor=_alpha(C['accent'], 0.08),
    ))
    if 'pmi_ma6' in dm.columns and dm['pmi_ma6'].notna().any():
        fig.add_trace(go.Scatter(
            x=dm['date'], y=dm['pmi_ma6'], name='6月均线',
            mode='lines',
            line=dict(color=C['warn'], width=1.5, dash='dot'),
        ))
    fig.add_hline(y=50, line_dash='dash', line_color=C['down'], opacity=0.5,
                  annotation_text='荣枯线', annotation_font_color=C['text_3'],
                  annotation_font_size=10)
    fig.update_layout(title=dict(text='PMI 制造业指数'))
    fig.update_layout(**CHART_LAYOUT)
    return make_range_slider(fig)


def _leverage_chart(lev):
    return make_range_slider(make_area_chart(
        lev['date'],
        {'居民': lev['household'],
         '非金融企业': lev['non_fin_corp'],
         '政府': lev['gov_total']},
        '宏观杠杆率构成 (占GDP %)',
        colors_dict={
            '居民': C['up'],
            '非金融企业': C['down'],
            '政府': C['accent'],
        },
    ))


# ---------------------------------------------------------------------------
# KPI metric tiles
# ---------------------------------------------------------------------------
def _kpi_strip():
    """Top KPI strip with latest values."""
    tiles = []

    # Latest M2 growth
    if 'm2_yoy' in _dm.columns and _dm['m2_yoy'].notna().any():
        val = _dm['m2_yoy'].dropna().iloc[0]
        prev = _dm['m2_yoy'].dropna().iloc[1] if len(_dm['m2_yoy'].dropna()) > 1 else val
        delta = f'{val - prev:+.1f}pp' if pd.notna(prev) else None
        tiles.append(make_metric_tile('M2 增速', f'{val:.1f}%', delta))

    # Latest CPI
    if 'cpi_yoy' in _dm.columns and _dm['cpi_yoy'].notna().any():
        val = _dm['cpi_yoy'].dropna().iloc[0]
        color = C['warn'] if val > 0 else C['down'] if val < 0 else C['text']
        tiles.append(make_metric_tile('CPI 同比', f'{val:.1f}%', color=color))

    # Latest PMI
    if 'pmi_official' in _dm.columns and _dm['pmi_official'].notna().any():
        val = _dm['pmi_official'].dropna().iloc[0]
        color = C['up'] if val >= 50 else C['down']
        tiles.append(make_metric_tile('PMI', f'{val:.1f}', color=color))

    # M2-M1 spread
    if 'm2_m1_spread' in _dm.columns and _dm['m2_m1_spread'].notna().any():
        val = _dm['m2_m1_spread'].dropna().iloc[0]
        color = C['info'] if val > 0 else C['warn']
        tiles.append(make_metric_tile('M2-M1 剪刀差', f'{val:.1f}pp', color=color))

    # Composite signal
    if _signals and 'composite_score' in _signals:
        score = _signals['composite_score']
        color = C['up'] if score > 0 else C['down'] if score < 0 else C['warn']
        interpretation = _signals.get('interpretation', '')
        tiles.append(make_metric_tile('综合信号', f'{score:+.0f}', interpretation, color=color))

    if not tiles:
        return html.Div()

    return html.Div(
        style={
            'display': 'flex',
            'gap': '12px',
            'flexWrap': 'wrap',
            'marginBottom': '20px',
        },
        children=tiles,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def _card_with_graph(title, graph_id):
    return make_card(
        [dcc.Graph(id=graph_id, config={'displayModeBar': False})],
        title=title,
    )


layout = html.Div(
    style={'padding': '24px 28px'},
    children=[
        # Page header
        html.Div(
            style={'marginBottom': '20px'},
            children=[
                html.H1('综合概览', style={
                    'color': C['text'], 'fontSize': '22px', 'fontWeight': '700',
                    'margin': '0 0 4px 0', 'fontFamily': FONT,
                }),
                html.P('中国宏观经济核心指标一览', style={
                    'color': C['text_3'], 'fontSize': '13px', 'margin': '0',
                }),
            ],
        ),
        make_date_range_selector(MIN_DATE, MAX_DATE, id_prefix='ov'),
        # KPI strip
        _kpi_strip(),
        # Row 1 — GDP & CPI/PPI
        make_row(
            _card_with_graph('GDP 同比增长率', 'ov-gdp-graph'),
            _card_with_graph('CPI / PPI 同比走势', 'ov-cpi-graph'),
        ),
        # Row 2 — M1/M2 & Spread
        make_row(
            _card_with_graph('M1 / M2 同比增速', 'ov-m1m2-graph'),
            _card_with_graph('M2-M1 剪刀差', 'ov-spread-graph'),
        ),
        # Row 3 — PMI & Leverage
        make_row(
            _card_with_graph('PMI 制造业指数', 'ov-pmi-graph'),
            _card_with_graph('宏观杠杆率', 'ov-lev-graph'),
        ),
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

    empty = go.Figure().update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title='暂无数据')
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
