import streamlit as st
import pandas as pd
import datetime
import matplotlib.pyplot as plt

# --------------------------------------------------------
# 1. INITIALIZE DATA STORAGE (Mock Database using Session State)
# --------------------------------------------------------
if 'employees' not in st.session_state:
    st.session_state.employees = pd.DataFrame([
        {"Employee ID": "EMP001", "Name": "John Doe", "Role": "Forklift Driver", "Status": "Active"},
        {"Employee ID": "EMP002", "Name": "Jane Smith", "Role": "Picker/Packer", "Status": "Active"},
        {"Employee ID": "EMP003", "Name": "Bob Johnson", "Role": "Sorter", "Status": "Active"}
    ])

if 'attendance' not in st.session_state:
    st.session_state.attendance = pd.DataFrame(columns=["Date", "Employee ID", "Name", "Status", "PPE Compliant"])

# Storing default target benchmarks for the automated parameters
if 'kpi_settings' not in st.session_state:
    st.session_state.kpi_settings = {
        "Boxes Packed": 50.0,
        "Safety Compliance Score": 98.0,         # Managed automatically via PPE check
        "Attendance Punctuality": 95.0          # Managed automatically via Present/Late radio
    }

if 'kpi_logs' not in st.session_state:
    st.session_state.kpi_logs = pd.DataFrame(columns=["Date", "Employee ID", "Name", "KPI", "Value"])

# Helper function to get active employees
def get_active_employees():
    return st.session_state.employees[st.session_state.employees["Status"] == "Active"]

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
    st.header("Employee Roster Management")
    
    tab1, tab2 = st.tabs(["➕ Add New Employee", "✏️ Edit Employee Roster"])
    
    with tab1:
        st.subheader("Register a New Warehouse Worker")
        with st.form("add_employee_form", clear_on_submit=True):
            new_id = st.text_input("Employee ID (e.g., EMP004)")
            new_name = st.text_input("Full Name")
            new_role = st.selectbox("Warehouse Role", ["Picker/Packer", "Forklift Driver", "Sorter", "Loader/Unloader", "Supervisor"])
            submit_btn = st.form_submit_button("Save Employee")
            
            if submit_btn:
                if new_id and new_name:
                    if new_id in st.session_state.employees["Employee ID"].values:
                        st.error("This Employee ID already exists!")
                    else:
                        new_worker = {"Employee ID": new_id, "Name": new_name, "Role": new_role, "Status": "Active"}
                        st.session_state.employees = pd.concat([st.session_state.employees, pd.DataFrame([new_worker])], ignore_index=True)
                        st.success(f"Successfully registered {new_name}!")
                else:
                    st.warning("Please fill out all fields.")

    with tab2:
        st.subheader("Current Employee Roster")
        edited_df = st.data_editor(st.session_state.employees, num_rows="dynamic", key="roster_editor")
        if st.button("Save Roster Changes"):
            st.session_state.employees = edited_df
            st.success("Roster updated successfully!")

