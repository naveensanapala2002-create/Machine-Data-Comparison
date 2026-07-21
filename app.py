import streamlit as st
import pandas as pd
import numpy as np
import zipfile
import os
import io
import math
import datetime

# Set wide presentation layout
st.set_page_config(page_title="Machine Data Comparison", layout="wide")

st.title("Machine Data Comparison Application")
st.write("Upload a ZIP file containing machine data to automatically analyze all parameters across all production days instantly.")

# --- Persistent Target Master File Path & Parsing Helper ---
TARGETS_FILE = "screw_rpm_targets.csv"

def parse_target_excel(file_bytes_or_path):
    """Parses Excel files containing Compound and Target Screw RPM master definitions."""
    try:
        df_raw = pd.read_excel(file_bytes_or_path, header=None)
        header_row = 0
        for idx, row in df_raw.iterrows():
            row_str = " ".join([str(v).lower() for v in row.values if pd.notnull(v)])
            if 'compound' in row_str or 'rpm' in row_str:
                header_row = idx
                break
                
        df = pd.read_excel(file_bytes_or_path, header=header_row)
        df = df.dropna(how='all')
        
        comp_col = None
        rpm_col = None
        
        for col in df.columns:
            col_str = str(col).lower()
            if 'compound' in col_str:
                comp_col = col
            elif 'rpm' in col_str or 'speed' in col_str or 'specified' in col_str or 'target' in col_str:
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
            {"Compound": "XLPE", "Target Screw RPM": 40},
            {"Compound": "EPR", "Target Screw RPM": 25},
            {"Compound": "EPDM HARD", "Target Screw RPM": 12}
        ])
        st.session_state["target_df"] = default_data
        default_data.to_csv(TARGETS_FILE, index=False)

if "targets_is_editing" not in st.session_state:
    st.session_state["targets_is_editing"] = False

# --- Application Navigation Tabs ---
tab1, tab2 = st.tabs(["🏭 Machine Data Comparison", "🎯 Screw RPM Targets"])

with tab2:
    st.subheader("🎯 Screw RPM Target Master Configuration")
    
    if st.session_state["targets_is_editing"]:
        st.markdown("#### Edit Screw RPM Targets")
        st.info("Method 1: Upload an Excel file OR Method 2: Manually edit/add/remove records in the table below.")
        
        # Method 1: Import Excel File
        uploaded_excel = st.file_uploader("Import Excel File for Target RPMs", type=["xlsx", "xls"], key="target_excel_uploader")
        if uploaded_excel is not None:
            parsed_df = parse_target_excel(uploaded_excel)
            if not parsed_df.empty:
                st.session_state["target_df"] = parsed_df
                st.success("✅ Target RPMs imported successfully from Excel file!")
        
        # Method 2: Manual Data Entry
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
            st.success("✅ Target master saved permanently!")
            st.rerun()
    else:
        # Frozen Read-Only Display
        st.dataframe(st.session_state["target_df"], use_container_width=True, hide_index=True)
        if st.button("✏️ Edit Targets", key="btn_edit_targets"):
            st.session_state["targets_is_editing"] = True
            st.rerun()

