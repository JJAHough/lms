import streamlit as st
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import sqlite3
import qrcode
import time
from io import BytesIO
from PIL import Image

# --------------------------------------------------------
# 1. INITIALIZE PERSISTENT SQLITE DATABASE STORAGE
# --------------------------------------------------------
DB_FILE = "warehouse_supply.db"

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Table 1: Employee Profiles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            employee_id TEXT PRIMARY KEY,
            name TEXT,
            role TEXT,
            status TEXT
        )
    """)
    
    # Create Table 2: Daily Attendance Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            date TEXT,
            employee_id TEXT,
            name TEXT,
            status TEXT,
            ppe_compliant INTEGER,
            time_scanned TEXT,
            verification_photo_blob BLOB
        )
    """)
    
    # Create Table 3: KPI Target Configurations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kpi_settings (
            kpi_name TEXT PRIMARY KEY,
            target_value REAL
        )
    """)
    
    # Create Table 4: Performance Value Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kpi_logs (
            date TEXT,
            employee_id TEXT,
            name TEXT,
            kpi_name TEXT,
            value REAL
        )
    """)
    
    # Seed default baseline rows if database is completely new
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone() == 0:
        default_workers = [
            ("EMP001", "John Doe", "Forklift Driver", "Active"),
            ("EMP002", "Jane Smith", "Picker/Packer", "Active"),
            ("EMP003", "Bob Johnson", "Sorter", "Active")
        ]
        cursor.executemany("INSERT INTO employees VALUES (?, ?, ?, 'Active')", default_workers)
        
    cursor.execute("SELECT COUNT(*) FROM kpi_settings")
    if cursor.fetchone() == 0:
        default_targets = [
            ("Boxes Packed", 50.0),
            ("Safety Compliance Score", 98.0),
            ("Attendance Punctuality", 95.0)
        ]
        cursor.executemany("INSERT INTO kpi_settings VALUES (?, ?)", default_targets)
        
    conn.commit()
    conn.close()

init_db()

def get_active_employees():
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM employees WHERE status = 'Active'", conn)
    conn.close()
    if not df.empty:
        df = df.rename(columns={"employee_id": "Employee ID", "name": "Name", "role": "Role", "status": "Status"})
    return df

# --------------------------------------------------------
# 2. APP LAYOUT & NAVIGATION
# --------------------------------------------------------
st.set_page_config(page_title="Warehouse Labour Management System", layout="wide")
st.title("🏭 Warehouse Labour Management System")
st.caption("Labour Supply Company Portal for Warehouse Supervisors")

menu = ["📈 Weekly Dashboard", "👥 Employee Management", "📝 Daily Attendance", "🎯 Setup & Log KPIs"]
choice = st.sidebar.selectbox("Navigation Menu", menu)

