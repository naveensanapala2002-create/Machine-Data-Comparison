import streamlit as st
import pandas as pd
import numpy as np
import zipfile
import os
import io
import math
import datetime

st.set_page_config(page_title="Machine Data Comparison", layout="wide")

st.title("Machine Data Comparison Application")
st.write("Upload a ZIP file containing machine data to automatically analyze all parameters across all production days instantly.")

# --- Persistent Target Master File Path & Parsing Helper ---
TARGETS_FILE = "screw_rpm_targets.csv"

def parse_target_excel(file_bytes_or_path):
    try:
        df_raw = pd.read_excel(file_bytes_or_path, header=None)
        header_row = 0
        for idx, row in df_raw.iterrows():
            row_str = " ".join([str(v).lower() for v in row.values if pd.notnull(v)])
            if 'compound' in row_str or 'rpm' in row_str:
                header_row = idx
                break
                
        df = pd.read_excel(file_bytes_or_path, header=header_row).dropna(how='all')
        
        comp_col, rpm_col = None, None
        for col in df.columns:
            col_str = str(col).lower()
            if 'compound' in col_str:
                comp_col = col
            elif any(k in col_str for k in ['rpm', 'speed', 'specified', 'target']):
                rpm_col = col
                
        if comp_col is not None and rpm_col is not None:
            res = pd.DataFrame({
                'Compound': df[comp_col].astype(str).str.strip(),
                'Target Screw RPM': pd.to_numeric(df[rpm_col], errors='coerce')
            }).dropna(subset=['Compound', 'Target Screw RPM'])
            res = res[~res['Compound'].str.lower().isin(['compound', 'compound name', 'nan', ''])]
            return res.reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame(columns=['Compound', 'Target Screw RPM'])

# --- Target Master Session State & Storage Initialization ---
if "target_df" not in st.session_state:
    if os.path.exists(TARGETS_FILE):
        try:
            st.session_state["target_df"] = pd.read_csv(TARGETS_FILE)
        except Exception:
            st.session_state["target_df"] = pd.DataFrame(columns=["Compound", "Target Screw RPM"])
    elif os.path.exists("Screw rpm.xlsx"):
        st.session_state["target_df"] = parse_target_excel("Screw rpm.xlsx")
        st.session_state["target_df"].to_csv(TARGETS_FILE, index=False)
    else:
        default_data = pd.DataFrame([
            {"Compound": "PVC", "Target Screw RPM": 80},
            {"Compound": "ZHFR - Black", "Target Screw RPM": 40},
            {"Compound": "ZHFR - Other colour", "Target Screw RPM": 35},
            {"Compound": "HDPE", "Target Screw RPM": 65},
            {"Compound": "HFDPE", "Target Screw RPM": 65},
            {"Compound": "SHF-2", "Target Screw RPM": 45},
            {"Compound": "SHF2", "Target Screw RPM": 45},
            {"Compound": "NYLON", "Target Screw RPM": 65},
            {"Compound": "LDPE", "Target Screw RPM": 65},
            {"Compound": "CPE", "Target Screw RPM": 30},
            {"Compound": "SHF2-RC", "Target Screw RPM": 38},
            {"Compound": "EVA", "Target Screw RPM": 32},
            {"Compound": "EPDM HARD", "Target Screw RPM": 40},
            {"Compound": "ELRS EPDM", "Target Screw RPM": 30},
            {"Compound": "TMEIC", "Target Screw RPM": 8},
            {"Compound": "EPR", "Target Screw RPM": 50},
            {"Compound": "XLPE", "Target Screw RPM": 55},
            {"Compound": "PU", "Target Screw RPM": 15},
            {"Compound": "TYPE-C", "Target Screw RPM": 30}
        ])
        st.session_state["target_df"] = default_data
        default_data.to_csv(TARGETS_FILE, index=False)

if "targets_is_editing" not in st.session_state:
    st.session_state["targets_is_editing"] = False

if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

# --- Application Navigation Tabs ---
tab1, tab2 = st.tabs(["🏭 Machine Data Comparison", "🎯 Screw RPM Targets"])