# --------------------------------------------------------
# 4. MODULE: DAILY ATTENDANCE
# --------------------------------------------------------
elif choice == "📝 Daily Attendance":
    st.header("Daily Attendance & PPE Safety Capture")
    
    attendance_date = st.date_input("Select Date for Attendance", datetime.date.today())
    active_workers = get_active_employees()
    
    if active_workers.empty:
        st.warning("No active employees found. Please add workers in Employee Management first.")
    else:
        st.write(f"Marking attendance for: **{attendance_date.strftime('%A, %B %d, %Y')}**")
        
        existing_att = st.session_state.attendance[st.session_state.attendance["Date"] == attendance_date]
        
        with st.form("attendance_form"):
            attendance_records = []
            
            st.markdown("### Worker Status & Safety Check")
            for idx, row in active_workers.iterrows():
                emp_id = row["Employee ID"]
                emp_name = row["Name"]
                
                default_status = "Present"
                default_ppe = True
                
                if not existing_att.empty and emp_id in existing_att["Employee ID"].values:
                    matching_row = existing_att[existing_att["Employee ID"] == emp_id]
                    default_status = matching_row["Status"].values
                    if "PPE Compliant" in matching_row.columns:
                        default_ppe = bool(matching_row["PPE Compliant"].values)
                
                st.markdown(f"**{emp_name} ({emp_id})** — *{row['Role']}*")
                col_status, col_ppe = st.columns(2)
                
                with col_status:
                    status = st.radio(
                        f"Status for {emp_id}", 
                        ["Present", "Absent", "Sick Leave", "Late"], 
                        index=["Present", "Absent", "Sick Leave", "Late"].index(default_status), 
                        horizontal=True,
                        label_visibility="collapsed"
                    )
                
                with col_ppe:
                    ppe_ok = st.checkbox("✅ PPE Compliant", value=default_ppe, key=f"ppe_{emp_id}_{idx}")
                
                final_ppe = ppe_ok if status in ["Present", "Late"] else False
                
                attendance_records.append({
                    "Date": attendance_date, 
                    "Employee ID": emp_id, 
                    "Name": emp_name, 
                    "Status": status,
                    "PPE Compliant": final_ppe
                })
                st.markdown("---")
            
            save_attendance = st.form_submit_button("Save Today's Records")
            
            if save_attendance:
                # 1. Save main attendance status rows
                st.session_state.attendance = st.session_state.attendance[st.session_state.attendance["Date"] != attendance_date]
                st.session_state.attendance = pd.concat([st.session_state.attendance, pd.DataFrame(attendance_records)], ignore_index=True)
                
                # 2. Automated Dual-KPI Logging calculations
                auto_kpi_records = []
                for record in attendance_records:
                    if record["Status"] in ["Present", "Late"]:
                        # Punctuality calculation
                        punct_score = 100.0 if record["Status"] == "Present" else 0.0
                        auto_kpi_records.append({
                            "Date": attendance_date, "Employee ID": record["Employee ID"], "Name": record["Name"],
                            "KPI": "Attendance Punctuality", "Value": punct_score
                        })
                        
                        # Safety Compliance score calculation
                        safety_score = 100.0 if record["PPE Compliant"] else 0.0
                        auto_kpi_records.append({
                            "Date": attendance_date, "Employee ID": record["Employee ID"], "Name": record["Name"],
                            "KPI": "Safety Compliance Score", "Value": safety_score
                        })
                
                # Clear previous automated logs for this exact date to prevent stacking data bloating
                if "kpi_logs" in st.session_state and not st.session_state.kpi_logs.empty:
                    st.session_state.kpi_logs = st.session_state.kpi_logs[
                        ~((st.session_state.kpi_logs["Date"] == attendance_date) & 
                          (st.session_state.kpi_logs["KPI"].isin(["Attendance Punctuality", "Safety Compliance Score"])))
                    ]
                
                if auto_kpi_records:
                    st.session_state.kpi_logs = pd.concat([st.session_state.kpi_logs, pd.DataFrame(auto_kpi_records)], ignore_index=True)
                
                st.success(f"Attendance captured perfectly. Safety Compliance & Punctuality KPIs updated dynamically!")

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
            if new_kpi not in st.session_state.kpi_settings:
                st.session_state.kpi_settings[new_kpi] = float(new_target)
                st.success(f"Metric '{new_kpi}' with target {new_target} added successfully!")
                st.rerun()
            else:
                st.error("Metric already exists.")
        
        st.markdown("#### Current Target Configurations")
        for item, target_val in st.session_state.kpi_settings.items():
            is_auto = " (Automated)" if item in ["Attendance Punctuality", "Safety Compliance Score"] else ""
            st.text(f"🎯 {item}{is_auto} — Target Average: {target_val:.1f}")

    with tab1:
        st.subheader("Capture Daily Worker Metrics")
        kpi_date = st.date_input("Select Performance Date", datetime.date.today())
        active_workers = get_active_employees()
        
        if not st.session_state.kpi_settings:
            st.warning("Please configure at least one KPI metric first.")
        else:
            # Hide systemic automated columns from manual forms
            hidden_kpis = ["Attendance Punctuality", "Safety Compliance Score"]
            manual_kpi_options = [k for k in st.session_state.kpi_settings.keys() if k not in hidden_kpis]
            
            if not manual_kpi_options:
                st.info("All current KPIs are automated. Create custom operational metrics in the config panel to log values manually.")
            else:
                selected_kpi = st.selectbox("Select Metric to Log", manual_kpi_options)
                
                existing_logs = st.session_state.kpi_logs[
                    (st.session_state.kpi_logs["Date"] == kpi_date) & 
                    (st.session_state.kpi_logs["KPI"] == selected_kpi)
                ]
                
                with st.form("kpi_form"):
                    kpi_records = []
                    for idx, row in active_workers.iterrows():
                        emp_id = row["Employee ID"]
                        emp_name = row["Name"]
                        
                        default_val = 0.0
                        if not existing_logs.empty and emp_id in existing_logs["Employee ID"].values:
                            default_val = float(existing_logs[existing_logs["Employee ID"] == emp_id]["Value"].values)
                        
                        val = st.number_input(f"Value for {emp_name} ({emp_id})", min_value=0.0, value=default_val, step=1.0)
                        kpi_records.append({"Date": kpi_date, "Employee ID": emp_id, "Name": emp_name, "KPI": selected_kpi, "Value": val})
                    
                    submit_kpi = st.form_submit_button("Save KPI Scores")
                    
                    if submit_kpi:
                        st.session_state.kpi_logs = st.session_state.kpi_logs[
                            ~((st.session_state.kpi_logs["Date"] == kpi_date) & 
                              (st.session_state.kpi_logs["KPI"] == selected_kpi))
                        ]
                        st.session_state.kpi_logs = pd.concat([st.session_state.kpi_logs, pd.DataFrame(kpi_records)], ignore_index=True)
                        st.success(f"Scores saved for '{selected_kpi}' on {kpi_date}!")

