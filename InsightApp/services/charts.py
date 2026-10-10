"""
Génération de graphiques Plotly.

Chaque `build_*` retourne une go.Figure.
Deux renderers :
    - fig_to_html(fig)      → HTML interactif
    - fig_to_data_uri(fig)  → PNG base64 pour le PDF
"""
from __future__ import annotations

import base64

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


# ==========================================================
# PALETTE
# ==========================================================

BRAND   = "#2563eb"
ACCENT  = "#dc2626"
EMERALD = "#10b981"
AMBER   = "#f59e0b"
VIOLET  = "#8b5cf6"

PALETTE = [
    BRAND, ACCENT, EMERALD, AMBER, VIOLET,
    "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#14b8a6",
]

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True, "displaylogo": False}


# ==========================================================
# LAYOUT
# ==========================================================

def _apply_layout(fig, title, *, dark=False, height=420):
    if dark:
        text, grid, tcol = "#e5e7eb", "rgba(255,255,255,.08)", "#f9fafb"
        hbg, hbd, tmpl = "#1f2937", "#374151", "plotly_dark"
    else:
        text, grid, tcol = "#374151", "rgba(0,0,0,.06)", "#111827"
        hbg, hbd, tmpl = "#ffffff", "#e5e7eb", "plotly_white"

    fig.update_layout(
        template=tmpl,
        height=height,
        margin=dict(l=16, r=16, t=56, b=32),
        font=dict(family="Inter, system-ui, sans-serif", size=12, color=text),
        title=dict(text=title,
                   font=dict(size=15, color=tcol, family="Inter, sans-serif"),
                   x=0.01, xanchor="left", pad=dict(l=4, b=8)),
        hoverlabel=dict(bgcolor=hbg, bordercolor=hbd,
                        font=dict(size=12, family="Inter, sans-serif", color=text)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        colorway=PALETTE,
        showlegend=False,
        dragmode=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False,
                     linecolor=grid, tickfont=dict(size=11))
    fig.update_yaxes(showgrid=True, gridcolor=grid, zeroline=False,
                     linecolor="rgba(0,0,0,0)", tickfont=dict(size=11))
    return fig


def _group_others(df, value_col, label_col, top_n):
    if top_n is None or len(df) <= top_n:
        return df
    head = df.head(top_n).copy()
    others = pd.DataFrame({
        label_col: ["Autres"],
        value_col: [df.iloc[top_n:][value_col].sum()],
    })
    return pd.concat([head, others], ignore_index=True)


def _apply_currency(fig, *, currency_symbol, orientation="v"):
    """Applique le format monétaire avec multiples (k, M, G) aux ticks."""
    if not currency_symbol:
        return
    kw = dict(
        tickformat="~s",              # 1.2k, 3.5M, 250
        ticksuffix=f" {currency_symbol}",
        tickfont=dict(size=11),
    )
    if orientation == "h":
        fig.update_xaxes(**kw)
    else:
        fig.update_yaxes(**kw)


# ==========================================================
# BUILDERS
# ==========================================================

def build_bar(
    df, x, y, title, *,
    currency_symbol: str = "",
    color: str | None = None,
    top_n: int | None = None,
    dark: bool = False,
) -> go.Figure:
    df = df.copy().sort_values(y, ascending=False).reset_index(drop=True)
    df = _group_others(df, value_col=y, label_col=x, top_n=top_n)

    avg_len = df[x].astype(str).str.len().mean()
    horizontal = len(df) > 8 or avg_len > 12

    cur = currency_symbol or ""
    bar_marker = dict(color=color or ACCENT, line=dict(width=0))

    if horizontal:
        df = df.sort_values(y, ascending=True)
        height = max(380, 36 * len(df) + 100)
        fig = go.Figure(go.Bar(
            x=df[y], y=df[x].astype(str), orientation="h",
            marker=bar_marker,
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} " + cur + "<extra></extra>",
        ))
        fig.update_yaxes(autorange="reversed", type="category", showgrid=False)
        _apply_currency(fig, currency_symbol=cur, orientation="h")
    else:
        height = 420
        fig = go.Figure(go.Bar(
            x=df[x].astype(str), y=df[y],
            marker=bar_marker,
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} " + cur + "<extra></extra>",
        ))
        _apply_currency(fig, currency_symbol=cur, orientation="v")

    return _apply_layout(fig, title, dark=dark, height=height)


def build_line(
    df, x, y, title, *,
    currency_symbol: str = "",
    area: bool = True,
    dark: bool = False,
) -> go.Figure:
    cur = currency_symbol or ""
    fig = go.Figure(go.Scatter(
        x=df[x].astype(str), y=df[y],
        mode="lines+markers",
        line=dict(color=ACCENT, width=3, shape="spline", smoothing=0.6),
        marker=dict(size=9, color="#ffffff", line=dict(color=ACCENT, width=2.5)),
        fill="tozeroy" if area else "none",
        fillcolor="rgba(220,38,38,.10)" if area else None,
        hovertemplate="<b>%{x}</b><br>%{y:,.0f} " + cur + "<extra></extra>",
    ))
    _apply_currency(fig, currency_symbol=cur, orientation="v")
    return _apply_layout(fig, title, dark=dark, height=420)


def build_donut(
    df, names, values, title, *,
    currency_symbol: str = "",
    top_n: int = 6,
    dark: bool = False,
) -> go.Figure:
    df = df.copy().sort_values(values, ascending=False).reset_index(drop=True)
    df = _group_others(df, value_col=values, label_col=names, top_n=top_n)

    cur = currency_symbol or ""
    fig = go.Figure(go.Pie(
        labels=df[names].astype(str),
        values=df[values],
        hole=0.55,
        marker=dict(colors=PALETTE[: len(df)], line=dict(color="#ffffff", width=2)),
        textinfo="percent",
        textfont=dict(size=12, family="Inter, sans-serif"),
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} " + cur + " (%{percent})<extra></extra>",
        sort=False, direction="clockwise",
    ))
    _apply_layout(fig, title, dark=dark, height=440)
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15,
                    xanchor="center", x=0.5, font=dict(size=11)),
    )
    return fig


# ==========================================================
# RENDERERS
# ==========================================================

def fig_to_html(fig) -> str:
    return pio.to_html(fig, full_html=False,
                       include_plotlyjs="cdn", config=PLOTLY_CONFIG)


def fig_to_data_uri(fig, *, scale: float = 1.8, width: int = 900) -> str:
    png_bytes = fig.to_image(format="png", scale=scale, width=width)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ==========================================================
# WRAPPERS HTML (compatibilité views)
# ==========================================================

def bar_chart(df, x, y, title, **kw) -> str:
    return fig_to_html(build_bar(df, x, y, title, **kw))


def line_chart(df, x, y, title, **kw) -> str:
    return fig_to_html(build_line(df, x, y, title, **kw))


def donut_chart(df, names, values, title, **kw) -> str:
    return fig_to_html(build_donut(df, names, values, title, **kw))