"""Main Dash application — Terminal Fintech dashboard."""

import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import dash
from dash import html, dcc, Input, Output, callback

from dashboard.config import C, FONT

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder=os.path.join(os.path.dirname(__file__), 'pages'),
    suppress_callback_exceptions=True,
    title='宏观经济分析平台',
    update_title=None,
)

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
_NAV_ITEMS = [
    ('/', '综合概览', '◉'),
    ('/merrill-clock', '美林时钟', '◐'),
    ('/credit-cycle', '信用周期', '◈'),
    ('/inventory-cycle', '库存周期', '▣'),
    ('/debt-cycle', '债务周期', '◆'),
    ('/real-estate', '房地产市场', '▧'),
]

_BASE_LINK = {
    'display': 'flex',
    'alignItems': 'center',
    'gap': '10px',
    'padding': '9px 14px',
    'color': C['text_3'],
    'textDecoration': 'none',
    'borderRadius': '8px',
    'marginBottom': '2px',
    'fontSize': '13px',
    'fontWeight': '500',
    'fontFamily': FONT,
    'transition': 'all 0.15s ease',
    'letterSpacing': '0.01em',
}

_ACTIVE_LINK = {
    **_BASE_LINK,
    'backgroundColor': C['accent_glow'],
    'color': C['text'],
    'borderLeft': f'2px solid {C["accent"]}',
    'paddingLeft': '12px',
}


def _sidebar():
    links = []
    for href, label, icon in _NAV_ITEMS:
        nav_id = f'nav-{href.strip("/").replace("/", "-") or "overview"}'
        links.append(
            dcc.Link(
                [
                    html.Span(icon, style={'fontSize': '14px', 'opacity': '0.6', 'width': '16px', 'textAlign': 'center'}),
                    html.Span(label),
                ],
                href=href,
                id=nav_id,
                style=_BASE_LINK,
                className='nav-link',
            )
        )

    return html.Div(
        style={
            'width': '200px',
            'minHeight': '100vh',
            'backgroundColor': C['surface'],
            'padding': '20px 12px',
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'overflowY': 'auto',
            'borderRight': f'1px solid {C["border"]}',
            'zIndex': '100',
        },
        children=[
            dcc.Location(id='url', refresh=False),
            # Brand
            html.Div(
                style={'padding': '0 14px 20px', 'marginBottom': '8px',
                       'borderBottom': f'1px solid {C["border"]}'},
                children=[
                    html.Div('MACRO', style={
                        'fontSize': '18px', 'fontWeight': '800',
                        'color': C['text'], 'letterSpacing': '0.08em',
                        'fontFamily': FONT,
                    }),
                    html.Div('中国经济分析平台', style={
                        'fontSize': '11px', 'color': C['text_3'],
                        'marginTop': '4px', 'letterSpacing': '0.02em',
                    }),
                ],
            ),
            # Nav links
            html.Div(children=links),
            # Footer
            html.Div(
                style={
                    'position': 'absolute', 'bottom': '16px',
                    'left': '12px', 'right': '12px',
                    'padding': '12px 14px',
                    'fontSize': '10px', 'color': C['text_3'],
                    'borderTop': f'1px solid {C["border"]}',
                    'lineHeight': '1.5',
                },
                children=[
                    html.Div('数据来源'),
                    html.Div('AKShare · 国家统计局 · 中国人民银行', style={'marginTop': '2px', 'opacity': '0.7'}),
                ],
            ),
        ],
    )


