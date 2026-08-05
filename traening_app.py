import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="Träning & Hälsa", page_icon="🏃‍♂️", layout="wide")

# Lösenordsskydd
def check_password():
    if "APP_PASSWORD" in st.secrets:
        def password_entered():
            if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
                del st.session_state["password"]
            else:
                st.session_state["password_correct"] = False

        if "password_correct" not in st.session_state:
            st.text_input("Ange lösenord:", type="password", on_change=password_entered, key="password")
            return False
        elif not st.session_state["password_correct"]:
            st.text_input("Ange lösenord:", type="password", on_change=password_entered, key="password")
            st.error("Felaktigt lösenord")
            return False
    return True

if not check_password():
    st.stop()

# Anslut till Supabase med säker rensning av nycklar
@st.cache_resource
def init_connection():
    url = str(st.secrets["SUPABASE_URL"]).strip().encode("ascii", "ignore").decode("ascii")
    key = str(st.secrets["SUPABASE_KEY"]).strip().encode("ascii", "ignore").decode("ascii")
    return create_client(url, key)

supabase = init_connection()

st.title("🏃‍♂️ Träning & Hälsa")
st.caption("Live från molnet – drivs av din Apple Hälsa-data")

# Hämta data
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

# Navigering via flikar
tab1, tab2, tab3, tab4 = st.tabs(["🏠 Hem", "📋 Träningsarkiv", "📊 Historik & Statistik", "⚙️ Mål & Schema"])

with tab1:
    st.subheader("Översikt")
    
    # Beräkna snabbstatistik
    total_workouts = len(workouts_df) if not workouts_df.empty else 0
    total_distance = workouts_df["distance_km"].sum() if not workouts_df.empty and "distance_km" in workouts_df.columns else 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Totalt antal pass", total_workouts)
    col2.metric("Total sträcka", f"{total_distance:.1f} km")
    col3.metric("Återhämtningsindex", "70 / 100")
    
    st.markdown("---")
    st.subheader("Senaste träningspassen")
    if not workouts_df.empty:
        display_df = workouts_df.sort_values(by="date", ascending=False).head(5).copy()
        
        # Byt till snygga svenska kolumnnamn om de finns
        rename_map = {
            "date": "Datum",
            "type": "Aktivitet",
            "duration_min": "Tid (min)",
            "distance_km": "Distans (km)",
            "calories": "Kalorier",
            "avg_hr": "Snittpuls"
        }
        display_df = display_df.rename(columns=rename_map)
        
        # Avrunda siffror snyggt
        if "Tid (min)" in display_df.columns:
            display_df["Tid (min)"] = display_df["Tid (min)"].round(1)
        if "Distans (km)" in display_df.columns:
            display_df["Distans (km)"] = display_df["Distans (km)"].round(2)
            
        st.dataframe(display_df[["Datum", "Aktivitet", "Tid (min)", "Distans (km)", "Kalorier", "Snittpuls"]], use_container_width=True)
    else:
        st.info("Inga träningspass inlagda än. Synka från din telefon!")

with tab2:
    st.subheader("Komplett Träningsarkiv")
    if not workouts_df.empty:
        full_df = workouts_df.sort_values(by="date", ascending=False).copy()
        rename_map = {
            "date": "Datum",
            "type": "Aktivitet",
            "duration_min": "Tid (min)",
            "distance_km": "Distans (km)",
            "calories": "Kalorier",
            "avg_hr": "Snittpuls",
            "max_hr": "Maxpuls"
        }
        full_df = full_df.rename(columns=rename_map)
        st.dataframe(full_df, use_container_width=True)
    else:
        st.info("Arkivet är tomt.")

with tab3:
    st.subheader("Träningstrender & Sömn")
    
    if not workouts_df.empty and "distance_km" in workouts_df.columns:
        st.markdown("### Distans per pass")
        chart_df = workouts_df.dropna(subset=["distance_km"])
        if not chart_df.empty:
            st.bar_chart(chart_df.set_index("date")["distance_km"])
            
    if not sleep_df.empty and "duration_hours" in sleep_df.columns:
        st.markdown("### Sömnlängd (timmar)")
        st.line_chart(sleep_df.set_index("date")["duration_hours"])
    else:
        st.write("Ingen sömnsdata att visa ännu.")

with tab4:
    st.subheader("Mål & Schema")
    st.write("Håll koll på dina träningsmål och veckomål här.")
    st.success("Mål för veckan: 2 träningspass genomförda.")
