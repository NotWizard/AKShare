"""P6 — Real Estate (房地产市场)."""

import dash
from dash import html, dcc, Input, Output, callback, ctx
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from dashboard.db import load
from dashboard.config import C, CHART_LAYOUT, DB_PATH
from dashboard.components.charts import (
    _apply_layout, _alpha, make_dual_axis_line, make_range_slider,
    HOVER_PCT, HOVER_IDX, empty_dark_fig,
)
from dashboard.components.controls import make_date_range_selector, make_city_selector
from dashboard.components.layout import make_card, make_row, make_graph_card

dash.register_page(__name__, path='/real-estate', name='房地产市场', order=5)

# ---------------------------------------------------------------------------
# Try to load the analysis module
# ---------------------------------------------------------------------------
try:
    from analysis.real_estate import analyze_real_estate
    _HAS_RE = True
except Exception:
    _HAS_RE = False

# Data boundaries
_hp = load('house_price')
_lpr = load('lpr')
_lev = load('leverage')

ALL_CITIES = sorted(_hp['city'].unique().tolist())
MIN_DATE = min(_hp['date'].min(), _lpr['date'].min()).strftime('%Y-%m-%d')
MAX_DATE = max(_hp['date'].max(), _lpr['date'].max()).strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
LINE_COLORS = [
    C['accent'], C['up'], C['down'], C['warn'],
    '#7c3aed', '#0891b2', '#db2777', '#0d9488', '#ca8a04', '#475569',
]


def _price_index_chart(hp, cities):
    """Multi-line house price index (new_base) by selected cities."""
    fig = go.Figure()
    for i, city in enumerate(cities):
        city_data = hp[hp['city'] == city].sort_values('date')
        if len(city_data) and 'new_base' in city_data.columns:
            color = LINE_COLORS[i % len(LINE_COLORS)]
            fig.add_trace(go.Scatter(
                x=city_data['date'], y=city_data['new_base'],
                name=city, mode='lines',
                line=dict(color=color, width=2),
                hovertemplate=HOVER_IDX,
            ))

    fig.update_layout(
        yaxis_title='指数',
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    _apply_layout(fig)
    return make_range_slider(fig)


def _used_price_chart(hp, cities):
    """Multi-line used house price index by selected cities."""
    fig = go.Figure()
    for i, city in enumerate(cities):
        city_data = hp[hp['city'] == city].sort_values('date')
        if len(city_data) and 'used_base' in city_data.columns:
            color = LINE_COLORS[i % len(LINE_COLORS)]
            fig.add_trace(go.Scatter(
                x=city_data['date'], y=city_data['used_base'],
                name=city, mode='lines',
                line=dict(color=color, width=2),
                hovertemplate=HOVER_IDX,
            ))

    fig.update_layout(
        yaxis_title='指数',
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    _apply_layout(fig)
    return make_range_slider(fig)


def _leverage_vs_price(lev, hp, city):
    """Dual axis: household leverage vs city house price index."""
    city_data = hp[hp['city'] == city].sort_values('date')
    if not len(city_data) or not len(lev):
        return go.Figure().update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title='暂无数据')

    # Merge on date (quarterly leverage, monthly prices — forward-fill leverage)
    merged = city_data[['date', 'new_base']].copy()
    lev_q = lev[['date', 'household']].copy()
    lev_q.columns = ['date', 'hh_lev']
    merged = merged.merge(lev_q, on='date', how='left')
    merged['hh_lev'] = merged['hh_lev'].ffill()

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=merged['date'], y=merged['hh_lev'],
                   name='居民杠杆率', mode='lines',
                   line=dict(color=C['down'], width=2),
                   hovertemplate=HOVER_PCT),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=merged['date'], y=merged['new_base'],
                   name=f'{city}新房指数', mode='lines',
                   line=dict(color=C['accent'], width=2),
                   hovertemplate=HOVER_IDX),
        secondary_y=True,
    )
    fig.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    fig.update_yaxes(title_text='杠杆率 (%)', secondary_y=False)
    fig.update_yaxes(title_text='房价指数', secondary_y=True)
    _apply_layout(fig)
    return make_range_slider(fig)