app.layout = html.Div(
    style={
        'backgroundColor': C['bg'],
        'minHeight': '100vh',
        'fontFamily': FONT,
    },
    children=[
        _sidebar(),
        html.Div(
            style={'marginLeft': '200px', 'minHeight': '100vh',
                   'backgroundColor': C['bg']},
            children=dash.page_container,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Callback: active nav highlight
# ---------------------------------------------------------------------------
@callback(
    *(Output(f'nav-{href.strip("/").replace("/", "-") or "overview"}', 'style')
      for href, _, _ in _NAV_ITEMS),
    Input('url', 'pathname'),
)
def highlight_nav(pathname):
    styles = []
    for href, _, _ in _NAV_ITEMS:
        if pathname == href or (href != '/' and pathname.startswith(href)):
            styles.append(_ACTIVE_LINK)
        else:
            styles.append(_BASE_LINK)
    return styles


# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
app.index_string = f'''
<!DOCTYPE html>
<html>
  <head>
    {{%metas%}}
    <title>{{%title%}}</title>
    {{%favicon%}}
    {{%css%}}
    <style>
      * {{ box-sizing: border-box; }}
      html {{
        background: {C["bg"]};
      }}
      body {{
        margin: 0;
        background: {C["bg"]};
        font-family: {FONT};
        color: {C["text"]};
        -webkit-font-smoothing: antialiased;
      }}
      /* Prevent white flash during Dash init */
      #react-entry-point,
      ._dash-loading {{
        background: {C["bg"]} !important;
        min-height: 100vh;
      }}
      .dash-graph .js-plotly-plot {{
        background: transparent !important;
      }}
      /* Scrollbar */
      ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
      ::-webkit-scrollbar-track {{ background: {C["bg"]}; }}
      ::-webkit-scrollbar-thumb {{ background: {C["border_hi"]}; border-radius: 3px; }}
      ::-webkit-scrollbar-thumb:hover {{ background: {C["text_3"]}; }}

      /* Date picker dark overrides */
      .dark-date-picker .DayPicker {{ background: {C["card"]} !important; border-radius: 8px; }}
      .dark-date-picker .CalendarDay {{
        background: {C["card"]}; color: {C["text_2"]}; border-color: {C["border"]};
      }}
      .dark-date-picker .CalendarDay__selected {{
        background: {C["accent"]} !important; color: #fff;
      }}
      .dark-date-picker .CalendarDay__hovered_span {{
        background: {C["accent_glow"]} !important; color: {C["text"]};
      }}
      .dark-date-picker .DateInput_input {{
        background: {C["card"]} !important; color: {C["text"]} !important;
        border-color: {C["border"]} !important; font-size: 12px;
        border-radius: 4px;
      }}
      .dark-date-picker .DateRangePickerInput {{
        background: {C["card"]}; border-color: {C["border"]};
        border-radius: 6px;
      }}
      .dark-date-picker .DateRangePickerInput_arrow {{ color: {C["text_3"]}; }}
      .dark-date-picker .DayPickerKeyboardShortcutPanel {{ background: {C["surface"]}; }}

      /* Dropdown dark overrides (React Select v1 + v5) */
      .dark-dropdown .Select-control,
      .dark-dropdown .select__control {{
        background: {C["card"]} !important;
        border-color: {C["border"]} !important;
        border-radius: 6px !important;
      }}
      .dark-dropdown .Select-control:hover,
      .dark-dropdown .select__control:hover,
      .dark-dropdown .select__control--is-focused {{
        border-color: {C["accent"]} !important;
        box-shadow: 0 0 0 1px {C["accent"]}40 !important;
      }}
      .dark-dropdown .Select-menu-outer,
      .dark-dropdown .select__menu {{
        background: {C["card"]} !important;
        border-color: {C["border"]} !important;
        border-radius: 8px !important;
      }}
      .dark-dropdown .Select-option,
      .dark-dropdown .select__option {{
        background: {C["card"]} !important; color: {C["text_2"]} !important;
      }}
      .dark-dropdown .Select-option:hover,
      .dark-dropdown .select__option:hover,
      .dark-dropdown .select__option--is-focused {{
        background: {C["card_hover"]} !important;
      }}
      .dark-dropdown .select__option--is-selected {{
        background: {C["accent_glow"]} !important; color: {C["text"]} !important;
      }}
      .dark-dropdown .Select-value-label,
      .dark-dropdown .select__single-value {{
        color: {C["text"]} !important; font-size: 12px;
      }}
      .dark-dropdown .Select-multi-value,
      .dark-dropdown .select__multi-value {{
        background: {C["accent_glow"]} !important;
        border: 1px solid {C["accent"]}40;
        border-radius: 4px;
      }}
      .dark-dropdown .Select-multi-value__label,
      .dark-dropdown .select__multi-value__label {{
        color: {C["text"]} !important; font-size: 11px;
      }}
      .dark-dropdown .Select-multi-value__remove:hover,
      .dark-dropdown .select__multi-value__remove:hover {{
        background: {C["down_bg"]} !important;
        color: {C["text"]} !important;
      }}
      .dark-dropdown .Select-placeholder,
      .dark-dropdown .select__placeholder {{
        color: {C["text_3"]} !important;
      }}
      .dark-dropdown .select__input {{ color: {C["text"]} !important; }}

      /* Nav link hover */
      .nav-link:hover {{
        background-color: {C["border_hi"]} !important;
        color: {C["text_2"]} !important;
      }}

      /* Button hover */
      button:hover {{
        border-color: {C["accent"]} !important;
        color: {C["text"]} !important;
      }}

      /* Plotly modebar */
      .modebar {{ opacity: 0.3; }}
      .modebar:hover {{ opacity: 0.8; }}

      /* Range slider */
      .rangeslider-container {{
        background: {C["range_slider"]} !important;
      }}

      /* Chart tip tooltip */
      .chart-tip {{
        position: relative;
      }}
      .chart-tip::after {{
        content: attr(data-tip);
        position: absolute;
        left: 50%;
        bottom: calc(100% + 8px);
        transform: translateX(-50%);
        width: max-content;
        max-width: 320px;
        background: #ffffff;
        color: {C["text"]};
        border: 1px solid {C["border_hi"]};
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 12px;
        font-weight: 400;
        line-height: 1.5;
        font-family: {FONT};
        box-shadow: 0 8px 24px rgba(15,23,42,0.08);
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
        transition: opacity 0.15s ease, visibility 0.15s ease;
        z-index: 1000;
        white-space: normal;
      }}
      .chart-tip:hover::after {{
        opacity: 1;
        visibility: visible;
      }}
    </style>
  </head>
  <body>
    {{%app_entry%}}
    <footer>
      {{%config%}}
      {{%scripts%}}
      {{%renderer%}}
    </footer>
  </body>
</html>
'''

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    _debug = os.environ.get('DASH_DEBUG', '0').lower() in ('1', 'true', 'yes')
    app.run(
        debug=_debug,
        port=int(os.environ.get('DASH_PORT', '8050')),
        dev_tools_ui=_debug,
    )
