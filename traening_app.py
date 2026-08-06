import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client
import folium
from streamlit_folium import st_folium
import openai

st.set_page_config(
    page_title="Träning & Hälsa Pro",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- APPLE HÄLSA & STRAVA DESIGN (CSS) ---
st.markdown("""
    <style>
    .main { background-color: #000000; color: #ffffff; }
    h1, h2, h3 { color: #ffffff !important; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    
    .stTabs [data-baseweb="tab-list"] { gap: 4px; background-color: #121212; padding: 10px; border-radius: 12px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1c1c1e;
        color: #8e8e93;
        border-radius: 8px;
        padding: 8px 12px;
        font-weight: 600;
        font-size: 13px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #fc4c02 !important;
        color: white !important;
    }
    
    .health-card {
        background-color: #1c1c1e;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 15px;
        border: 1px solid #2c2c2e;
    }
    .health-title {
        color: #ff453a;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .health-value {
        font-size: 32px;
        font-weight: 700;
        color: #ffffff;
    }
    .strava-stat-row {
        display: flex;
        justify-content: space-between;
        padding: 12px 0px;
        border-bottom: 1px solid #2c2c2e;
        font-size: 16px;
    }
    .strava-stat-val {
        font-weight: bold;
        color: #ffffff;
    }
    .muscle-card {
        background-color: #1c1c1e;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #2c2c2e;
        text-align: center;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- LÖSENORDSSKYDD ---
def check_password():
    if "APP_PASSWORD" in st.secrets:
        def password_entered():
            if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
                del st.session_state["password"]
            else:
                st.session_state["password_correct"] = False

        if "password_correct" not in st.session_state:
            st.text_input("🔑 Ange lösenord för din träningsapp:", type="password", on_change=password_entered, key="password")
            return False
        elif not st.session_state["password_correct"]:
            st.text_input("🔑 Ange lösenord för din träningsapp:", type="password", on_change=password_entered, key="password")
            st.error("Felaktigt lösenord")
            return False
    return True

if not check_password():
    st.stop()

# --- ANSLUTNING TILL SUPABASE ---
@st.cache_resource
def init_connection():
    url = str(st.secrets["SUPABASE_URL"]).strip().encode("ascii", "ignore").decode("ascii")
    key = str(st.secrets["SUPABASE_KEY"]).strip().encode("ascii", "ignore").decode("ascii")
    return create_client(url, key)

supabase = init_connection()

# --- HÄMTA DATA ---
@st.cache_data(ttl=30)
def load_data():
    workouts_res = supabase.table("workouts").select("*").execute()
    workouts_df = pd.DataFrame(workouts_res.data) if workouts_res.data else pd.DataFrame()
    
    sleep_res = supabase.table("sleep").select("*").execute()
    sleep_df = pd.DataFrame(sleep_res.data) if sleep_res.data else pd.DataFrame()
    
    recovery_res = supabase.table("recovery").select("*").execute()
    recovery_df = pd.DataFrame(recovery_res.data) if recovery_res.data else pd.DataFrame()
    
    body_res = supabase.table("body").select("*").execute()
    body_df = pd.DataFrame(body_res.data) if body_res.data else pd.DataFrame()
    
    return workouts_df, sleep_df, recovery_df, body_df

workouts_df, sleep_df, recovery_df, body_df = load_data()

if not workouts_df.empty and "date" in workouts_df.columns:
    workouts_df["date"] = pd.to_datetime(workouts_df["date"])

if not sleep_df.empty and "date" in sleep_df.columns:
    sleep_df["date"] = pd.to_datetime(sleep_df["date"])

# --- SESSION STATE FÖR MÅL ---
if "goals" not in st.session_state:
    st.session_state.goals = [
        {"category": "Löpning", "title": "Springa milen under 45 min", "progress": 80, "target": "45 min"},
        {"category": "Styrka", "title": "Bänkpress 100 kg", "progress": 70, "target": "100 kg"}
    ]

# --- NAVIGERING (STATISTIK ALLRA LÄNGST TILL HÖGER) ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "❤️ Översikt (Hälsa)", 
    "🏃‍♂️ Löpning & Pass", 
    "💪 Styrketräning", 
    "🛌 Sömnanalys", 
    "👤 Du & AI-Coach",
    "📈 Statistik"
])

# ==========================================
# FLIK 1: ÖVERSIKT (APPLE HÄLSA-STIL)
# ==========================================
with tab1:
    st.title("Översikt")
    st.caption("Fastnålat i Apple Hälsa-stil")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
            <div class="health-card">
                <div class="health-title">🔥 Steg (idag)</div>
                <div class="health-value">11 110 <span style="font-size: 16px; color: #8e8e93;">steg</span></div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
            <div class="health-card">
                <div class="health-title">🛌 Sömnpoäng</div>
                <div class="health-value">72 <span style="font-size: 18px; color: #30d158;">OK</span></div>
            </div>
        """, unsafe_allow_html=True)
        
    with c2:
        st.markdown("""
            <div class="health-card">
                <div class="health-title">🧍 Ståtimmar</div>
                <div class="health-value">14 <span style="font-size: 16px; color: #8e8e93;">timmar</span></div>
                <p style="color: #8e8e93; font-size: 13px; margin-top: 10px;">Under de senaste 9 veckorna har du stått upp mer i genomsnitt.</p>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📊 Veckans Stegutveckling")
    steps_data = pd.DataFrame({
        "Dag": ["Mån", "Tis", "Ons", "Tors", "Fre", "Lör", "Sön"],
        "Steg": [8500, 11200, 9400, 12800, 6500, 9100, 11110]
    })
    st.bar_chart(steps_data.set_index("Dag"), color="#ff453a")

# ==========================================
# FLIK 2: LÖPNING & PASS (STRAVA-STIL)
# ==========================================
with tab2:
    st.title("🏃‍♂️ Löpning & Aktivitet")
    
    running_df = workouts_df[workouts_df["type"].str.contains("Löp|Utomhus Kör", case=False, na=False)] if not workouts_df.empty else pd.DataFrame()
    
    if not running_df.empty:
        running_df = running_df.sort_values(by="date", ascending=False)
        run_options = running_df.apply(lambda row: f"{row['date'].strftime('%Y-%m-%d %H:%M')} – {row.get('distance_km', 10.13):.2f} km", axis=1).tolist()
        
        selected_run_str = st.selectbox("📂 Välj löppass att analysera:", run_options)
        selected_idx = run_options.index(selected_run_str)
        selected_run = running_df.iloc[selected_idx]
        
        st.markdown(f"### 🌙 Passdetaljer – {selected_run['date'].strftime('%Y-%m-%d')}")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Distans", f"{selected_run.get('distance_km', 10.13):.2f} km")
        col2.metric("Tid i rörelse", f"{selected_run.get('duration_min', 47.8):.0f} min")
        col3.metric("Kalorier", f"{selected_run.get('calories', 703)} kcal")
        col4.metric("Snittpuls", f"{selected_run.get('avg_hr', 164)} bpm")
        
        st.markdown("---")
        st.subheader("🗺️ GPS-karta (Ljungby)")
        m = folium.Map(location=[56.8333, 13.9333], zoom_start=13, tiles="CartoDB dark_matter")
        route_coords = [
            [56.8333, 13.9333], [56.8360, 13.9380], [56.8400, 13.9450],
            [56.8420, 13.9350], [56.8380, 13.9250], [56.8300, 13.9200],
            [56.8250, 13.9280], [56.8300, 13.9333]
        ]
        folium.PolyLine(route_coords, color="#fc4c02", weight=4, opacity=0.9).add_to(m)
        st_folium(m, height=350, use_container_width=True)
    else:
        st.info("Inga löppass hittades.")

# ==========================================
# FLIK 3: STYRKETRÄNING & MUSKELSTATUS
# ==========================================
with tab3:
    st.title("💪 Styrketräning & Muskelstatus")
    st.markdown("Logga pass med standardmallar eller välj tidigare pass för att se detaljer och muskelåterhämtning.")
    
    # Muskelstatus (Heatmap)
    st.subheader("🔥 Muskelåterhämtning")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.markdown('<div class="muscle-card"><span style="color: #ff453a; font-weight:bold;">🔴 Ben / Glutes</span><br>Behöver vila</div>', unsafe_allow_html=True)
    m2.markdown('<div class="muscle-card"><span style="color: #ff453a; font-weight:bold;">🔴 Rygg / Ländrygg</span><br>Behöver vila</div>', unsafe_allow_html=True)
    m3.markdown('<div class="muscle-card"><span style="color: #30d158; font-weight:bold;">🟢 Bröst</span><br>Återhämtad</div>', unsafe_allow_html=True)
    m4.markdown('<div class="muscle-card"><span style="color: #30d158; font-weight:bold;">🟢 Axlar / Armar</span><br>Återhämtad</div>', unsafe_allow_html=True)
    m5.markdown('<div class="muscle-card"><span style="color: #ff453a; font-weight:bold;">🔴 Core</span><br>Trött</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Välj tidigare pass för att se detaljer
    strength_df = workouts_df[workouts_df["type"].str.contains("Styrka|Traditionell|Bröst|Rygg|Armar|Axlar|Ben", case=False, na=False)] if not workouts_df.empty else pd.DataFrame()
    
    if not strength_df.empty:
        st.subheader("📂 Välj tidigare styrkepass")
        strength_df = strength_df.sort_values(by="date", ascending=False)
        strength_options = strength_df.apply(lambda row: f"{row['date'].strftime('%Y-%m-%d %H:%M')} – {row.get('type', 'Styrka')} ({row.get('duration_min', 45):.0f} min)", axis=1).tolist()
        
        selected_strength_str = st.selectbox("Välj pass att granska:", strength_options)
        selected_s_idx = strength_options.index(selected_strength_str)
        selected_pass = strength_df.iloc[selected_s_idx]
        
        st.markdown(f"### Passdetaljer: {selected_pass.get('type', 'Styrka')}")
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Datum", selected_pass['date'].strftime('%Y-%m-%d'))
        sc2.metric("Tid", f"{selected_pass.get('duration_min', 0):.0f} min")
        sc3.metric("Kalorier", f"{selected_pass.get('calories', 0)} kcal")
        sc4.metric("Typ", selected_pass.get('type', 'Styrka'))
    
    st.markdown("---")
    st.subheader("⚙️ Logga nytt pass / Standardmallar")
    
    # Meny med standardmallar eller egen
    workout_template = st.selectbox(
        "Välj pass-typ (Standard eller Anpassad):",
        ["Bröst, axlar, triceps pass", "Rygg, biceps, axlar", "Armar", "Axlar", "Benpass", "Eget pass (Anpassat)"]
    )
    
    if workout_template == "Eget pass (Anpassat)":
        custom_type = st.text_input("Skriv egen typ av pass:")
        pass_type_to_save = custom_type if custom_type else "Anpassat pass"
    else:
        pass_type_to_save = workout_template
        
    selected_exercise = st.selectbox("Välj övning:", ["Marklyft (Deadlift)", "Bänkpress", "Knäböj (Squats)", "Chins / Pullups", "Militärpress", "Hantelpress", "Bicepscurl", "Triceps pushdown"])
    
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    with col_ex1:
        weight_input = st.number_input("Vikt (kg)", value=100.0, step=2.5)
    with col_ex2:
        reps_input = st.number_input("Repetitioner", value=5, step=1)
    with col_ex3:
        sets_input = st.number_input("Set", value=3, step=1)
        
    if st.button("Spara pass & övning"):
        st.success(f"Sparat! Pass: {pass_type_to_save} | Övning: {selected_exercise} ({sets_input} set x {reps_input} reps på {weight_input} kg).")

# ==========================================
# FLIK 4: SÖMNANALYS (APPLE HÄLSA-STIL)
# ==========================================
with tab4:
    st.title("🛌 Sömnanalys")
    st.markdown("Detaljerad översikt över din sömn, sömnstadier och tidigare dars sömn i Apple Hälsa-stil.")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown("""
            <div class="health-card">
                <div class="health-title">💤 SNITTID SOVANDE (31 juli – 6 aug)</div>
                <div class="health-value">6 tim 34 min</div>
                <p style="color: #8e8e93; font-size: 13px; margin-top: 5px;">Sömnpoäng i snitt: 72 / 100 (OK)</p>
            </div>
        """, unsafe_allow_html=True)
    with col_s2:
        st.markdown("""
            <div class="health-card">
                <div class="health-title">🌙 Senaste nattens sömn</div>
                <div class="health-value">4 tim 3 min</div>
                <p style="color: #ff453a; font-size: 13px; margin-top: 5px;">Avbrott upptäckta – rekommenderar vila.</p>
            </div>
        """, unsafe_allow_html=True)
        
    st.markdown("### 📊 Sömnstadier & Veckoöversikt")
    sleep_chart_data = pd.DataFrame({
        "Dag": ["Fre", "Lör", "Sön", "Mån", "Tis", "Ons", "Tors"],
        "Sömntid (timmar)": [7.5, 8.0, 7.2, 4.2, 3.8, 7.6, 6.5]
    })
    st.bar_chart(sleep_chart_data.set_index("Dag"), color="#0a84ff")

# ==========================================
# FLIK 5: DU & AI-COACH
# ==========================================
with tab5:
    st.title("👤 Du, Hälsa & AI-Coach")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("📌 Mina Mål")
        for goal in st.session_state.goals:
            st.write(f"**{goal['title']}** ({goal['category']}) – Mål: {goal['target']}")
            st.progress(goal["progress"] / 100)
            
    with col_b:
        st.subheader("🤖 Personlig AI-Coach")
        if "GROQ_API_KEY" in st.secrets:
            client_groq = openai.OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=st.secrets["GROQ_API_KEY"]
            )
            
            if "messages" not in st.session_state:
                st.session_state.messages = [{"role": "assistant", "content": "Hej! Hur kan jag hjälpa dig med din träning eller sömn idag?"}]
                
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    
            if prompt := st.chat_input("Skriv till din coach..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                    
                response = client_groq.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": "Du är en personlig tränings- och hälsocoach."}] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                )
                answer = response.choices[0].message.content
                st.session_state.messages.append({"role": "assistant", "content": answer})
                with st.chat_message("assistant"):
                    st.markdown(answer)
        else:
            st.info("Lägg till din GROQ_API_KEY under Secrets.")

# ==========================================
# FLIK 6: STATISTIK (ALLRA LÄNGST TILL HÖGER)
# ==========================================
with tab6:
    st.title("📈 Statistik")
    
    st.subheader("BÄSTA INSATSER")
    records = [
        ("400 m", "1:22"),
        ("½ mile", "3:04"),
        ("1 km", "3:51"),
        ("1 mile", "7:00"),
        ("2 miles", "14:11"),
        ("5 km", "22:30"),
        ("10 km", "45:24"),
        ("15 km", "1:12:06"),
        ("10 miles", "1:17:27"),
        ("20 km", "1:36:19"),
        ("Halvmaraton", "1:41:43")
    ]
    for dist, time_val in records:
        st.markdown(f"""
            <div class="strava-stat-row">
                <span>{dist}</span>
                <span class="strava-stat-val">{time_val}</span>
            </div>
        """, unsafe_allow_html=True)
        
    st.markdown("---")
    st.subheader("AKTIVITET (SNITT)")
    st.markdown("""
        <div class="strava-stat-row">
            <span>Genomsnittligt antal löprundor per vecka</span>
            <span class="strava-stat-val">1</span>
        </div>
        <div class="strava-stat-row">
            <span>Genomsnittlig tid/vecka</span>
            <span class="strava-stat-val">54 min 7 sek</span>
        </div>
        <div class="strava-stat-row">
            <span>Genomsnittligt avstånd/vecka</span>
            <span class="strava-stat-val">10 km</span>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("I ÅR")
    st.markdown("""
        <div class="strava-stat-row">
            <span>Löprundor</span>
            <span class="strava-stat-val">41</span>
        </div>
        <div class="strava-stat-row">
            <span>Tid</span>
            <span class="strava-stat-val">36 tim 24 min</span>
        </div>
        <div class="strava-stat-row">
            <span>Distans</span>
            <span class="strava-stat-val">396 km</span>
        </div>
        <div class="strava-stat-row">
            <span>Höjdökning</span>
            <span class="strava-stat-val">2 897 m</span>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("NÅGONSIN")
    st.markdown("""
        <div class="strava-stat-row">
            <span>Löprundor</span>
            <span class="strava-stat-val">91</span>
        </div>
        <div class="strava-stat-row">
            <span>Distans</span>
            <span class="strava-stat-val">864 km</span>
        </div>
    """, unsafe_allow_html=True)
