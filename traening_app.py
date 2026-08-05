# -*- coding: utf-8 -*-
"""
traening_app.py
Träning & Hälsa – mobilanpassad Streamlit-dashboard i "Strava Premium"-stil.

Datan lagras 100% i molnet (Supabase/Postgres) – inga lokala filer.
Apple Hälsa-data strömmar in automatiskt i bakgrunden via iPhone-appen
"Health Auto Export" -> en Supabase Edge Function -> databasen.

Funktioner:
- Lösenordsskyddad inloggning
- Live-koppling mot Supabase (läsning + skrivning)
- Sömn, HRV, vilopuls, kroppsmått, andningsfrekvens, syresättning
- Träningsarkiv med sök/filter samt kartvisning (rutter lagrade som JSON i DB)
- Engångsimport av historik (gammal Apple Hälsa-export eller CSV) rakt in i molnet
- Målsättning + AI-genererat dynamiskt veckoschema
- Inbyggd AI-tränarchatt (regelbaserad + valfri OpenAI-koppling)
- Styrketräningslogg (Nordic Wellness-övningsbank) + muskelåterhämtning
"""

import re
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
    from supabase import create_client
    SUPABASE_LIB_OK = True
except ImportError:
    SUPABASE_LIB_OK = False

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

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_OK = True
except ImportError:
    AUTOREFRESH_OK = False


