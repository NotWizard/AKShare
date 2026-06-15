"""Main Dash application — multi-page dashboard with dark theme.

Run:  python -m dashboard.app          (from project root)
  or: python dashboard/app.py
"""

import os
import sys

# Ensure project root is on sys.path so ``dashboard.*`` imports work
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import dash
from dash import html, dcc, Input, Output, callback

from dashboard.config import COLORS

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder=os.path.join(os.path.dirname(__file__), 'pages'),
    suppress_callback_exceptions=True,
    title='中国宏观经济分析平台',
    update_title='加载中...',
)

# ---------------------------------------------------------------------------
# Sidebar + page container layout
# ---------------------------------------------------------------------------
_NAV_ITEMS = [
    ('/', '📊 综合概览'),
    ('/merrill-clock', '🕐 美林时钟'),
    ('/credit-cycle', '💳 信用周期'),
    ('/inventory-cycle', '📦 库存周期'),
    ('/debt-cycle', '🏦 债务周期'),
    ('/real-estate', '🏠 房地产市场'),
]

_BASE_LINK_STYLE = {
    'display': 'block',
    'padding': '10px 16px',
    'color': COLORS['text'],
    'textDecoration': 'none',
    'borderRadius': '8px',
    'marginBottom': '4px',
    'fontSize': '14px',
}

_ACTIVE_LINK_STYLE = {
    **_BASE_LINK_STYLE,
    'backgroundColor': COLORS['primary'],
    'color': '#ffffff',
}


def _sidebar():
    links = []
    for href, label in _NAV_ITEMS:
        links.append(
            dcc.Link(
                label,
                href=href,
                id=f'nav-{href.strip("/").replace("/", "-") or "overview"}',
                style=_BASE_LINK_STYLE,
                className='nav-link',
            )
        )

    return html.Div(
        style={
            'width': '220px',
            'minHeight': '100vh',
            'backgroundColor': COLORS['bg_card'],
            'padding': '20px 12px',
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'overflowY': 'auto',
            'boxShadow': '2px 0 8px rgba(0,0,0,0.3)',
            'zIndex': '100',
        },
        children=[
            dcc.Location(id='url', refresh=False),
            html.H2(
                '宏观经济分析',
                style={
                    'color': COLORS['text'],
                    'fontSize': '18px',
                    'fontWeight': '700',
                    'padding': '0 16px 16px',
                    'marginBottom': '12px',
                    'borderBottom': f'2px solid {COLORS["grid"]}',
                },
            ),
        ] + links + [
            html.Div(
                style={
                    'position': 'absolute', 'bottom': '20px',
                    'left': '12px', 'right': '12px',
                    'padding': '12px 16px',
                    'fontSize': '12px', 'color': COLORS['text_muted'],
                    'borderTop': f'1px solid {COLORS["grid"]}',
                },
                children='数据来源: AKShare / 国家统计局 / 中国人民银行',
            ),
        ],
    )


app.layout = html.Div(
    style={
        'backgroundColor': COLORS['bg_dark'],
        'minHeight': '100vh',
        'fontFamily': (
            '-apple-system, BlinkMacSystemFont, "Segoe UI", '
            '"Noto Sans SC", "Microsoft YaHei", sans-serif'
        ),
    },
    children=[
        _sidebar(),
        html.Div(
            style={
                'marginLeft': '220px',
                'minHeight': '100vh',
            },
            children=dash.page_container,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Callback: highlight the active nav link
# ---------------------------------------------------------------------------
@callback(
    *(Output(f'nav-{href.strip("/").replace("/", "-") or "overview"}', 'style')
      for href, _ in _NAV_ITEMS),
    Input('url', 'pathname'),
)
def highlight_nav(pathname):
    styles = []
    for href, _ in _NAV_ITEMS:
        if pathname == href or (href != '/' and pathname.startswith(href)):
            styles.append(_ACTIVE_LINK_STYLE)
        else:
            styles.append(_BASE_LINK_STYLE)
    return styles


# ---------------------------------------------------------------------------
# Global CSS overrides for dark-themed controls
# ---------------------------------------------------------------------------
app.index_string = '''
<!DOCTYPE html>
<html>
  <head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
      body { margin: 0; background: #1e1e2e; }
      /* Date picker dark overrides */
      .dark-date-picker .DayPicker { background: #2d2d44 !important; }
      .dark-date-picker .CalendarDay { background: #2d2d44; color: #cdd6f4; border-color: #45475a; }
      .dark-date-picker .CalendarDay__selected { background: #1a73e8 !important; color: #fff; }
      .dark-date-picker .DateInput_input {
        background: #2d2d44 !important; color: #cdd6f4 !important;
        border-color: #45475a !important;
      }
      .dark-date-picker .DateRangePickerInput { background: #2d2d44; border-color: #45475a; }
      .dark-date-picker .DateRangePickerInput_arrow { color: #a6adc8; }
      /* Dropdown dark overrides */
      .dark-dropdown .Select-control { background: #2d2d44 !important; }
      .dark-dropdown .Select-menu-outer { background: #2d2d44 !important; }
      .dark-dropdown .Select-option { background: #2d2d44 !important; color: #cdd6f4 !important; }
      .dark-dropdown .Select-value-label { color: #cdd6f4 !important; }
      .dark-dropdown .Select-multi-value { background: #45475a !important; }
      /* Nav link hover */
      .nav-link:hover { background-color: #45475a !important; }
      /* Scrollbar */
      ::-webkit-scrollbar { width: 6px; }
      ::-webkit-scrollbar-track { background: #1e1e2e; }
      ::-webkit-scrollbar-thumb { background: #45475a; border-radius: 3px; }
    </style>
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
  </body>
</html>
'''

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=8050)