# --------------------------------------------------------
# 3. MODULE: EMPLOYEE MANAGEMENT
# --------------------------------------------------------
if choice == "👥 Employee Management":
    st.header("Employee Roster & ID Badge Generation")
    
    tab1, tab2, tab3 = st.tabs(["➕ Add New Employee", "✏️ Edit Employee Roster", "🔲 Print Employee QR Badges"])
    
    with tab1:
        st.subheader("Register a New Warehouse Worker")
        with st.form("add_employee_form", clear_on_submit=True):
            new_id = st.text_input("Employee ID (e.g., EMP004)")
            new_name = st.text_input("Full Name")
            new_role = st.selectbox("Warehouse Role", ["Picker/Packer", "Forklift Driver", "Sorter", "Loader/Unloader", "Supervisor"])
            submit_btn = st.form_submit_button("Save Employee")
            
            if submit_btn:
                if new_id and new_name:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    try:
                        cursor.execute("INSERT INTO employees VALUES (?, ?, ?, 'Active')", (new_id, new_name, new_role))
                        conn.commit()
                        st.success(f"Successfully registered {new_name}!")
                    except sqlite3.IntegrityError:
                        st.error("This Employee ID already exists!")
                    finally:
                        conn.close()
                else:
                    st.warning("Please fill out all fields.")

    with tab2:
        st.subheader("Current Employee Roster")
        conn = get_db_connection()
        current_df = pd.read_sql("SELECT * FROM employees", conn)
        conn.close()
        
        edited_df = st.data_editor(current_df, num_rows="dynamic", key="roster_editor")
        if st.button("Save Roster Changes"):
            conn = get_db_connection()
            edited_df.to_sql("employees", conn, if_exists="replace", index=False)
            conn.close()
            st.success("Roster updated successfully!")

    with tab3:
        st.subheader("Generate & Export QR Code Badges")
        active_workers = get_active_employees()
        
        if active_workers.empty:
            st.info("No active profiles available to generate badges.")
        else:
            st.write("Select an employee below to view and save their printable check-in QR card:")
            selected_worker_str = st.selectbox(
                "Select Worker", 
                active_workers.apply(lambda r: f"{r['Employee ID']} - {r['Name']}", axis=1)
            )
            
            selected_id = selected_worker_str.split(" - ")[0]
            selected_name = selected_worker_str.split(" - ")[1]
            
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(selected_id)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buf = BytesIO()
            img.save(buf, format="PNG")
            byte_im = buf.getvalue()
            
            col_card, col_badge_info = st.columns(2)
            with col_card:
                st.image(byte_im, width=220, caption=f"Scan Card for ID: {selected_id}")
            with col_badge_info:
                st.markdown(f"### **{selected_name}**")
                st.write(f"**Staff Placement Reference:** {selected_id}")
                st.write("Instruct employees to present this badge at the checkpoint station monitor.")
                st.download_button(
                    label=f"📥 Download {selected_id} QR Badge (PNG)",
                    data=byte_im,
                    file_name=f"QR_Badge_{selected_id}.png",
                    mime="image/png"
                )

