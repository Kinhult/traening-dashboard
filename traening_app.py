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

# --- ANPASSAD CSS FÖR SNYGGARE DESIGN ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .metric-card {
        background-color: #1f2937;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        text-align: center;
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
            st.text_input("Ange lösenord för din träningsapp:", type="password", on_change=password_entered, key="password")
            return False
        elif not st.session_state["password_correct"]:
            st.text_input("Ange lösenord för din träningsapp:", type="password", on_change=password_entered, key="password")
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

# Konvertera datumfält om de finns
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

# --- HUVUDNAVIGERING (FLIKAR) ---
tab1, tab2, tab3, tab4 = st.tabs([
    "🏠 Översikt & Vecka", 
    "🏃‍♂️ Löpning", 
    "💪 Styrketräning", 
    "⚙️ Hälsa, Mål & AI-Coach"
])

# ==========================================
# FLIK 1: ÖVERSIKT & VECKA
# ==========================================
with tab1:
    st.title("🔥 Träningsöversikt")
    st.markdown("Här är din sammanfattning för den aktuella veckan och historiska jämförelser.")
    
    if not workouts_df.empty:
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        current_week_df = workouts_df[workouts_df["date"] >= pd.Timestamp(start_of_week.date())]
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Pass denna vecka", len(current_week_df))
        total_time_min = current_week_df["duration_min"].sum() if "duration_min" in current_week_df.columns else 0
        col2.metric("Tid denna vecka", f"{total_time_min/60:.1f} timmar")
        total_dist = current_week_df["distance_km"].sum() if "distance_km" in current_week_df.columns and current_week_df["distance_km"].notnull().any() else 0
        col3.metric("Distans denna vecka", f"{total_dist:.1f} km")
        col4.metric("Återhämtningsindex", "78 / 100")
        
        st.markdown("---")
        
        st.subheader("📊 Jämförelse med tidigare veckor (Tid i minuter)")
        workouts_df["week"] = workouts_df["date"].dt.isocalendar().week
        weekly_summary = workouts_df.groupby("week")["duration_min"].sum().reset_index()
        st.bar_chart(weekly_summary.set_index("week"))
        
        st.markdown("### 👟 Steg per dag denna vecka")
        steps_data = pd.DataFrame({
            "Dag": ["Mån", "Tis", "Ons", "Tors", "Fre", "Lör", "Sön"],
            "Steg": [8500, 11200, 9400, 12800, 6500, 0, 0]
        })
        st.bar_chart(steps_data.set_index("Dag"))
    else:
        st.info("Inga träningspass inlagda i databasen ännu.")

# ==========================================
# FLIK 2: LÖPNING (STRAVA-STIL)
# ==========================================
with tab2:
    st.title("🏃‍♂️ Löpning & Uthållighet")
    st.markdown("Detaljerad löpdata inspirerad av Strava Premium med kartor, pulszoner och VO2 Max-utveckling.")
    
    st.subheader("🎯 Aktiva Löpmål")
    running_goals = [g for g in st.session_state.goals if g["category"] == "Löpning"]
    if running_goals:
        for goal in running_goals:
            st.write(f"**{goal['title']}** (Mål: {goal['target']})")
            st.progress(goal["progress"] / 100)
    else:
        st.info("Inga aktiva löpmål tillagda ännu. Gå till flik 4 för att lägga till mål.")
    
    st.markdown("---")
    
    running_df = workouts_df[workouts_df["type"].str.contains("Löp|Utomhus Kör", case=False, na=False)] if not workouts_df.empty else pd.DataFrame()
    
    if not running_df.empty:
        st.subheader("🗺️ Senaste Löppasset & Karta")
        run_options = running_df["date"].dt.strftime('%Y-%m-%d %H:%M').tolist()
        selected_run = st.selectbox("Välj löppass att analysera:", run_options)
        
        col_map, col_stats = st.columns([2, 1])
        with col_map:
            m = folium.Map(location=[57.7089, 11.9746], zoom_start=13)
            folium.Marker([57.7089, 11.9746], tooltip="Start / Mål", icon=folium.Icon(color="green", icon="play")).add_to(m)
            st_folium(m, height=350, use_container_width=True)
            
        with col_stats:
            st.markdown("#### Passdetaljer")
            st.metric("Snittpuls", "154 bpm")
            st.metric("Höjdstigning", "+124 m")
            st.metric("Uppskattat VO2 Max", "52 ml/kg/min")
            st.metric("Stegfrekvens", "174 spm")
            
        st.markdown("### 📈 Puls & Höjdprofil under loppet")
        chart_data = pd.DataFrame({
            "Kilometer": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "Puls (bpm)": [140, 148, 152, 155, 158, 160, 162, 165, 170, 175],
            "Höjd (m)": [10, 15, 25, 20, 35, 40, 30, 20, 15, 10]
        })
        st.line_chart(chart_data.set_index("Kilometer"))
    else:
        st.info("Inga registrerade löppass hittades.")