with tab2:
    st.subheader("🎯 Screw RPM Target Master Configuration")
    
    if st.session_state["targets_is_editing"]:
        if not st.session_state["admin_authenticated"]:
            st.warning("🔒 Admin Access Required to Edit Targets")
            admin_pwd = st.text_input("Enter Admin Password:", type="password", key="admin_pwd_input")
            col_auth1, col_auth2 = st.columns([1, 4])
            with col_auth1:
                if st.button("Unlock Editing", key="btn_unlock_editing"):
                    if admin_pwd == "admin123":
                        st.session_state["admin_authenticated"] = True
                        st.success("✅ Admin authenticated successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Incorrect Admin Password!")
            with col_auth2:
                if st.button("Cancel", key="btn_cancel_editing"):
                    st.session_state["targets_is_editing"] = False
                    st.session_state["admin_authenticated"] = False
                    st.rerun()
        else:
            st.markdown("#### Edit Screw RPM Targets")
            st.info("Method 1: Upload an Excel file OR Method 2: Manually edit/add/remove records in the table below.")
            
            uploaded_excel = st.file_uploader("Import Excel File for Target RPMs", type=["xlsx", "xls"], key="target_excel_uploader")
            if uploaded_excel is not None:
                parsed_df = parse_target_excel(uploaded_excel)
                if not parsed_df.empty:
                    st.session_state["target_df"] = parsed_df
                    parsed_df.to_csv(TARGETS_FILE, index=False)
                    st.success("✅ Target RPMs imported successfully from Excel file!")
            
            st.markdown("#### Manual Data Entry")
            edited_df = st.data_editor(
                st.session_state["target_df"],
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Compound": st.column_config.TextColumn("Compound", required=True),
                    "Target Screw RPM": st.column_config.NumberColumn("Target Screw RPM", min_value=0, required=True)
                },
                key="targets_data_editor"
            )
            
            if st.button("💾 Save Targets", key="btn_save_targets"):
                clean_df = edited_df.dropna(subset=["Compound", "Target Screw RPM"]).copy()
                clean_df["Compound"] = clean_df["Compound"].astype(str).str.strip()
                clean_df["Target Screw RPM"] = pd.to_numeric(clean_df["Target Screw RPM"], errors="coerce")
                clean_df = clean_df.dropna(subset=["Target Screw RPM"]).reset_index(drop=True)
                
                st.session_state["target_df"] = clean_df
                clean_df.to_csv(TARGETS_FILE, index=False)
                st.session_state["targets_is_editing"] = False
                st.session_state["admin_authenticated"] = False
                st.success("✅ Target master saved permanently!")
                st.rerun()
    else:
        st.dataframe(st.session_state["target_df"], use_container_width=True, hide_index=True)
        if st.button("✏️ Edit Targets", key="btn_edit_targets"):
            st.session_state["targets_is_editing"] = True
            st.rerun()

