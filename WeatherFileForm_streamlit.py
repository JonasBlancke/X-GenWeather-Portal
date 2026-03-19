import streamlit as st
import yaml
import pandas as pd
import requests
from datetime import datetime
from timezonefinder import TimezoneFinder
import pytz
import folium
from streamlit_folium import st_folium

# --- CONFIGURATION ---
FORMSPREE_ENDPOINT = "https://formspree.io/f/myknozkr"

st.set_page_config(page_title="Climate Simulation Portal", page_icon="🌍", layout="wide")

# --- SESSION STATE ---
if "lat" not in st.session_state: st.session_state.lat = 53.3442
if "lon" not in st.session_state: st.session_state.lon = -6.2265
if "tz" not in st.session_state: st.session_state.tz = "Europe/Dublin"
if "gmt" not in st.session_state: st.session_state.gmt = 0

def auto_calc_timezone(lat, lon):
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if tz_name:
        st.session_state.tz = tz_name
        tz = pytz.timezone(tz_name)
        winter_month = 7 if lat < 0 else 1
        winter_dt = tz.localize(datetime(2024, winter_month, 1), is_dst=False)
        st.session_state.gmt = int(winter_dt.utcoffset().total_seconds() / 3600)

# --- UI HEADER ---
st.title("🌍 Climate Simulation Request Portal")
st.markdown("Select your location and parameters. Our team will process the EPW files and contact you.")

# --- SIDEBAR: CORE PARAMETERS ---
with st.sidebar:
    st.header("1. Core Setup")
    client_name = st.text_input("Project / Client Name", "MyProject_01")
    ssp_choice = st.multiselect("Climate Scenarios (SSP)", ["ssp126", "ssp245", "ssp370", "ssp585"], default=["ssp585"])
    gwl_choice = st.selectbox("Global Warming Level (GWL)", ["/", "1.5", "2.0", "3.0", "4.0"])
    
    st.header("2. Time Window")
    f_start, f_end = st.slider("Future Period", 2015, 2100, (2031, 2050))
    
    st.header("3. Output Format")
    epw_format = st.selectbox("Requested EPW Type", ["TMY (Typical)", "AMY (Actual)", "XMY (Extreme)", "DSY (Design)"])

# --- MAIN AREA ---
col_map, col_opts = st.columns([3, 2])

with col_map:
    st.subheader("Select Location")
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=6)
    folium.Marker([st.session_state.lat, st.session_state.lon], popup="Target Location").add_to(m)
    map_data = st_folium(m, width="100%", height=450)
    
    if map_data and map_data.get("last_clicked"):
        st.session_state.lat = map_data["last_clicked"]["lat"]
        st.session_state.lon = map_data["last_clicked"]["lng"]
        auto_calc_timezone(st.session_state.lat, st.session_state.lon)
        st.rerun()

with col_opts:
    st.subheader("Simulation Detail")
    sim_type = st.radio("Primary Metric Focus", ["Heatwave", "Fire Weather (FWI)"])
    
    if sim_type == "Heatwave":
        metric = st.selectbox("Heatwave Metric", ['TX7d', 'TX5d', 'TX3d', 'HWMId', 'EHF', 'Hotspell', 'HeatwaveAvgTmax'])
    else:
        metric = "FWI"
        
    ret_period = st.number_input("Return Period (Years)", value=10)
    
    st.divider()
    st.subheader("Urban Context")
    uhi_on = st.toggle("Apply Urban Heat Island (UHI) Correction", value=True)
    if uhi_on:
        lcz = st.selectbox("Local Climate Zone (LCZ)", range(1, 11), index=2, help="3 = Compact Low-rise")
        ashrae = st.selectbox("ASHRAE Class", ["4A", "5A", "6A", "4B", "5B"])
    else:
        lcz, ashrae = "/", "/"

# --- BUILD FINAL YAML ---
info_data = {
    "SIMULATION": f"{client_name}_{ssp_choice[0]}_{f_start}_{f_end}_{sim_type.lower()}",
    "CITY": {
        "LAT": round(st.session_state.lat, 4),
        "LON": round(st.session_state.lon, 4),
        "GMT": st.session_state.gmt,
        "TZ": st.session_state.tz,
    },
    "YEARS": {
        "FIRST_FUTURE": f_start, "LAST_FUTURE": f_end,
    },
    "CMIP6": {
        "SSP": ssp_choice,
        "GWL": gwl_choice,
        "intimeperiod": "YES" if gwl_choice == "/" else "NO"
    },
    "EXTREME_SELECTION": {
        "METHOD": metric,
        "RETURN_PERIOD": ret_period
    },
    "UHI": {
        "ENABLED": "YES" if uhi_on else "NO",
        "LCZ_URBAN": lcz,
        "ASHRAE_CLASS": ashrae
    },
    "CLIENT_EXPORT": {
        "EPW_FORMAT": epw_format
    }
}

final_yaml = f"###############################################################################\n" \
             f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n" \
             f"###############################################################################\n\n" + \
             yaml.dump(info_data, sort_keys=False)

# --- SUBMISSION ---
st.divider()
c1, c2 = st.columns(2)

with c1:
    if st.button("🚀 SUBMIT REQUEST BY EMAIL", type="primary", use_container_width=True):
        payload = {
            "Client": client_name,
            "Coordinates": f"{st.session_state.lat}, {st.session_state.lon}",
            "Config": final_yaml
        }
        res = requests.post(FORMSPREE_ENDPOINT, json=payload)
        if res.status_code == 200:
            st.success("Success! B-Kode has received your configuration.")
            st.balloons()
        else:
            st.error("Submission failed. Please use the download button.")

with c2:
    st.download_button("⬇️ DOWNLOAD YAML LOCALLY", final_yaml, f"config_{client_name}.yaml", use_container_width=True)

with st.expander("Review Technical Config"):
    st.code(final_yaml, language="yaml")