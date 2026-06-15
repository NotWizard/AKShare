"""Dashboard configuration — theme colors, chart defaults, and paths."""

import os

# ---------------------------------------------------------------------------
# Color palette (Catppuccin-Mocha inspired)
# ---------------------------------------------------------------------------
COLORS = {
    'primary': '#1a73e8',
    'secondary': '#5f6368',
    'success': '#2ecc71',
    'danger': '#e74c3c',
    'warning': '#f39c12',
    'info': '#3498db',
    'bg_dark': '#1e1e2e',
    'bg_card': '#2d2d44',
    'text': '#cdd6f4',
    'text_muted': '#a6adc8',
    'grid': '#45475a',
}

# ---------------------------------------------------------------------------
# Chart layout defaults applied to every Plotly figure
# ---------------------------------------------------------------------------
CHART_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(30,30,46,0.8)',
    font=dict(color='#cdd6f4', size=12),
    margin=dict(l=60, r=30, t=40, b=40),
    xaxis=dict(gridcolor='#45475a', zerolinecolor='#45475a'),
    yaxis=dict(gridcolor='#45475a', zerolinecolor='#45475a'),
)

# ---------------------------------------------------------------------------
# Phase → color mapping used across cycle pages
# ---------------------------------------------------------------------------
PHASE_COLORS = {
    # Merrill clock
    'recovery': '#2ecc71',
    'overheating': '#e74c3c',
    'stagflation': '#f39c12',
    'recession': '#3498db',
    # Credit cycle
    'easing': '#2ecc71',
    'tightening': '#e74c3c',
    # Inventory cycle
    'active_restocking': '#2ecc71',
    'passive_restocking': '#f39c12',
    'active_destocking': '#e74c3c',
    'passive_destocking': '#3498db',
}

# Chinese labels for phases
PHASE_LABELS = {
    'recovery': '复苏',
    'overheating': '过热',
    'stagflation': '滞胀',
    'recession': '衰退',
    'easing': '宽松',
    'tightening': '紧缩',
    'active_restocking': '主动补库',
    'passive_restocking': '被动补库',
    'active_destocking': '主动去库',
    'passive_destocking': '被动去库',
}

# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'macro_data.db')