with tab1:
    uploaded_file = st.file_uploader("Upload Machine Data ZIP File", type=["zip"])

    def parse_duration_hm(seconds):
        if pd.isna(seconds) or seconds < 0:
            return "0m"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes:02d}m"
        return f"{minutes}m"

    if "zip_status" not in st.session_state:
        st.session_state.zip_status = {"uploaded": "No", "total_files": 0, "excel_read": 0, "csv_read": 0, "failed_files": 0}
    if "file_details" not in st.session_state:
        st.session_state.file_details = []

    def fast_parse_timestamp(series, filepath=""):
        clean_series = series.astype(str).str.strip()
        parsed = pd.Series(pd.NaT, index=series.index, dtype='datetime64[ns]')
        
        valid_mask = ~clean_series.isna() & ~clean_series.str.lower().isin(['nan', 'nat', '', 'none', 'null'])
        if not valid_mask.any():
            return parsed
            
        s = clean_series[valid_mask]
        
        # 1. Direct fast-path for standard ISO timestamps
        parsed_iso = pd.to_datetime(s, format='ISO8601', errors='coerce')
        parsed.loc[s.index] = parsed_iso
        
        # 2. 12-Hour AM/PM timestamps
        rem_mask = valid_mask & parsed.isna()
        if rem_mask.any():
            s_rem = clean_series[rem_mask]
            am_pm_mask = s_rem.str.contains(r'(?i)\b(?:am|pm)\b')
            if am_pm_mask.any():
                parsed.loc[s_rem[am_pm_mask].index] = pd.to_datetime(s_rem[am_pm_mask], errors='coerce')
            
        # 3. Industrial YYYY-DD-MM sequences
        rem_mask = valid_mask & parsed.isna()
        if rem_mask.any():
            s_rem = clean_series[rem_mask]
            ydm_mask = s_rem.str.match(r'^\d{4}[-/]\d{2}[-/](?:07|08)(?:\s|$)')
            if ydm_mask.any():
                parsed.loc[s_rem[ydm_mask].index] = pd.to_datetime(
                    s_rem[ydm_mask].str.replace('/', '-'), 
                    format='%Y-%d-%m %H:%M:%S', 
                    errors='coerce'
                )
                
        # 4. Sequential Fallbacks with direct explicit formats
        rem_mask = valid_mask & parsed.isna()
        if rem_mask.any():
            s_rem = clean_series[rem_mask]
            norm = s_rem.str.replace('/', '-').str.replace('.', '-')
            fallback_formats = [
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %I:%M:%S %p",
                "%d-%m-%Y %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%m-%d-%Y %H:%M:%S",
                "%m-%d-%Y %H:%M",
                "%Y-%d-%m %H:%M:%S",
                "%Y-%d-%m %H:%M"
            ]
            for fmt in fallback_formats:
                unparsed_mask = valid_mask & parsed.isna()
                if not unparsed_mask.any():
                    break
                subset = norm.loc[unparsed_mask[unparsed_mask].index]
                parsed.loc[subset.index] = pd.to_datetime(subset, format=fmt, errors='coerce')
                
        # 5. Fallback for remaining arbitrary mixed/tz formats
        rem_mask = valid_mask & parsed.isna()
        if rem_mask.any():
            s_rem = clean_series[rem_mask]
            dt_mixed = pd.to_datetime(s_rem, format='mixed', errors='coerce')
            if hasattr(dt_mixed.dt, 'tz') and dt_mixed.dt.tz is not None:
                dt_mixed = dt_mixed.dt.tz_localize(None)
            parsed.loc[s_rem.index] = dt_mixed
            
        return parsed

    def load_and_preprocess_file(file_obj, filepath, tracking_log=None):
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filename)[1].lower()
        
        status_entry = {"name": filename, "ext": ext, "status": "Failed", "reason": "", "rows": 0, "columns": {}, "available_dates": set()}
        
        try:
            if ext == '.csv':
                df = pd.read_csv(file_obj, dtype=str)
                st.session_state.zip_status["csv_read"] += 1
            elif ext in ['.xlsx', '.xls']:
                df = pd.read_excel(file_obj, dtype=str)
                st.session_state.zip_status["excel_read"] += 1
            else:
                status_entry["reason"] = "Unsupported format"
                st.session_state.zip_status["failed_files"] += 1
                st.session_state.file_details.append(status_entry)
                return pd.DataFrame(), set()
                
            df.columns = [str(c).strip() for c in df.columns]
            status_entry["rows"] = len(df)
            
            if df.empty:
                status_entry["reason"] = "Empty data source sheet structure"
                st.session_state.file_details.append(status_entry)
                return pd.DataFrame(), set()
                
            required_cols = ['Timestamp', 'Speed', 'Screw rpm', 'Compound', 'Thickness', 'Diameter', 'Operator']
            col_mapping = {}
            for rc in required_cols:
                found = False
                for actual_col in df.columns:
                    norm_actual = actual_col.lower().replace(" ", "").replace("_", "")
                    norm_rc = rc.lower().replace(" ", "").replace("_", "")
                    if norm_rc == norm_actual or (rc == 'Compound' and norm_actual in ['comound', 'compoundname']):
                        col_mapping[actual_col] = rc
                        found = True
                        break
                status_entry["columns"][rc] = "✓" if found else "✗"
                
            if "✗" in status_entry["columns"].values():
                status_entry["reason"] = "Required columns missing from dataset headers"
                st.session_state.file_details.append(status_entry)
                return pd.DataFrame(), set()
                
            df = df.rename(columns=col_mapping)
                
            raw_dates = df['Timestamp'].copy()
            df['Timestamp'] = fast_parse_timestamp(df['Timestamp'], filepath)

            # Report unparseable values with complete metadata
            if tracking_log is not None:
                invalid_mask = df['Timestamp'].isna() & ~raw_dates.isna() & ~raw_dates.astype(str).str.strip().str.lower().isin(['nan', 'nat', '', 'none', 'null'])
                if invalid_mask.any():
                    for idx in df[invalid_mask].index:
                        tracking_log["exclusions"].append({
                            "File Name": filename,
                            "Column Name": "Timestamp",
                            "Row Number": idx + 2,
                            "Original Value": raw_dates.loc[idx],
                            "Parsed Value": "NaT",
                            "Error Reason": "Unparseable date/time format"
                        })

            df = df.dropna(subset=['Timestamp']).sort_values('Timestamp').reset_index(drop=True)
            
            if not df.empty and tracking_log is not None:
                tracking_log["input_dates"].append((df['Timestamp'].min(), df['Timestamp'].max(), filename))

            for col in ['Speed', 'Screw rpm', 'Thickness', 'Diameter']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['Production_Date'] = (df['Timestamp'] - pd.Timedelta(hours=6)).dt.date
            
            detected_prod_dates = {d for d in df['Production_Date'].unique() if pd.notnull(d)}
            status_entry["available_dates"] = detected_prod_dates

            # Fast vectorized truncation via NumPy
            df['Int_Diameter'] = np.trunc(df['Diameter'])
            df['Int_Speed'] = np.trunc(df['Speed'])
            df['Int_RPM'] = np.trunc(df['Screw rpm'])
            
            df = df.dropna(subset=['Int_Diameter']).reset_index(drop=True)
            
            status_entry["status"] = "Read Successfully"
            st.session_state.file_details.append(status_entry)
            return df, detected_prod_dates
            
        except Exception as e:
            status_entry["reason"] = f"Pipeline execution error: {str(e)}"
            st.session_state.zip_status["failed_files"] += 1
            st.session_state.file_details.append(status_entry)
            return pd.DataFrame(), set()

    # --- CACHED MAIN EXTRACTION FUNCTION ---
    @st.cache_data(show_spinner="⚡ Fast Processing Machine Data from ZIP...")
    def process_zip_payload(zip_bytes, target_lookup):
        all_extracted_rows = []
        tracking_log = {"input_dates": [], "exclusions": []}
        
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            valid_file_infos = [
                info for info in z.infolist() 
                if not info.is_dir() and '__MACOSX' not in info.filename and os.path.splitext(info.filename)[1].lower() in ['.csv', '.xlsx', '.xls']
            ]

            st.session_state.zip_status = {"uploaded": "Yes", "total_files": len(valid_file_infos), "excel_read": 0, "csv_read": 0, "failed_files": 0}
            st.session_state.file_details = []

            for file_info in valid_file_infos:
                filename = file_info.filename
                machine_clean_name = os.path.basename(filename).split(" - ")[-1].replace(".csv", "").replace(".xlsx", "").replace(".xls", "").strip()
                
                with z.open(file_info) as file_obj:
                    raw_continuous_df, _ = load_and_preprocess_file(file_obj, filename, tracking_log)
                
                if raw_continuous_df.empty:
                    continue
                
                # Forward fill metadata
                raw_continuous_df['Compound'] = raw_continuous_df['Compound'].astype(str).str.strip().replace({'nan': np.nan, '': np.nan}).ffill().fillna("Unknown")
                raw_continuous_df['Operator'] = raw_continuous_df['Operator'].astype(str).str.strip().replace({'nan': np.nan, '': np.nan}).ffill().fillna("Unknown")
                raw_continuous_df['Thickness'] = raw_continuous_df['Thickness'].ffill().fillna(0)

                condition_dia = raw_continuous_df['Int_Diameter'] != raw_continuous_df['Int_Diameter'].shift()
                condition_op  = raw_continuous_df['Operator'] != raw_continuous_df['Operator'].shift()
                condition_cmp = raw_continuous_df['Compound'] != raw_continuous_df['Compound'].shift()
                condition_thk = raw_continuous_df['Thickness'] != raw_continuous_df['Thickness'].shift()
                
                raw_continuous_df['Zone_Block'] = (condition_dia | condition_op | condition_cmp | condition_thk).cumsum()
                
                for _, block_df in raw_continuous_df.groupby('Zone_Block'):
                    if len(block_df) <= 20:
                        continue
                        
                    zone_start_dt = block_df['Timestamp'].min()
                    zone_end_dt = block_df['Timestamp'].max()
                    
                    valid_records = block_df[
                        (block_df['Diameter'] > 0) & 
                        (block_df['Speed'] > 0) & 
                        (block_df['Screw rpm'] > 0)
                    ]
                    
                    if len(valid_records) <= 20:
                        continue
                        
                    dia_seconds = (valid_records['Timestamp'].max() - valid_records['Timestamp'].min()).total_seconds()
                    
                    if dia_seconds < 1200:
                        continue
                        
                    diameter_duration_str = f"{len(valid_records)} minutes"
                    duration_hm_str = parse_duration_hm(dia_seconds)
                    duration_min_str = f"{math.ceil(dia_seconds / 60.0)} minutes"
                    
                    min_screw_rpm_val = valid_records['Screw rpm'].min()
                    max_screw_rpm_val = valid_records['Screw rpm'].max()
                    min_speed_val = valid_records['Speed'].min()
                    max_speed_val = valid_records['Speed'].max()
                    
                    mode_rpm_series = valid_records['Int_RPM'].mode()
                    if mode_rpm_series.empty:
                        continue
                    selected_int_rpm = mode_rpm_series.iloc[0]
                    
                    rpm_subset_df = valid_records[(valid_records['Int_RPM'] - selected_int_rpm).abs() <= 1]
                    if len(rpm_subset_df) <= 20:
                        continue
                        
                    rpm_seconds = (rpm_subset_df['Timestamp'].max() - rpm_subset_df['Timestamp'].min()).total_seconds()
                    if rpm_seconds < 1200:
                        continue
                        
                    rpm_duration_str = f"{len(rpm_subset_df)} minutes"
                    
                    mode_speed_series = rpm_subset_df['Int_Speed'].mode()
                    if mode_speed_series.empty:
                        continue
                    selected_int_speed = mode_speed_series.iloc[0]
                    
                    speed_subset_df = rpm_subset_df[(rpm_subset_df['Int_Speed'] - selected_int_speed).abs() <= 1]
                    if len(speed_subset_df) <= 20:
                        continue
                        
                    speed_seconds = (speed_subset_df['Timestamp'].max() - speed_subset_df['Timestamp'].min()).total_seconds()
                    if speed_seconds < 1200:
                        continue
                        
                    speed_duration_str = f"{len(speed_subset_df)} minutes"
                    
                    def get_primary_value(series):
                        modes = series.mode()
                        return modes.iloc[0] if not modes.empty else (series.iloc[0] if not series.empty else "N/A")
                        
                    operator = get_primary_value(valid_records['Operator'])
                    compound = get_primary_value(valid_records['Compound'])
                    thickness = get_primary_value(valid_records['Thickness'])
                    current_int_dia = int(valid_records['Int_Diameter'].iloc[0])
                    
                    comp_key = str(compound).strip().lower()
                    target_rpm_val = target_lookup.get(comp_key, "N/A")
                    
                    start_time_str = zone_start_dt.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(zone_start_dt) else "NaT"
                    end_time_str = zone_end_dt.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(zone_end_dt) else "NaT"
                    
                    rpm_start_str = rpm_subset_df['Timestamp'].min().strftime("%Y-%m-%d %H:%M:%S") if not rpm_subset_df.empty else start_time_str
                    rpm_end_str = rpm_subset_df['Timestamp'].max().strftime("%Y-%m-%d %H:%M:%S") if not rpm_subset_df.empty else end_time_str
                    
                    speed_start_str = speed_subset_df['Timestamp'].min().strftime("%Y-%m-%d %H:%M:%S") if not speed_subset_df.empty else start_time_str
                    speed_end_str = speed_subset_df['Timestamp'].max().strftime("%Y-%m-%d %H:%M:%S") if not speed_subset_df.empty else end_time_str
                    
                    all_extracted_rows.append({
                        "Machine": machine_clean_name,
                        "Operator": operator,
                        "Compound": compound,
                        "Diameter": current_int_dia,
                        "Diameter Duration": diameter_duration_str,
                        "RPM": selected_int_rpm,
                        "Target Screw RPM": target_rpm_val,
                        "Minimum Screw RPM": min_screw_rpm_val,
                        "Maximum Screw RPM": max_screw_rpm_val,
                        "RPM Duration": rpm_duration_str,
                        "Speed": selected_int_speed,
                        "Minimum Speed": min_speed_val,
                        "Maximum Speed": max_speed_val,
                        "Speed Duration": speed_duration_str,
                        "Thickness": thickness,
                        "Start Date & Time": start_time_str,
                        "End Date & Time": end_time_str,
                        "Duration (Hours & Minutes)": duration_hm_str,
                        "Duration (Minutes)": duration_min_str,
                        "Prod_Date_Obj": (zone_start_dt - pd.Timedelta(hours=6)).date(),
                        "Zone_Start_Timestamp": zone_start_dt,
                        "RPM_Start_Time": rpm_start_str,
                        "RPM_End_Time": rpm_end_str,
                        "Speed_Start_Time": speed_start_str,
                        "Speed_End_Time": speed_end_str,
                        "dia_seconds_raw": dia_seconds
                    })

        return pd.DataFrame(all_extracted_rows), tracking_log

    if uploaded_file is not None:
        target_lookup = {}
        if "target_df" in st.session_state and not st.session_state["target_df"].empty:
            for _, r in st.session_state["target_df"].iterrows():
                comp_key = str(r["Compound"]).strip().lower()
                try:
                    val = float(r["Target Screw RPM"])
                    target_lookup[comp_key] = int(val) if val.is_integer() else val
                except (ValueError, TypeError):
                    pass

        master_df, tracking_log = process_zip_payload(uploaded_file.getvalue(), target_lookup)

        columns_ordered = [
            "Machine", "Operator", "Compound", "Diameter", "Diameter Duration", 
            "RPM", "Target Screw RPM", "Minimum Screw RPM", "Maximum Screw RPM", "RPM Duration", 
            "Speed", "Minimum Speed", "Maximum Speed", "Speed Duration", "Thickness", 
            "Start Date & Time", "End Date & Time", "Duration (Hours & Minutes)", "Duration (Minutes)"
        ]

        # --- Date Range Verification Summary ---
        if tracking_log["input_dates"]:
            overall_input_min = min(item[0] for item in tracking_log["input_dates"])
            overall_input_max = max(item[1] for item in tracking_log["input_dates"])
            
            output_min = master_df["Zone_Start_Timestamp"].min() if not master_df.empty else "None"
            output_max = master_df["Zone_Start_Timestamp"].max() if not master_df.empty else "None"
            
            st.info(
                f"📅 **Date Range Verification Summary:**\n\n"
                f"• **Uploaded Input Files Date Range:** `{overall_input_min}` to `{overall_input_max}`\n\n"
                f"• **Processed Output Date Range:** `{output_min}` to `{output_max}`"
            )

        # Report excluded records if any
        if tracking_log["exclusions"]:
            with st.expander("⚠️ Excluded Records / Parsing Warnings"):
                st.dataframe(pd.DataFrame(tracking_log["exclusions"]), use_container_width=True, hide_index=True)

        if not master_df.empty:
            # --- EXCEL STYLE COLUMN FILTER CONTROL DESK ---
            st.markdown("### 🎛️ Excel-Style Column Filters")
            
            min_date = master_df["Prod_Date_Obj"].min()
            max_date_buffer = master_df["Prod_Date_Obj"].max() + pd.Timedelta(days=1)
            
            col_date1, col_date2, col_mach = st.columns([1, 1, 2])
            with col_date1:
                from_date = st.date_input("From Date", value=min_date, min_value=min_date, max_value=max_date_buffer, format="YYYY-MM-DD")
            with col_date2:
                to_date = st.date_input("To Date", value=max_date_buffer, min_value=min_date, max_value=max_date_buffer, format="YYYY-MM-DD")
            with col_mach:
                machine_opts = sorted(list(master_df["Machine"].unique()))
                selected_machines = st.multiselect("Select Machines for Analysis Matrix:", options=machine_opts, default=machine_opts)

            # Strict timestamp filtering boundaries construction
            full_filter_start = datetime.datetime.combine(from_date, datetime.time(0, 0, 0))
            full_filter_end = datetime.datetime.combine(to_date, datetime.time(23, 59, 59))

            # Filter the dataframe safely based on dates and active machine selectors
            filtered_df = master_df[
                (master_df["Zone_Start_Timestamp"] >= full_filter_start) & 
                (master_df["Zone_Start_Timestamp"] <= full_filter_end) & 
                (master_df["Machine"].isin(selected_machines))
            ]

            def display_selection_window(select_data, df_source):
                if select_data and isinstance(select_data, dict) and select_data.get("selection", {}).get("rows"):
                    sel_row_idx = select_data["selection"]["rows"][0]
                    if sel_row_idx < len(df_source):
                        row_data = df_source.iloc[sel_row_idx]
                        st.info(
                            f"⏱️ **EXACT TIME WINDOW FOR SELECTED RUN**\n\n"
                            f"• **Diameter Run Window:** `{row_data['Start Date & Time']}` to `{row_data['End Date & Time']}`\n\n"
                            f"• **RPM Run Window:** `{row_data['RPM_Start_Time']}` to `{row_data['RPM_End_Time']}`\n\n"
                            f"• **Speed Run Window:** `{row_data['Speed_Start_Time']}` to `{row_data['Speed_End_Time']}`"
                        )

            # --- Table 1: Diameter Zone Verification Table Rendering (Deduplicated Distinct Runs) ---
            st.markdown("---")
            st.subheader("📋 Diameter Zone Verification Table")
            
            # Deduplicate runs having identical machine, compound, diameter, RPM, and speed while keeping the longest duration
            p3_df = filtered_df.sort_values(by=["dia_seconds_raw"], ascending=False).drop_duplicates(
                subset=["Machine", "Diameter", "Compound", "RPM", "Speed"]
            ).sort_values(by=["Diameter", "Machine", "RPM"], ascending=[True, True, True]).reset_index(drop=True)
            
            p3_select = st.dataframe(p3_df[columns_ordered], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="table_1")
            display_selection_window(p3_select, p3_df)

            # --- Table 2: Cross-Machine Operating Parameters Comparison Table (Aggregated Matrix) ---
            st.markdown("---")
            st.subheader("📊 Cross-Machine Operating Parameters Comparison Table")
            
            # Group by physical comparative targets (Diameter, Machine, Compound) to prevent repeating identical parameters
            p4_df = filtered_df.sort_values(by=["dia_seconds_raw"], ascending=False).drop_duplicates(
                subset=["Diameter", "Machine", "Compound"]
            ).sort_values(by=["Diameter", "Machine", "RPM"], ascending=[True, True, True]).reset_index(drop=True)
            
            p4_select = st.dataframe(p4_df[columns_ordered], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="table_2")
            display_selection_window(p4_select, p4_df)
            
            # Master Exporter CSV Utility Buffer for Table 2
            csv_buffer = io.StringIO()
            p4_df[columns_ordered].to_csv(csv_buffer, index=False)
            st.download_button(
                label="📥 Download Master Comparison Matrix (CSV)",
                data=csv_buffer.getvalue(),
                file_name="production_master_comparison.csv",
                mime="text/csv"
            )

            # --- Table 3: Cross-Machine Less Than Target Screw RPM Zones ---
            st.markdown("---")
            st.subheader("⚠️ Cross-Machine Less Than Target Screw RPM Zones")
            
            p5_rows = []
            for idx, row in p4_df.iterrows():
                try:
                    target_rpm = float(row["Target Screw RPM"])
                    actual_rpm = float(row["RPM"])
                    if actual_rpm < target_rpm:
                        p5_rows.append(row)
                except (ValueError, TypeError):
                    pass

            p5_df = pd.DataFrame(p5_rows) if p5_rows else pd.DataFrame(columns=columns_ordered)
            
            p5_select = st.dataframe(p5_df[columns_ordered], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="table_3")
            display_selection_window(p5_select, p5_df)
            
            # Exporter CSV Utility Buffer for Table 3
            csv_buffer3 = io.StringIO()
            p5_df[columns_ordered].to_csv(csv_buffer3, index=False)
            st.download_button(
                label="📥 Download Less Than Target Screw RPM Matrix (CSV)",
                data=csv_buffer3.getvalue(),
                file_name="cross_machine_less_than_target_screw_rpm_zones.csv",
                mime="text/csv"
            )
        else:
            st.warning("No tracking zones matched your production window filtering metrics.")