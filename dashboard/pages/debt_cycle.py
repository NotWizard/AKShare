"""P5 — Debt Cycle (债务周期)."""

import dash
from dash import html, dcc, Input, Output, callback, ctx
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import numpy as np

from dashboard.db import load
from dashboard.config import C, CHART_LAYOUT, PHASE_COLORS, PHASE_LABELS, DB_PATH
from dashboard.components.charts import make_area_chart, make_range_slider
from dashboard.components.controls import make_date_range_selector, make_phase_badge
from dashboard.components.layout import make_card, make_row

dash.register_page(__name__, path='/debt-cycle', name='债务周期', order=4)

# ---------------------------------------------------------------------------
# Try to load the analysis module
# ---------------------------------------------------------------------------
try:
    from analysis.cycle_debt import classify_debt
    _dc = classify_debt(DB_PATH)
except Exception:
    _dc = None

# Data boundaries
_lev = load('leverage')
MIN_DATE = _lev['date'].min().strftime('%Y-%m-%d')
MAX_DATE = _lev['date'].max().strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _leverage_stacked(lev):
    """Stacked area chart: household / corporate / government leverage."""
    return make_range_slider(make_area_chart(
        lev['date'],
        {
            '居民杠杆': lev['household'],
            '非金融企业杠杆': lev['non_fin_corp'],
            '政府杠杆': lev['gov_total'],
        },
        '宏观杠杆率构成 (占GDP比重 %)',
        colors_dict={
            '居民杠杆': '#2ecc71',
            '非金融企业杠杆': '#e74c3c',
            '政府杠杆': C['accent'],
        },
    ))


