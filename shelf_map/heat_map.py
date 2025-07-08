import math
import base64
from decimal import Decimal
from typing import Any

import streamlit as st
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

from shelf_map.shelf_map_handler import ShelfMapHandler

handler = ShelfMapHandler()

# ─────────── helpers ──────────────────────────────────────────────────────
def _png_ratio(path: str = "assets/shelf_map.png") -> float:
    """Return height/width ratio of the PNG; cheap header read – no Pillow."""
    with open(path, "rb") as f:
        f.seek(16)
        w = int.from_bytes(f.read(4), "big")
        h = int.from_bytes(f.read(4), "big")
    return h / w


PNG_RATIO = _png_ratio()


@st.cache_resource
def bg_png() -> str:
    """Return the floor-plan as a base-64 data-URI (cached per session)."""
    if "bg_png" not in st.session_state:
        with open("assets/shelf_map.png", "rb") as f:
            st.session_state["bg_png"] = (
                "data:image/png;base64," + base64.b64encode(f.read()).decode()
            )
    return st.session_state["bg_png"]


def _to_float(v: Any, default: float = 0.0) -> float:
    """Convert Decimal / int / str / None → float (with fallback)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clamp(v: Any) -> float:
    """Clamp *v* to [0, 0.999] as plain float (avoids Decimal–float issues)."""
    val = _to_float(v)
    return max(0.0, min(val, 0.999))


# ─────────── main tab function ────────────────────────────────────────────
def heat_map_tab() -> None:
    st.subheader("🔥 Shelf Heat-map")

    # choose metric without leaving blank space for label
    mode = st.radio(
        label="Colour mode",
        options=("Total quantity", "Near-expiry", "Below threshold"),
        horizontal=True,
        label_visibility="collapsed",
    )

    near_days = (
        st.slider("Expire within (days)", 1, 90, 30) if mode == "Near-expiry" else 0
    )

    # ----- fetch data -----------------------------------------------------
    if mode == "Total quantity":
        locs = handler.get_heatmap_data()
        value_key = "quantity"

    elif mode == "Near-expiry":
        locs = handler.get_heatmap_data(near_days=near_days)
        value_key = "quantity"

    else:  # Below threshold
        locs = handler.get_heatmap_threshold()
        for r in locs:
            q = _to_float(r["quantity"])
            t = _to_float(r.get("threshold") or 1)
            r["ratio"] = q / t if t else 0
        value_key = "ratio"

    # ----- colour mapping -------------------------------------------------
    if mode == "Below threshold":
        intensities = [_clamp(1 - min(_to_float(r["ratio"]), 1)) for r in locs]
        colorscale = ["#27ae60", "#e74c3c"]  # green → red
    else:
        max_val = max((_to_float(r[value_key]) for r in locs), default=0.0)
        intensities = [
            _clamp((_to_float(r[value_key]) / max_val) if max_val else 0.0)
            for r in locs
        ]
        colorscale = "YlOrRd"  # yellow → red

    # ----- build shapes ---------------------------------------------------
    shapes = []
    for row, inten in zip(locs, intensities):
        x, y, w, h = map(_to_float, (row["x_pct"], row["y_pct"], row["w_pct"], row["h_pct"]))
        deg = _to_float(row.get("rotation_deg") or 0)
        colour = sample_colorscale(colorscale, [inten])[0]

        cx, cy = x + w / 2, 1 - (y + h / 2)
        y_draw = 1 - y - h

        if deg == 0:
            shapes.append(
                dict(
                    type="rect",
                    x0=x,
                    y0=y_draw,
                    x1=x + w,
                    y1=y_draw + h,
                    line=dict(width=1, color="rgba(255,255,255,0.5)"),
                    fillcolor=colour,
                )
            )
        else:
            rad = math.radians(deg)
            c, s = math.cos(rad), math.sin(rad)
            pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
            path = "M " + " L ".join(f"{cx + u * c - v * s},{cy + u * s + v * c}" for u, v in pts) + " Z"
            shapes.append(
                dict(
                    type="path",
                    path=path,
                    line=dict(width=1, color="rgba(255,255,255,0.5)"),
                    fillcolor=colour,
                )
            )

    # ----- figure ---------------------------------------------------------
    fig = go.Figure()
    fig.add_layout_image(
        dict(
            source=bg_png(),
            xref="x",
            yref="y",
            x=0,
            y=1,
            sizex=1,
            sizey=1,
            xanchor="left",
            yanchor="top",
            layer="below",
        )
    )
    fig.update_layout(shapes=shapes, height=700, margin=dict(l=0, r=0, t=0, b=0))
    fig.update_xaxes(visible=False, range=[0, 1], constrain="domain")
    fig.update_yaxes(visible=False, range=[0, 1], scaleanchor="x", scaleratio=PNG_RATIO)

    st.plotly_chart(fig, use_container_width=True, key="heatmap")

    # ----- caption --------------------------------------------------------
    if mode == "Total quantity":
        st.caption("🟡 pale = few units  🔴 red = many units in stock")
    elif mode == "Near-expiry":
        st.caption("🟡 pale = few soon-to-expire units  🔴 red = many expiring soon")
    else:
        st.caption("✅ green = at / above threshold  🔴 red = needs restock")
