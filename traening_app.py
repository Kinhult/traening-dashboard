# -*- coding: utf-8 -*-
"""
traening_app.py
Träning & Hälsa – en mobilanpassad Streamlit-dashboard i "Strava Premium"-stil.

Funktioner:
- Import av Apple Hälsa-data (export.xml) samt CSV/JSON
- Sömn, HRV, vilopuls, kroppsmått, andningsfrekvens, syresättning
- Träningsarkiv med sök/filter samt kartvisning (GPX-rutter)
- Målsättning + AI-genererat dynamiskt veckoschema
- Inbyggd AI-tränarchatt (regelbaserad + valfri OpenAI-koppling)
- Styrketräningslogg (Nordic Wellness-övningsbank) + muskelåterhämtning
"""

import os
import re
import json
import uuid
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import streamlit as st
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Valfria bibliotek (appen ska inte krascha om något saknas)
# ---------------------------------------------------------------------------
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except ImportError:
    FOLIUM_OK = False

try:
    import gpxpy
    GPXPY_OK = True
except ImportError:
    GPXPY_OK = False

try:
    from openai import OpenAI
    OPENAI_LIB_OK = True
except ImportError:
    OPENAI_LIB_OK = False


# =============================================================================
# GRUNDINSTÄLLNINGAR
# =============================================================================
st.set_page_config(
    page_title="Träning & Hälsa",
    page_icon="🏃‍♂️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

DATA_DIR = "data"
ROUTES_DIR = os.path.join(DATA_DIR, "routes")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ROUTES_DIR, exist_ok=True)

FILES = {
    "workouts": os.path.join(DATA_DIR, "workouts.csv"),
    "sleep": os.path.join(DATA_DIR, "sleep.csv"),
    "recovery": os.path.join(DATA_DIR, "recovery.csv"),
    "body": os.path.join(DATA_DIR, "body.csv"),
    "physio": os.path.join(DATA_DIR, "physio.csv"),
    "strength": os.path.join(DATA_DIR, "strength.csv"),
    "goals": os.path.join(DATA_DIR, "goals.csv"),
}

SCHEMAS = {
    "workouts": ["id", "date", "type", "duration_min", "distance_km", "calories",
                 "avg_hr", "max_hr", "elevation_gain", "route_file", "notes"],
    "sleep": ["date", "duration_hours", "quality_score", "deep_hours", "rem_hours", "awake_min"],
    "recovery": ["date", "hrv_ms", "resting_hr"],
    "body": ["date", "weight_kg", "height_cm"],
    "physio": ["date", "respiratory_rate", "spo2"],
    "strength": ["id", "date", "muscle_group", "exercise", "equipment",
                 "sets", "reps", "weight_kg", "rpe", "notes"],
    "goals": ["race_name", "race_date", "race_distance_km", "target_time", "sessions_per_week"],
}

MUSCLE_GROUPS = ["Bröst", "Rygg", "Axlar", "Biceps", "Triceps", "Ben", "Rumpa", "Vader", "Core"]

# Ungefärligt antal timmar för full återhämtning per muskelgrupp
RECOVERY_HOURS = {
    "Bröst": 72, "Rygg": 72, "Axlar": 48, "Biceps": 48, "Triceps": 48,
    "Ben": 72, "Rumpa": 72, "Vader": 48, "Core": 30,
}

# Nordic Wellness-inspirerad övningsbank
EXERCISE_BANK = {
    "Bröst": ["Bänkpress (Eleiko skivstång)", "Hantelpress (Eleiko hantlar)",
              "Chest Press (Gymleco)", "Cable Fly (Kabelmaskin)",
              "Lutande hantelpress", "Dips (Bröstfokus)"],
    "Rygg": ["Latsdrag (Gymleco)", "Sittande rodd (Gymleco)", "Pull-up (Stång)",
             "Enarmsrodd hantel", "T-bar rodd", "Cable row (Kabelmaskin)"],
    "Axlar": ["Militärpress (Skivstång)", "Hantelpress axlar", "Sidolyft hantlar",
              "Cable lateral raise", "Face pull (Kabel)", "Shoulder Press (Technogym)"],
    "Biceps": ["Bicepscurl skivstång", "Hantelcurl", "Cable curl (Kabelmaskin)",
               "Preacher curl (Gymleco)", "Koncentrationscurl"],
    "Triceps": ["Triceps pushdown (Kabel)", "Franskpress", "Dips (Tricepsfokus)",
                "Triceps kickback", "Skull crusher (Eleiko skivstång)"],
    "Ben": ["Benpress (Gymleco/Technogym)", "Knäböj (Eleiko skivstång)",
            "Utfallssteg (Hantlar)", "Benspark – Leg Extension (Gymleco)",
            "Bencurl – Leg Curl (Gymleco)", "Bulgarian split squat"],
    "Rumpa": ["Hip Thrust (Gymleco)", "Rumpbrygga", "Kickback (Kabel)",
              "Marklyft (Eleiko skivstång)", "Sumo-knäböj"],
    "Vader": ["Ståendevadpress (Technogym)", "Sittandevadpress (Gymleco)",
              "Vadpress i benpress"],
    "Core": ["Plankan", "Cable crunch (Kabelmaskin)", "Hanging leg raise",
             "Russian twist", "Ab Crunch (Technogym)"],
}


# =============================================================================
# STIL – mobilanpassad "Strava Premium"-look
# =============================================================================
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
}