def _leverage_change_speed(lev):
    """Year-over-year change in leverage (Δ per year) as bar chart."""
    if len(lev) < 5:
        return go.Figure().update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title='暂无足够数据')

    # Compute annual change (~4 quarters back for quarterly data)
    df = lev.copy().sort_values('date')
    for col in ['household', 'non_fin_corp', 'gov_total']:
        df[f'{col}_dy'] = df[col].diff(4)

    fig = make_subplots()
    for col, name, color in [
        ('household_dy', '居民', '#2ecc71'),
        ('non_fin_corp_dy', '非金融企业', '#e74c3c'),
        ('gov_total_dy', '政府', C['accent']),
    ]:
        fig.add_trace(go.Bar(
            x=df['date'], y=df[col], name=name,
            marker_color=color, opacity=0.8,
        ))

    fig.update_layout(
        title=dict(text='杠杆率变化速度 (年度Δ)', x=0.5),
        barmode='group',
        **CHART_LAYOUT,
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    return make_range_slider(fig)


def _gov_breakdown(lev):
    """Central vs local government leverage."""
    fig = go.Figure()
    if 'gov_central' in lev.columns and lev['gov_central'].notna().any():
        fig.add_trace(go.Scatter(
            x=lev['date'], y=lev['gov_central'], name='中央政府杠杆',
            mode='lines', line=dict(color=C['accent'], width=2),
            fill='tozeroy', fillcolor='rgba(26,115,232,0.15)',
        ))
    if 'gov_local' in lev.columns and lev['gov_local'].notna().any():
        fig.add_trace(go.Scatter(
            x=lev['date'], y=lev['gov_local'], name='地方政府杠杆',
            mode='lines', line=dict(color='#f39c12', width=2),
            fill='tozeroy', fillcolor='rgba(243,156,18,0.15)',
        ))
    fig.update_layout(
        title=dict(text='政府杠杆: 中央 vs 地方', x=0.5),
        yaxis_title='%',
        **CHART_LAYOUT,
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    return make_range_slider(fig)


# ---------------------------------------------------------------------------
# Phase badges
# ---------------------------------------------------------------------------
def _phase_badges(dc_df):
    if dc_df is None or not len(dc_df):
        return html.Div(style={'marginBottom': '12px'},
                        children=[html.Span('分析模块未就绪', style={'color': C['text_2']})])

    last = dc_df.iloc[-1]
    badges = []
    for col, sector in [('household_phase', '居民'),
                         ('corp_phase', '企业'),
                         ('gov_phase', '政府'),
                         ('overall_phase', '整体')]:
        phase = last.get(col)
        if phase and phase is not np.nan:
            label = PHASE_LABELS.get(str(phase), str(phase))
            color = PHASE_COLORS.get(str(phase), C['text_2'])
            badges.append(make_phase_badge(str(phase), color, f'{sector}: {label}'))

    return html.Div(style={'marginBottom': '12px', 'display': 'flex',
                           'flexWrap': 'wrap', 'gap': '8px'},
                    children=badges)


def _dalio_assessment(dc_df, lev):
    """Generate a brief Dalio-framework text assessment."""
    if dc_df is None or not len(dc_df) or lev is None or not len(lev):
        return html.P('债务周期分析模块尚未就绪。', style={'color': C['text_2']})

    last_lev = lev.iloc[-1]
    last_dc = dc_df.iloc[-1]

    total = last_lev.get('real_economy', 0) or 0
    lines = [
        f'实体经济总杠杆率: {total:.1f}%',
    ]

    overall = last_dc.get('overall_phase', '')
    if overall:
        label = PHASE_LABELS.get(str(overall), str(overall))
        lines.append(f'整体债务周期阶段: {label}')

    return html.Div(
        style={
            'backgroundColor': C['card'], 'borderRadius': '8px',
            'padding': '16px', 'marginTop': '12px',
            'borderLeft': '4px solid #1a73e8',
        },
        children=[
            html.H4('达里奥债务周期框架评估', style={
                'color': C['text'], 'marginTop': '0', 'marginBottom': '8px',
                'fontSize': '15px',
            }),
        ] + [
            html.P(line, style={'color': C['text_2'], 'margin': '4px 0', 'fontSize': '14px'})
            for line in lines
        ],
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = html.Div(
    style={'padding': '20px'},
    children=[
        make_date_range_selector(MIN_DATE, MAX_DATE, id_prefix='dc'),
        html.Div(id='dc-phase-badges'),
        make_card(
            [dcc.Graph(id='dc-stack-graph', config={'displayModeBar': False})],
            title='宏观杠杆率构成',
        ),
        html.Div(style={'height': '16px'}),
        make_row(
            make_card(
                [dcc.Graph(id='dc-speed-graph', config={'displayModeBar': False})],
                title='杠杆率变化速度',
            ),
            make_card(
                [dcc.Graph(id='dc-gov-graph', config={'displayModeBar': False})],
                title='政府杠杆拆分',
            ),
        ),
        html.Div(id='dc-assessment'),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
def _filter_dc(dc_df, start, end):
    if dc_df is None:
        return None
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    return dc_df[(dc_df['date'] >= s) & (dc_df['date'] <= e)]


@callback(
    Output('dc-stack-graph', 'figure'),
    Output('dc-speed-graph', 'figure'),
    Output('dc-gov-graph', 'figure'),
    Output('dc-phase-badges', 'children'),
    Output('dc-assessment', 'children'),
    Input('dc-picker', 'start_date'),
    Input('dc-picker', 'end_date'),
)
def update_debt_charts(start_date, end_date):
    lev = load('leverage', start_date=start_date, end_date=end_date)
    dc_filtered = _filter_dc(_dc, start_date, end_date)
    return (
        _leverage_stacked(lev),
        _leverage_change_speed(lev),
        _gov_breakdown(lev),
        _phase_badges(dc_filtered),
        _dalio_assessment(dc_filtered, lev),
    )


@callback(
    Output('dc-picker', 'start_date', allow_duplicate=True),
    Output('dc-picker', 'end_date', allow_duplicate=True),
    Input('dc-btn-5y', 'n_clicks'),
    Input('dc-btn-10y', 'n_clicks'),
    Input('dc-btn-20y', 'n_clicks'),
    Input('dc-btn-all', 'n_clicks'),
    prevent_initial_call=True,
)
def apply_preset(_5y, _10y, _20y, _all):
    trigger = ctx.triggered_id or ''
    if not trigger.startswith('dc-btn-'):
        return dash.no_update, dash.no_update
    preset = trigger.replace('dc-btn-', '')
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