# =============================================================================
# GRUNDINSTÄLLNINGAR
# =============================================================================
st.set_page_config(
    page_title="Träning & Hälsa",
    page_icon="🏃‍♂️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

MUSCLE_GROUPS = ["Bröst", "Rygg", "Axlar", "Biceps", "Triceps", "Ben", "Rumpa", "Vader", "Core"]

RECOVERY_HOURS = {
    "Bröst": 72, "Rygg": 72, "Axlar": 48, "Biceps": 48, "Triceps": 48,
    "Ben": 72, "Rumpa": 72, "Vader": 48, "Core": 30,
}

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

SCHEMAS = {
    "workouts": ["id", "date", "type", "duration_min", "distance_km", "calories",
                 "avg_hr", "max_hr", "elevation_gain", "route", "notes"],
    "sleep": ["date", "duration_hours", "quality_score", "deep_hours", "rem_hours", "awake_min"],
    "recovery": ["date", "hrv_ms", "resting_hr"],
    "body": ["date", "weight_kg", "height_cm"],
    "physio": ["date", "respiratory_rate", "spo2"],
    "strength": ["id", "date", "muscle_group", "exercise", "equipment",
                 "sets", "reps", "weight_kg", "rpe", "notes"],
    "goals": ["id", "race_name", "race_date", "race_distance_km", "target_time", "sessions_per_week"],
}


# =============================================================================
# LÖSENORDSGRIND (Säkerhet)[cite: 5]
# =============================================================================
def check_password():
    """Returnerar True om användaren angett rätt lösenord."""
    def password_entered():
        if st.session_state["password"] == st.secrets.get("APP_PASSWORD", "bytt-detta-losenord"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("<h2 style='text-align: center;'>🔐 Logga in</h2>", unsafe_allow_html=True)
        st.text_input("Ange lösenord för att öppna träningsappen", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("<h2 style='text-align: center;'>🔐 Logga in</h2>", unsafe_allow_html=True)
        st.text_input("Ange lösenord för att öppna träningsappen", type="password", on_change=password_entered, key="password")
        st.error("😕 Fel lösenord, försök igen.")
        return False
    else:
        return True

if not check_password():
    st.stop()


# =============================================================================
# STIL – mobilanpassad "Strava Premium"-look[cite: 5]
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
.conn-ok { color:#00c878; font-size:0.75rem; }
.conn-bad { color:#ff4646; font-size:0.75rem; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# SUPABASE-ANSLUTNING[cite: 5]
# =============================================================================
def _empty_df(name):
    return pd.DataFrame(columns=SCHEMAS[name])


@st.cache_resource
def get_supabase_client():
    if not SUPABASE_LIB_OK:
        return None
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None


supabase = get_supabase_client()


@st.cache_data(ttl=45, show_spinner=False)
def load_table(name: str) -> pd.DataFrame:
    """Läser en tabell live från Supabase (cachad 45 sekunder)."""
    if supabase is None:
        return _empty_df(name)
    try:
        res = supabase.table(name).select("*").execute()
        rows = res.data or []
        if not rows:
            return _empty_df(name)
        df = pd.DataFrame(rows)
        for col in SCHEMAS[name]:
            if col not in df.columns:
                df[col] = np.nan
        return df[SCHEMAS[name]]
    except Exception as e:
        st.session_state["_last_db_error"] = str(e)
        return _empty_df(name)


def refresh_data():
    load_table.clear()


def db_insert(name: str, row: dict):
    if supabase is None:
        st.error("Ingen databaskoppling – kontrollera Supabase-secrets.")
        return
    supabase.table(name).insert(row).execute()
    refresh_data()


def db_upsert(name: str, rows, on_conflict: str):
    if supabase is None or not rows:
        return 0
    supabase.table(name).upsert(rows, on_conflict=on_conflict).execute()
    refresh_data()
    return len(rows)


def db_update_field(name: str, match_col: str, match_val, field: str, value):
    if supabase is None:
        return
    supabase.table(name).update({field: value}).eq(match_col, match_val).execute()
    refresh_data()


# =============================================================================
# HJÄLPFUNKTIONER – BERÄKNINGAR[cite: 5]
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
    w = load_table("workouts").copy()
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
    strength = load_table("strength").copy()
    workouts = load_table("workouts").copy()
    now = pd.Timestamp.now()
    last_hit = {m: None for m in MUSCLE_GROUPS}

    if not strength.empty:
        strength["_d"] = strength["date"].apply(safe_date)
        for m in MUSCLE_GROUPS:
            sub = strength[strength["muscle_group"] == m]
            if not sub.empty:
                last_hit[m] = sub["_d"].max()

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
    rec = load_table("recovery").copy()
    sleep = load_table("sleep").copy()
    score = 70
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
# ENGÅNGSIMPORT AV HISTORIK (Apple Hälsa export.xml)[cite: 5]
# =============================================================================
def parse_apple_health_xml(file_obj):
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
                    recovery_records.setdefault(d, {}).setdefault("hrv_list", []).append(float(value))
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierRestingHeartRate" and d:
                try:
                    recovery_records.setdefault(d, {}).setdefault("rhr_list", []).append(float(value))
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierBodyMass" and d:
                try:
                    body_records.append({"date": d, "weight_kg": float(value), "height_cm": None})
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierHeight" and d:
                try:
                    v = float(value)
                    if elem.get("unit", "cm") == "m":
                        v *= 100
                    body_records.append({"date": d, "weight_kg": None, "height_cm": v})
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierRespiratoryRate" and d:
                try:
                    physio_records.setdefault(d, {}).setdefault("resp_list", []).append(float(value))
                except ValueError:
                    pass
            elif rtype == "HKQuantityTypeIdentifierOxygenSaturation" and d:
                try:
                    v = float(value)
                    v = v * 100 if v <= 1 else v
                    physio_records.setdefault(d, {}).setdefault("spo2_list", []).append(v)
                except ValueError:
                    pass
            elif rtype == "HKCategoryTypeIdentifierSleepAnalysis" and start and end:
                try:
                    t0, t1 = pd.to_datetime(start), pd.to_datetime(end)
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
                if dur_unit == "sec" and dur_min is not None:
                    dur_min = dur_min / 60.0
            except (TypeError, ValueError):
                dur_min = None
            try:
                dist_km = float(dist_raw) if dist_raw else None
                if dist_unit == "mi" and dist_km is not None:
                    dist_km = dist_km * 1.60934
            except (TypeError, ValueError):
                dist_km = None
            try:
                cal = float(energy_raw) if energy_raw else None
            except (TypeError, ValueError):
                cal = None

            if d:
                workout_records.append({
                    "id": f"xmlimport_{uuid.uuid4().hex[:10]}",
                    "date": d, "type": wtype, "duration_min": dur_min,
                    "distance_km": dist_km, "calories": cal,
                    "avg_hr": None, "max_hr": None, "elevation_gain": None,
                    "route": None, "notes": "Importerad historik (Apple Hälsa)",
                })
            elem.clear()

    sleep_by_day = {}
    for r in sleep_records:
        d = r["date"]
        sleep_by_day.setdefault(d, {"asleep": 0.0, "deep": 0.0, "rem": 0.0, "awake": 0.0})
        if r["kind"] == "deep":
            sleep_by_day[d]["deep"] += r["hours"]; sleep_by_day[d]["asleep"] += r["hours"]
        elif r["kind"] == "rem":
            sleep_by_day[d]["rem"] += r["hours"]; sleep_by_day[d]["asleep"] += r["hours"]
        elif r["kind"] == "awake":
            sleep_by_day[d]["awake"] += r["hours"] * 60
        else:
            sleep_by_day[d]["asleep"] += r["hours"]

    sleep_rows = [
        {"date": d, "duration_hours": round(v["asleep"], 2), "quality_score": None,
         "deep_hours": round(v["deep"], 2), "rem_hours": round(v["rem"], 2),
         "awake_min": round(v["awake"], 0)}
        for d, v in sleep_by_day.items()
    ]
    recovery_rows = [
        {"date": d,
         "hrv_ms": round(np.mean(v["hrv_list"]), 1) if "hrv_list" in v else None,
         "resting_hr": round(np.mean(v["rhr_list"]), 1) if "rhr_list" in v else None}
        for d, v in recovery_records.items()
    ]
    physio_rows = [
        {"date": d,
         "respiratory_rate": round(np.mean(v["resp_list"]), 1) if "resp_list" in v else None,
         "spo2": round(np.mean(v["spo2_list"]), 1) if "spo2_list" in v else None}
        for d, v in physio_records.items()
    ]

    return workout_records, sleep_rows, recovery_rows, body_records, physio_rows


# =============================================================================
# UI-KOMPONENTER[cite: 5]
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
# AI-COACH[cite: 5]
# =============================================================================
def build_context_summary():
    sessions, dist, dur = weekly_summary()
    score, notes = avg_recovery_score()
    rec = muscle_recovery()
    hrv = latest_value(load_table("recovery"), "hrv_ms")
    rhr = latest_value(load_table("recovery"), "resting_hr")
    sleep_h = latest_value(load_table("sleep"), "duration_hours")
    weight = latest_value(load_table("body"), "weight_kg")
    goals = load_table("goals")
    goal_txt = "Inget mål satt ännu."
    if not goals.empty:
        g = goals.iloc[-1]
        goal_txt = (f"Lopp: {g.get('race_name')}, datum: {g.get('race_date')}, "
                    f"distans: {g.get('race_distance_km')} km, måltid: {g.get('target_time')}, "
                    f"{g.get('sessions_per_week')} pass/vecka.")

    low_muscles = [m for m, (p, h) in rec.items() if p < 50]
    return f"""
Återhämtningsindex: {score}/100.
HRV senast: {hrv}. Vilopuls senast: {rhr}. Sömn senaste natten: {sleep_h} h.
Veckans träning: {sessions} pass, {dist} km, {dur} min totalt.
Kroppsvikt senast: {weight} kg.
Muskler med låg återhämtning (<50%): {', '.join(low_muscles) if low_muscles else 'inga'}.
Mål: {goal_txt}
""".strip()


def try_parse_strength_log(msg: str):
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

    return {
        "id": f"chat_{uuid.uuid4().hex[:10]}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "muscle_group": muscle_found or "Övrigt",
        "exercise": exercise_name,
        "equipment": "",
        "sets": int(sets_reps.group(1)) if sets_reps else None,
        "reps": int(sets_reps.group(2)) if sets_reps else None,
        "weight_kg": float(weight_match.group(1).replace(",", ".")) if weight_match else None,
        "rpe": None,
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
        sleep_h = latest_value(load_table("sleep"), "duration_hours")
        if sleep_h is None:
            return "Jag har ingen sömndata ännu – kontrollera att Health Auto Export synkar mot webhooken."
        if sleep_h < 6.5:
            return (f"Du sov {sleep_h:.1f} h senaste natten, vilket är lite lågt. "
                     "Prioritera 7–9 h de kommande nätterna och håll intensiteten nere idag.")
        return f"Du sov {sleep_h:.1f} h senaste natten – helt okej nivå för prestation."

    if any(k in m for k in ["schema", "vecka", "plan"]):
        return ("Kolla fliken 'Mål & Schema' där jag genererar ett dynamiskt veckoschema baserat på ditt lopp, "
                "sömn och återhämtning.")

    if any(k in m for k in ["vikt", "väger"]):
        w = latest_value(load_table("body"), "weight_kg")
        return f"Din senast loggade vikt är {w} kg." if w else "Ingen viktdata synkad ännu."

    if any(k in m for k in ["hrv"]):
        h = latest_value(load_table("recovery"), "hrv_ms")
        return f"Din senaste HRV är {h} ms. {notes[0] if notes else ''}" if h else "Ingen HRV-data synkad ännu."

    return (f"Den här veckan har du kört {sessions} pass ({dist} km, {dur} min totalt) "
            f"och ditt återhämtningsindex är {score}/100. Fråga mig gärna om sömn, HRV, "
            "schema eller säg 'lägg till [övning] [muskelgrupp] 3x10 40kg' för att logga styrka.")


def get_ai_response(user_msg: str) -> str:
    context = build_context_summary()

    parsed = try_parse_strength_log(user_msg)
    if parsed:
        db_insert("strength", parsed)
        weight_txt = f"@ {parsed['weight_kg']} kg" if parsed['weight_kg'] else ""
        return (f"✅ Loggat: **{parsed['exercise']}** ({parsed['muscle_group']}) – "
                f"{parsed['sets'] or '?'}x{parsed['reps'] or '?'} {weight_txt}. "
                "Sparat permanent i databasen och muskelåterhämtningen är uppdaterad!")

    api_key = st.session_state.get("openai_key", "")
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
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_msg}],
                max_tokens=400,
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"(Kunde inte nå OpenAI: {e})\n\n" + rule_based_reply(user_msg, context)

    return rule_based_reply(user_msg, context)


# =============================================================================
# SCHEMA-GENERERING[cite: 5]
# =============================================================================
def generate_schedule(goal_row):
    score, _ = avg_recovery_score()
    sessions_per_week = int(goal_row.get("sessions_per_week", 4) or 4)
    race_date = goal_row.get("race_date")

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
# SESSION STATE[cite: 5]
# =============================================================================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "assistant", "content":
         "Hej! Jag är din AI-tränarcoach 💪. Din Apple Hälsa-data synkas nu automatiskt i "
         "bakgrunden. Fråga mig om återhämtning, sömn, schema – eller säg t.ex. "
         "*'lägg till bänkpress bröst 3x8 70kg'* för att logga ett styrkepass direkt här."}
    ]
if "selected_workout" not in st.session_state:
    st.session_state.selected_workout = None
if "openai_key" not in st.session_state:
    st.session_state.openai_key = ""


# =============================================================================
# HEADER + SIDOPANEL[cite: 5]
# =============================================================================
st.markdown('<div class="app-title">🏃‍♂️ Träning & Hälsa</div>', unsafe_allow_html=True)
st.markdown('<div class="app-sub">Live från molnet – drivs av din Apple Hälsa-data</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Inställningar")
    if supabase is not None:
        st.markdown('<span class="conn-ok">🟢 Ansluten till Supabase</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="conn-bad">🔴 Ingen databaskoppling</span>', unsafe_allow_html=True)
        st.caption("Lägg in SUPABASE_URL och SUPABASE_KEY i App settings -> Secrets.")
        if "_last_db_error" in st.session_state:
            st.caption(f"Fel: {st.session_state['_last_db_error']}")

    st.session_state.openai_key = st.text_input(
        "OpenAI API-nyckel (valfritt, för smartare AI-chatt)",
        value=st.session_state.openai_key, type="password",
        help="Utan nyckel används en inbyggd regelbaserad coach istället."
    )

    if AUTOREFRESH_OK:
        auto_on = st.toggle("Auto-uppdatera var 2:a minut", value=False)
        if auto_on:
            st_autorefresh(interval=120_000, key="auto_refresh_health")
    if st.button("🔄 Uppdatera data nu"):
        refresh_data()
        st.rerun()

tabs = st.tabs(["🏠 Hem", "📥 Historik", "🗂️ Arkiv", "🎯 Mål & Schema", "💪 Styrka"])


# =============================================================================
# TAB 1 – HEM[cite: 5]
# =============================================================================
with tabs[0]:
    score, notes = avg_recovery_score()
    sessions, dist, dur = weekly_summary()
    hrv = latest_value(load_table("recovery"), "hrv_ms")
    rhr = latest_value(load_table("recovery"), "resting_hr")
    sleep_h = latest_value(load_table("sleep"), "duration_hours")

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
# TAB 2 – HISTORIK[cite: 5]
# =============================================================================
with tabs[1]:
    st.markdown('<div class="section-title">📥 Importera gammal historik</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="glass-card">
    Din nya träning, sömn, HRV och vikt synkas <b>automatiskt</b> i bakgrunden via
    Health Auto Export – du behöver inte göra något mer här för framtida data.<br><br>
    Använd fliken nedan bara <b>en gång</b> om du vill fylla på med gammal historik
    som ligger längre bak i tiden än du börjat auto-synka.
    </div>
    """, unsafe_allow_html=True)

    xml_file = st.file_uploader("Ladda upp gammal export.xml från Apple Hälsa", type=["xml"])
    if xml_file is not None:
        with st.spinner("Läser in och sparar historik i molnet..."):
            try:
                w_rows, s_rows, r_rows, b_rows, p_rows = parse_apple_health_xml(xml_file)
                added = 0
                if w_rows:
                    added += db_upsert("workouts", w_rows, "id")
                if s_rows:
                    added += db_upsert("sleep", s_rows, "date")
                if r_rows:
                    added += db_upsert("recovery", r_rows, "date")
                if b_rows:
                    added += db_upsert("body", b_rows, "date")
                if p_rows:
                    added += db_upsert("physio", p_rows, "date")
                st.success(f"Klart! {added} rader sparades permanent i din databas.")
            except Exception as e:
                st.error(f"Kunde inte tolka filen: {e}")

    st.markdown('<div class="section-title">📄 Generisk CSV-import</div>', unsafe_allow_html=True)
    target = st.selectbox("Vilken datatyp vill du importera?",
                           ["workouts", "sleep", "recovery", "body", "physio", "strength"],
                           format_func=lambda x: {
                               "workouts": "Träningspass", "sleep": "Sömn",
                               "recovery": "Återhämtning (HRV/vilopuls)",
                               "body": "Kroppsmått", "physio": "Fysiologi (andning/syre)",
                               "strength": "Styrkelogg"
                           }[x])
    st.code(", ".join(SCHEMAS[target]), language="text")
    csv_file = st.file_uploader(f"Ladda upp CSV för {target}", type=["csv"], key=f"csv_{target}")
    if csv_file is not None:
        try:
            df_new = pd.read_csv(csv_file)
            for col in SCHEMAS[target]:
                if col not in df_new.columns:
                    df_new[col] = np.nan
            if "id" in SCHEMAS[target]:
                df_new["id"] = df_new["id"].apply(
                    lambda x: x if pd.notna(x) and str(x).strip() else f"csv_{uuid.uuid4().hex[:10]}")
            conflict_col = "id" if "id" in SCHEMAS[target] else "date"
            rows = df_new[SCHEMAS[target]].to_dict(orient="records")
            added = db_upsert(target, rows, conflict_col)
            st.success(f"{added} rader sparades permanent i {target}.")
        except Exception as e:
            st.error(f"Fel vid import: {e}")

    st.markdown('<div class="section-title">🗺️ Koppla GPS-rutt manuellt (GPX)</div>', unsafe_allow_html=True)
    st.caption("Vanligtvis kommer rutten automatiskt med via webhooken. Detta är bara ett manuellt komplement.")
    w_df_now = load_table("workouts")
    if not w_df_now.empty:
        options = w_df_now.apply(lambda r: f"{r['date']} – {r['type']} ({r['id']})", axis=1).tolist()
        choice = st.selectbox("Välj träningspass", options) if options else None
        gpx_file = st.file_uploader("Ladda upp .gpx-fil", type=["gpx"])
        if gpx_file is not None and choice and GPXPY_OK:
            wid = choice.split("(")[-1].replace(")", "")
            try:
                gpx = gpxpy.parse(gpx_file)
                points = [{"lat": p.latitude, "lon": p.longitude}
                          for track in gpx.tracks for seg in track.segments for p in seg.points]
                if points:
                    db_update_field("workouts", "id", wid, "route", points)
                    st.success("Rutt sparad permanent i databasen! Se den i Arkiv-fliken.")
                else:
                    st.warning("Hittade inga punkter i GPX-filen.")
            except Exception as e:
                st.error(f"Kunde inte läsa GPX-filen: {e}")
        elif gpx_file is not None and not GPXPY_OK:
            st.warning("Installera paketet 'gpxpy' (finns i requirements.txt) för GPX-stöd.")
    else:
        st.info("Inga träningspass i databasen ännu.")


# =============================================================================
# TAB 3 – ARKIV[cite: 5]
# =============================================================================
with tabs[2]:
    st.markdown('<div class="section-title">🗂️ Träningsarkiv</div>', unsafe_allow_html=True)
    w = load_table("workouts").copy()

    if w.empty:
        st.info("Inga träningspass i arkivet ännu. Vänta på automatisk synk eller importera historik.")
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

                route = row.get("route")
                if isinstance(route, list) and len(route) > 0:
                    if FOLIUM_OK:
                        try:
                            points = [(p.get("lat"), p.get("lon")) for p in route
                                      if p.get("lat") is not None and p.get("lon") is not None]
                            if points:
                                m = folium.Map(location=points[len(points)//2], zoom_start=14,
                                                tiles="CartoDB dark_matter")
                                folium.PolyLine(points, color="#FC5200", weight=5).add_to(m)
                                folium.Marker(points[0], tooltip="Start",
                                              icon=folium.Icon(color="green")).add_to(m)
                                folium.Marker(points[-1], tooltip="Mål",
                                              icon=folium.Icon(color="red")).add_to(m)
                                st_folium(m, height=340, width=None)
                            else:
                                st.info("Ruttdatan innehöll inga giltiga punkter.")
                        except Exception as e:
                            st.warning(f"Kunde inte rendera kartan: {e}")
                    else:
                        st.warning("Installera 'folium' och 'streamlit-folium' för kartvisning.")
                else:
                    st.caption("📍 Ingen GPS-rutt kopplad till detta pass ännu.")

                if st.button("Stäng detaljer"):
                    st.session_state.selected_workout = None
                    st.rerun()


# =============================================================================
# TAB 4 – MÅL & SCHEMA[cite: 5]
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
            db_insert("goals", {
                "id": str(uuid.uuid4().int % 2_000_000_000),
                "race_name": race_name, "race_date": str(race_date),
                "race_distance_km": race_distance, "target_time": target_time,
                "sessions_per_week": sessions_per_week,
            })
            st.success("Mål sparat permanent i databasen! Ditt schema uppdateras nedan.")

    goals = load_table("goals")
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
                   "eftersom det läses live från databasen varje gång du öppnar appen.")
    else:
        st.info("Sätt ett mål ovan så genererar AI-coachen ett schema åt dig.")


# =============================================================================
# TAB 5 – STYRKA[cite: 5]
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
            db_insert("strength", {
                "id": f"manual_{uuid.uuid4().hex[:10]}", "date": datetime.now().strftime("%Y-%m-%d"),
                "muscle_group": muscle, "exercise": final_exercise, "equipment": "",
                "sets": sets, "reps": reps, "weight_kg": weight, "rpe": rpe, "notes": notes,
            })
            st.success(f"Loggat {final_exercise} – {sets}x{reps} @ {weight} kg! Sparat permanent i molnet.")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">📖 Styrkehistorik</div>', unsafe_allow_html=True)
    s = load_table("strength").copy()
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
