from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .io import write_json

MODEL_VERSION = "pam04-rate-v2-live"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _median(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    return float(np.median(values)) if len(values) else 0.0


def _seeded_shuffle(values: np.ndarray, seed: int) -> np.ndarray:
    out = values.copy()
    state = int(seed) & 0xFFFFFFFF or 1
    for i in range(len(out) - 1, 0, -1):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        j = state % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def _rate_event_count(series: list[float], body_id: int, dt_ms: float, max_rate_hz: float) -> int:
    phase = (int(body_id) % 17) / 17.0
    count = 0
    for value in series:
        phase += max(0.0, float(value)) * float(max_rate_hz) * float(dt_ms) / 1000.0
        while phase >= 1.0:
            count += 1
            phase -= 1.0
    return count


def default_parameters(experiment: dict) -> dict:
    model = experiment.get("model", {})
    receptors = model.get("receptors", {})
    candidates = [int(x) for x in experiment.get("candidate_ids", [])]
    first_candidate = str(candidates[0]) if candidates else (str(experiment.get("cells", [{}])[0].get("body_id", "")) if experiment.get("cells") else "")
    input_channels = [c for c in experiment.get("input_channels", []) if c.get("name") != "other"]
    stimulus = input_channels[0].get("name", "") if input_channels else ""
    return {
        "mode": "real",
        "candidate": first_candidate,
        "candidate_gain": 2.0,
        "stimulus": stimulus,
        "stimulus_strength": 1.5,
        "pulse_start_ms": int(model.get("pulse_start_ms", 450)),
        "pulse_duration_ms": int(model.get("pulse_duration_ms", 900)),
        "dopamine_tone": float(model.get("dopamine_tone", 0.04)),
        "dat_clearance": float(model.get("dat_clearance", 1.0)),
        "receptor_gains": {
            name: float(receptors.get(name, {}).get("gain", 1.0))
            for name in ["Dop1R1", "Dop1R2", "Dop2R"]
        },
    }


def normalize_parameters(experiment: dict, scenario: dict | None) -> dict:
    params = default_parameters(experiment)
    raw = (scenario or {}).get("parameters", scenario or {})
    for key in [
        "mode", "candidate", "candidate_gain", "stimulus", "stimulus_strength",
        "pulse_start_ms", "pulse_duration_ms", "dopamine_tone", "dat_clearance",
    ]:
        if key in raw:
            params[key] = raw[key]
    if "receptor_gains" in raw and isinstance(raw["receptor_gains"], dict):
        params["receptor_gains"].update(raw["receptor_gains"])
    params["mode"] = str(params["mode"])
    params["candidate"] = str(params["candidate"])
    for key in ["candidate_gain", "stimulus_strength", "dopamine_tone", "dat_clearance"]:
        params[key] = float(params[key])
    for key in ["pulse_start_ms", "pulse_duration_ms"]:
        params[key] = int(params[key])
    params["receptor_gains"] = {k: float(v) for k, v in params["receptor_gains"].items()}
    return params


def _selected_indices(experiment: dict, params: dict) -> list[int]:
    ids = [int(x) for x in experiment.get("candidate_ids", [])]
    selected = ids[:2] if params.get("candidate") == "pair" else [int(params["candidate"])]
    index = {int(c["body_id"]): i for i, c in enumerate(experiment.get("cells", []))}
    return [index[x] for x in selected if x in index]


def _intervention_input_matrix(experiment: dict, params: dict) -> tuple[np.ndarray, set[int]]:
    matrix = np.asarray([c["weights"] for c in experiment.get("input_channels", [])], dtype=float)
    if params["mode"] == "real":
        return matrix.copy(), set()
    matrix = matrix.copy()
    selected = _selected_indices(experiment, params)
    off: set[int] = set()
    med_by_channel = np.median(matrix, axis=1) if matrix.size else np.asarray([])
    cells = experiment.get("cells", [])
    for ci in selected:
        if params["mode"] == "knockout":
            off.add(ci)
        elif params["mode"] == "medianize":
            total = float(matrix[:, ci].sum())
            med_total = float(med_by_channel.sum()) or 1.0
            matrix[:, ci] = med_by_channel / med_total * total
        elif params["mode"] == "amplify" and matrix.shape[0]:
            best = int(np.argmax(matrix[:, ci]))
            matrix[best, ci] *= float(params["candidate_gain"])
        elif params["mode"] == "shuffle" and matrix.shape[0]:
            body = int(cells[ci]["body_id"])
            matrix[:, ci] = _seeded_shuffle(matrix[:, ci], body)
    return matrix, off


def simulate_pam04(experiment: dict, params: dict, force_real: bool = False) -> dict:
    if not experiment.get("available"):
        raise ValueError("PAM04 experiment data are unavailable")
    effective = dict(params)
    effective["receptor_gains"] = dict(params.get("receptor_gains", {}))
    if force_real:
        effective["mode"] = "real"
    model = experiment.get("model", {})
    dt = float(model.get("dt_ms", 20))
    duration = float(model.get("duration_ms", 3000))
    steps = int(math.floor(duration / dt)) + 1
    input_matrix, off = _intervention_input_matrix(experiment, effective)
    output_matrix = np.asarray([c["weights"] for c in experiment.get("output_channels", [])], dtype=float)
    n = len(experiment.get("cells", []))
    if input_matrix.shape[1] != n or output_matrix.shape[1] != n:
        raise ValueError("Experiment channel matrices do not match PAM04 cell count")

    input_totals = input_matrix.sum(axis=0)
    output_totals = output_matrix.sum(axis=0)
    med_in = _median(input_totals[input_totals > 0]) or 1.0
    med_out = _median(output_totals[output_totals > 0]) or 1.0
    names = [c.get("name") for c in experiment.get("input_channels", [])]
    try:
        stim_index = names.index(effective.get("stimulus"))
    except ValueError:
        stim_index = 0

    activity = np.zeros(n, dtype=float)
    dopamine = 0.0
    slope = float(model.get("activation_slope", 8.0))
    threshold = float(model.get("activation_threshold", 0.34))
    tau = float(model.get("cell_tau_ms", 120))
    tau_d = float(model.get("dopamine_tau_ms", 380))
    baseline_input = float(model.get("baseline_input", 0.08))
    receptor_cfg = model.get("receptors", {})

    result = {
        "model_version": MODEL_VERSION,
        "parameters": effective,
        "time_ms": [],
        "dopamine": [],
        "Dop1R1": [],
        "Dop1R2": [],
        "Dop2R": [],
        "coupling_index": [],
        "cell_activity": [],
        "output_drive": [],
    }
    for step in range(steps):
        time_ms = step * dt
        pulse = effective["pulse_start_ms"] <= time_ms < (effective["pulse_start_ms"] + effective["pulse_duration_ms"])
        for i in range(n):
            total = float(input_totals[i]) or 1.0
            share = float(input_matrix[stim_index, i] / total) if len(input_matrix) else 0.0
            capacity = _clamp(math.sqrt(total / med_in), 0.45, 1.8)
            drive = baseline_input + capacity * share * (effective["stimulus_strength"] if pulse else 0.0)
            target = 0.0 if i in off else _sigmoid(slope * (drive - threshold))
            activity[i] += _clamp(dt / tau, 0.0, 1.0) * (target - activity[i])

        release = float(np.mean([
            activity[i] * _clamp(math.sqrt((float(output_totals[i]) or 1.0) / med_out), 0.45, 1.8)
            for i in range(n)
        ])) if n else 0.0
        dopamine += _clamp(dt / tau_d, 0.0, 1.0) * (
            (effective["dopamine_tone"] + release) - effective["dat_clearance"] * dopamine
        )
        dopamine = max(0.0, dopamine)

        receptor_values = {}
        for name in ["Dop1R1", "Dop1R2", "Dop2R"]:
            cfg = receptor_cfg.get(name, {})
            half = float(cfg.get("half_activation", 0.4))
            gain = float(effective["receptor_gains"].get(name, cfg.get("gain", 1.0)))
            receptor_values[name] = gain * dopamine / (half + dopamine + 1e-9)
        coupling = sum(
            receptor_values[name] * float(receptor_cfg.get(name, {}).get("coupling_prior", 0.0))
            for name in receptor_values
        )
        output_drive = []
        for row in output_matrix:
            denominator = float(row.sum())
            output_drive.append(float(np.dot(activity, row) / denominator) if denominator else 0.0)

        result["time_ms"].append(float(time_ms))
        result["dopamine"].append(float(dopamine))
        for name in receptor_values:
            result[name].append(float(receptor_values[name]))
        result["coupling_index"].append(float(coupling))
        result["cell_activity"].append(activity.astype(float).tolist())
        result["output_drive"].append(output_drive)
    return result


def compare_pam04(experiment: dict, scenario: dict | None) -> dict:
    params = normalize_parameters(experiment, scenario)
    baseline = simulate_pam04(experiment, params, force_real=True)
    intervention = simulate_pam04(experiment, params, force_real=False)
    selected = _selected_indices(experiment, params)
    peak_candidate = max(
        (max(frame[i] for frame in intervention["cell_activity"]) for i in selected),
        default=0.0,
    )
    dt_ms = float(experiment.get("model", {}).get("dt_ms", 20.0))
    max_event_rate = float(experiment.get("model", {}).get("visual_event_rate_hz", 28.0))
    cells = experiment.get("cells", [])
    candidate_auc = float(sum(
        sum(float(frame[i]) for frame in intervention["cell_activity"]) * dt_ms
        for i in selected
    ))
    candidate_events = int(sum(
        _rate_event_count([float(frame[i]) for frame in intervention["cell_activity"]], int(cells[i]["body_id"]), dt_ms, max_event_rate)
        for i in selected
    ))
    base_peak = max(baseline["dopamine"], default=0.0)
    int_peak = max(intervention["dopamine"], default=0.0)
    dopamine_auc = float(sum(intervention["dopamine"]) * dt_ms)
    return {
        "experiment": experiment.get("experiment_id"),
        "dataset": experiment.get("dataset"),
        "model_version": MODEL_VERSION,
        "parameters": params,
        "summary": {
            "baseline_peak_dopamine": float(base_peak),
            "intervention_peak_dopamine": float(int_peak),
            "delta_peak_dopamine": float(int_peak - base_peak),
            "selected_candidate_peak_activity": float(peak_candidate),
            "candidate_activity_auc": candidate_auc,
            "candidate_simulated_events": candidate_events,
            "dopamine_auc": dopamine_auc,
        },
        "baseline": baseline,
        "intervention": intervention,
        "assumptions": experiment.get("assumptions", []),
    }


def run_scenario_file(experiment_path: str | Path, scenario_path: str | Path, output: str | Path) -> dict:
    experiment = json.loads(Path(experiment_path).read_text(encoding="utf-8"))
    scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    result = compare_pam04(experiment, scenario)
    result["scenario_source"] = str(scenario_path)
    write_json(output, result)
    return result