# --------------------------------------------------------
# 6. MODULE: WEEKLY DASHBOARD
# --------------------------------------------------------
elif choice == "📈 Weekly Dashboard":
    st.header("Weekly Operations Dashboard")
    
    today = datetime.date.today()
    start_week = st.date_input("Start Date for Dashboard View", today - datetime.timedelta(days=6))
    
    kpi_options = list(st.session_state.kpi_settings.keys())
    chosen_dashboard_kpi = st.selectbox("📊 Select KPI for Card & Chart Filtering", kpi_options, index=0)
    
    weekly_target_threshold = st.session_state.kpi_settings.get(chosen_dashboard_kpi, 0.0)
    st.write(f"Showing operational data from **{start_week}** to **{today}**")
    
    # Filter Dataframes based on selected date range
    att_df = st.session_state.attendance.copy()
    kpi_df = st.session_state.kpi_logs.copy()
    
    if not att_df.empty:
        att_df['Date'] = pd.to_datetime(att_df['Date']).dt.date
        filtered_att = att_df[(att_df['Date'] >= start_week) & (att_df['Date'] <= today)]
    else:
        filtered_att = pd.DataFrame()
        
    if not kpi_df.empty:
        kpi_df['Date'] = pd.to_datetime(kpi_df['Date']).dt.date
        filtered_kpi = kpi_df[(kpi_df['Date'] >= start_week) & (kpi_df['Date'] <= today)]
    else:
        filtered_kpi = pd.DataFrame()

    # --- NEW: Process Weekly perfect-performance bonus qualifiers ---
    bonus_workers = []
    if not filtered_att.empty:
        # Group records by each worker to analyze their full week
        for emp_id in filtered_att["Employee ID"].unique():
            worker_week = filtered_att[filtered_att["Employee ID"] == emp_id]
            worker_name = worker_week["Name"].iloc[0]
            
            # Condition 1: Was never once late or absent when scheduled
            has_lates = "Late" in worker_week["Status"].values
            has_absents = "Absent" in worker_week["Status"].values
            
            # Condition 2: Cleared 100% of safety gear audits
            onsite_days = worker_week[worker_week["Status"].isin(["Present", "Late"])]
            failed_ppe = False
            if not onsite_days.empty:
                failed_ppe = (onsite_days["PPE Compliant"] == False).any()
            
            # Perfect score match qualifier flag rule
            if not has_lates and not has_absents and not failed_ppe and not worker_week.empty:
                bonus_workers.append(worker_name)

    # --- KPI Overview Cards (Extended to 5 Columns) ---
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Active Supply Staff", len(get_active_employees()))
        
    with col2:
        if not filtered_att.empty:
            presents = len(filtered_att[filtered_att["Status"] == "Present"])
            st.metric("Attendance Rate", f"{((presents / len(filtered_att)) * 100):.1f}%")
        else:
            st.metric("Attendance Rate", "No Data")

    with col3:
        if not filtered_att.empty and "PPE Compliant" in filtered_att.columns:
            on_site = filtered_att[filtered_att["Status"].isin(["Present", "Late"])]
            ppe_rate = (on_site["PPE Compliant"].sum() / len(on_site)) * 100 if not on_site.empty else 0.0
            st.metric("PPE Safety Compliance", f"{ppe_rate:.1f}%")
        else:
            st.metric("PPE Safety Compliance", "No Data")
            
    with col4:
        if not filtered_kpi.empty:
            custom_data = filtered_kpi[filtered_kpi["KPI"] == chosen_dashboard_kpi]
            if not custom_data.empty:
                calculated_avg = custom_data["Value"].mean()
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
        # NEW Visual card tracking active performance incentives
        st.metric("⭐ Attendance Bonus Qualifiers", len(bonus_workers))

    # Highlight qualifier names directly under the metric row if any exist
    if bonus_workers:
        st.success(f"🏅 **Weekly Bonus Recipients (100% Punctual & Safe):** {', '.join(bonus_workers)}")

    st.markdown("---")

    # --- Visualizations Section ---
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Attendance Breakdown")
        if not filtered_att.empty:
            status_counts = filtered_att["Status"].value_counts()
            fig, ax = plt.subplots(figsize=(5, 4))
            status_counts.plot(kind='bar', color=['#4CAF50', '#F44336', '#FFC107', '#2196F3'], ax=ax)
            ax.set_ylabel("Days Tracked")
            plt.xticks(rotation=40)
            st.pyplot(fig)
        else:
            st.info("No attendance data logged in this range.")

    with c2:
        st.subheader("Top Performers (KPI Totals)")
        if not filtered_kpi.empty:
            chart_data = filtered_kpi[filtered_kpi["KPI"] == chosen_dashboard_kpi]
            if not chart_data.empty:
                leaderboard = chart_data.groupby("Name")["Value"].sum().sort_values(ascending=False)
                fig, ax = plt.subplots(figsize=(5, 4))
                leaderboard.plot(kind='barh', color='#8884d8', ax=ax)
                ax.set_xlabel("Cumulative Total")
                st.pyplot(fig)
            else:
                st.info(f"No logs found for '{chosen_dashboard_kpi}' in the chosen date range.")
        else:
            st.info("No KPI data logged in this range.")
            
    st.markdown("---")
    
    # --- Detailed Data View & CSV Export Buttons ---
    st.subheader("Raw Activity Logs & Data Export")
    t1, t2 = st.tabs(["Attendance Records", "KPI Tracking Records"])
    
    with t1:
        st.dataframe(filtered_att, use_container_width=True)
        if not filtered_att.empty:
            csv_attendance = filtered_att.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Attendance & PPE CSV", data=csv_attendance,
                file_name=f"attendance_and_ppe_logs_{start_week}_to_{today}.csv", mime="text/csv"
            )
            
    with t2:
        st.dataframe(filtered_kpi, use_container_width=True)
        if not filtered_kpi.empty:
            csv_kpis = filtered_kpi.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download KPI Logs CSV", data=csv_kpis,
                file_name=f"kpi_logs_{start_week}_to_{today}.csv", mime="text/csv"
            )

