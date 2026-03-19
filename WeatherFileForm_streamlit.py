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

ASHRAE_ZONES = {
    "0 - Extremely Hot": ["0A - Extremely Hot - Humid", "0B - Extremely Hot - Dry"],
    "1 - Very Hot": ["1A - Very Hot - Humid", "1B - Very Hot - Dry"],
    "2 - Hot": ["2A - Hot - Humid", "2B - Hot - Dry"],
    "3 - Warm": ["3A - Warm - Humid", "3B - Warm - Dry", "3C - Warm - Marine"],
    "4 - Mixed": ["4A - Mixed - Humid", "4B - Mixed - Dry", "4C - Mixed - Marine"],
    "5 - Cool": ["5A - Cool - Humid", "5B - Cool - Dry", "5C - Cool - Marine"],
    "6 - Cold": ["6A - Cold - Humid", "6B - Cold - Dry"],
    "7 - Very Cold": ["7 - Very Cold"],
    "8 - Subarctic": ["8 - Subarctic / Arctic"],
}

st.set_page_config(page_title="EPW Climate Simulation Portal", page_icon="🌍", layout="wide")

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
st.title("🌍 EPW Climate Simulation Request Portal")
st.markdown("Select your location and parameters. B-Kode will process the EPW files and contact you.")

# --- SIDEBAR: CORE PARAMETERS ---
with st.sidebar:
    st.header("1. Core Setup")
    client_name = st.text_input("Project / Client Name", "MyProject_01")
    
    # Future Scenario Selection
    scenario_type = st.selectbox("Future Scenario Selection", ["Global Warming Level (GWL)", "Shared Economic Pathway (SSP)"])
    
    if scenario_type == "Global Warming Level (GWL)":
        gwl_choice = st.selectbox("Select GWL Target", ["1.5", "2.0", "3.0", "4.0"])
        ssp_choice = []
        # Auto-detect years based on GWL (simplified mapping)
        gwl_year_map = {"1.5": (2025, 2040), "2.0": (2035, 2055), "3.0": (2055, 2080), "4.0": (2080, 2100)}
        f_start, f_end = gwl_year_map.get(gwl_choice, (2031, 2050))
    else:  # SSP
        ssp_choice = st.multiselect("Climate Scenarios (SSP)", ["ssp126", "ssp245", "ssp370", "ssp585"], default=["ssp585"])
        gwl_choice = "/"
        f_start, f_end = st.slider("Future Period", 2015, 2100, (2031, 2050))
    
    st.header("2. Output Format")
    
    # Historical EPW Selection
    st.subheader("Historical EPW")
    hist_epw_types = st.multiselect("Select Historical Type(s)", ["AMY (Actual)", "TMY (Typical)"], key="hist_epw_types")
    
    hist_epw_config = {}
    if "TMY (Typical)" in hist_epw_types:
        tmy_start, tmy_end = st.slider("TMY Creation Period (Years)", 1960, 2025, (1990, 2020), key="tmy_period")
        hist_epw_config["TMY"] = {"start_year": tmy_start, "end_year": tmy_end}
    
    if "AMY (Actual)" in hist_epw_types:
        amy_year = st.selectbox("Select Year for AMY", range(2025, 1959, -1), key="amy_year")
        hist_epw_config["AMY"] = amy_year
    
    # Future EPW Selection
    st.subheader("Future EPW")
    
    if scenario_type == "Global Warming Level (GWL)":
        st.info(f"📅 Using GWL {gwl_choice}°C target - Future period varies by model")
    else:
        st.info(f"📅 Using SSP {ssp_choice[0] if ssp_choice else 'N/A'} - Fixed period: {f_start} - {f_end}")
    
    future_epw_types = st.multiselect("Select Future Type(s)", ["TMY (Typical)", "XMY (Extreme)"], key="future_epw_types")
    
    future_epw_config = {"period": (f_start, f_end)}
    if "XMY (Extreme)" in future_epw_types:
        with st.expander("⚡ Extreme Event Details", expanded=True):
            extreme_return_period = st.number_input("Return Period (Years)", value=10, min_value=1, key="extreme_return_period")
            extreme_event_type = st.selectbox("Extreme Event Type", ["Heatwave"], key="extreme_event_type")
            extreme_metric = st.selectbox("Specific Metric", ['TX7d', 'TX5d', 'TX3d', 'HWMId', 'EHF', 'Hotspell'], key="extreme_metric")
            future_epw_config["XMY"] = {
                "return_period": extreme_return_period,
                "event_type": extreme_event_type,
                "metric": extreme_metric
            }
    
    if "TMY (Typical)" in future_epw_types:
        future_epw_config["TMY"] = True

