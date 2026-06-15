"""Layout helpers — cards, rows, sections for the dark-themed dashboard."""

from __future__ import annotations

from dash import html


def make_card(children, title: str | None = None, style: dict | None = None) -> html.Div:
    """Styled card container on the dark background.

    Parameters
    ----------
    children : Dash component or list
        Body content of the card.
    title : str, optional
        Header text rendered above the body.
    style : dict, optional
        Extra CSS overrides merged onto the card wrapper.
    """
    card_style = {
        'backgroundColor': '#2d2d44',
        'borderRadius': '12px',
        'padding': '20px',
        'boxShadow': '0 2px 8px rgba(0,0,0,0.3)',
        'flex': '1 1 0',
        'minWidth': '0',
    }
    if style:
        card_style.update(style)

    body = []
    if title:
        body.append(html.H4(
            title,
            style={
                'color': '#cdd6f4', 'marginTop': '0', 'marginBottom': '12px',
                'fontSize': '16px', 'fontWeight': '600',
            },
        ))
    if isinstance(children, list):
        body.extend(children)
    else:
        body.append(children)

    return html.Div(style=card_style, children=body)


def make_row(*cards, gap: str = '16px') -> html.Div:
    """Responsive row — flex-wrap so 2-column on desktop, stacks on narrow screens."""
    return html.Div(
        style={
            'display': 'flex', 'gap': gap,
            'flexWrap': 'wrap', 'marginBottom': '16px',
        },
        children=list(cards),
    )


def make_section(title: str, children) -> html.Div:
    """Section with a prominent header line."""
    return html.Div(
        style={'marginBottom': '24px'},
        children=[
            html.H3(
                title,
                style={
                    'color': '#cdd6f4',
                    'borderBottom': '2px solid #45475a',
                    'paddingBottom': '8px',
                    'marginBottom': '16px',
                    'fontSize': '20px',
                    'fontWeight': '700',
                },
            ),
            children if isinstance(children, list) else [children],
        ],
    )
