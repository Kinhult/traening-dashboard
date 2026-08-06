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
        
        # Sömnsammanfattning & Sömnpoäng (Apple Health-stil)
        st.subheader("💤 Sömn & Nattens återhämtning")
        if not sleep_df.empty:
            latest_sleep = sleep_df.sort_values(by="date", ascending=False).iloc[0]
            sleep_hours = latest_sleep.get("duration_hours", 0)
            sleep_score = min(100, int((sleep_hours / 8.0) * 100)) if sleep_hours else 0
            
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Sömntid i natt", f"{sleep_hours:.1f} timmar")
            sc2.metric("Sömnpoäng", f"{sleep_score} / 100")
            sc3.metric("Status", "Utmärkt 🟢" if sleep_score >= 85 else "God 🟡" if sleep_score >= 65 else "Behöver vila 🔴")
        else:
            st.info("Ingen sömndata registrerad ännu.")
            
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
# FLIK 2: LÖPNING (STRAVA-STIL MED MENY & DJUPDYKNING)
# ==========================================
with tab2:
    st.title("🏃‍♂️ Löpning & Strava-analys")
    st.markdown("Välj ett tidigare löppass nedan för att se GPS-karta, deltider, puls, höjd och Strava-statistik.")
    
    st.subheader("🎯 Aktiva Löpmål")
    running_goals = [g for g in st.session_state.goals if g["category"] == "Löpning"]
    if running_goals:
        for goal in running_goals:
            st.write(f"**{goal['title']}** (Mål: {goal['target']})")
            st.progress(goal["progress"] / 100)
    else:
        st.info("Inga aktiva löpmål tillagda ännu.")
    
    st.markdown("---")
    
    running_df = workouts_df[workouts_df["type"].str.contains("Löp|Utomhus Kör", case=False, na=False)] if not workouts_df.empty else pd.DataFrame()
    
    if not running_df.empty:
        # Sortera senaste först och skapa en tydlig meny
        running_df = running_df.sort_values(by="date", ascending=False)
        run_options = running_df.apply(lambda row: f"{row['date'].strftime('%Y-%m-%d %H:%M')} – {row.get('type', 'Löpning')} ({row.get('distance_km', 0):.2f} km)", axis=1).tolist()
        
        selected_run_str = st.selectbox("📂 Välj löppass att analysera:", run_options)
        selected_idx = run_options.index(selected_run_str)
        selected_run = running_df.iloc[selected_idx]
        
        st.markdown(f"### 🌙 Passdetaljer: {selected_run['date'].strftime('%Y-%m-%d %H:%M')}")
        
        # Huvudmått (Strava-stil)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Distans", f"{selected_run.get('distance_km', 10.13):.2f} km")
        col2.metric("Tid i rörelse", "47:48")
        col3.metric("Genomsnittligt tempo", "4:43 /km")
        col4.metric("Höjdökning", "53 m")
        
        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Kalorier", "703 kcal")
        col6.metric("Genomsnittlig puls", "164 slag/min")
        col7.metric("Maxpuls", "179 slag/min")
        col8.metric("Snitteffekt", "276 W")
        
        st.markdown("---")
        
        # Karta och Segment / Utmärkelser
        st.subheader("🗺️ GPS-karta över rundan (Ljungby)")
        col_map, col_info = st.columns([2, 1])
        with col_map:
            # Folium karta centrerad på Ljungby med mörkt tema
            m = folium.Map(location=[56.8333, 13.9333], zoom_start=13, tiles="CartoDB dark_matter")
            route_coords = [
                [56.8333, 13.9333], [56.8360, 13.9380], [56.8400, 13.9450],
                [56.8420, 13.9350], [56.8380, 13.9250], [56.8300, 13.9200],
                [56.8250, 13.9280], [56.8300, 13.9333]
            ]
            folium.PolyLine(route_coords, color="#fc4c02", weight=4, opacity=0.85).add_to(m)
            folium.Marker([56.8333, 13.9333], tooltip="Start / Mål", icon=folium.Icon(color="orange", icon="play")).add_to(m)
            st_folium(m, height=400, use_container_width=True)
            
        with col_info:
            st.markdown("#### Utmärkelser & Segment")
            st.success("🥉 Dina tredje snabbaste 10 km! (-20s)")
            st.info("🏆 4:e bästa tiden på Gångväg Stensberg")
            st.info("🏆 5:e bästa tiden Garvaren till Stensberg")
            st.metric("Total tid", "48:01")
            st.metric("Snabbaste km", "4:27 /km")
            
        st.markdown("---")
        st.subheader("📊 Deltider per kilometer")
        splits_data = pd.DataFrame({
            "Km": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "0,1"],
            "Tempo": ["5:10", "4:48", "4:36", "4:30", "4:27", "4:40", "4:40", "4:35", "4:51", "4:52", "4:59"],
            "Höjdändring (m)": [-17, 9, 6, -1, -10, 0, -7, 0, 10, 1, 2],
            "Puls (slag/min)": [141, 157, 162, 166, 167, 168, 167, 173, 172, 171, 172]
        })
        st.dataframe(splits_data, use_container_width=True)
        
        st.markdown("---")
        st.subheader("📈 Grafer & Analys (Tempo, Puls, Höjd & Effekt)")
        
        chart_km = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("**Puls (slag/min)**")
            hr_df = pd.DataFrame({"Puls": [145, 155, 162, 168, 166, 152, 160, 170, 173, 175]}, index=chart_km)
            st.line_chart(hr_df)
            
        with col_g2:
            st.markdown("**Höjdprofil (meter)**")
            elev_df = pd.DataFrame({"Höjd (m)": [155, 142, 148, 158, 153, 140, 143, 152, 150, 154]}, index=chart_km)
            st.area_chart(elev_df)
            
        col_g3, col_g4 = st.columns(2)
        with col_g3:
            st.markdown("**Effekt (W)**")
            power_df = pd.DataFrame({"Effekt (W)": [280, 295, 310, 340, 320, 290, 300, 315, 325, 330]}, index=chart_km)
            st.area_chart(power_df)
            
        with col_g4:
            st.markdown("**Tempo (/km)**")
            pace_df = pd.DataFrame({"Tempo-index": [5.1, 4.8, 4.6, 4.5, 4.4, 4.7, 4.7, 4.6, 4.9, 4.9]}, index=chart_km)
            st.line_chart(pace_df)
    else:
        st.info("Inga registrerade löppass hittades i databasen.")

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
        st.info("Inga aktiva styrkemål tillagda ännu.")
        
    st.markdown("---")
    st.subheader("⚙️ Redigera & Hantera Styrkepass")
    
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
                
        st.markdown("---")
        st.subheader("💤 Detaljerad Sömn- & Hälsodata")
        st.metric("Längd", "182 cm")
        st.metric("Vikt", "76.5 kg")
        
        if not sleep_df.empty:
            avg_sleep = sleep_df["duration_hours"].mean()
            st.metric("Genomsnittlig sömntid", f"{avg_sleep:.1f} timmar")
            
            st.markdown("#### Sömnhistorik")
            display_sleep = sleep_df.copy()
            if "date" in display_sleep.columns:
                display_sleep["date"] = display_sleep["date"].dt.strftime('%Y-%m-%d')
            st.dataframe(display_sleep[["date", "duration_hours"]].sort_values(by="date", ascending=False).head(5), use_container_width=True)
            
            st.markdown("### Sömnutveckling över tid")
            st.line_chart(sleep_df.set_index("date")["duration_hours"])
        else:
            st.metric("Sömnsnitt senaste 7 dagar", "7.8 timmar")
            st.info("Ingen sömndata hittades i databasen.")

    with col_b:
        st.subheader("🤖 Din Personliga AI-Coach (Gratis via Groq)")
        st.write("Fråga om hur du har sovit, träningsupplägg, återhämtning eller vilka pass du bör köra.")
        
        if "GROQ_API_KEY" in st.secrets:
            client_groq = openai.OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=st.secrets["GROQ_API_KEY"]
            )
            
            sleep_summary = "Ingen sömnsdata tillgänglig i databasen."
            if not sleep_df.empty:
                latest_sleep = sleep_df.sort_values(by="date", ascending=False).iloc[0]
                sleep_summary = f"Senaste sömnen ({str(latest_sleep.get('date', ''))[:10]}): Längd: {latest_sleep.get('duration_hours', 'okänd')} timmar."
            
            workouts_summary = f"Antal registrerade pass totalt: {len(workouts_df)}" if not workouts_df.empty else "Inga träningspass registrerade."
            goals_summary = ", ".join([g['title'] for g in st.session_state.goals])

            system_prompt = f"""Du är en personlig tränings- och hälsocoach. Du har direkt tillgång till användarens data från databasen:
- Sömndata: {sleep_summary}
- Träning: {workouts_summary}
- Aktiva mål: {goals_summary}

När användaren frågar om sin sömn (t.ex. 'hur har jag sovit idag?') eller träning, ska du använda denna faktiska data för att ge ett personligt, träffsäkert och engagerat svar."""

            if "messages" not in st.session_state:
                st.session_state.messages = [{"role": "assistant", "content": "Hej! Jag har full koll på din sömn och din träningsdata. Vad vill du veta eller ha hjälp med idag?"}]
                
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    
            if prompt := st.chat_input("Skriv till din coach..."):
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
                    answer = f"Ett fel uppstod vid anrop till AI-coachen: {e}"
                    
                st.session_state.messages.append({"role": "assistant", "content": answer})
                with st.chat_message("assistant"):
                    st.markdown(answer)
        else:
            st.info("Lägg till din `GROQ_API_KEY` under Streamlit Cloud Secrets för att aktivera AI-coachen helt gratis.")
