"""Reusable UI control components — date pickers, selectors, badges."""

from __future__ import annotations

from dash import dcc, html


def make_date_range_selector(
    min_date: str,
    max_date: str,
    id_prefix: str = 'global',
) -> html.Div:
    """DatePickerRange plus preset quick-select buttons (5Y / 10Y / 20Y / 全部).

    Component IDs produced:
    - ``{id_prefix}-picker``  — the :class:`dcc.DatePickerRange`
    - ``{id_prefix}-btn-5y``, ``-btn-10y``, ``-btn-20y``, ``-btn-all``

    Parameters
    ----------
    min_date, max_date : str
        ISO date strings (``'YYYY-MM-DD'``).
    id_prefix : str
        Prepended to every component ``id`` so multiple selectors on
        different pages don't collide.
    """
    return html.Div(
        style={
            'display': 'flex', 'alignItems': 'center', 'gap': '12px',
            'marginBottom': '16px', 'flexWrap': 'wrap',
        },
        children=[
            dcc.DatePickerRange(
                id=f'{id_prefix}-picker',
                min_date_allowed=min_date,
                max_date_allowed=max_date,
                start_date=min_date,
                end_date=max_date,
                display_format='YYYY-MM-DD',
                style={'backgroundColor': '#2d2d44', 'color': '#cdd6f4'},
                className='dark-date-picker',
            ),
            html.Div(
                style={'display': 'flex', 'gap': '6px'},
                children=[
                    html.Button(label, id=f'{id_prefix}-btn-{key}',
                                n_clicks=0,
                                style={
                                    'backgroundColor': '#45475a',
                                    'color': '#cdd6f4',
                                    'border': 'none',
                                    'borderRadius': '4px',
                                    'padding': '4px 12px',
                                    'cursor': 'pointer',
                                    'fontSize': '13px',
                                })
                    for key, label in [('5y', '5年'), ('10y', '10年'),
                                       ('20y', '20年'), ('all', '全部')]
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
        style={'marginBottom': '16px'},
        children=[
            html.Label('选择城市:', style={'color': '#cdd6f4', 'marginRight': '8px'}),
            dcc.Dropdown(
                id=f'{id_prefix}-city-selector',
                options=[{'label': c, 'value': c} for c in cities],
                value=cities[:4],  # default first 4
                multi=True,
                style={
                    'backgroundColor': '#2d2d44',
                    'color': '#cdd6f4',
                    'minWidth': '300px',
                },
                className='dark-dropdown',
            ),
        ],
    )


def make_phase_badge(
    phase: str,
    color: str,
    label: str | None = None,
) -> html.Span:
    """Compact badge showing a cycle phase name and coloured dot."""
    display = label or phase
    return html.Span(
        style={
            'display': 'inline-flex', 'alignItems': 'center', 'gap': '6px',
            'backgroundColor': '#2d2d44', 'borderRadius': '16px',
            'padding': '4px 14px', 'marginRight': '8px',
            'fontSize': '13px', 'color': '#cdd6f4',
            'border': f'1px solid {color}',
        },
        children=[
            html.Span(style={
                'width': '8px', 'height': '8px', 'borderRadius': '50%',
                'backgroundColor': color, 'display': 'inline-block',
            }),
            display,
        ],
    )