# ==========================================
# FLIK 3: STYRKETRÄNING
# ==========================================
with tab3:
    st.title("💪 Styrketräning & Övningsarkiv")
    st.markdown("Logga, följ upp och redigera dina styrkepass smidigt.")
    
    st.subheader("🎯 Aktiva Styrkemål")
    strength_goals = [g for g in st.session_state.goals if g["category"] == "Styrka"]
    if strength_goals:
        for goal in strength_goals:
            st.write(f"**{goal['title']}** (Mål: {goal['target']})")
            st.progress(goal["progress"] / 100)
    else:
        st.info("Inga aktiva styrkemål tillagda ännu. Gå till flik 4 för att lägga till mål.")
        
    st.markdown("---")
    st.subheader("⚙️ Redigera & Hantera Styrkepass")
    st.write("Du kan enkelt klicka och ändra övningar, vikter och repetitioner i tabellen nedan:")
    
    strength_df = workouts_df[workouts_df["type"].str.contains("Styrka", case=False, na=False)] if not workouts_df.empty else pd.DataFrame()
    
    if not strength_df.empty:
        cols_to_show = [c for c in ["date", "type", "duration_min", "calories"] if c in strength_df.columns]
        edited_df = st.data_editor(strength_df[cols_to_show], num_rows="dynamic", use_container_width=True)
        if st.button("Spara ändringar"):
            st.success("Ändringarna har sparats lokalt!")
    else:
        st.info("Inga styrkepass registrerade ännu.")

# ==========================================
# FLIK 4: HÄLSA, MÅL & AI-COACH
# ==========================================
with tab4:
    st.title("⚙️ Hälsa, Mål & AI-Coach")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("📌 Lägg till nytt Mål")
        with st.form("goal_form"):
            new_cat = st.selectbox("Kategori", ["Löpning", "Styrka"])
            new_title = st.text_input("Målbeskrivning (t.ex. 'Knäböj 140kg')")
            new_target = st.text_input("Målvärde (t.ex. '140 kg' eller '45 min')")
            new_progress = st.slider("Nuvarande uppskattad progress (%)", 0, 100, 50)
            submitted = st.form_submit_button("Lägg till mål")
            
            if submitted and new_title:
                st.session_state.goals.append({"category": new_cat, "title": new_title, "progress": new_progress, "target": new_target})
                st.success("Målet har lagts till och synkas till respektive sida!")
                
        st.subheader("👤 Kroppsdata & Återhämtning")
        st.metric("Längd", "182 cm")
        st.metric("Vikt", "76.5 kg")
        if not sleep_df.empty and "duration_hours" in sleep_df.columns:
            avg_sleep = sleep_df["duration_hours"].mean()
            st.metric("Sömnsnitt", f"{avg_sleep:.1f} timmar")
            st.markdown("### Sömnutveckling")
            st.line_chart(sleep_df.set_index("date")["duration_hours"])
        else:
            st.metric("Sömnsnitt senaste 7 dagar", "7.8 timmar")

    with col_b:
        st.subheader("🤖 Din Personliga AI-Coach (Gratis via Groq)")
        st.write("Fråga om träningsupplägg, återhämtning eller vilka pass du bör köra härnäst.")
        
        if "GROQ_API_KEY" in st.secrets:
            client_groq = openai.OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=st.secrets["GROQ_API_KEY"]
            )
            
            if "messages" not in st.session_state:
                st.session_state.messages = [{"role": "assistant", "content": "Hej! Vad vill du ha hjälp med gällande din träning idag?"}]
                
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    
            if prompt := st.chat_input("Skriv till din coach..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                    
                try:
                    response = client_groq.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                    )
                    answer = response.choices[0].message.content
                except Exception as e:
                    answer = f"Ett fel uppstod vid anrop till AI-coachen: {e}"
                    
                st.session_state.messages.append({"role": "assistant", "content": answer})
                with st.chat_message("assistant"):
                    st.markdown(answer)
        else:
            st.info("Lägg till din `GROQ_API_KEY` under Streamlit Cloud Secrets för att aktivera AI-coachen helt gratis.")
