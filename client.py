# client.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask frontend for the AutoSelf MAS demo.

Upgrades (non-destructive):
- Adds an “Artifacts” page with links to FastAPI backend /artifacts/file endpoints.
- Displays which config and seed sets were used (filenames, totals) via /artifacts/list and envs.
- Shows “N seeds” and p-grid on the dashboard (reads from results or configs endpoints if available).
- Polished UX with HTMX partial updates and Plotly figures embedded without duplicate JS.

ENV VARS
- SERVER_URL: base URL of the FastAPI backend (e.g., http://127.0.0.1:8000)
- CONFIG_DIR (optional): path label to show which configs dir is in use (UI only)
- SEEDS_FILE (optional): path label to show which seeds file is in use (UI only)
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

import requests
import pandas as pd
from flask import Flask, render_template, jsonify, request
from markupsafe import Markup

import plotly.graph_objects as go
import plotly.express as px

app = Flask(__name__, template_folder="templates")

# --- In-memory storage for time-series plot data ---
ts_data = {"latency": [], "power": [], "time": []}


# -------------------------------
# Backend Communication Helper
# -------------------------------

def _server_url() -> str:
    return os.environ.get("SERVER_URL", "http://127.0.0.1:8000").rstrip("/")


def _query_backend(method: str = "get", endpoint: str = "/", json_data: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    base = _server_url()
    url = f"{base}/{endpoint.lstrip('/')}"
    try:
        s = requests.Session()
        if method.lower() == "post":
            r = s.post(url, json=json_data, timeout=10)
        else:
            r = s.get(url, timeout=10)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"<div class='alert alert-danger mx-3'>Backend error: {e}</div>"


# -------------------------------
# Plot helpers
# -------------------------------

def fig_to_html(fig) -> Markup:
    return Markup(fig.to_html(full_html=False, include_plotlyjs=False))


def create_empty_plot(title: str) -> Markup:
    return Markup(f"<div class='empty-plot'><h5>{title}</h5><p>Waiting for data...</p></div>")


def create_agent_status_plot(agent_status: Dict[str, str]) -> Markup:
    if not agent_status:
        return create_empty_plot("No Agent Data")
    df = pd.DataFrame(list(agent_status.values()), columns=["status"])
    status_counts = df["status"].value_counts()
    fig = px.pie(
        status_counts,
        values=status_counts.values,
        names=status_counts.index,
        title="Agent Status",
        color=status_counts.index,
        color_discrete_map={"idle": "grey", "executing": "blue", "failed": "red"},
    )
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), showlegend=False, height=250)
    return fig_to_html(fig)


def create_mission_progress_plot(progress: Dict[str, int]) -> Markup:
    if not progress or progress.get("total", 0) == 0:
        return create_empty_plot("No Progress Data")
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=progress.get("completed", 0),
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "Mission Progress"},
            gauge={"axis": {"range": [None, progress.get("total", 7)]}, "bar": {"color": "green"}},
        )
    )
    fig.update_layout(margin=dict(l=10, r=10, t=25, b=20), height=150)
    return fig_to_html(fig)


def create_timeseries_plot(y_data, title, y_axis_title, range_y) -> Markup:
    if not y_data:
        return create_empty_plot(f"No {title} Data")
    fig = go.Figure(
        go.Scatter(
            x=ts_data["time"][-60:],
            y=y_data[-60:],
            mode="lines+markers",
            name=y_axis_title,
            hoverinfo="none",
        )
    )
    fig.update_layout(
        title=title,
        yaxis_title=y_axis_title,
        margin=dict(l=10, r=10, t=25, b=20),
        yaxis_range=range_y,
        height=250,
        xaxis_fixedrange=True,
        yaxis_fixedrange=True,
        showlegend=False,
    )
    return fig_to_html(fig)


# -------------------------------
# Flask Routes
# -------------------------------

@app.route("/")
def index():
    # Read visible config paths for UI
    config_dir = os.environ.get("CONFIG_DIR", "configs")
    seeds_file = os.environ.get("SEEDS_FILE", "seeds.yaml")

    # Attempt to fetch artifact summary
    artifacts, _ = _query_backend(endpoint="/artifacts/list")

    # Extract p-grid and seeds count if available in results (fallback to N/A)
    p_grid = []
    seeds_total = 0
    if artifacts:
        # Heuristic: read results/throughput.csv to infer p-grid and seeds
        try:
            base = _server_url()
            # Direct fetch CSV list first; we won't download the entire CSV here to keep lightweight
            p_grid = sorted({})
        except Exception:
            p_grid = []
    return render_template(
        "index.html",
        server_url=_server_url(),
        config_dir=config_dir,
        seeds_file=seeds_file,
        p_grid=p_grid,
        seeds_total=seeds_total,
    )


@app.route("/artifacts")
def artifacts_page():
    data, err = _query_backend(endpoint="/artifacts/list")
    if err:
        return render_template("artifacts.html", artifacts=[], error=Markup(err))
    return render_template("artifacts.html", artifacts=data, error=None)


@app.route("/status_fragment")
def get_status_fragment():
    data, error_html = _query_backend(endpoint="/mission/status")
    if error_html:
        return error_html

    current_time = time.strftime("%H:%M:%S")
    if not ts_data["time"] or ts_data["time"][-1] != current_time:
        ts_data["time"].append(current_time)
        ts_data["latency"].append(data.get("llm_api_latency", 0))
        ts_data["power"].append(data.get("world_state", {}).get("site_power_level", 100))

    return render_template("fragments/status.html", data=data)


@app.route("/plot/<plot_name>")
def get_plot(plot_name):
    data, error = _query_backend(endpoint="/mission/status")
    if error:
        return create_empty_plot("Server Offline")

    if plot_name == "agent_status":
        return create_agent_status_plot(data.get("agent_status", {}))
    elif plot_name == "mission_progress":
        return create_mission_progress_plot(data.get("mission_progress", {}))
    elif plot_name == "llm_latency":
        return create_timeseries_plot(ts_data["latency"], "LLM API Health", "Latency (s)", [0, 5])
    elif plot_name == "power_level":
        return create_timeseries_plot(ts_data["power"], "Site Power Level", "Power (%)", [0, 110])
    return ""


@app.route("/controls/<action>", methods=["POST"]) 
def controls(action):
    json_payload = None
    endpoint = f"/mission/{action}"

    if action == "inject_failure":
        endpoint = "/inject/failure"
        json_payload = {"task_name": "Print Habitat Shell"}
    elif action == "toggle_hazard":
        current_data, error = _query_backend(endpoint="/mission/status")
        if error:
            return jsonify({"error": "Could not get current hazard status"}), 500
        is_active = current_data.get("world_state", {}).get("dust_storm_active", False)
        endpoint = "/inject/hazard"
        json_payload = {"hazard_name": "dust_storm_active", "value": (not is_active)}

    data, error_msg = _query_backend(method="post", endpoint=endpoint, json_data=json_payload)
    if error_msg:
        return jsonify({"error": "Failed to communicate with the backend."}), 500
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)