with tab1:
    # --- File Uploader ---
    uploaded_file = st.file_uploader("Upload Machine Data ZIP File", type=["zip"])

    def parse_duration_hm(seconds):
        """Formats raw seconds into human-readable hours and minutes string (e.g., 4h 05m)."""
        if pd.isna(seconds) or seconds < 0:
            return "0m"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes:02d}m"
        return f"{minutes}m"

    # Track explicit metrics globally for session state consistency
    if "zip_status" not in st.session_state:
        st.session_state.zip_status = {"uploaded": "No", "total_files": 0, "excel_read": 0, "csv_read": 0, "failed_files": 0}
    if "file_details" not in st.session_state:
        st.session_state.file_details = []

    def parse_timestamp_strictly(series, filepath):
        """
        STRICT CENTRAL PARSER ENGINE:
        Directly targets YYYY-DD-MM sequences to completely eliminate automated month-flipping 
        by pandas, converting raw data strictly to correct datetime objects.
        """
        filename = os.path.basename(filepath)
        parsed_series = pd.Series(index=series.index, dtype='datetime64[ns]')
        
        clean_series = series.astype(str).str.strip()
        
        for idx, raw_val in clean_series.items():
            if pd.isna(raw_val) or raw_val.lower() in ['nan', 'nat', '']:
                continue
                
            # Normalize slashes or mixed separators to uniform hyphens
            normalized_val = raw_val.replace('/', '-')

            # Target: YYYY-DD-MM format parsing pattern safely
            try:
                parsed_series.loc[idx] = pd.to_datetime(normalized_val, format="%Y-%d-%m %H:%M:%S", errors='raise')
                continue
            except (ValueError, TypeError):
                pass
            try:
                parsed_series.loc[idx] = pd.to_datetime(normalized_val, format="%Y-%d-%m %H:%M", errors='raise')
                continue
            except (ValueError, TypeError):
                pass
                
            # Fallbacks for standard alternative format matches
            try:
                parsed_series.loc[idx] = pd.to_datetime(normalized_val, format="%d-%m-%Y %H:%M:%S", errors='raise')
                continue
            except (ValueError, TypeError):
                pass
            try:
                parsed_series.loc[idx] = pd.to_datetime(normalized_val, format="%Y-%m-%d %H:%M:%S", errors='raise')
                continue
            except (ValueError, TypeError):
                pass
            try:
                parsed_series.loc[idx] = pd.to_datetime(normalized_val, errors='raise')
                continue
            except (ValueError, TypeError) as e:
                err_msg = (
                    f"❌ **Critical Datetime Format Violation Detected!** \n"
                    f"**File Name:** `{filename}`  \n"
                    f"**Row Index Number:** `{idx + 2}`  \n"
                    f"**Malformed Value:** `{raw_val}`  \n"
                    f"**Parser Trace Reason:** {str(e)}"
                )
                st.error(err_msg)
                st.stop()
                
        return parsed_series

    def load_and_preprocess_file(file_bytes, filepath):
        """Phase 1: Ingests raw data via central gateway and enforces the factory Production Day Logic offset."""
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filename)[1].lower()
        
        status_entry = {"name": filename, "ext": ext, "status": "Failed", "reason": "", "rows": 0, "columns": {}, "available_dates": set()}
        
        try:
            if ext == '.csv':
                df = pd.read_csv(io.BytesIO(file_bytes), dtype=str)
                st.session_state.zip_status["csv_read"] += 1
            elif ext in ['.xlsx', '.xls']:
                df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
                st.session_state.zip_status["excel_read"] += 1
            else:
                status_entry["reason"] = "Unsupported format"
                st.session_state.zip_status["failed_files"] += 1
                st.session_state.file_details.append(status_entry)
                return pd.DataFrame(), set()
                
            df.columns = [c.strip() for c in df.columns]
            status_entry["rows"] = len(df)
            
            if df.empty:
                status_entry["reason"] = "Empty data source sheet structure"
                st.session_state.file_details.append(status_entry)
                return pd.DataFrame(), set()
                
            required_cols = ['Timestamp', 'Speed', 'Screw rpm', 'Comound', 'Thickness', 'Diameter', 'Operator']
            col_mapping = {}
            for rc in required_cols:
                found = False
                for actual_col in df.columns:
                    if rc.lower().replace(" ", "") == actual_col.lower().replace(" ", ""):
                        col_mapping[actual_col] = rc
                        found = True
                status_entry["columns"][rc] = "✓" if found else "✗"
                
            if "✗" in status_entry["columns"].values():
                status_entry["reason"] = "Required columns missing from dataset headers"
                st.session_state.file_details.append(status_entry)
                return pd.DataFrame(), set()
                
            df = df.rename(columns=col_mapping)
            if 'Comound' not in df.columns and 'Compound' in df.columns:
                df = df.rename(columns={'Compound': 'Comound'})
                
            df['Timestamp'] = parse_timestamp_strictly(df['Timestamp'], filepath)
            df = df.dropna(subset=['Timestamp']).sort_values('Timestamp').reset_index(drop=True)
            
            for col in ['Speed', 'Screw rpm', 'Thickness', 'Diameter']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['Production_Date'] = (df['Timestamp'] - pd.Timedelta(hours=6)).dt.date
            
            detected_prod_dates = {d for d in df['Production_Date'].unique() if pd.notnull(d)}
            status_entry["available_dates"] = detected_prod_dates

            df['Int_Diameter'] = df['Diameter'].apply(lambda x: math.trunc(float(x)) if pd.notnull(x) and str(x).strip() != "" else np.nan)
            df['Int_Speed'] = df['Speed'].apply(lambda x: math.trunc(float(x)) if pd.notnull(x) and str(x).strip() != "" else np.nan)
            df['Int_RPM'] = df['Screw rpm'].apply(lambda x: math.trunc(float(x)) if pd.notnull(x) and str(x).strip() != "" else np.nan)
            
            df = df.dropna(subset=['Int_Diameter']).reset_index(drop=True)
            
            status_entry["status"] = "Read Successfully"
            st.session_state.file_details.append(status_entry)
            return df, detected_prod_dates
            
        except Exception as e:
            status_entry["reason"] = f"Pipeline execution error: {str(e)}"
            st.session_state.zip_status["failed_files"] += 1
            st.session_state.file_details.append(status_entry)
            return pd.DataFrame(), set()

    if uploaded_file is not None:
        zip_bytes_cached = {}
        
        with zipfile.ZipFile(uploaded_file) as z:
            infolist = z.infolist()
            for file_info in infolist:
                if not file_info.is_dir() and '__MACOSX' not in file_info.filename:
                    filename = file_info.filename
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in ['.csv', '.xlsx', '.xls']:
                        file_bytes = z.read(filename)
                        zip_bytes_cached[filename] = file_bytes

        st.session_state.zip_status = {"uploaded": "Yes", "total_files": len(zip_bytes_cached), "excel_read": 0, "csv_read": 0, "failed_files": 0}
        st.session_state.file_details = []
        
        all_extracted_rows = []

        for filename, file_bytes in zip_bytes_cached.items():
            machine_clean_name = os.path.basename(filename).split(" - ")[-1].replace(".csv", "").replace(".xlsx", "").replace(".xls", "").strip()
            raw_continuous_df, _ = load_and_preprocess_file(file_bytes, filename)
            
            if raw_continuous_df.empty:
                continue
            
            # REQUIREMENT 1 (Zone Logic Enhancement): Split zone blocks safely whenever Diameter, Operator, Comound, or Thickness changes
            condition_dia = raw_continuous_df['Int_Diameter'] != raw_continuous_df['Int_Diameter'].shift()
            condition_op  = raw_continuous_df['Operator'] != raw_continuous_df['Operator'].shift()
            condition_cmp = raw_continuous_df['Comound'] != raw_continuous_df['Comound'].shift()
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
                ].copy()
                
                if valid_records.empty:
                    continue
                    
                # Compute Diameter Block Duration (Total valid runtime inside block run)
                dia_deltas = valid_records['Timestamp'].diff().dropna().dt.total_seconds()
                dia_seconds = dia_deltas[dia_deltas <= 300].sum()
                if dia_seconds == 0:
                    dia_seconds = (zone_end_dt - zone_start_dt).total_seconds()
                
                # REQUIREMENT CHECK LAYER 1: Diameter Block Duration must be greater than 20 minutes (1200 seconds)
                if dia_seconds <= 1200:
                    continue
                    
                # REQUIREMENT 2: Display record count as "X minutes" format inside columns without dropping core clock calculations
                diameter_duration_str = f"{len(valid_records)} minutes"
                duration_hm_str = parse_duration_hm(dia_seconds)
                duration_min_str = f"{math.ceil(dia_seconds / 60.0)} minutes"
                
                # Find Most Repeated Integer RPM first
                mode_rpm_series = valid_records['Int_RPM'].mode()
                if mode_rpm_series.empty:
                    continue
                selected_int_rpm = mode_rpm_series.iloc[0]
                
                # Compute RPM Duration: Most repeated rpm duration corresponding to same diameter zone block
                rpm_subset_df = valid_records[valid_records['Int_RPM'] == selected_int_rpm]
                rpm_deltas = rpm_subset_df['Timestamp'].diff().dropna().dt.total_seconds()
                rpm_seconds = rpm_deltas[rpm_deltas <= 300].sum()
                if rpm_seconds == 0 and len(rpm_subset_df) > 0:
                    rpm_seconds = (rpm_subset_df['Timestamp'].max() - rpm_subset_df['Timestamp'].min()).total_seconds()
                
                # REQUIREMENT CHECK LAYER 2: RPM Duration must be greater than 20 minutes (1200 seconds)
                if rpm_seconds <= 1200:
                    continue
                    
                # REQUIREMENT 2: Display record count as "X minutes" format inside table mapping
                rpm_duration_str = f"{len(rpm_subset_df)} minutes"
                
                # Find Corresponding Most Repeated Integer Speed second
                rpm_filtered_df = valid_records[valid_records['Int_RPM'] == selected_int_rpm]
                mode_speed_series = rpm_filtered_df['Int_Speed'].mode()
                if mode_speed_series.empty:
                    continue
                selected_int_speed = mode_speed_series.iloc[0]
                
                # Compute Speed Duration: Most repeated speed duration corresponding to same rpm zone block subset
                speed_subset_df = rpm_filtered_df[rpm_filtered_df['Int_Speed'] == selected_int_speed]
                speed_deltas = speed_subset_df['Timestamp'].diff().dropna().dt.total_seconds()
                speed_seconds = speed_deltas[speed_deltas <= 300].sum()
                if speed_seconds == 0 and len(speed_subset_df) > 0:
                    speed_seconds = (speed_subset_df['Timestamp'].max() - speed_subset_df['Timestamp'].min()).total_seconds()
                
                # REQUIREMENT CHECK LAYER 3: Speed Duration must be greater than 20 minutes (1200 seconds)
                if speed_seconds <= 1200:
                    continue
                    
                # REQUIREMENT 2: Display record count as "X minutes" format inside table mapping
                speed_duration_str = f"{len(speed_subset_df)} minutes"
                
                def get_primary_value(series):
                    modes = series.mode()
                    return modes.iloc[0] if not modes.empty else (series.iloc[0] if not series.empty else "N/A")
                    
                operator = get_primary_value(valid_records['Operator'])
                compound = get_primary_value(valid_records['Comound'])
                thickness = get_primary_value(valid_records['Thickness'])
                current_int_dia = int(valid_records['Int_Diameter'].iloc[0])
                
                start_time_str = zone_start_dt.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(zone_start_dt) else "NaT"
                end_time_str = zone_end_dt.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(zone_end_dt) else "NaT"
                
                # Precise timestamps matching each internal duration type segment (Requirement 3: Kept exactly identical)
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
                    "RPM Duration": rpm_duration_str,
                    "Speed": selected_int_speed,
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
                    "Speed_End_Time": speed_end_str
                })

        # Exact columns sequence layout matches requirement parameters 100%
        columns_ordered = [
            "Machine", "Operator", "Compound", "Diameter", "Diameter Duration", 
            "RPM", "RPM Duration", "Speed", "Speed Duration", "Thickness", 
            "Start Date & Time", "End Date & Time", "Duration (Hours & Minutes)", "Duration (Minutes)"
        ]

        if all_extracted_rows:
            master_df = pd.DataFrame(all_extracted_rows)

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

            target_columns = ["Diameter Duration", "RPM Duration", "Speed Duration", "Duration (Hours & Minutes)", "Duration (Minutes)"]

            # --- Table 1: Diameter Zone Verification Table Rendering ---
            st.markdown("---")
            st.subheader("📋 Diameter Zone Verification Table")
            p3_df = filtered_df.sort_values(by=["Diameter", "Machine", "RPM"], ascending=[True, True, True]).reset_index(drop=True)
            
            p3_select = st.dataframe(p3_df[columns_ordered], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-cell", key="table_1")
            
            # Tuple extraction layer for Table 1 (Requirement 4: Kept completely identical)
            if p3_select and "selection" in p3_select and p3_select["selection"].get("cells"):
                cell_info = p3_select["selection"]["cells"][0]
                sel_row_idx = cell_info[0] if isinstance(cell_info, tuple) else cell_info.get("row")
                sel_col_name = cell_info[1] if isinstance(cell_info, tuple) else cell_info.get("column")
                
                if sel_row_idx is not None and sel_row_idx < len(p3_df):
                    row_data = p3_df.iloc[sel_row_idx]
                    
                    # Dynamic matching layer: Extract exact run windows per duration type
                    if sel_col_name in ["Diameter Duration", "Duration (Hours & Minutes)", "Duration (Minutes)"]:
                        st.info(f"⏱️ **EXACT WINDOW FOR: {sel_col_name}**\n\n"
                                f"• **Start Date & Time:** `{row_data['Start Date & Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['End Date & Time']}`")
                    elif sel_col_name == "RPM Duration":
                        st.info(f"⏱️ **EXACT WINDOW FOR: RPM Duration (RPM: {row_data['RPM']})**\n\n"
                                f"• **Start Date & Time:** `{row_data['RPM_Start_Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['RPM_End_Time']}`")
                    elif sel_col_name == "Speed Duration":
                        st.info(f"⏱️ **EXACT WINDOW FOR: Speed Duration (Speed: {row_data['Speed']})**\n\n"
                                f"• **Start Date & Time:** `{row_data['Speed_Start_Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['Speed_End_Time']}`")

            # --- Table 2: Cross-Machine Comparison Table Rendering ---
            st.markdown("---")
            st.subheader("📊 Cross-Machine Operating Parameters Comparison Table")
            p4_df = filtered_df.sort_values(by=["Diameter", "Machine", "RPM"], ascending=[True, True, True]).reset_index(drop=True)
            
            p4_select = st.dataframe(p4_df[columns_ordered], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-cell", key="table_2")
            
            # Tuple extraction layer for Table 2 (Requirement 4: Kept completely identical)
            if p4_select and "selection" in p4_select and p4_select["selection"].get("cells"):
                cell_info = p4_select["selection"]["cells"][0]
                sel_row_idx = cell_info[0] if isinstance(cell_info, tuple) else cell_info.get("row")
                sel_col_name = cell_info[1] if isinstance(cell_info, tuple) else cell_info.get("column")
                
                if sel_row_idx is not None and sel_row_idx < len(p4_df):
                    row_data = p4_df.iloc[sel_row_idx]
                    
                    # Dynamic matching layer: Extract exact run windows per duration type
                    if sel_col_name in ["Diameter Duration", "Duration (Hours & Minutes)", "Duration (Minutes)"]:
                        st.info(f"⏱️ **EXACT WINDOW FOR: {sel_col_name}**\n\n"
                                f"• **Start Date & Time:** `{row_data['Start Date & Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['End Date & Time']}`")
                    elif sel_col_name == "RPM Duration":
                        st.info(f"⏱️ **EXACT WINDOW FOR: RPM Duration (RPM: {row_data['RPM']})**\n\n"
                                f"• **Start Date & Time:** `{row_data['RPM_Start_Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['RPM_End_Time']}`")
                    elif sel_col_name == "Speed Duration":
                        st.info(f"⏱️ **EXACT WINDOW FOR: Speed Duration (Speed: {row_data['Speed']})**\n\n"
                                f"• **Start Date & Time:** `{row_data['Speed_Start_Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['Speed_End_Time']}`")
            
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
            
            # Build Screw RPM Target Master dictionary mapping normalized compound name -> Target RPM
            target_dict = {}
            if "target_df" in st.session_state and not st.session_state["target_df"].empty:
                for _, r in st.session_state["target_df"].iterrows():
                    comp_name = str(r["Compound"]).strip().lower()
                    try:
                        target_dict[comp_name] = float(r["Target Screw RPM"])
                    except (ValueError, TypeError):
                        pass

            # Filter p4_df rows where Compound exists in Master AND Actual RPM < Target Screw RPM
            p5_rows = []
            if target_dict:
                for idx, row in p4_df.iterrows():
                    comp_key = str(row["Compound"]).strip().lower()
                    if comp_key in target_dict:
                        target_rpm = target_dict[comp_key]
                        try:
                            actual_rpm = float(row["RPM"])
                            if actual_rpm < target_rpm:
                                p5_rows.append(row)
                        except (ValueError, TypeError):
                            pass

            p5_df = pd.DataFrame(p5_rows) if p5_rows else pd.DataFrame(columns=p4_df.columns)
            
            p5_select = st.dataframe(p5_df[columns_ordered], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-cell", key="table_3")
            
            # Tuple extraction layer for Table 3
            if p5_select and "selection" in p5_select and p5_select["selection"].get("cells"):
                cell_info = p5_select["selection"]["cells"][0]
                sel_row_idx = cell_info[0] if isinstance(cell_info, tuple) else cell_info.get("row")
                sel_col_name = cell_info[1] if isinstance(cell_info, tuple) else cell_info.get("column")
                
                if sel_row_idx is not None and sel_row_idx < len(p5_df):
                    row_data = p5_df.iloc[sel_row_idx]
                    
                    if sel_col_name in ["Diameter Duration", "Duration (Hours & Minutes)", "Duration (Minutes)"]:
                        st.info(f"⏱️ **EXACT WINDOW FOR: {sel_col_name}**\n\n"
                                f"• **Start Date & Time:** `{row_data['Start Date & Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['End Date & Time']}`")
                    elif sel_col_name == "RPM Duration":
                        st.info(f"⏱️ **EXACT WINDOW FOR: RPM Duration (RPM: {row_data['RPM']})**\n\n"
                                f"• **Start Date & Time:** `{row_data['RPM_Start_Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['RPM_End_Time']}`")
                    elif sel_col_name == "Speed Duration":
                        st.info(f"⏱️ **EXACT WINDOW FOR: Speed Duration (Speed: {row_data['Speed']})**\n\n"
                                f"• **Start Date & Time:** `{row_data['Speed_Start_Time']}`\n\n"
                                f"• **End Date & Time:** `{row_data['Speed_End_Time']}`")
            
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