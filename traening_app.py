import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="Träning & Hälsa", page_icon="🏃‍♂️", layout="wide")

# Kontrollera lösenord om det finns satt i secrets
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

# Anslut till Supabase
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

st.title("🏃‍♂️ Träning & Hälsa")
st.write("Live från molnet – drivs av din Apple Hälsa-data")

# Hämta data från tabeller
@st.cache_data(ttl=60)
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

tab1, tab2, tab3, tab4 = st.tabs(["🏠 Hem", "📋 Arkiv", "📊 Historik", "⚙️ Mål & Schema"])

with tab1:
    st.subheader("Senaste aktivitet")
    if not workouts_df.empty:
        st.dataframe(workouts_df.sort_values(by="date", ascending=False).head(5), use_container_width=True)
    else:
        st.info("Inga träningspass inlagda än. Synka från din telefon!")

with tab2:
    st.subheader("Träningsarkiv")
    if not workouts_df.empty:
        st.dataframe(workouts_df, use_container_width=True)
    else:
        st.info("Inga träningspass i arkivet ännu. Vänta på automatisk synk eller importera historik.")

with tab3:
    st.subheader("Hälsostatistik & Sömn")
    if not sleep_df.empty:
        st.line_chart(sleep_df.set_index("date")["duration_hours"])
    else:
        st.write("Ingen sömnsdata tillgänglig.")

with tab4:
    st.subheader("Mål & Schema")
    st.write("Här kan du följa dina träningsmål.")
