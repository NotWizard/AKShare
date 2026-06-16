"""Dashboard design system — Terminal Fintech theme.

Color palette, chart defaults, phase mappings, and shared constants.
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
# Color tokens (Terminal Fintech — deep navy-black + emerald/rose accents)
# ---------------------------------------------------------------------------
C = {
    # Backgrounds
    'bg':           '#0a0e17',   # near-black navy
    'surface':      '#111827',   # elevated surface (sidebar, footer)
    'card':         '#1a2332',   # card surface
    'card_hover':   '#1f2937',   # card hover state

    # Borders
    'border':       'rgba(255,255,255,0.06)',
    'border_hi':    'rgba(255,255,255,0.10)',
    'border_accent':'rgba(255,255,255,0.15)',

    # Text hierarchy
    'text':         '#f1f5f9',   # primary
    'text_2':       '#94a3b8',   # secondary / muted
    'text_3':       '#64748b',   # tertiary / disabled

    # Accents (used sparingly, one per context)
    'accent':       '#6366f1',   # indigo-500 (primary actions, active state)
    'accent_glow':  'rgba(99,102,241,0.15)',

    # Semantic
    'up':           '#10b981',   # emerald-500 (positive, growth, easing)
    'up_bg':        'rgba(16,185,129,0.10)',
    'down':         '#ef4444',   # red-500 (negative, decline, tightening)
    'down_bg':      'rgba(239,68,68,0.10)',
    'warn':         '#f59e0b',   # amber-500 (neutral, caution)
    'warn_bg':      'rgba(245,158,11,0.10)',
    'info':         '#3b82f6',   # blue-500 (informational)
    'info_bg':      'rgba(59,130,246,0.10)',

    # Chart-specific
    'grid':         'rgba(148,163,184,0.05)',   # very subtle grid
    'grid_hi':      'rgba(148,163,184,0.08)',   # zeroline / emphasis (kept faint)
    'chart_bg':     'rgba(0,0,0,0)',            # transparent chart bg
    'range_slider': '#1e293b',                  # range slider fill
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
    colorway=[C['accent'], C['up'], C['down'], C['warn'], '#a78bfa', '#06b6d4', '#f97316', '#ec4899'],
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
        spikecolor='rgba(148,163,184,0.35)',
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
        spikecolor='rgba(148,163,184,0.35)',
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
        bgcolor='#1e293b',
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
