"""Dashboard design system — Light Analytics SaaS theme.

Color palette, chart defaults, phase mappings, and shared constants.
Off-white canvas + white surfaces + near-black ink, a single trust-blue accent,
restrained white cards (hairline borders, no heavy shadows), airy whitespace.
All phases reference semantic tokens (up/down/warn/info), so token changes
propagate to PHASE_COLORS automatically.
"""

import os

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
FONT = (
    '-apple-system, BlinkMacSystemFont, "Inter", "SF Pro Display", '
    '"Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
)
MONO = '"SF Mono", "JetBrains Mono", "Fira Code", "Cascadia Code", monospace'

# ---------------------------------------------------------------------------
# Color tokens (Light Analytics SaaS — off-white canvas, single trust-blue accent)
# No pure #ffffff surfaces for large fills, no pure #000 ink — depth via off-values.
# ---------------------------------------------------------------------------
C = {
    # Backgrounds
    'bg':           '#f8fafc',   # page canvas (off-white, slate-50)
    'surface':      '#f1f5f9',   # elevated surface (sidebar, toolbar)
    'card':         '#ffffff',   # card surface
    'card_hover':   '#f8fafc',   # card hover state

    # Borders (slate-ink derived, very faint)
    'border':       'rgba(15,23,42,0.08)',
    'border_hi':    'rgba(15,23,42,0.12)',
    'border_accent':'rgba(37,99,235,0.25)',

    # Text hierarchy (near-black ink, not pure #000)
    'text':         '#0f172a',   # primary (slate-900)
    'text_2':       '#475569',   # secondary (slate-600)
    'text_3':       '#94a3b8',   # tertiary / disabled (slate-400)

    # Accent (single — trust blue)
    'accent':       '#2563eb',   # blue-600 (primary actions, active state)
    'accent_hover': '#1d4ed8',   # blue-700 (interaction)
    'accent_glow':  'rgba(37,99,235,0.08)',

    # Semantic (light-friendly, deeper saturation for contrast on white)
    'up':           '#16a34a',   # green-600 (positive, growth, easing)
    'up_bg':        'rgba(22,163,74,0.10)',
    'down':         '#dc2626',   # red-600 (negative, decline, tightening)
    'down_bg':      'rgba(220,38,38,0.10)',
    'warn':         '#d97706',   # amber-600 (neutral, caution)
    'warn_bg':      'rgba(217,119,6,0.10)',
    'info':         '#2563eb',   # blue-600 (informational, merged with accent)
    'info_bg':      'rgba(37,99,235,0.10)',

    # Chart-specific
    'grid':         'rgba(15,23,42,0.06)',   # very subtle slate gridline
    'grid_hi':      'rgba(15,23,42,0.10)',   # zeroline / emphasis
    'chart_bg':     '#ffffff',               # white chart plot (not transparent)
    'range_slider': '#e2e8f0',               # range slider fill (slate-200)
}

# ---------------------------------------------------------------------------
# Chart layout defaults (Plotly)
# CHART_LAYOUT: base keys safe to spread (no page conflicts)
# CHART_DEFAULTS: axis/legend/hover defaults, applied via _apply_layout
# ---------------------------------------------------------------------------
CHART_LAYOUT = dict(
    paper_bgcolor=C['chart_bg'],
    plot_bgcolor=C['chart_bg'],
    font=dict(
        family=FONT,
        color=C['text_2'],
        size=12,
    ),
    margin=dict(l=52, r=20, t=32, b=36),
    # light-friendly, -600 depth so multi-series lines stay legible on white
    colorway=[C['accent'], C['up'], C['down'], C['warn'], '#7c3aed', '#0891b2', '#db2777', '#0d9488'],
)

CHART_DEFAULTS = dict(
    xaxis=dict(
        gridcolor=C['grid'],
        zerolinecolor=C['grid_hi'],
        tickfont=dict(size=11, color=C['text_3']),
        linecolor=C['border'],
        showspikes=True,
        spikemode='across',
        spikesnap='cursor',
        spikethickness=0.8,
        spikedash='dot',
        spikecolor='rgba(100,116,139,0.45)',
        zerolinewidth=1,
    ),
    yaxis=dict(
        gridcolor=C['grid'],
        zerolinecolor=C['grid_hi'],
        tickfont=dict(size=11, color=C['text_3']),
        linecolor=C['border'],
        showspikes=True,
        spikemode='across',
        spikesnap='cursor',
        spikethickness=0.8,
        spikedash='dot',
        spikecolor='rgba(100,116,139,0.45)',
        zerolinewidth=1,
    ),
    legend=dict(
        font=dict(size=11, color=C['text_2']),
        bgcolor='rgba(0,0,0,0)',
        bordercolor='rgba(0,0,0,0)',
        orientation='h',
        yanchor='bottom',
        y=1.02,
        xanchor='right',
        x=1,
    ),
    hoverlabel=dict(
        bgcolor='#ffffff',
        bordercolor=C['border_hi'],
        font=dict(family=FONT, size=12, color=C['text']),
        namelength=-1,
    ),
    hovermode='x unified',
    spikedistance=-1,
    hoverdistance=100,
)

# ---------------------------------------------------------------------------
# Phase colors (semantic, consistent across all cycle pages)
# ---------------------------------------------------------------------------
PHASE_COLORS = {
    # Merrill clock
    'recovery':             C['up'],
    'overheating':          C['warn'],
    'stagflation':          C['down'],
    'recession':            C['info'],
    # Credit cycle
    'easing':               C['up'],
    'tightening':           C['down'],
    'neutral':              C['text_3'],
    # Inventory cycle
    'active_restocking':    C['up'],
    'passive_restocking':   C['warn'],
    'active_destocking':    C['down'],
    'passive_destocking':   C['info'],
    # Debt cycle
    'leveraging':           C['up'],
    'deleveraging':         C['down'],
    'stable':               C['warn'],
    'beautiful_deleveraging': C['up'],
    'ugly_deleveraging':    C['down'],
    'leveraging_boom':      C['warn'],
    'leveraging_bust':      C['down'],
    'stable_growth':        C['info'],
    'stable_contraction':   C['text_3'],
}

PHASE_LABELS = {
    'recovery': '复苏', 'overheating': '过热', 'stagflation': '滞胀', 'recession': '衰退',
    'easing': '宽松', 'tightening': '紧缩', 'neutral': '中性',
    'active_restocking': '主动补库', 'passive_restocking': '被动补库',
    'active_destocking': '主动去库', 'passive_destocking': '被动去库',
    'leveraging': '加杠杆', 'deleveraging': '去杠杆', 'stable': '稳定',
    'beautiful_deleveraging': '美丽去杠杆', 'ugly_deleveraging': '丑陋去杠杆',
    'leveraging_boom': '加杠杆繁荣', 'leveraging_bust': '加杠杆崩溃',
    'stable_growth': '稳定增长', 'stable_contraction': '稳定收缩',
}

# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'macro_data.db')
