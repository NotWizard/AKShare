"""Layout primitives — cards, rows, sections, metric tiles."""

from __future__ import annotations
from dash import html
from dashboard.config import C, FONT


def make_card(children, title: str | None = None, style: dict | None = None) -> html.Div:
    """Elevated card with subtle border and refined header."""
    card_style = {
        'backgroundColor': C['card'],
        'borderRadius': '12px',
        'border': f'1px solid {C["border"]}',
        'padding': '20px 24px',
        'flex': '1 1 0',
        'minWidth': '0',
        'position': 'relative',
        'overflow': 'hidden',
    }
    if style:
        card_style.update(style)

    body = []
    if title:
        body.append(html.Div(
            title,
            style={
                'color': C['text_2'],
                'fontSize': '13px',
                'fontWeight': '500',
                'letterSpacing': '0.02em',
                'marginBottom': '12px',
                'paddingBottom': '10px',
                'borderBottom': f'1px solid {C["border"]}',
                'fontFamily': FONT,
            },
        ))
    if isinstance(children, list):
        body.extend(children)
    else:
        body.append(children)

    return html.Div(style=card_style, children=body)


def make_row(*cards, gap: str = '16px') -> html.Div:
    """Responsive flex row, wraps on narrow viewports."""
    return html.Div(
        style={
            'display': 'flex',
            'gap': gap,
            'flexWrap': 'wrap',
            'marginBottom': '16px',
        },
        children=list(cards),
    )


def make_metric_tile(label: str, value: str, delta: str | None = None,
                     color: str | None = None) -> html.Div:
    """Compact metric card for the top KPI strip.

    Parameters
    ----------
    label : str   — e.g. "GDP 同比"
    value : str   — e.g. "5.2%"
    delta : str   — e.g. "+0.3pp", optional
    color : str   — accent color for the value text
    """
    val_color = color or C['text']
    children = [
        html.Div(label, style={
            'fontSize': '12px', 'fontWeight': '500',
            'color': C['text_3'], 'letterSpacing': '0.04em',
            'textTransform': 'uppercase', 'marginBottom': '6px',
        }),
        html.Div(value, style={
            'fontSize': '28px', 'fontWeight': '700',
            'color': val_color, 'lineHeight': '1.1',
            'fontFamily': FONT,
        }),
    ]
    if delta:
        delta_color = C['up'] if delta.startswith('+') or delta.startswith('↑') else \
                      C['down'] if delta.startswith('-') or delta.startswith('↓') else C['text_3']
        children.append(html.Div(delta, style={
            'fontSize': '12px', 'fontWeight': '500',
            'color': delta_color, 'marginTop': '4px',
        }))

    return html.Div(
        style={
            'backgroundColor': C['card'],
            'borderRadius': '10px',
            'border': f'1px solid {C["border"]}',
            'padding': '16px 20px',
            'flex': '1 1 140px',
            'minWidth': '140px',
        },
        children=children,
    )


def make_section(title: str, children) -> html.Div:
    """Section with subtle left-accent header."""
    return html.Div(
        style={'marginBottom': '24px'},
        children=[
            html.Div(
                style={
                    'display': 'flex', 'alignItems': 'center', 'gap': '10px',
                    'marginBottom': '16px',
                },
                children=[
                    html.Div(style={
                        'width': '3px', 'height': '18px',
                        'backgroundColor': C['accent'],
                        'borderRadius': '2px',
                    }),
                    html.H3(title, style={
                        'color': C['text'],
                        'fontSize': '16px',
                        'fontWeight': '600',
                        'margin': '0',
                        'fontFamily': FONT,
                    }),
                ],
            ),
            children if isinstance(children, list) else [children],
        ],
    )
