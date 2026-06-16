"""Reusable UI controls — date pickers, selectors, phase badges."""

from __future__ import annotations
from dash import dcc, html
from dashboard.config import C, FONT


def make_date_range_selector(
    min_date: str,
    max_date: str,
    id_prefix: str = 'global',
) -> html.Div:
    """DatePickerRange + preset buttons (5Y / 10Y / 20Y / 全部).

    Component IDs produced:
    - ``{id_prefix}-picker``
    - ``{id_prefix}-btn-5y``, ``-btn-10y``, ``-btn-20y``, ``-btn-all``
    """
    btn_style = {
        'backgroundColor': 'transparent',
        'color': C['text_3'],
        'border': f'1px solid {C["border"]}',
        'borderRadius': '6px',
        'padding': '5px 14px',
        'cursor': 'pointer',
        'fontSize': '12px',
        'fontWeight': '500',
        'fontFamily': FONT,
        'transition': 'all 0.15s ease',
    }
    return html.Div(
        style={
            'display': 'flex',
            'alignItems': 'center',
            'gap': '12px',
            'marginBottom': '20px',
            'flexWrap': 'wrap',
            'padding': '10px 16px',
            'backgroundColor': C['surface'],
            'borderRadius': '10px',
            'border': f'1px solid {C["border"]}',
        },
        children=[
            dcc.DatePickerRange(
                id=f'{id_prefix}-picker',
                min_date_allowed=min_date,
                max_date_allowed=max_date,
                start_date=min_date,
                end_date=max_date,
                display_format='YYYY-MM-DD',
                className='dark-date-picker',
                style={'backgroundColor': 'transparent', 'flex': '1'},
            ),
            html.Div(
                style={'display': 'flex', 'gap': '6px', 'marginLeft': 'auto'},
                children=[
                    html.Button(
                        label,
                        id=f'{id_prefix}-btn-{key}',
                        n_clicks=0,
                        style=btn_style,
                    )
                    for key, label in [
                        ('5y', '5Y'), ('10y', '10Y'),
                        ('20y', '20Y'), ('all', '全部'),
                    ]
                ],
            ),
        ],
    )


def make_city_selector(
    cities: list[str],
    id_prefix: str = 're',
) -> html.Div:
    """Multi-select dropdown for cities."""
    return html.Div(
        style={
            'display': 'flex',
            'alignItems': 'center',
            'gap': '10px',
            'marginBottom': '16px',
        },
        children=[
            html.Label(
                '城市',
                style={
                    'color': C['text_2'],
                    'fontSize': '13px',
                    'fontWeight': '500',
                    'fontFamily': FONT,
                },
            ),
            dcc.Dropdown(
                id=f'{id_prefix}-city-selector',
                options=[{'label': c, 'value': c} for c in cities],
                value=cities[:4],
                multi=True,
                className='dark-dropdown',
                style={'minWidth': '320px', 'flex': '1'},
            ),
        ],
    )


def make_phase_badge(
    phase: str,
    color: str,
    label: str | None = None,
) -> html.Span:
    """Glassmorphic phase badge with colored glow."""
    display = label or phase
    # Convert hex color to rgba with 15% opacity (Plotly-safe)
    _h = color.lstrip('#')
    _r, _g, _b = int(_h[0:2], 16), int(_h[2:4], 16), int(_h[4:6], 16)
    _bg = f'rgba({_r},{_g},{_b},0.15)'
    _border = f'rgba({_r},{_g},{_b},0.30)'

    return html.Span(
        style={
            'display': 'inline-flex',
            'alignItems': 'center',
            'gap': '7px',
            'backgroundColor': _bg,
            'borderRadius': '20px',
            'padding': '5px 14px',
            'marginRight': '8px',
            'fontSize': '12px',
            'fontWeight': '500',
            'color': C['text'],
            'border': f'1px solid {_border}',
            'fontFamily': FONT,
            'backdropFilter': 'blur(8px)',
        },
        children=[
            html.Span(style={
                'width': '7px',
                'height': '7px',
                'borderRadius': '50%',
                'backgroundColor': color,
                'display': 'inline-block',
                'boxShadow': f'0 0 6px rgba({_r},{_g},{_b},0.5)',
            }),
            display,
        ],
    )


def make_chart_tip(tip: str) -> html.Span:
    """Small question-mark icon that shows a tooltip on hover.

    Parameters
    ----------
    tip : str
        Tooltip text explaining the chart logic / meaning.
    """
    return html.Span(
        className='chart-tip',
        **{'data-tip': tip},
        children='?',
        style={
            'display': 'inline-flex',
            'alignItems': 'center',
            'justifyContent': 'center',
            'width': '16px',
            'height': '16px',
            'borderRadius': '50%',
            'backgroundColor': C['border_hi'],
            'color': C['text_2'],
            'fontSize': '10px',
            'fontWeight': '700',
            'fontFamily': FONT,
            'cursor': 'help',
            'lineHeight': '1',
            'marginLeft': '8px',
        },
    )
