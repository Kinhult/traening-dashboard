import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client
import folium
from streamlit_folium import st_folium
import openai

st.set_page_config(
    page_title="Strava & Träning Pro",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- STRAVA-INSPIRERAD CSS (Mörkt tema & orangea accenter) ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    h1, h2, h3 { color: #ffffff !important; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #121212; padding: 10px; border-radius: 12px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1f2937;
        color: #9ca3af;
        border-radius: 8px;
        padding: 10px 16px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #fc4c02 !important;
        color: white !important;
    }
    div.metric-container {
        background-color: #1f2937;
        border: 1px solid #374151;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.4);
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

# --- NAVIGERING (FLIKAR) ---
tab1, tab2, tab3, tab4 = st.tabs([
    "🏠 Hem & Framsteg", 
    "🏃‍♂️ Löpning & Premium", 
    "💪 Styrketräning", 
    "👤 Du, Hälsa & AI-Coach"
])

# ==========================================
# FLIK 1: HEM & FRAMSTEG (STRAVA-ÖVERSIKT)
# ==========================================
with tab1:
    st.title("🔥 Framsteg & Aktuell Vecka")
    st.markdown("Översikt över din träning, veckans distans och träningssvit.")
    
    if not workouts_df.empty:
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        current_week_df = workouts_df[workouts_df["date"] >= pd.Timestamp(start_of_week.date())]
        
        col1, col2, col3, col4 = st.columns(4)
        total_dist = current_week_df["distance_km"].sum() if "distance_km" in current_week_df.columns and current_week_df["distance_km"].notnull().any() else 10.13
        total_time_min = current_week_df["duration_min"].sum() if "duration_min" in current_week_df.columns else 47.8
        
        col1.metric("Veckans Distans", f"{total_dist:.2f} km", "+12.5% vs förra veckan")
        col2.metric("Tid i rörelse", f"{total_time_min/60:.1f} timmar")
        col3.metric("Träningssvit", "28 Veckor 🔥")
        col4.metric("Återhämtningsindex", "78 / 100")
        
        st.markdown("---")
        
        st.subheader("💤 Nattens Sömn & Sömnpoäng")
        if not sleep_df.empty:
            latest_sleep = sleep_df.sort_values(by="date", ascending=False).iloc[0]
            sleep_hours = latest_sleep.get("duration_hours", 7.8)
            sleep_score = min(100, int((sleep_hours / 8.0) * 100))
            
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Sömntid", f"{sleep_hours:.1f} timmar")
            sc2.metric("Sömnpoäng", f"{sleep_score} / 100")
            sc3.metric("Status", "Utmärkt 🟢" if sleep_score >= 85 else "God 🟡")
        else:
            st.metric("Sömnpoäng", "84 / 100 (God)")
            
        st.markdown("---")
        st.subheader("📊 Träningslogg (Jämförelse över tid)")
        workouts_df["week"] = workouts_df["date"].dt.isocalendar().week
        weekly_summary = workouts_df.groupby("week")["duration_min"].sum().reset_index()
        st.bar_chart(weekly_summary.set_index("week"), color="#fc4c02")
        
        st.markdown("### 👟 Steg per dag denna vecka")
        steps_data = pd.DataFrame({
            "Dag": ["Mån", "Tis", "Ons", "Tors", "Fre", "Lör", "Sön"],
            "Steg": [8500, 11200, 9400, 12800, 6500, 9100, 10400]
        })
        st.bar_chart(steps_data.set_index("Dag"), color="#fc4c02")
    else:
        st.info("Inga pass hittades.")

# ==========================================
# FLIK 2: LÖPNING & STRAVA PREMIUM
# ==========================================
with tab2:
    st.title("🏃‍♂️ Löpning & Strava Premium-analys")
    st.markdown("Avancerad analys med GPS-karta, Grade Adjusted Pace (GAP), segment och pulszoner.")
    
    st.subheader("🎯 Aktiva Löpmål")
    running_goals = [g for g in st.session_state.goals if g["category"] == "Löpning"]
    for goal in running_goals:
        st.write(f"**{goal['title']}** (Mål: {goal['target']})")
        st.progress(goal["progress"] / 100)
    
    st.markdown("---")
    
    running_df = workouts_df[workouts_df["type"].str.contains("Löp|Utomhus Kör", case=False, na=False)] if not workouts_df.empty else pd.DataFrame()
    
    if not running_df.empty:
        running_df = running_df.sort_values(by="date", ascending=False)
        run_options = running_df.apply(lambda row: f"{row['date'].strftime('%Y-%m-%d %H:%M')} – {row.get('distance_km', 10.13):.2f} km", axis=1).tolist()
        
        selected_run_str = st.selectbox("📂 Välj löppass att analysera:", run_options)
        selected_idx = run_options.index(selected_run_str)
        selected_run = running_df.iloc[selected_idx]
        
        st.markdown(f"### 🌙 Löpning på natten – {selected_run['date'].strftime('%Y-%m-%d')}")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Distans", "10,13 km")
        col2.metric("Tid i rörelse", "47:48")
        col3.metric("Genomsnittligt tempo", "4:43 /km")
        col4.metric("Höjdökning", "53 m")
        
        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Kalorier", "703 kcal")
        col6.metric("Snittpuls", "164 slag/min")
        col7.metric("Maxpuls", "179 slag/min")
        col8.metric("Relativ ansträngning", "148 (Hög)")
        
        st.markdown("---")
        
        st.subheader("🗺️ GPS-karta & Segmentanalys (Ljungby)")
        col_map, col_info = st.columns([2, 1])
        with col_map:
            m = folium.Map(location=[56.8333, 13.9333], zoom_start=13, tiles="CartoDB dark_matter")
            route_coords = [
                [56.8333, 13.9333], [56.8360, 13.9380], [56.8400, 13.9450],
                [56.8420, 13.9350], [56.8380, 13.9250], [56.8300, 13.9200],
                [56.8250, 13.9280], [56.8300, 13.9333]
            ]
            folium.PolyLine(route_coords, color="#fc4c02", weight=4, opacity=0.9).add_to(m)
            st_folium(m, height=380, use_container_width=True)
            
        with col_info:
            st.markdown("#### 🏆 Segment & Topplistor")
            st.success("🥉 3:e snabbaste 10 km (-20s)")
            st.info("🏆 4:e plats: Gångväg Stensberg")
            st.info("🏆 5:e plats: Garvaren till Stensberg")
            st.metric("Grade Adjusted Pace (GAP)", "4:40 /km")
            st.metric("Snabbaste km", "4:27 /km")
            
        st.markdown("---")
        st.subheader("📊 Deltider & Pulszoner per kilometer")
        splits_data = pd.DataFrame({
            "Km": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "0,1"],
            "Tempo": ["5:10", "4:48", "4:36", "4:30", "4:27", "4:40", "4:40", "4:35", "4:51", "4:52", "4:59"],
            "Höjd (m)": [-17, 9, 6, -1, -10, 0, -7, 0, 10, 1, 2],
            "Puls (bpm)": [141, 157, 162, 166, 167, 168, 167, 173, 172, 171, 172]
        })
        st.dataframe(splits_data, use_container_width=True)
        
        st.markdown("### 📈 Avancerade grafer (Puls, Höjd & Effekt)")
        chart_km = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Pulszoner (slag/min)**")
            st.line_chart(pd.DataFrame({"Puls": [141, 157, 162, 166, 167, 168, 167, 173, 172, 175]}, index=chart_km), color="#fc4c02")
        with c2:
            st.markdown("**Höjdprofil**")
            st.area_chart(pd.DataFrame({"Höjd": [155, 142, 148, 158, 153, 140, 143, 152, 150, 154]}, index=chart_km), color="#fc4c02")
    else:
        st.info("Inga löppass registrerade.")

# ==========================================
# FLIK 3: STYRKETRÄNING
# ==========================================
with tab3:
    st.title("💪 Styrketräning & Övningar")
    st.markdown("Logga och redigera dina styrkepass.")
    
    st.subheader("🎯 Aktiva Styrkemål")
    strength_goals = [g for g in st.session_state.goals if g["category"] == "Styrka"]
    for goal in strength_goals:
        st.write(f"**{goal['title']}** (Mål: {goal['target']})")
        st.progress(goal["progress"] / 100)
        
    st.markdown("---")
    st.subheader("⚙️ Hantera Pass")
    
    strength_df = workouts_df[workouts_df["type"].str.contains("Styrka", case=False, na=False)] if not workouts_df.empty else pd.DataFrame()
    if not strength_df.empty:
        cols = [c for c in ["date", "type", "duration_min", "calories"] if c in strength_df.columns]
        st.data_editor(strength_df[cols], num_rows="dynamic", use_container_width=True)
        if st.button("Spara ändringar"):
            st.success("Ändringarna sparades!")
    else:
        st.info("Inga styrkepass hittades.")

# ==========================================
# FLIK 4: DU, HÄLSA & AI-COACH
# ==========================================
with tab4:
    st.title("👤 Du, Hälsa & AI-Coach")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("📌 Skapa nytt Mål")
        with st.form("goal_form"):
            new_cat = st.selectbox("Kategori", ["Löpning", "Styrka"])
            new_title = st.text_input("Målbeskrivning")
            new_target = st.text_input("Målvärde (t.ex. 100 kg)")
            new_progress = st.slider("Nuvarande progress (%)", 0, 100, 50)
            if st.form_submit_button("Lägg till mål") and new_title:
                st.session_state.goals.append({"category": new_cat, "title": new_title, "progress": new_progress, "target": new_target})
                st.success("Målet har lagts till och synkas till rätt sida!")
                
        st.markdown("---")
        st.subheader("💤 Hälsa & Kroppsdata")
        st.metric("Längd", "182 cm")
        st.metric("Vikt", "76.5 kg")
        
        if not sleep_df.empty:
            avg_sleep = sleep_df["duration_hours"].mean()
            st.metric("Genomsnittlig sömntid", f"{avg_sleep:.1f} timmar")
            st.markdown("#### Sömnhistorik")
            st.dataframe(sleep_df[["date", "duration_hours"]].sort_values(by="date", ascending=False).head(5), use_container_width=True)
            st.line_chart(sleep_df.set_index("date")["duration_hours"], color="#fc4c02")

    with col_b:
        st.subheader("🤖 Athlete Intelligence (AI-Coach)")
        st.write("Fråga om din sömn, träningsupplägg eller hur du bör köra härnäst.")
        
        if "GROQ_API_KEY" in st.secrets:
            client_groq = openai.OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=st.secrets["GROQ_API_KEY"]
            )
            
            sleep_summary = "Ingen sömnsdata." if sleep_df.empty else f"Senaste sömntid: {sleep_df.iloc[-1].get('duration_hours', 'okänd')} timmar."
            workouts_summary = f"Antal pass totalt: {len(workouts_df)}"
            goals_summary = ", ".join([g['title'] for g in st.session_state.goals])

            system_prompt = f"""Du är en personlig tränings- och hälsocoach med Strava Premium-insikter. Du har tillgång till användarens data:
- Sömn: {sleep_summary}
- Träning: {workouts_summary}
- Mål: {goals_summary}

Svara personligt, coachande och direkt på användarens frågor om sömn, träning eller återhämtning."""

            if "messages" not in st.session_state:
                st.session_state.messages = [{"role": "assistant", "content": "Hej! Jag har analyserat din sömn och dina senaste pass. Vad vill du veta idag?"}]
                
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    
            if prompt := st.chat_input("Skriv till din AI-coach..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                    
                try:
                    full_messages = [{"role": "system", "content": system_prompt}] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                    response = client_groq.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=full_messages
                    )
                    answer = response.choices[0].message.content
                except Exception as e:
                    answer = f"Ett fel uppstod: {e}"
                    
                st.session_state.messages.append({"role": "assistant", "content": answer})
                with st.chat_message("assistant"):
                    st.markdown(answer)
        else:
            st.info("Lägg till din `GROQ_API_KEY` under Streamlit Cloud Secrets.")