.stApp {
    background: linear-gradient(180deg, #0f1115 0%, #14161c 100%);
    color: #f2f2f2;
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 5rem;
    max-width: 620px;
}

/* Kort */
.glass-card {
    background: linear-gradient(145deg, #1c1f26, #181a20);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 18px;
    padding: 18px 20px;
    margin-bottom: 14px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.35);
}
.metric-card {
    background: linear-gradient(145deg, #1c1f26, #181a20);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 14px;
    text-align: center;
    box-shadow: 0 4px 14px rgba(0,0,0,0.3);
}
.metric-value { font-size: 1.55rem; font-weight: 700; color: #ffffff; }
.metric-label { font-size: 0.72rem; color: #9aa0aa; text-transform: uppercase; letter-spacing: .06em; }
.metric-sub { font-size: 0.72rem; color: #FC5200; font-weight: 600; }

.app-title { font-size: 1.7rem; font-weight: 800; color: #fff; margin-bottom: 0px;}
.app-sub { color: #9aa0aa; font-size: 0.85rem; margin-top: -6px; margin-bottom: 12px;}

.section-title { font-size: 1.05rem; font-weight: 700; color: #fff; margin: 18px 0 8px 0; }

.badge {
    display:inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing:.04em;
}
.badge-orange{ background: rgba(252,82,0,0.18); color:#FC5200; }
.badge-green{ background: rgba(0,200,120,0.18); color:#00c878; }
.badge-blue{ background: rgba(60,140,255,0.18); color:#3c8cff; }
.badge-red{ background: rgba(255,70,70,0.18); color:#ff4646; }

.workout-row {
    background: #1c1f26; border-radius: 14px; padding: 12px 16px; margin-bottom: 8px;
    border: 1px solid rgba(255,255,255,0.05);
}
.wr-title { font-weight: 700; color:#fff; font-size: 0.95rem;}
.wr-sub { color:#9aa0aa; font-size: 0.78rem; }

.bar-bg { background:#2a2d35; border-radius: 8px; height: 10px; width:100%; overflow:hidden; }
.bar-fill { height: 10px; border-radius: 8px; background: linear-gradient(90deg,#FC5200,#ff8a3d); }

hr { border-color: rgba(255,255,255,0.08); }

div[data-testid="stChatInput"] textarea { background-color:#1c1f26; color:#fff; }

.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] {
    background-color:#1c1f26; border-radius: 12px 12px 0 0; padding: 8px 10px; color:#9aa0aa;
}
.stTabs [aria-selected="true"] { color:#FC5200 !important; font-weight:700; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# DATAHANTERING
# =============================================================================
def _empty_df(name):
    return pd.DataFrame(columns=SCHEMAS[name])


def load_df(name):
    path = FILES[name]
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            for col in SCHEMAS[name]:
                if col not in df.columns:
                    df[col] = np.nan
            return df[SCHEMAS[name]]
        except Exception:
            return _empty_df(name)
    return _empty_df(name)


def save_df(name, df):
    df.to_csv(FILES[name], index=False)


def init_state():
    if "data" not in st.session_state:
        st.session_state.data = {name: load_df(name) for name in FILES}
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content":
             "Hej! Jag är din AI-tränarcoach 💪. Fråga mig om din återhämtning, "
             "sömn, träningsschema – eller säg t.ex. *'lägg till bänkpress bröst 3x8 70kg'* "
             "för att logga ett styrkepass direkt här i chatten."}
        ]
    if "selected_workout" not in st.session_state:
        st.session_state.selected_workout = None
    if "openai_key" not in st.session_state:
        st.session_state.openai_key = ""


def add_row(name, row: dict):
    df = st.session_state.data[name]
    new_row = pd.DataFrame([row])
    df = pd.concat([df, new_row], ignore_index=True)
    st.session_state.data[name] = df
    save_df(name, df)


def upsert_bulk(name, new_df: pd.DataFrame, dedup_cols):
    old_df = st.session_state.data[name]
    combined = pd.concat([old_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=dedup_cols, keep="last")
    st.session_state.data[name] = combined
    save_df(name, combined)
    return len(combined) - len(old_df)


init_state()


# =============================================================================
# HJÄLPFUNKTIONER – BERÄKNINGAR
# =============================================================================
def safe_date(x):
    try:
        return pd.to_datetime(x)
    except Exception:
        return pd.NaT


def latest_value(df, col):
    if df.empty or col not in df.columns:
        return None
    d = df.dropna(subset=[col]).copy()
    if d.empty:
        return None
    d["_d"] = d["date"].apply(safe_date)
    d = d.sort_values("_d")
    return d.iloc[-1][col]


def weekly_summary():
    w = st.session_state.data["workouts"].copy()
    if w.empty:
        return 0, 0.0, 0.0
    w["_d"] = w["date"].apply(safe_date)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=7)
    recent = w[w["_d"] >= cutoff]
    sessions = len(recent)
    dist = pd.to_numeric(recent["distance_km"], errors="coerce").fillna(0).sum()
    dur = pd.to_numeric(recent["duration_min"], errors="coerce").fillna(0).sum()
    return sessions, round(dist, 1), round(dur, 0)


def muscle_recovery():
    """Returnerar dict muskelgrupp -> (recovery_pct, timmar_sedan_senast)"""
    strength = st.session_state.data["strength"].copy()
    workouts = st.session_state.data["workouts"].copy()
    now = pd.Timestamp.now()

    last_hit = {m: None for m in MUSCLE_GROUPS}

    if not strength.empty:
        strength["_d"] = strength["date"].apply(safe_date)
        for m in MUSCLE_GROUPS:
            sub = strength[strength["muscle_group"] == m]
            if not sub.empty:
                last_hit[m] = sub["_d"].max()

    # Löpning/promenad/cykling belastar Ben, Vader, Core (lättare)
    if not workouts.empty:
        workouts["_d"] = workouts["date"].apply(safe_date)
        cardio = workouts[workouts["type"].isin(
            ["Löpning", "Promenad", "Cykling", "Trail-löpning", "Vandring"])]
        if not cardio.empty:
            last_cardio = cardio["_d"].max()
            for m in ["Ben", "Vader", "Core"]:
                if last_hit[m] is None or last_cardio > last_hit[m]:
                    last_hit[m] = last_cardio

    result = {}
    for m in MUSCLE_GROUPS:
        if last_hit[m] is None or pd.isna(last_hit[m]):
            result[m] = (100, None)
        else:
            hours_since = (now - last_hit[m]).total_seconds() / 3600.0
            pct = min(100, round((hours_since / RECOVERY_HOURS[m]) * 100))
            result[m] = (max(0, pct), round(hours_since, 1))
    return result


def avg_recovery_score():
    """Ett samlat 0-100 återhämtningsindex baserat på HRV-trend, vilopuls och sömn."""
    rec = st.session_state.data["recovery"].copy()
    sleep = st.session_state.data["sleep"].copy()
    score = 70  # neutralt baseline
    notes = []

    if not rec.empty:
        rec["_d"] = rec["date"].apply(safe_date)
        rec = rec.sort_values("_d")
        hrv_vals = pd.to_numeric(rec["hrv_ms"], errors="coerce").dropna()
        if len(hrv_vals) >= 2:
            recent_avg = hrv_vals.tail(3).mean()
            baseline_avg = hrv_vals.mean()
            diff = recent_avg - baseline_avg
            score += max(-20, min(20, diff))
            notes.append(f"HRV senaste dagarna: {recent_avg:.0f} ms (snitt {baseline_avg:.0f} ms)")

    if not sleep.empty:
        sleep["_d"] = sleep["date"].apply(safe_date)
        sleep = sleep.sort_values("_d")
        dur = pd.to_numeric(sleep["duration_hours"], errors="coerce").dropna()
        if len(dur):
            last_sleep = dur.iloc[-1]
            if last_sleep < 6:
                score -= 12
                notes.append(f"Kort sömn senast: {last_sleep:.1f} h")
            elif last_sleep >= 7.5:
                score += 8
                notes.append(f"Bra sömnlängd senast: {last_sleep:.1f} h")

    return int(max(0, min(100, score))), notes


def recovery_badge(pct):
    if pct >= 80:
        return '<span class="badge badge-green">Redo</span>'
    elif pct >= 50:
        return '<span class="badge badge-blue">Delvis</span>'
    else:
        return '<span class="badge badge-red">Vila</span>'


# =============================================================================
# APPLE HÄLSA-IMPORT
# =============================================================================
def parse_apple_health_xml(file_obj):
    """Läser export.xml från Apple Hälsa och fyller på sleep/recovery/body/physio/workouts."""
    sleep_records = []
    recovery_records = {}
    body_records = []
    physio_records = {}
    workout_records = []

    context = ET.iterparse(file_obj, events=("end",))
    for event, elem in context:
        tag = elem.tag
        if tag == "Record":
            rtype = elem.get("type", "")
            start = elem.get("startDate", "")
            end = elem.get("endDate", "")
            value = elem.get("value", "")
            d = start[:10] if start else None

            if rtype == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN" and d:
                try:
                    v = float(value)
                    recovery_records.setdefault(d, {}).setdefault("hrv_list", []).append(v)
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierRestingHeartRate" and d:
                try:
                    v = float(value)
                    recovery_records.setdefault(d, {}).setdefault("rhr_list", []).append(v)
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierBodyMass" and d:
                try:
                    v = float(value)
                    body_records.append({"date": d, "weight_kg": v, "height_cm": None})
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierHeight" and d:
                try:
                    v = float(value)
                    unit = elem.get("unit", "cm")
                    if unit == "m":
                        v = v * 100
                    body_records.append({"date": d, "weight_kg": None, "height_cm": v})
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierRespiratoryRate" and d:
                try:
                    v = float(value)
                    physio_records.setdefault(d, {}).setdefault("resp_list", []).append(v)
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierOxygenSaturation" and d:
                try:
                    v = float(value) * 100 if float(value) <= 1 else float(value)
                    physio_records.setdefault(d, {}).setdefault("spo2_list", []).append(v)
                except ValueError:
                    pass
            elif rtype == "HKCategoryTypeIdentifierSleepAnalysis" and start and end:
                try:
                    t0 = pd.to_datetime(start)
                    t1 = pd.to_datetime(end)
                    dur_h = (t1 - t0).total_seconds() / 3600.0
                    kind = "deep" if "Deep" in value else ("rem" if "REM" in value else
                                                            ("awake" if "Awake" in value else "asleep"))
                    sleep_records.append({"date": d, "kind": kind, "hours": dur_h})
                except Exception:
                    pass
            elem.clear()

        elif tag == "Workout":
            wtype_raw = elem.get("workoutActivityType", "")
            start = elem.get("startDate", "")
            d = start[:10] if start else None
            dur_raw = elem.get("duration")
            dur_unit = elem.get("durationUnit", "min")
            dist_raw = elem.get("totalDistance")
            dist_unit = elem.get("totalDistanceUnit", "km")
            energy_raw = elem.get("totalEnergyBurned")

            wtype_map = {
                "HKWorkoutActivityTypeRunning": "Löpning",
                "HKWorkoutActivityTypeWalking": "Promenad",
                "HKWorkoutActivityTypeCycling": "Cykling",
                "HKWorkoutActivityTypeHiking": "Vandring",
                "HKWorkoutActivityTypeTraditionalStrengthTraining": "Styrketräning",
                "HKWorkoutActivityTypeFunctionalStrengthTraining": "Styrketräning",
                "HKWorkoutActivityTypeSwimming": "Simning",
                "HKWorkoutActivityTypeYoga": "Yoga",
            }
            wtype = wtype_map.get(wtype_raw, wtype_raw.replace("HKWorkoutActivityType", "") or "Övrigt")

            try:
                dur_min = float(dur_raw) if dur_raw else None
                if dur_unit == "sec":
                    dur_min = dur_min / 60.0
            except (TypeError, ValueError):
                dur_min = None

            try:
                dist_km = float(dist_raw) if dist_raw else None
                if dist_unit == "mi":
                    dist_km = dist_km * 1.60934
            except (TypeError, ValueError):
                dist_km = None

            try:
                cal = float(energy_raw) if energy_raw else None
            except (TypeError, ValueError):
                cal = None

            if d:
                workout_records.append({
                    "id": str(uuid.uuid4())[:8],
                    "date": d, "type": wtype, "duration_min": dur_min,
                    "distance_km": dist_km, "calories": cal,
                    "avg_hr": None, "max_hr": None, "elevation_gain": None,
                    "route_file": None, "notes": "Importerad från Apple Hälsa",
                })
            elem.clear()

    # Aggregera sömn per dag
    sleep_by_day = {}
    for r in sleep_records:
        d = r["date"]
        sleep_by_day.setdefault(d, {"asleep": 0.0, "deep": 0.0, "rem": 0.0, "awake": 0.0})
        if r["kind"] == "deep":
            sleep_by_day[d]["deep"] += r["hours"]
            sleep_by_day[d]["asleep"] += r["hours"]
        elif r["kind"] == "rem":
            sleep_by_day[d]["rem"] += r["hours"]
            sleep_by_day[d]["asleep"] += r["hours"]
        elif r["kind"] == "awake":
            sleep_by_day[d]["awake"] += r["hours"] * 60
        else:
            sleep_by_day[d]["asleep"] += r["hours"]

    sleep_df = pd.DataFrame([
        {"date": d, "duration_hours": round(v["asleep"], 2),
         "quality_score": None, "deep_hours": round(v["deep"], 2),
         "rem_hours": round(v["rem"], 2), "awake_min": round(v["awake"], 0)}
        for d, v in sleep_by_day.items()
    ])

    recovery_df = pd.DataFrame([
        {"date": d,
         "hrv_ms": round(np.mean(v["hrv_list"]), 1) if "hrv_list" in v else None,
         "resting_hr": round(np.mean(v["rhr_list"]), 1) if "rhr_list" in v else None}
        for d, v in recovery_records.items()
    ])

    physio_df = pd.DataFrame([
        {"date": d,
         "respiratory_rate": round(np.mean(v["resp_list"]), 1) if "resp_list" in v else None,
         "spo2": round(np.mean(v["spo2_list"]), 1) if "spo2_list" in v else None}
        for d, v in physio_records.items()
    ])

    body_df = pd.DataFrame(body_records)
    workouts_df = pd.DataFrame(workout_records)

    return workouts_df, sleep_df, recovery_df, body_df, physio_df


# =============================================================================
# UI-KOMPONENTER
# =============================================================================
def metric_card(col, label, value, sub=""):
    with col:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{value}</div>
            <div class="metric-label">{label}</div>
            <div class="metric-sub">{sub}</div>
        </div>
        """, unsafe_allow_html=True)


def render_muscle_bars():
    rec = muscle_recovery()
    for m in MUSCLE_GROUPS:
        pct, hours = rec[m]
        color = "#00c878" if pct >= 80 else ("#3c8cff" if pct >= 50 else "#ff4646")
        hours_txt = f"{hours:.0f}h sedan senaste pass" if hours is not None else "Ingen data ännu"
        st.markdown(f"""
        <div style="margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; font-size:0.82rem; color:#e5e5e5;">
                <span>{m}</span><span style="color:{color}; font-weight:700;">{pct}%</span>
            </div>
            <div class="bar-bg"><div class="bar-fill" style="width:{pct}%; background:{color};"></div></div>
            <div style="font-size:0.68rem; color:#77808c; margin-top:2px;">{hours_txt}</div>
        </div>
        """, unsafe_allow_html=True)


# =============================================================================
# AI-COACH
# =============================================================================
def build_context_summary():
    sessions, dist, dur = weekly_summary()
    score, notes = avg_recovery_score()
    rec = muscle_recovery()
    hrv = latest_value(st.session_state.data["recovery"], "hrv_ms")
    rhr = latest_value(st.session_state.data["recovery"], "resting_hr")
    sleep_h = latest_value(st.session_state.data["sleep"], "duration_hours")
    weight = latest_value(st.session_state.data["body"], "weight_kg")
    goals = st.session_state.data["goals"]
    goal_txt = "Inget mål satt ännu."
    if not goals.empty:
        g = goals.iloc[-1]
        goal_txt = (f"Lopp: {g.get('race_name')}, datum: {g.get('race_date')}, "
                    f"distans: {g.get('race_distance_km')} km, måltid: {g.get('target_time')}, "
                    f"{g.get('sessions_per_week')} pass/vecka.")

    low_muscles = [m for m, (p, h) in rec.items() if p < 50]

    summary = f"""
Återhämtningsindex: {score}/100.
HRV senast: {hrv}. Vilopuls senast: {rhr}. Sömn senaste natten: {sleep_h} h.
Veckans träning: {sessions} pass, {dist} km, {dur} min totalt.
Kroppsvikt senast: {weight} kg.
Muskler med låg återhämtning (<50%): {', '.join(low_muscles) if low_muscles else 'inga'}.
Mål: {goal_txt}
"""
    return summary.strip()


def try_parse_strength_log(msg: str):
    """Försöker tolka ett meddelande som 'lägg till <övning> <muskelgrupp> 3x8 70kg'."""
    lower = msg.lower()
    if not any(k in lower for k in ["lägg till", "logga"]):
        return None

    muscle_found = None
    for m in MUSCLE_GROUPS:
        if m.lower() in lower:
            muscle_found = m
            break

    sets_reps = re.search(r"(\d+)\s*x\s*(\d+)", lower)
    weight_match = re.search(r"(\d+(?:[.,]\d+)?)\s*kg", lower)

    if not (sets_reps or weight_match or muscle_found):
        return None

    exercise_name = re.sub(r"(lägg till|logga)", "", lower)
    exercise_name = re.sub(r"(\d+)\s*x\s*(\d+)", "", exercise_name)
    exercise_name = re.sub(r"(\d+(?:[.,]\d+)?)\s*kg", "", exercise_name)
    if muscle_found:
        exercise_name = exercise_name.replace(muscle_found.lower(), "")
    exercise_name = exercise_name.strip(" ,.-").capitalize() or "Övning"

    sets = int(sets_reps.group(1)) if sets_reps else None
    reps = int(sets_reps.group(2)) if sets_reps else None
    weight = float(weight_match.group(1).replace(",", ".")) if weight_match else None

    return {
        "id": str(uuid.uuid4())[:8],
        "date": datetime.now().strftime("%Y-%m-%d"),
        "muscle_group": muscle_found or "Övrigt",
        "exercise": exercise_name,
        "equipment": "",
        "sets": sets, "reps": reps, "weight_kg": weight, "rpe": None,
        "notes": "Tillagd via AI-chatten",
    }


def rule_based_reply(user_msg: str, context: str) -> str:
    m = user_msg.lower()
    score, notes = avg_recovery_score()
    sessions, dist, dur = weekly_summary()
    rec = muscle_recovery()

    if any(k in m for k in ["återhämtning", "redo", "trött", "vila"]):
        low = [k for k, (p, h) in rec.items() if p < 60]
        txt = f"Ditt återhämtningsindex just nu är **{score}/100**. "
        if score >= 75:
            txt += "Du ser pigg ut på pappret – bra läge för ett kvalitetspass. "
        elif score >= 50:
            txt += "Helt okej, men kör gärna lugnare idag eller fokusera på teknik. "
        else:
            txt += "Din kropp signalerar att den vill vila – överväg lätt återhämtningsträning eller vilodag. "
        if low:
            txt += f"Muskelgrupper som fortfarande återhämtar sig: {', '.join(low)}."
        return txt

    if any(k in m for k in ["sömn", "sova"]):
        sleep_h = latest_value(st.session_state.data["sleep"], "duration_hours")
        if sleep_h is None:
            return "Jag har ingen sömndata ännu – importera din Apple Hälsa-export så kan jag ge bättre råd."
        if sleep_h < 6.5:
            return (f"Du sov {sleep_h:.1f} h senaste natten, vilket är lite lågt. "
                     "Prioritera 7–9 h de kommande nätterna och håll intensiteten nere idag.")
        return f"Du sov {sleep_h:.1f} h senaste natten – helt okej nivå för prestation."

    if any(k in m for k in ["schema", "vecka", "plan"]):
        return ("Kolla fliken 'Mål & Schema' där jag genererar ett dynamiskt veckoschema baserat på ditt lopp, "
                "sömn och återhämtning. Justera målen där så uppdateras schemat automatiskt.")

    if any(k in m for k in ["vikt", "väger"]):
        w = latest_value(st.session_state.data["body"], "weight_kg")
        if w:
            return f"Din senast loggade vikt är {w} kg."
        return "Ingen viktdata är importerad ännu."

    if any(k in m for k in ["hrv"]):
        h = latest_value(st.session_state.data["recovery"], "hrv_ms")
        if h:
            return f"Din senaste HRV är {h} ms. {notes[0] if notes else ''}"
        return "Ingen HRV-data importerad ännu."

    return (f"Den här veckan har du kört {sessions} pass ({dist} km, {dur} min totalt) "
            f"och ditt återhämtningsindex är {score}/100. Fråga mig gärna om sömn, HRV, "
            "schema eller säg 'lägg till [övning] [muskelgrupp] 3x10 40kg' för att logga styrka.")


def get_ai_response(user_msg: str) -> str:
    context = build_context_summary()

    # Försök logga styrkepass direkt via chatten
    parsed = try_parse_strength_log(user_msg)
    if parsed:
        add_row("strength", parsed)
        weight_txt = f"@ {parsed['weight_kg']} kg" if parsed['weight_kg'] else ""
        return (f"✅ Loggat: **{parsed['exercise']}** ({parsed['muscle_group']}) – "
                f"{parsed['sets'] or '?'}x{parsed['reps'] or '?'} {weight_txt}. "
                "Muskelåterhämtningen är uppdaterad!")

    api_key = st.session_state.openai_key or os.environ.get("OPENAI_API_KEY", "")
    if api_key and OPENAI_LIB_OK:
        try:
            client = OpenAI(api_key=api_key)
            system_prompt = (
                "Du är en erfaren, peppande men datadriven löp- och styrketränarcoach. "
                "Svara kort, konkret och på svenska. Använd datan nedan om användarens hälsa "
                "och träning för att ge personliga råd.\n\n" + context
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=400,
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"(Kunde inte nå OpenAI, faller tillbaka på inbyggd logik: {e})\n\n" + rule_based_reply(user_msg, context)

    return rule_based_reply(user_msg, context)


# =============================================================================
# SCHEMA-GENERERING
# =============================================================================
def generate_schedule(goal_row):
    score, _ = avg_recovery_score()
    sessions_per_week = int(goal_row.get("sessions_per_week", 4) or 4)
    race_date = goal_row.get("race_date")
    race_distance = goal_row.get("race_distance_km", 10)

    try:
        weeks_left = max(1, (pd.to_datetime(race_date) - pd.Timestamp.now()).days // 7)
    except Exception:
        weeks_left = 8

    if score >= 75:
        intensity_note = "Full fart – kroppen är redo för kvalitetspass."
    elif score >= 50:
        intensity_note = "Måttlig belastning – blanda lugna och medelhårda pass."
    else:
        intensity_note = "Lågt återhämtningsläge – prioritera lätta pass och rörlighet denna vecka."

    days = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]
    pass_types = []
    base_cycle = ["Lugn löpning", "Styrka – underkropp", "Intervaller",
                  "Styrka – överkropp", "Vila/rörlighet", "Långpass", "Vila"]

    if score < 50:
        base_cycle = ["Lätt promenad", "Lätt styrka/mobility", "Vila",
                      "Lugn löpning", "Vila", "Lätt löpning", "Vila"]

    chosen_days = sorted(np.random.RandomState(hash(str(goal_row)) % (2**32)).choice(
        range(7), size=min(sessions_per_week, 7), replace=False))

    schedule = []
    for i, day in enumerate(days):
        if i in chosen_days:
            idx = chosen_days.index(i) % len(base_cycle)
            schedule.append((day, base_cycle[idx]))
        else:
            schedule.append((day, "Vila"))

    return schedule, weeks_left, intensity_note


# =============================================================================
# HEADER
# =============================================================================
st.markdown('<div class="app-title">🏃‍♂️ Träning & Hälsa</div>', unsafe_allow_html=True)
st.markdown('<div class="app-sub">Din personliga coach – drivs av din Apple Hälsa-data</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Inställningar")
    st.session_state.openai_key = st.text_input(
        "OpenAI API-nyckel (valfritt, för smartare AI-chatt)",
        value=st.session_state.openai_key, type="password",
        help="Utan nyckel används en inbyggd regelbaserad coach istället."
    )
    st.caption("Nyckeln sparas endast i din session, inte i filerna.")

tabs = st.tabs(["🏠 Hem", "📥 Importera", "🗂️ Arkiv", "🎯 Mål & Schema", "💪 Styrka"])


# =============================================================================
# TAB 1 – HEM
# =============================================================================
with tabs[0]:
    score, notes = avg_recovery_score()
    sessions, dist, dur = weekly_summary()
    hrv = latest_value(st.session_state.data["recovery"], "hrv_ms")
    rhr = latest_value(st.session_state.data["recovery"], "resting_hr")
    sleep_h = latest_value(st.session_state.data["sleep"], "duration_hours")

    c1, c2 = st.columns(2)
    metric_card(c1, "Återhämtning", f"{score}", recovery_badge(score))
    metric_card(c2, "Sömn senast", f"{sleep_h:.1f} h" if sleep_h else "–", "Senaste natten")

    c3, c4 = st.columns(2)
    metric_card(c3, "HRV", f"{hrv:.0f} ms" if hrv else "–", "Senaste mätning")
    metric_card(c4, "Vilopuls", f"{rhr:.0f}" if rhr else "–", "bpm")

    st.markdown('<div class="section-title">📅 Denna vecka</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="glass-card">
        <b>{sessions}</b> pass &nbsp;|&nbsp; <b>{dist}</b> km &nbsp;|&nbsp; <b>{dur:.0f}</b> min totalt
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">💪 Muskelåterhämtning</div>', unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        render_muscle_bars()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">🤖 AI-tränarcoach</div>', unsafe_allow_html=True)
    chat_box = st.container(height=380)
    with chat_box:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    user_msg = st.chat_input("Fråga din coach om återhämtning, sömn, schema...")
    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        reply = get_ai_response(user_msg)
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.rerun()


# =============================================================================
# TAB 2 – IMPORTERA
# =============================================================================
with tabs[1]:
    st.markdown('<div class="section-title">📥 Importera Apple Hälsa-data</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="glass-card">
    1. Öppna appen <b>Hälsa</b> på din iPhone → tryck på din profilbild → <b>Exportera all hälsodata</b>.<br>
    2. Packa upp zip-filen på din dator – leta upp filen <b>export.xml</b>.<br>
    3. Ladda upp <b>export.xml</b> nedan (kan ta en stund för stora filer).
    </div>
    """, unsafe_allow_html=True)

    xml_file = st.file_uploader("Ladda upp export.xml", type=["xml"])
    if xml_file is not None:
        with st.spinner("Läser in din hälsodata... detta kan ta en stund för stora filer."):
            try:
                w_df, s_df, r_df, b_df, p_df = parse_apple_health_xml(xml_file)
                added = 0
                if not w_df.empty:
                    added += upsert_bulk("workouts", w_df, ["date", "type", "duration_min"])
                if not s_df.empty:
                    added += upsert_bulk("sleep", s_df, ["date"])
                if not r_df.empty:
                    added += upsert_bulk("recovery", r_df, ["date"])
                if not b_df.empty:
                    added += upsert_bulk("body", b_df, ["date", "weight_kg", "height_cm"])
                if not p_df.empty:
                    added += upsert_bulk("physio", p_df, ["date"])
                st.success(f"Klart! {added} nya rader importerade från Apple Hälsa.")
            except Exception as e:
                st.error(f"Kunde inte tolka filen: {e}")

    st.markdown('<div class="section-title">📄 Generisk import (CSV)</div>', unsafe_allow_html=True)
    st.caption("Använd detta för äldre historik eller export från andra appar. "
               "CSV-filen bör matcha kolumnerna nedan (extra kolumner ignoreras).")
    target = st.selectbox("Vilken datatyp vill du importera?",
                           ["workouts", "sleep", "recovery", "body", "physio", "strength"],
                           format_func=lambda x: {
                               "workouts": "Träningspass", "sleep": "Sömn", "recovery": "Återhämtning (HRV/vilopuls)",
                               "body": "Kroppsmått", "physio": "Fysiologi (andning/syre)", "strength": "Styrkelogg"
                           }[x])
    st.code(", ".join(SCHEMAS[target]), language="text")
    csv_file = st.file_uploader(f"Ladda upp CSV för {target}", type=["csv"], key=f"csv_{target}")
    if csv_file is not None:
        try:
            df_new = pd.read_csv(csv_file)
            for col in SCHEMAS[target]:
                if col not in df_new.columns:
                    df_new[col] = np.nan
            if "id" in SCHEMAS[target] and "id" not in df_new.columns:
                df_new["id"] = [str(uuid.uuid4())[:8] for _ in range(len(df_new))]
            dedup = ["id"] if "id" in SCHEMAS[target] else ["date"]
            added = upsert_bulk(target, df_new[SCHEMAS[target]], dedup)
            st.success(f"{added} nya rader importerade till {target}.")
        except Exception as e:
            st.error(f"Fel vid import: {e}")

    st.markdown('<div class="section-title">🗺️ Ladda upp GPS-rutt (GPX)</div>', unsafe_allow_html=True)
    st.caption("Apple Hälsa-export innehåller GPX-filer i mappen 'workout-routes'. "
               "Koppla en rutt till ett träningspass här.")
    w_df_now = st.session_state.data["workouts"]
    if not w_df_now.empty:
        options = w_df_now.apply(lambda r: f"{r['date']} – {r['type']} ({r['id']})", axis=1).tolist()
        choice = st.selectbox("Välj träningspass", options) if options else None
        gpx_file = st.file_uploader("Ladda upp .gpx-fil", type=["gpx"])
        if gpx_file is not None and choice:
            wid = choice.split("(")[-1].replace(")", "")
            fname = f"{wid}.gpx"
            fpath = os.path.join(ROUTES_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(gpx_file.getbuffer())
            df = st.session_state.data["workouts"]
            df.loc[df["id"] == wid, "route_file"] = fpath
            st.session_state.data["workouts"] = df
            save_df("workouts", df)
            st.success("Rutt kopplad till träningspasset! Se den i Arkiv-fliken.")
    else:
        st.info("Inga träningspass importerade ännu.")


# =============================================================================
# TAB 3 – ARKIV
# =============================================================================
with tabs[2]:
    st.markdown('<div class="section-title">🗂️ Träningsarkiv</div>', unsafe_allow_html=True)
    w = st.session_state.data["workouts"].copy()

    if w.empty:
        st.info("Inga träningspass i arkivet ännu. Importera data i fliken 'Importera'.")
    else:
        w["_d"] = w["date"].apply(safe_date)
        w = w.sort_values("_d", ascending=False)

        search = st.text_input("🔍 Sök i arkivet (typ, anteckning, datum)")
        types = sorted(w["type"].dropna().unique().tolist())
        selected_types = st.multiselect("Filtrera på träningstyp", types, default=types)

        filtered = w[w["type"].isin(selected_types)]
        if search:
            s = search.lower()
            filtered = filtered[
                filtered.apply(lambda r: s in str(r["type"]).lower()
                                or s in str(r["notes"]).lower()
                                or s in str(r["date"]).lower(), axis=1)
            ]

        st.caption(f"{len(filtered)} pass hittades")

        for _, row in filtered.iterrows():
            wid = row["id"]
            with st.container():
                st.markdown(f"""
                <div class="workout-row">
                    <div class="wr-title">{row['type']} – {row['date']}</div>
                    <div class="wr-sub">
                        {f"{row['distance_km']:.1f} km" if pd.notna(row['distance_km']) else ""}
                        {f" · {row['duration_min']:.0f} min" if pd.notna(row['duration_min']) else ""}
                        {f" · {row['calories']:.0f} kcal" if pd.notna(row['calories']) else ""}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Visa detaljer", key=f"btn_{wid}"):
                    st.session_state.selected_workout = wid

        if st.session_state.selected_workout:
            sel = w[w["id"] == st.session_state.selected_workout]
            if not sel.empty:
                row = sel.iloc[0]
                st.markdown("---")
                st.markdown(f"### {row['type']} – {row['date']}")
                d1, d2, d3 = st.columns(3)
                d1.metric("Distans", f"{row['distance_km']:.1f} km" if pd.notna(row['distance_km']) else "–")
                d2.metric("Tid", f"{row['duration_min']:.0f} min" if pd.notna(row['duration_min']) else "–")
                d3.metric("Kalorier", f"{row['calories']:.0f}" if pd.notna(row['calories']) else "–")
                if pd.notna(row.get("notes")):
                    st.caption(row["notes"])

                route_file = row.get("route_file")
                if pd.notna(route_file) and route_file and os.path.exists(str(route_file)):
                    if FOLIUM_OK and GPXPY_OK:
                        try:
                            with open(route_file, "r") as f:
                                gpx = gpxpy.parse(f)
                            points = []
                            for track in gpx.tracks:
                                for seg in track.segments:
                                    for p in seg.points:
                                        points.append((p.latitude, p.longitude))
                            if points:
                                m = folium.Map(location=points[len(points)//2], zoom_start=14, tiles="CartoDB dark_matter")
                                folium.PolyLine(points, color="#FC5200", weight=5).add_to(m)
                                folium.Marker(points[0], tooltip="Start",
                                              icon=folium.Icon(color="green")).add_to(m)
                                folium.Marker(points[-1], tooltip="Mål",
                                              icon=folium.Icon(color="red")).add_to(m)
                                st_folium(m, height=340, width=None)
                            else:
                                st.info("GPX-filen innehöll inga rutt-punkter.")
                        except Exception as e:
                            st.warning(f"Kunde inte rendera kartan: {e}")
                    else:
                        st.warning("Installera 'folium', 'streamlit-folium' och 'gpxpy' för kartvisning.")
                else:
                    st.caption("📍 Ingen GPS-rutt kopplad till detta pass. Ladda upp GPX i fliken Importera.")

                if st.button("Stäng detaljer"):
                    st.session_state.selected_workout = None
                    st.rerun()


# =============================================================================
# TAB 4 – MÅL & SCHEMA
# =============================================================================
with tabs[3]:
    st.markdown('<div class="section-title">🎯 Sätt ditt mål</div>', unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        with st.form("goal_form"):
            race_name = st.text_input("Lopp / mål", placeholder="T.ex. Stockholm Halvmarathon")
            gcol1, gcol2 = st.columns(2)
            race_date = gcol1.date_input("Datum", value=date.today() + timedelta(days=90))
            race_distance = gcol2.number_input("Distans (km)", min_value=1.0, value=21.1, step=0.5)
            target_time = st.text_input("Tidsmål (hh:mm:ss)", placeholder="01:45:00")
            sessions_per_week = st.slider("Träningsdagar per vecka", 1, 7, 4)
            submitted = st.form_submit_button("💾 Spara mål & generera schema")
        st.markdown('</div>', unsafe_allow_html=True)

        if submitted and race_name:
            goal_row = {
                "race_name": race_name, "race_date": str(race_date),
                "race_distance_km": race_distance, "target_time": target_time,
                "sessions_per_week": sessions_per_week,
            }
            df = pd.DataFrame([goal_row])
            st.session_state.data["goals"] = df  # ett aktivt mål i taget
            save_df("goals", df)
            st.success("Mål sparat! Ditt schema uppdateras nedan.")

    goals = st.session_state.data["goals"]
    if not goals.empty:
        g = goals.iloc[-1].to_dict()
        st.markdown('<div class="section-title">📆 Ditt dynamiska veckoschema</div>', unsafe_allow_html=True)
        schedule, weeks_left, intensity_note = generate_schedule(g)
        st.markdown(f"""
        <div class="glass-card">
        <b>{g['race_name']}</b> · {g['race_distance_km']} km · mål {g['target_time'] or '–'}<br>
        <span style="color:#9aa0aa;">{weeks_left} veckor kvar · {intensity_note}</span>
        </div>
        """, unsafe_allow_html=True)

        for day, activity in schedule:
            badge = "badge-red" if activity == "Vila" else "badge-orange"
            st.markdown(f"""
            <div class="workout-row" style="display:flex; justify-content:space-between; align-items:center;">
                <span class="wr-title">{day}</span>
                <span class="badge {badge}">{activity}</span>
            </div>
            """, unsafe_allow_html=True)

        st.caption("Schemat räknas om automatiskt utifrån din senaste sömn, HRV och muskelåterhämtning "
                   "varje gång du öppnar appen eller sparar nya mätvärden.")
    else:
        st.info("Sätt ett mål ovan så genererar AI-coachen ett schema åt dig.")


# =============================================================================
# TAB 5 – STYRKA
# =============================================================================
with tabs[4]:
    st.markdown('<div class="section-title">💪 Logga styrketräning</div>', unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        muscle = st.selectbox("Muskelgrupp", MUSCLE_GROUPS)
        exercise = st.selectbox("Övning (Nordic Wellness-utrustning)", EXERCISE_BANK[muscle])
        custom_exercise = st.text_input("...eller skriv en egen övning (valfritt)")
        c1, c2, c3 = st.columns(3)
        sets = c1.number_input("Sets", 1, 10, 3)
        reps = c2.number_input("Reps", 1, 50, 10)
        weight = c3.number_input("Vikt (kg)", 0.0, 500.0, 20.0, step=2.5)
        rpe = st.slider("RPE (ansträngning, 1-10)", 1, 10, 7)
        notes = st.text_input("Anteckning (valfritt)")
        if st.button("➕ Logga pass"):
            final_exercise = custom_exercise.strip() if custom_exercise.strip() else exercise
            add_row("strength", {
                "id": str(uuid.uuid4())[:8], "date": datetime.now().strftime("%Y-%m-%d"),
                "muscle_group": muscle, "exercise": final_exercise, "equipment": "",
                "sets": sets, "reps": reps, "weight_kg": weight, "rpe": rpe, "notes": notes,
            })
            st.success(f"Loggat {final_exercise} – {sets}x{reps} @ {weight} kg!")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">📖 Styrkehistorik</div>', unsafe_allow_html=True)
    s = st.session_state.data["strength"].copy()
    if s.empty:
        st.info("Inga styrkepass loggade ännu.")
    else:
        s["_d"] = s["date"].apply(safe_date)
        s = s.sort_values("_d", ascending=False)
        muscle_filter = st.multiselect("Filtrera muskelgrupp", MUSCLE_GROUPS, default=MUSCLE_GROUPS)
        s = s[s["muscle_group"].isin(muscle_filter)]
        for _, row in s.head(40).iterrows():
            st.markdown(f"""
            <div class="workout-row">
                <div class="wr-title">{row['exercise']} <span class="badge badge-blue">{row['muscle_group']}</span></div>
                <div class="wr-sub">{row['date']} · {row['sets']}x{row['reps']} @ {row['weight_kg']} kg
                {f"· RPE {row['rpe']}" if pd.notna(row['rpe']) else ""}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">💪 Aktuell muskelåterhämtning</div>', unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        render_muscle_bars()
        st.markdown('</div>', unsafe_allow_html=True)