# --------------------------------------------------------
# 4. MODULE: DAILY ATTENDANCE
# --------------------------------------------------------
elif choice == "📝 Daily Attendance":
    st.header("Daily Attendance & Instant Snapshot Verification")
    
    attendance_date = st.date_input("Select Date for Attendance", datetime.date.today())
    date_str = str(attendance_date)
    active_workers = get_active_employees()
    
    if active_workers.empty:
        st.warning("No active employees found.")
    else:
        # --- SUB-SECTION: LIVE CAMERA QR SCANNING WITH GREEN FLASH FEEDBACK ---
        st.markdown("### 📷 Live Desk QR Check-In Scanner (Auto-Snapshot enabled)")
        enable_scanner = st.checkbox("Turn On Webcam Scanner Window")
        
        if enable_scanner:
            img_file = st.camera_input("Hold worker QR badge clearly in front of camera lens:")
            
            if img_file is not None:
                try:
                    import cv2
                    import numpy as np
                    
                    file_bytes = np.asarray(bytearray(img_file.read()), dtype=np.uint8)
                    opencv_img = cv2.imdecode(file_bytes, 1)
                    
                    detector = cv2.QRCodeDetector()
                    scanned_val, _, _ = detector.detectAndDecode(opencv_img)
                    
                    if scanned_val:
                        match = active_workers[active_workers["Employee ID"] == scanned_val]
                        
                        if not match.empty:
                            matched_name = match["Name"].values[0]
                            
                            # NEW: Inject a temporary green overlay container across the app layout
                            flash_placeholder = st.empty()
                            flash_placeholder.markdown("""
                                <div style="fixed; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; 
                                            background-color: rgba(40, 167, 69, 0.95); z-index: 99999; 
                                            display: flex; flex-direction: column; justify-content: center; align-items: center;
                                            color: white; font-family: sans-serif; transition: all 0.5s ease;">
                                    <h1 style="font-size: 80px; margin: 0;">🎯 VERIFIED PRESENT</h1>
                                    <h2 style="font-size: 40px; margin-top: 10px;">""" + f"{matched_name} ({scanned_val})" + """</h2>
                                    <p style="font-size: 20px; opacity: 0.8; margin-top: 5px;">Photo captured & logged into system rows successfully.</p>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            # Run core database commit processing queries behind the overlay screen
                            raw_photo_bytes = img_file.getvalue()
                            now_time = datetime.datetime.now().strftime("%H:%M:%S")
                            
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            
                            cursor.execute(f"DELETE FROM attendance WHERE date='{date_str}' AND employee_id='{scanned_val}'")
                            cursor.execute(
                                "INSERT INTO attendance VALUES (?, ?, ?, 'Present', 1, ?, ?)", 
                                (date_str, scanned_val, matched_name, now_time, sqlite3.Binary(raw_photo_bytes))
                            )
                            
                            cursor.execute(f"DELETE FROM kpi_logs WHERE date='{date_str}' AND employee_id='{scanned_val}' AND kpi_name IN ('Attendance Punctuality', 'Safety Compliance Score')")
                            cursor.execute("INSERT INTO kpi_logs VALUES (?, ?, ?, 'Attendance Punctuality', 100.0)", (date_str, scanned_val, matched_name))
                            cursor.execute("INSERT INTO kpi_logs VALUES (?, ?, ?, 'Safety Compliance Score', 100.0)", (date_str, scanned_val, matched_name))
                            
                            conn.commit()
                            conn.close()
                            
                            # Let the green alert display for 1 second before clearing and reloading the page
                            time.sleep(1.0)
                            flash_placeholder.empty()
                            st.rerun()
                        else:
                            st.error(f"Scanned data code '{scanned_val}' does not match any profile in your active system.")
                except Exception as ex:
                    st.error(f"Scanner engine error occurred: {ex}")

        st.markdown("---")
        
        # --- SUB-SECTION: MANUAL OVERRIDE ROSTER FORM ---
        st.markdown("### 📋 Manual Override Ledger Sheets")
        conn = get_db_connection()
        existing_att = pd.read_sql(f"SELECT * FROM attendance WHERE date = '{date_str}'", conn)
        conn.close()

        with st.form("attendance_form"):
            attendance_records = []
            
            for idx, row in active_workers.iterrows():
                emp_id = row["Employee ID"]
                emp_name = row["Name"]
                
                default_status = "Present"
                default_ppe = True
                default_time = "Manual Log"
                
                if not existing_att.empty and emp_id in existing_att["employee_id"].values:
                    matching_row = existing_att[existing_att["employee_id"] == emp_id]
                    default_status = matching_row["status"].values[0]
                    default_ppe = bool(matching_row["ppe_compliant"].values[0])
                    default_time = str(matching_row["time_scanned"].values[0])
                
                st.markdown(f"**{emp_name} ({emp_id})** — *{row['Role']}* | Checked: `{default_time}`")
                
                if not existing_att.empty and emp_id in existing_att["employee_id"].values:
                    photo_val = existing_att[existing_att["employee_id"] == emp_id]["verification_photo_blob"].values[0]
                    if photo_val:
                        st.image(photo_val, width=120, caption="Audit verification snap")
                
                col_status, col_ppe = st.columns(2)
                with col_status:
                    status = st.radio(
                        f"Status for {emp_id}", ["Present", "Absent", "Sick Leave", "Late"], 
                        index=["Present", "Absent", "Sick Leave", "Late"].index(default_status), 
                        horizontal=True, label_visibility="collapsed"
                    )
                with col_ppe:
                    ppe_ok = st.checkbox("✅ PPE Compliant", value=default_ppe, key=f"ppe_{emp_id}_{idx}")
                
                final_ppe = ppe_ok if status in ["Present", "Late"] else False
                
                attendance_records.append({
                    "date": date_str, "employee_id": emp_id, "name": emp_name, 
                    "status": status, "ppe_compliant": 1 if final_ppe else 0, "time_scanned": default_time
                })
                st.markdown("---")
            
            save_attendance = st.form_submit_button("Save Attendance Ledger Overrides")
            
            if save_attendance:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                for r in attendance_records:
                    cursor.execute(f"SELECT verification_photo_blob FROM attendance WHERE date='{date_str}' AND employee_id='{r['employee_id']}'")
                    existing_photo = cursor.fetchone()
                    photo_to_save = existing_photo[0] if existing_photo and existing_photo[0] else None
                    
                    cursor.execute(f"DELETE FROM attendance WHERE date = '{date_str}' AND employee_id='{r['employee_id']}'")
                    cursor.execute(
                        "INSERT INTO attendance VALUES (?, ?, ?, ?, ?, ?, ?)", 
                        (r["date"], r["employee_id"], r["name"], r["status"], r["ppe_compliant"], r["time_scanned"], photo_to_save)
                    )
                    
                    cursor.execute(f"DELETE FROM kpi_logs WHERE date='{date_str}' AND employee_id='{r['employee_id']}' AND kpi_name IN ('Attendance Punctuality', 'Safety Compliance Score')")
                    if r["status"] in ["Present", "Late"]:
                        p_score = 100.0 if r["status"] == "Present" else 0.0
                        s_score = 100.0 if r["ppe_compliant"] == 1 else 0.0
                        cursor.execute("INSERT INTO kpi_logs VALUES (?, ?, ?, 'Attendance Punctuality', ?)", (date_str, r["employee_id"], r["name"], p_score))
                        cursor.execute("INSERT INTO kpi_logs VALUES (?, ?, ?, 'Safety Compliance Score', ?)", (date_str, r["employee_id"], r["name"], s_score))
                        
                conn.commit()
                conn.close()
                st.success("Manual changes saved successfully.")
                st.rerun()

# --------------------------------------------------------
# 5. MODULE: SETUP & CAPTURE KPIS DAILY
# --------------------------------------------------------
elif choice == "🎯 Setup & Log KPIs":
    st.header("Daily Performance KPIs")
    
    tab1, tab2 = st.tabs(["📝 Log Daily KPIs", "⚙️ Configure Global KPIs & Targets"])
    
    with tab2:
        st.subheader("Manage Custom Tracking Metrics & Targets")
        col_new1, col_new2 = st.columns(2)
        with col_new1:
            new_kpi = st.text_input("Add New Metric Name (e.g., 'Pallets Moved')")
        with col_new2:
            new_target = st.number_input("Set Target Value for This Metric", min_value=0.0, value=10.0, step=1.0)
            
        if st.button("Add Metric & Target") and new_kpi:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO kpi_settings VALUES (?, ?)", (new_kpi, float(new_target)))
                conn.commit()
                st.success(f"Metric '{new_kpi}' added successfully!")
            except sqlite3.IntegrityError:
                st.error("Metric already exists.")
            finally:
                conn.close()
                st.rerun()
        
        st.markdown("#### Current Target Configurations")
        conn = get_db_connection()
        settings_df = pd.read_sql("SELECT * FROM kpi_settings", conn)
        conn.close()
        for idx, row in settings_df.iterrows():
            item = row["kpi_name"]
            is_auto = " (Automated)" if item in ["Attendance Punctuality", "Safety Compliance Score"] else ""
            st.text(f"🎯 {item}{is_auto} — Target Average: {row['target_value']:.1f}")

    with tab1:
        st.subheader("Capture Daily Worker Metrics")
        kpi_date = st.date_input("Select Performance Date", datetime.date.today())
        date_str = str(kpi_date)
        active_workers = get_active_employees()
        
        conn = get_db_connection()
        settings_df = pd.read_sql("SELECT * FROM kpi_settings", conn)
        conn.close()
        
        if settings_df.empty:
            st.warning("Please configure at least one KPI metric first.")
        else:
            hidden_kpis = ["Attendance Punctuality", "Safety Compliance Score"]
            manual_kpi_options = [row["kpi_name"] for idx, row in settings_df.iterrows() if row["kpi_name"] not in hidden_kpis]
            
            if not manual_kpi_options:
                st.info("All current KPIs are automated via the Attendance logging module framework configurations.")
            else:
                selected_kpi = st.selectbox("Select Metric to Log", manual_kpi_options)
                
                conn = get_db_connection()
                existing_logs = pd.read_sql(f"SELECT * FROM kpi_logs WHERE date='{date_str}' AND kpi_name='{selected_kpi}'", conn)
                conn.close()
                
                with st.form("kpi_form"):
                    kpi_records = []
                    for idx, row in active_workers.iterrows():
                        emp_id = row["Employee ID"]
                        emp_name = row["Name"]
                        
                        default_val = 0.0
                        if not existing_logs.empty and emp_id in existing_logs["employee_id"].values:
                            default_val = float(existing_logs[existing_logs["employee_id"] == emp_id]["value"].values)
                        
                        val = st.number_input(f"Value for {emp_name} ({emp_id})", min_value=0.0, value=default_val, step=1.0)
                        kpi_records.append({"date": date_str, "employee_id": emp_id, "name": emp_name, "kpi_name": selected_kpi, "value": val})
                    
                    submit_kpi = st.form_submit_button("Save KPI Scores")
                    
                    if submit_kpi:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute(f"DELETE FROM kpi_logs WHERE date='{date_str}' AND kpi_name='{selected_kpi}'")
                        for rec in kpi_records:
                            cursor.execute("INSERT INTO kpi_logs VALUES (?, ?, ?, ?, ?)", (rec["date"], rec["employee_id"], rec["name"], rec["kpi_name"], rec["value"]))
                        conn.commit()
                        conn.close()
                        st.success("KPI Scores saved successfully!")
                        st.rerun()

# --------------------------------------------------------
# 6. MODULE: WEEKLY DASHBOARD
# --------------------------------------------------------
elif choice == "📈 Weekly Dashboard":
    st.header("Weekly Operations Dashboard")
    
    today = datetime.date.today()
    start_week = st.date_input("Start Date for Dashboard View", today - datetime.timedelta(days=6))
    
    conn = get_db_connection()
    settings_df = pd.read_sql("SELECT * FROM kpi_settings", conn)
    kpi_logs_all = pd.read_sql("SELECT * FROM kpi_logs", conn)
    attendance_all = pd.read_sql("SELECT * FROM attendance", conn)
    conn.close()
    
    kpi_options = list(settings_df["kpi_name"].values) if not settings_df.empty else ["Boxes Packed"]
    chosen_dashboard_kpi = st.selectbox("📊 Select KPI for Card & Chart Filtering", kpi_options, index=0)
    
    target_row = settings_df[settings_df["kpi_name"] == chosen_dashboard_kpi] if not settings_df.empty else pd.DataFrame()
    weekly_target_threshold = float(target_row["target_value"].values) if not target_row.empty else 50.0
    
    start_str, today_str = str(start_week), str(today)
    
    if not attendance_all.empty:
        filtered_att = attendance_all[(attendance_all['date'] >= start_str) & (attendance_all['date'] <= today_str)]
    else:
        filtered_att = pd.DataFrame()
        
    if not kpi_logs_all.empty:
        filtered_kpi = kpi_logs_all[(kpi_logs_all['date'] >= start_str) & (kpi_logs_all['date'] <= today_str)]
    else:
        filtered_kpi = pd.DataFrame()

    bonus_workers = []
    if not filtered_att.empty:
        for emp_id in filtered_att["employee_id"].unique():
            worker_week = filtered_att[filtered_att["employee_id"] == emp_id]
            worker_name = worker_week["name"].iloc[0]
            
            has_lates = "Late" in worker_week["status"].values
            has_absents = "Absent" in worker_week["status"].values
            onsite_days = worker_week[worker_week["status"].isin(["Present", "Late"])]
            failed_ppe = (onsite_days["ppe_compliant"] == 0).any() if not onsite_days.empty else False
            
            if not has_lates and not has_absents and not failed_ppe and not worker_week.empty:
                bonus_workers.append(worker_name)

    # --- KPI Dashboard Summary Overview Cards Row Grid ---
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Active Supply Staff", len(get_active_employees()))
    with col2:
        if not filtered_att.empty:
            presents = len(filtered_att[filtered_att["status"] == "Present"])
            st.metric("Attendance Rate", f"{((presents / len(filtered_att)) * 100):.1f}%")
        else:
            st.metric("Attendance Rate", "No Data")
    with col3:
        if not filtered_att.empty:
            on_site = filtered_att[filtered_att["status"].isin(["Present", "Late"])]
            ppe_rate = (on_site["ppe_compliant"].sum() / len(on_site)) * 100 if not on_site.empty else 0.0
            st.metric("PPE Safety Compliance", f"{ppe_rate:.1f}%")
        else:
            st.metric("PPE Safety Compliance", "No Data")
    with col4:
        if not filtered_kpi.empty:
            custom_data = filtered_kpi[filtered_kpi["kpi_name"] == chosen_dashboard_kpi]
            if not custom_data.empty:
                calculated_avg = custom_data["value"].mean()
                is_pct = "%" if "Punctuality" in chosen_dashboard_kpi or "Safety" in chosen_dashboard_kpi else ""
                card_bg, text_color, status_symbol = ("#D4EDDA", "#155724", "✅ Pass") if calculated_avg >= weekly_target_threshold else ("#F8D7DA", "#721C24", "⚠️ Fail")
                st.markdown(f"""
                    <div style="background-color: {card_bg}; padding: 6px; border-radius: 6px; border: 1px solid {text_color}; text-align: center;">
                        <p style="margin: 0; font-size: 12px; color: {text_color}; font-weight: bold;">Avg {chosen_dashboard_kpi}</p>
                        <h3 style="margin: 2px 0; color: {text_color}; font-size: 22px;">{calculated_avg:.1f}{is_pct}</h3>
                        <p style="margin: 0; font-size: 10px; color: {text_color};">Target: {weekly_target_threshold:.1f}{is_pct} ({status_symbol})</p>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.metric(f"Avg {chosen_dashboard_kpi}", "0.0")
        else:
            st.metric(f"Avg {chosen_dashboard_kpi}", "No Data")
    with col5:
        st.metric("⭐ Bonus Qualifiers", len(bonus_workers))

    if bonus_workers:
        st.success(f"🏅 **Weekly Bonus Recipients (100% Punctual & Safe):** {', '.join(bonus_workers)}")

    st.markdown("---")

    # --- Charts Visualizations Graphing Grid Rows ---
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Attendance Breakdown")
        if not filtered_att.empty:
            status_counts = filtered_att["status"].value_counts()
            fig, ax = plt.subplots(figsize=(5, 4))
            status_counts.plot(kind='bar', color=['#4CAF50', '#F44336', '#FFC107', '#2196F3'], ax=ax)
            ax.set_ylabel("Days Tracked")
            plt.xticks(rotation=40)
            st.pyplot(fig)
        else:
            st.info("No logs present for this date range scope.")
    with c2:
        st.subheader(f"Top Performers - {chosen_dashboard_kpi}")
        if not filtered_kpi.empty:
            chart_data = filtered_kpi[filtered_kpi["kpi_name"] == chosen_dashboard_kpi]
            if not chart_data.empty:
                leaderboard = chart_data.groupby("name")["value"].sum().sort_values(ascending=False)
                fig, ax = plt.subplots(figsize=(5, 4))
                leaderboard.plot(kind='barh', color='#8884d8', ax=ax)
                ax.set_xlabel("Cumulative Total")
                st.pyplot(fig)
            else:
                st.info(f"No records mapped to metric '{chosen_dashboard_kpi}' within this window.")
        else:
            st.info("No KPI metric inputs saved yet.")
            
    st.markdown("---")
    
    # --- Detailed Ledger Grid Views & CSV Download Generators ---
    st.subheader("Raw Activity Logs & Data Export")
    t1, t2 = st.tabs(["Attendance & Scan Timestamps Records", "KPI Tracking Records"])
    with t1:
        if not filtered_att.empty:
            display_att_df = filtered_att.drop(columns=["verification_photo_blob"], errors="ignore")
            st.dataframe(display_att_df, use_container_width=True)
            st.download_button("📥 Download Attendance & Timestamps CSV", display_att_df.to_csv(index=False).encode('utf-8'), f"attendance_and_time_logs_{start_week}_to_{today}.csv", "text/csv")
        else:
            st.dataframe(filtered_att)
    with t2:
        st.dataframe(filtered_kpi, use_container_width=True)
        if not filtered_kpi.empty:
            st.download_button("📥 Download KPI Logs CSV", filtered_kpi.to_csv(index=False).encode('utf-8'), f"kpi_logs_{start_week}_to_{today}.csv", "text/csv")