# --- MAIN AREA ---
col_map, col_opts = st.columns([3, 2])

with col_map:
    st.subheader("Select Location")
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=6)
    folium.CircleMarker(
        location=[st.session_state.lat, st.session_state.lon],
        radius=8,
        color="#d1495b",
        weight=2,
        fill=True,
        fill_color="#d1495b",
        fill_opacity=0.85,
    ).add_to(m)
    map_data = st_folium(m, width="100%", height=450)
    
    if map_data and map_data.get("last_clicked"):
        st.session_state.lat = map_data["last_clicked"]["lat"]
        st.session_state.lon = map_data["last_clicked"]["lng"]
        auto_calc_timezone(st.session_state.lat, st.session_state.lon)
        st.rerun()

with col_opts:
    st.subheader("Urban Context")
    uhi_on = st.toggle("Apply Urban Heat Island (UHI) Correction", value=True)
    if uhi_on:
        lcz_options = [
            "1 - Compact High-Rise",
            "2 - Compact Mid-Rise",
            "3 - Compact Low-Rise",
            "4 - Open High-Rise",
            "5 - Open Mid-Rise",
            "6 - Open Low-Rise",
            "7 - Lightweight Low-Rise",
            "8 - Large Low-Rise",
            "9 - Sparsely Built",
            "10 - Heavy Industry",
            "A - Dense Trees",
            "B - Scattered Trees",
            "C - Bush, Scrub",
            "D - Low Plants (Grass/crops)",
            "E - Bare Rock or Paved",
            "F - Bare Soil or Sand",
            "G - Water (River/lake/sea)"
        ]
        lcz_selection = st.selectbox("Local Climate Zone (LCZ)", lcz_options, index=2)
        lcz = lcz_selection.split(" - ")[0]

        ashrae_main = st.selectbox("ASHRAE Main Climate Zone", list(ASHRAE_ZONES.keys()), index=4)
        ashrae_subtype = st.selectbox("ASHRAE Subtype", ASHRAE_ZONES[ashrae_main])
        ashrae = ashrae_subtype.split(" - ")[0]
    else:
        lcz, ashrae = "/", "/"

st.divider()
special_requests = st.text_area(
    "Questions / Notes / Special Requests",
    placeholder="Add any extra context, questions, delivery notes, or special requests here.",
    height=140,
)

# --- BUILD FINAL YAML ---
# Set defaults for metric/return period (used if XMY not selected)
metric = "TX_max_7d"  # Default heatwave metric
ret_period = 10  # Default return period

# Override with XMY settings if extreme event is selected
if "XMY (Extreme)" in future_epw_types:
    metric = extreme_metric
    ret_period = extreme_return_period

info_data = {
    "SIMULATION": f"{client_name}_{'GWL'+gwl_choice if gwl_choice != '/' else ssp_choice[0]}_{f_start}_{f_end}_epw",
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
        "SSP": ssp_choice if ssp_choice else "/",
        "GWL": gwl_choice if gwl_choice != "/" else "/",
        "intimeperiod": "YES" if scenario_type == "Shared Economic Pathway (SSP)" else "NO"
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
    "CLIENT_NOTES": special_requests if special_requests.strip() else "/",
    "CLIENT_EXPORT": {
        "HISTORICAL_EPW": hist_epw_config,
        "FUTURE_EPW": future_epw_config
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
            "Config": final_yaml,
            "Notes": special_requests,
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