def _lpr_trend_chart(lpr_df):
    """LPR 5Y trend with historical percentile bands."""
    if not len(lpr_df):
        return go.Figure().update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title='暂无LPR数据')

    fig = go.Figure()
    lpr5 = lpr_df['lpr_5y'].dropna()

    # Percentile bands
    if len(lpr5) > 10:
        p10 = lpr5.expanding().quantile(0.10)
        p90 = lpr5.expanding().quantile(0.90)
        dates_valid = lpr_df.loc[lpr5.index, 'date']
        fig.add_trace(go.Scatter(
            x=dates_valid, y=p90, name='90%分位',
            mode='lines', line=dict(color=C['border'], width=1, dash='dot'),
            hovertemplate=HOVER_PCT,
        ))
        fig.add_trace(go.Scatter(
            x=dates_valid, y=p10, name='10%分位',
            mode='lines', line=dict(color=C['border'], width=1, dash='dot'),
            fill='tonexty', fillcolor='rgba(37,99,235,0.08)',
            hovertemplate=HOVER_PCT,
        ))

    fig.add_trace(go.Scatter(
        x=lpr_df['date'], y=lpr_df['lpr_5y'], name='LPR 5年期',
        mode='lines', line=dict(color=C['accent'], width=2.5),
        hovertemplate=HOVER_PCT,
    ))

    fig.update_layout(
        yaxis_title='%',
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    _apply_layout(fig)
    return make_range_slider(fig)


def _hh_debt_to_income_chart(dq):
    """Household debt / disposable income ratio — more realistic leverage gauge."""
    if dq is None or 'hh_debt_to_income' not in dq.columns or dq['hh_debt_to_income'].isna().all():
        return go.Figure().update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        )

    fig = go.Figure()
    s = dq['hh_debt_to_income'].dropna()
    if len(s) > 10:
        dates_valid = dq.loc[s.index, 'date']
        p90 = s.expanding().quantile(0.90)
        median = s.expanding().median()
        fig.add_trace(go.Scatter(
            x=dates_valid, y=p90, name='90%分位',
            mode='lines', line=dict(color=C['border'], width=1, dash='dot'),
            hovertemplate=HOVER_PCT,
        ))
        fig.add_trace(go.Scatter(
            x=dates_valid, y=median, name='历史中位',
            mode='lines', line=dict(color=C['warn'], width=1, dash='dot'),
            hovertemplate=HOVER_PCT,
        ))

    fig.add_trace(go.Scatter(
        x=dq['date'], y=dq['hh_debt_to_income'], name='债务/可支配收入',
        mode='lines', line=dict(color=C['down'], width=2.5),
        fill='tozeroy', fillcolor=_alpha(C['down'], 0.10),
        hovertemplate=HOVER_PCT,
    ))
    fig.update_layout(
        yaxis_title='%',
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    _apply_layout(fig)
    return make_range_slider(fig)


def _radar_chart(assessment):
    """Radar chart for 4-dimension real estate assessment."""
    if assessment is None or not isinstance(assessment, dict):
        return go.Figure().update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', title='房地产综合评估 (分析模块未就绪)')

    dims = ['价格动量', '杠杆空间', '利率环境', '综合评分']
    key_map = {
        '价格动量': 'price_momentum_score',
        '杠杆空间': 'leverage_space_score',
        '利率环境': 'rate_env_score',
        '综合评分': 'composite_score',
    }
    vals = [assessment.get(key_map[d], 50) / 100.0 for d in dims]

    fig = go.Figure(go.Scatterpolar(
        r=vals + [vals[0]],
        theta=dims + [dims[0]],
        fill='toself',
        line=dict(color=C['accent']),
        fillcolor='rgba(37,99,235,0.15)',
        hovertemplate='<b>%{theta}</b>: %{r:.2f}<extra></extra>',
    ))
    fig.update_layout(
        hovermode='closest',
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1],
                            gridcolor=C['border'], color=C['text']),
            angularaxis=dict(gridcolor=C['border'], color=C['text']),
            bgcolor='rgba(255,255,255,0)',
        ),
    )
    _apply_layout(fig)
    return fig


