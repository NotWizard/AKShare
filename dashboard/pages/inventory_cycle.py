"""P4 — Inventory Cycle (库存周期)."""

import dash
from dash import html, dcc, Input, Output, callback, ctx
import plotly.graph_objects as go
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from dashboard.db import load
from dashboard.config import C, CHART_LAYOUT, PHASE_COLORS, PHASE_LABELS, DB_PATH
from dashboard.components.charts import (
    _apply_layout, make_range_slider, add_phase_background,
    make_phase_timeline, HOVER_PCT, HOVER_IDX,
)
from dashboard.components.controls import make_date_range_selector
from dashboard.components.layout import make_card, make_row

dash.register_page(__name__, path='/inventory-cycle', name='库存周期', order=3)

# ---------------------------------------------------------------------------
# Try to load the analysis module
# ---------------------------------------------------------------------------
try:
    from analysis.cycle_inventory import classify_inventory
    _ic = classify_inventory(DB_PATH)
except Exception:
    _ic = None

# Data boundaries
_dm = load('derived_monthly')
MIN_DATE = _dm['date'].min().strftime('%Y-%m-%d')
MAX_DATE = _dm['date'].max().strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _pmi_chart(dm, ic_df):
    """PMI with 50-line and 6M MA, background shaded by inventory phase."""
    fig = go.Figure()

    # Background shading (merged segments)
    if ic_df is not None and len(ic_df) and 'phase' in ic_df.columns:
        add_phase_background(
            fig,
            ic_df['date'].tolist(),
            ic_df['phase'].tolist(),
            PHASE_COLORS,
        )

    fig.add_trace(go.Scatter(
        x=dm['date'], y=dm['pmi_official'], name='官方PMI',
        mode='lines', line=dict(color=C['accent'], width=2),
        hovertemplate=HOVER_IDX,
    ))
    if 'pmi_ma6' in dm.columns and dm['pmi_ma6'].notna().any():
        fig.add_trace(go.Scatter(
            x=dm['date'], y=dm['pmi_ma6'], name='PMI 6月均线',
            mode='lines', line=dict(color='#f39c12', width=1.5, dash='dot'),
            hovertemplate=HOVER_IDX,
        ))

    fig.add_hline(y=50, line_dash='dash', line_color='#e74c3c', opacity=0.6,
                  annotation_text='荣枯线')

    fig.update_layout(
        title=dict(text='PMI制造业指数与库存周期', x=0.5),
        yaxis_title='PMI',
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    _apply_layout(fig)
    return make_range_slider(fig)


def _ip_chart(dm, ic_df):
    """Industrial production YoY with trend, background by phase."""
    fig = go.Figure()

    # Background shading (merged segments)
    if ic_df is not None and len(ic_df) and 'phase' in ic_df.columns:
        add_phase_background(
            fig,
            ic_df['date'].tolist(),
            ic_df['phase'].tolist(),
            PHASE_COLORS,
        )

    fig.add_trace(go.Scatter(
        x=dm['date'], y=dm['ip_yoy'], name='工业增加值同比',
        mode='lines', line=dict(color=C['accent'], width=2),
        hovertemplate=HOVER_PCT,
    ))
    if 'ip_trend' in dm.columns and dm['ip_trend'].notna().any():
        fig.add_trace(go.Scatter(
            x=dm['date'], y=dm['ip_trend'], name='工业趋势',
            mode='lines', line=dict(color='#f39c12', width=2, dash='dash'),
            hovertemplate=HOVER_PCT,
        ))

    fig.update_layout(
        title=dict(text='工业增加值同比与趋势', x=0.5),
        yaxis_title='%',
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    _apply_layout(fig)
    return make_range_slider(fig)


def _phase_timeline(ic_df):
    """Horizontal bar showing inventory cycle phase transitions."""
    if ic_df is None or not len(ic_df) or 'phase' not in ic_df.columns:
        return go.Figure().update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title='库存周期阶段 (分析模块未就绪)')

    fig = make_phase_timeline(
        ic_df['date'].tolist(),
        ic_df['phase'].tolist(),
        PHASE_COLORS,
        PHASE_LABELS,
        title='库存周期阶段时间线',
    )
    return make_range_slider(fig)


def _current_phase_badge(ic_df):
    if ic_df is None or not len(ic_df) or 'phase' not in ic_df.columns:
        return html.Div()
    phase = ic_df.iloc[-1]['phase']
    label = PHASE_LABELS.get(phase, phase)
    color = PHASE_COLORS.get(phase, '#888')
    return html.Div(
        style={
            'display': 'inline-flex', 'alignItems': 'center', 'gap': '6px',
            'backgroundColor': C['card'], 'borderRadius': '16px',
            'padding': '6px 16px', 'marginBottom': '16px',
            'border': f'1px solid {color}', 'color': C['text'],
        },
        children=[
            html.Span(style={
                'width': '10px', 'height': '10px', 'borderRadius': '50%',
                'backgroundColor': color, 'display': 'inline-block',
            }),
            f'当前库存周期: {label}',
        ],
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
layout = html.Div(
    style={'padding': '20px'},
    children=[
        make_date_range_selector(MIN_DATE, MAX_DATE, id_prefix='ic'),
        html.Div(id='ic-phase-badge'),
        make_row(
            make_card(
                [dcc.Graph(id='ic-pmi-graph', config={'displayModeBar': False})],
                title='PMI制造业指数',
            ),
            make_card(
                [dcc.Graph(id='ic-ip-graph', config={'displayModeBar': False})],
                title='工业增加值同比',
            ),
        ),
        make_card(
            [dcc.Graph(id='ic-timeline-graph', config={'displayModeBar': False})],
            title='库存周期阶段',
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
def _filter_ic(ic_df, start, end):
    if ic_df is None:
        return None
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    return ic_df[(ic_df['date'] >= s) & (ic_df['date'] <= e)]


@callback(
    Output('ic-pmi-graph', 'figure'),
    Output('ic-ip-graph', 'figure'),
    Output('ic-timeline-graph', 'figure'),
    Output('ic-phase-badge', 'children'),
    Input('ic-picker', 'start_date'),
    Input('ic-picker', 'end_date'),
)
def update_inventory_charts(start_date, end_date):
    dm = load('derived_monthly', start_date=start_date, end_date=end_date)
    ic_filtered = _filter_ic(_ic, start_date, end_date)
    return (
        _pmi_chart(dm, ic_filtered),
        _ip_chart(dm, ic_filtered),
        _phase_timeline(ic_filtered),
        _current_phase_badge(ic_filtered),
    )


@callback(
    Output('ic-picker', 'start_date', allow_duplicate=True),
    Output('ic-picker', 'end_date', allow_duplicate=True),
    Input('ic-btn-5y', 'n_clicks'),
    Input('ic-btn-10y', 'n_clicks'),
    Input('ic-btn-20y', 'n_clicks'),
    Input('ic-btn-all', 'n_clicks'),
    prevent_initial_call=True,
)
def apply_preset(_5y, _10y, _20y, _all):
    trigger = ctx.triggered_id or ''
    if not trigger.startswith('ic-btn-'):
        return dash.no_update, dash.no_update
    preset = trigger.replace('ic-btn-', '')
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
