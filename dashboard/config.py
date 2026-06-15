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
    'neutral': '#a6adc8',
    # Inventory cycle
    'active_restocking': '#2ecc71',
    'passive_restocking': '#f39c12',
    'active_destocking': '#e74c3c',
    'passive_destocking': '#3498db',
    # Debt cycle
    'leveraging': '#2ecc71',
    'deleveraging': '#e74c3c',
    'stable': '#f39c12',
    'beautiful_deleveraging': '#2ecc71',
    'ugly_deleveraging': '#e74c3c',
    'leveraging_boom': '#f39c12',
    'leveraging_bust': '#e74c3c',
    'stable_growth': '#3498db',
    'stable_contraction': '#a6adc8',
}

# Chinese labels for phases
PHASE_LABELS = {
    'recovery': '复苏',
    'overheating': '过热',
    'stagflation': '滞胀',
    'recession': '衰退',
    'easing': '宽松',
    'tightening': '紧缩',
    'neutral': '中性',
    'active_restocking': '主动补库',
    'passive_restocking': '被动补库',
    'active_destocking': '主动去库',
    'passive_destocking': '被动去库',
    # Debt cycle
    'leveraging': '加杠杆',
    'deleveraging': '去杠杆',
    'stable': '稳定',
    'beautiful_deleveraging': '美丽去杠杆',
    'ugly_deleveraging': '丑陋去杠杆',
    'leveraging_boom': '加杠杆繁荣',
    'leveraging_bust': '加杠杆崩溃',
    'stable_growth': '稳定增长',
    'stable_contraction': '稳定收缩',
}

# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'macro_data.db')