def _assessment_text(assessment):
    if assessment is None or not isinstance(assessment, dict):
        return html.P('房地产评估分析模块尚未就绪。', style={'color': C['text_2']})
    text = assessment.get('summary', '暂无综合评估文本。')
    return html.Div(
        style={
            'backgroundColor': C['card'], 'borderRadius': '8px',
            'padding': '16px', 'marginTop': '12px',
            'borderLeft': f'4px solid {C["accent"]}',
        },
        children=[
            html.H4('市场综合评估', style={
                'color': C['text'], 'marginTop': '0', 'marginBottom': '8px',
                'fontSize': '15px',
            }),
            html.P(text, style={'color': C['text_2'], 'margin': '0', 'fontSize': '14px',
                                'lineHeight': '1.6'}),
        ],
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div(
    style={'padding': '20px'},
    children=[
        make_date_range_selector(MIN_DATE, MAX_DATE, id_prefix='re'),
        make_city_selector(ALL_CITIES, id_prefix='re'),
        # Price charts
        make_row(
            make_graph_card(
                '新建住宅价格指数', 're-new-graph',
                tip='以定基指数展示各城市新建住宅价格的长期走势，便于跨城市比较。'
            ),
            make_graph_card(
                '二手住宅价格指数', 're-used-graph',
                tip='以定基指数展示各城市二手住宅价格的长期走势，反映二手市场热度。'
            ),
        ),
        # Leverage vs price & LPR
        make_row(
            make_graph_card(
                '杠杆率 vs 房价', 're-lev-price-graph',
                tip='对比居民部门杠杆率与重点城市房价指数，观察杠杆对房价的支撑空间。'
            ),
            make_graph_card(
                'LPR 5年期利率', 're-lpr-graph',
                tip='房贷利率基准；同时展示历史 10%/90% 分位区间，判断当前利率相对历史的高低。'
            ),
        ),
        # Household real leverage
        make_graph_card(
            '居民真实杠杆率 (债务 / 可支配收入)', 're-hh-debt-graph',
            tip='居民债务余额除以可支配收入，比债务/GDP 更真实反映居民偿债压力；数值越高负担越重。'
        ),
        # Radar & assessment
        make_row(
            make_graph_card(
                '综合评估雷达', 're-radar-graph',
                tip='从价格动量、杠杆空间、利率环境、综合评分四个维度评估房地产市场整体健康度。'
            ),
            make_card(
                [html.Div(id='re-assessment-text')],
                title='市场评估',
                tip='基于上述三维评分给出的综合结论，分数越高表示当前环境对住房需求越有利。',
            ),
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output('re-new-graph', 'figure'),
    Output('re-used-graph', 'figure'),
    Output('re-lev-price-graph', 'figure'),
    Output('re-lpr-graph', 'figure'),
    Output('re-hh-debt-graph', 'figure'),
    Output('re-radar-graph', 'figure'),
    Output('re-assessment-text', 'children'),
    Input('re-picker', 'start_date'),
    Input('re-picker', 'end_date'),
    Input('re-city-selector', 'value'),
)
def update_re_charts(start_date, end_date, cities):
    if not cities:
        cities = ALL_CITIES[:4]

    hp = load('house_price', start_date=start_date, end_date=end_date)
    lpr_df = load('lpr', start_date=start_date, end_date=end_date)
    lev = load('leverage', start_date=start_date, end_date=end_date)
    dq = load('derived_quarterly', start_date=start_date, end_date=end_date)

    # Get analysis if available
    assessment = None
    if _HAS_RE:
        try:
            result = analyze_real_estate(DB_PATH, cities)
            assessment = result.get('assessment')
        except Exception:
            pass

    # Pick the first selected city for leverage-vs-price comparison
    primary_city = cities[0] if cities else ALL_CITIES[0]

    return (
        _price_index_chart(hp, cities),
        _used_price_chart(hp, cities),
        _leverage_vs_price(lev, hp, primary_city),
        _lpr_trend_chart(lpr_df),
        _hh_debt_to_income_chart(dq),
        _radar_chart(assessment),
        _assessment_text(assessment),
    )


@callback(
    Output('re-picker', 'start_date', allow_duplicate=True),
    Output('re-picker', 'end_date', allow_duplicate=True),
    Input('re-btn-5y', 'n_clicks'),
    Input('re-btn-10y', 'n_clicks'),
    Input('re-btn-20y', 'n_clicks'),
    Input('re-btn-all', 'n_clicks'),
    prevent_initial_call=True,
)
def apply_preset(_5y, _10y, _20y, _all):
    trigger = ctx.triggered_id or ''
    if not trigger.startswith('re-btn-'):
        return dash.no_update, dash.no_update
    preset = trigger.replace('re-btn-', '')
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
