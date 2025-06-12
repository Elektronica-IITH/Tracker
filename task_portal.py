import streamlit as st
import gspread
import os
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, time
import uuid

# Configure page
st.set_page_config(
    page_title="Task Management System",
    page_icon="📋",
    layout="wide"
)

# --- Session State Initialization ---
if "username" not in st.session_state:
    st.session_state["username"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None
if "pending_task_additions" not in st.session_state:
    st.session_state["pending_task_additions"] = [] # List of new tasks to add
if "pending_task_updates" not in st.session_state:
    st.session_state["pending_task_updates"] = {} # Dict: {task_id: {col_index: new_value, ...}}
if "pending_task_deletions" not in st.session_state:
    st.session_state["pending_task_deletions"] = [] # List of task_ids to delete

@st.cache_resource
def get_gsheet_client():
    """Initialize Google Sheets client with caching"""
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        st.error("GOOGLE_CREDENTIALS_JSON environment variable not set. Please set it to your service account JSON.")
        st.stop()
    try:
        creds_dict = json.loads(creds_json)
    except json.JSONDecodeError:
        st.error("Invalid JSON in GOOGLE_CREDENTIALS_JSON. Please check the format.")
        st.stop()

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=10)
def load_users():
    """Load users with caching"""
    try:
        gc = get_gsheet_client()
        user_sheet = gc.open("Task-management").worksheet("users")
        return user_sheet.get_all_records()
    except Exception as e:
        st.error(f"Error loading users: {e}")
        return []

@st.cache_data(ttl=5)
def load_tasks():
    """Load tasks with caching"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        tasks = task_sheet.get_all_records()
        expected_columns = ["id", "title", "description", "assigned_to", "created_by", "status", "timestamp", "deadline"]
        for task in tasks:
            for col in expected_columns:
                if col not in task:
                    task[col] = ''
        return tasks
    except Exception as e:
        st.error(f"Error loading tasks: {e}")
        return []

def apply_pending_changes():
    """Applies all pending changes from session_state to Google Sheet."""
    gc = get_gsheet_client()
    task_sheet = gc.open("Task-management").worksheet("tasks")

    # 1. Process Additions
    if st.session_state["pending_task_additions"]:
        rows_to_add = []
        for task_data in st.session_state["pending_task_additions"]:
            rows_to_add.append([
                task_data['id'],
                task_data['title'],
                task_data['description'],
                task_data['assigned_to'],
                task_data['created_by'],
                task_data['status'],
                task_data['timestamp'],
                task_data['deadline']
            ])
        try:
            task_sheet.append_rows(rows_to_add)
            st.success(f"Added {len(rows_to_add)} new task(s) to the sheet.")
        except Exception as e:
            st.error(f"Error adding new tasks: {e}")
        st.session_state["pending_task_additions"] = []

    # 2. Process Deletions (do before updates to avoid conflicts)
    if st.session_state["pending_task_deletions"]:
        current_tasks = task_sheet.get_all_values()
        header = current_tasks[0]
        data_rows = current_tasks[1:]
        
        task_id_to_row = {row[0]: i + 2 for i, row in enumerate(data_rows)}

        rows_to_delete_actual = []
        for task_id in st.session_state["pending_task_deletions"]:
            if task_id in task_id_to_row:
                rows_to_delete_actual.append(task_id_to_row[task_id])
        
        rows_to_delete_actual.sort(reverse=True)

        for row_num in rows_to_delete_actual:
            try:
                task_sheet.delete_rows(row_num)
                st.success(f"Deleted task at row {row_num}.")
            except Exception as e:
                st.error(f"Error deleting task at row {row_num}: {e}")
        st.session_state["pending_task_deletions"] = []

    # 3. Process Updates
    if st.session_state["pending_task_updates"]:
        current_tasks_for_update = task_sheet.get_all_values()
        header_map = {col: i + 1 for i, col in enumerate(current_tasks_for_update[0])}
        task_id_to_actual_row = {row[0]: i + 2 for i, row in enumerate(current_tasks_for_update[1:])}

        updates_performed = 0
        for task_id, updates in st.session_state["pending_task_updates"].items():
            if task_id in task_id_to_actual_row:
                row_num = task_id_to_actual_row[task_id]
                for col_name, new_value in updates.items():
                    col_index = header_map.get(col_name)
                    if col_index:
                        try:
                            task_sheet.update_cell(row_num, col_index, new_value)
                            updates_performed += 1
                        except Exception as e:
                            st.error(f"Error updating task {task_id}, column {col_name}: {e}")
        if updates_performed > 0:
            st.success(f"Applied {updates_performed} task update(s).")
        st.session_state["pending_task_updates"] = {}

    st.cache_data.clear()
    st.rerun()

def verify_user_credentials(username, password):
    """Verify user credentials against Google Sheets"""
    users = load_users()
    existing_user = next((user for user in users if user['username'] == username), None)

    if existing_user:
        stored_password = existing_user.get('password', '')
        return stored_password == password, "existing", existing_user.get('role')
    else:
        return True, "new", None

def ensure_user(username, role, password):
    """Add new user or verify existing user credentials"""
    try:
        is_valid, user_status, existing_role = verify_user_credentials(username, password)

        if user_status == "new":
            gc = get_gsheet_client()
            user_sheet = gc.open("Task-management").worksheet("users")
            user_sheet.append_row([username, role, password])
            st.cache_data.clear()
            return True, "New user created successfully", role
        elif user_status == "existing":
            if not is_valid:
                return False, "Invalid username or password", None
            if existing_role != role:
                return False, f"User '{username}' exists with role '{existing_role}'. Please select the correct role.", None
            return True, "Login successful", existing_role
        else:
            return False, "Invalid credentials or unknown user status", None

    except Exception as e:
        return False, f"Error managing user: {e}", None

# --- Helper functions to mark changes in session state ---
def add_pending_task(title, desc, assigned_to, created_by, deadline):
    new_task_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    st.session_state["pending_task_additions"].append({
        'id': new_task_id,
        'title': title,
        'description': desc,
        'assigned_to': assigned_to,
        'created_by': created_by,
        'status': 'Pending',
        'timestamp': timestamp,
        'deadline': deadline
    })
    st.info("New task added to pending changes. Click 'Save Changes' to commit.")

def update_pending_task(task_id, column_name, new_value):
    if task_id not in st.session_state["pending_task_updates"]:
        st.session_state["pending_task_updates"][task_id] = {}
    st.session_state["pending_task_updates"][task_id][column_name] = new_value
    st.info("Change marked as pending. Click 'Save Changes' to commit.")

def delete_pending_task(task_id):
    if task_id not in st.session_state["pending_task_deletions"]:
        st.session_state["pending_task_deletions"].append(task_id)
    st.warning(f"Task {task_id} marked for deletion. Click 'Save Changes' to commit.")

def login():
    """Handle user login with password system from Google Sheets"""
    st.sidebar.title("🔐 Login")

    with st.sidebar.expander("ℹ️ Login Instructions"):
        st.markdown("""
        **For Existing Users:**
        - Enter your username and password
        - Select your role as registered

        **For New Users:**
        - Enter desired username
        - Enter desired password
        - Select your role
        - The system will create your account
        """)

    username = st.sidebar.text_input("Username", key="login_username")
    password = st.sidebar.text_input("Password", type="password", key="login_password")
    role = st.sidebar.selectbox("Role", ["Coordinator", "Head"], key="login_role")

    if st.sidebar.button("Login", key="login_btn"):
        if username.strip() and password.strip():
            success, message, user_role = ensure_user(username, role, password)
            if success:
                st.session_state["username"] = username
                st.session_state["role"] = user_role
                st.sidebar.success(message)
                st.rerun()
            else:
                st.sidebar.error(f"Login failed: {message}")
        else:
            st.sidebar.error("Please enter both username and password")

def coordinator_view():
    """Coordinator dashboard"""
    st.title("📋 Coordinator Dashboard")
    username = st.session_state["username"]

    all_tasks = load_tasks()
    my_tasks = [t for t in all_tasks if t.get("assigned_to") == username]

    # Statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Tasks", len(my_tasks))
    with col2:
        pending_count = len([t for t in my_tasks if t.get("status") == "Pending"])
        st.metric("Pending", pending_count)
    with col3:
        done_count = len([t for t in my_tasks if t.get("status") == "Done"])
        st.metric("Completed", done_count)

    st.markdown("---")

    # Add task for all coordinators (unassigned)
    st.subheader("➕ Create General Task")
    st.info("Tasks created here will be unassigned and can be assigned by Heads to specific coordinators.")

    # Initialize form inputs in session state if not already present
    if "coord_task_title_form_value" not in st.session_state:
        st.session_state["coord_task_title_form_value"] = ""
    if "coord_task_desc_form_value" not in st.session_state:
        st.session_state["coord_task_desc_form_value"] = ""
    if "coord_deadline_date_form_value" not in st.session_state:
        st.session_state["coord_deadline_date_form_value"] = None
    if "coord_deadline_time_form_value" not in st.session_state:
        st.session_state["coord_deadline_time_form_value"] = None


    with st.form("create_general_task_form"):
        # Use a new key for the form submission to avoid conflicts
        submit_button_pressed = st.form_submit_button("Add Task to Pending Changes", key="coord_submit_task")

        # Now, use the _value session state for the input defaults
        title = st.text_input("Task Title", value=st.session_state["coord_task_title_form_value"], key="coord_task_title_form")
        desc = st.text_area("Task Description", value=st.session_state["coord_task_desc_form_value"], key="coord_task_desc_form")
        col_deadline_date, col_deadline_time = st.columns(2)
        with col_deadline_date:
            deadline_date = st.date_input("Deadline Date (Optional)", value=st.session_state["coord_deadline_date_form_value"], key="coord_deadline_date_form")
        with col_deadline_time:
            deadline_time = st.time_input("Deadline Time (Optional)", value=st.session_state["coord_deadline_time_form_value"], key="coord_deadline_time_form")

        deadline_str = ""
        if deadline_date and deadline_time:
            deadline_str = f"{deadline_date.strftime('%Y-%m-%d')} {deadline_time.strftime('%H:%M')}"
        elif deadline_date:
            deadline_str = f"{deadline_date.strftime('%Y-%m-%d')} 23:59"

        if submit_button_pressed:
            if title.strip() and desc.strip():
                add_pending_task(title, desc, "Unassigned", username, deadline_str)
                # Clear the temporary values used for inputs
                st.session_state["coord_task_title_form_value"] = ""
                st.session_state["coord_task_desc_form_value"] = ""
                st.session_state["coord_deadline_date_form_value"] = None
                st.session_state["coord_deadline_time_form_value"] = None
                st.rerun() # Rerun to display cleared form and pending message
            else:
                st.error("Please fill in task title and description.")

    st.markdown("---")

    # Display assigned tasks
    st.subheader("🗂 My Assigned Tasks")

    if not my_tasks:
        st.info("No tasks assigned to you yet.")
    else:
        status_filter = st.selectbox("Filter by Status", ["All", "Pending", "Done"], key="coord_filter_display")

        filtered_tasks = my_tasks if status_filter == "All" else [t for t in my_tasks if t.get("status") == status_filter]

        def task_sort_key(task):
            deadline_val = task.get('deadline')
            try:
                deadline_dt = datetime.strptime(deadline_val, "%Y-%m-%d %H:%M") if deadline_val else datetime.max
            except ValueError:
                deadline_dt = datetime.max
            status_order = 0 if task.get('status') == 'Pending' else 1
            timestamp_val = task.get('timestamp')
            try:
                timestamp_dt = datetime.strptime(timestamp_val, "%Y-%m-%d %H:%M") if timestamp_val else datetime.min
            except ValueError:
                timestamp_dt = datetime.min
            return (deadline_dt, status_order, timestamp_dt)

        display_tasks = []
        for task in filtered_tasks:
            display_task = task.copy()
            if display_task['id'] in st.session_state["pending_task_updates"]:
                for col, val in st.session_state["pending_task_updates"][display_task['id']].items():
                    display_task[col] = val
            display_tasks.append(display_task)

        display_tasks = [t for t in display_tasks if t['id'] not in st.session_state["pending_task_deletions"]]

        display_tasks.sort(key=task_sort_key)

        for i, task in enumerate(display_tasks):
            with st.container(border=True):
                st.markdown(f"**{task.get('title', 'N/A')}**")
                st.markdown(f"📄 {task.get('description', 'N/A')}")

                status_color = "🟢" if task.get('status') == "Done" else "🟡"
                current_status_display = task.get('status', 'N/A')

                new_status = st.radio(
                    "Status:",
                    ["Pending", "Done"],
                    index=0 if current_status_display == "Pending" else 1,
                    key=f"status_radio_{task.get('id')}_{i}",
                    horizontal=True
                )
                if new_status != current_status_display:
                    update_pending_task(task["id"], "status", new_status)


                deadline_val = task.get('deadline')
                if deadline_val:
                    try:
                        deadline_dt = datetime.strptime(deadline_val, "%Y-%m-%d %H:%M")
                        if deadline_dt < datetime.now():
                            st.markdown(f"🚨 **Deadline: {deadline_val} (OVERDUE!)**")
                        else:
                            st.markdown(f"📅 Deadline: {deadline_val}")
                    except ValueError:
                        st.markdown(f"📅 Deadline: Invalid Date Format")
                else:
                    st.markdown("📅 **No Deadline**")

                st.markdown(f"Created by: **{task.get('created_by', 'N/A')}** | Created On: {task.get('timestamp', 'N/A')}")


def head_view():
    """Head dashboard - Consolidated View with single save button"""
    st.title("👤 Head Dashboard")
    username = st.session_state["username"]

    all_tasks = load_tasks()
    users = load_users()
    coordinators = [u["username"] for u in users if u["role"] == "Coordinator"]

    # Statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Tasks", len(all_tasks))
    with col2:
        pending_count = len([t for t in all_tasks if t.get("status") == "Pending"])
        st.metric("Pending", pending_count)
    with col3:
        done_count = len([t for t in all_tasks if t.get("status") == "Done"])
        st.metric("Completed", done_count)
    with col4:
        unassigned_count = len([t for t in all_tasks if t.get("assigned_to") == "Unassigned"])
        st.metric("Unassigned", unassigned_count)

    st.markdown("---")

    # --- Create New Task Section ---
    st.subheader("➕ Create & Assign New Task(s)")
    st.info("Assigning to multiple coordinators will create separate tasks for each.")

    # Initialize form inputs in session state if not already present
    if "head_task_title_form_value" not in st.session_state:
        st.session_state["head_task_title_form_value"] = ""
    if "head_task_desc_form_value" not in st.session_state:
        st.session_state["head_task_desc_form_value"] = ""
    if "head_assignees_form_value" not in st.session_state:
        st.session_state["head_assignees_form_value"] = []
    if "head_deadline_date_create_form_value" not in st.session_state:
        st.session_state["head_deadline_date_create_form_value"] = None
    if "head_deadline_time_create_form_value" not in st.session_state:
        st.session_state["head_deadline_time_create_form_value"] = None


    with st.form("create_assign_task_form"):
        # Use a new key for the form submission to avoid conflicts
        submit_button_pressed = st.form_submit_button("Add Task(s) to Pending Changes", key="head_submit_task")

        col_title, col_assignees = st.columns(2)
        with col_title:
            title = st.text_input("Task Title", value=st.session_state["head_task_title_form_value"], key="head_task_title_form")
        with col_assignees:
            assignees = st.multiselect("Assign To Coordinator(s)", coordinators, default=st.session_state["head_assignees_form_value"], key="head_assignees_form")

        desc = st.text_area("Task Description", value=st.session_state["head_task_desc_form_value"], key="head_task_desc_form")

        col_deadline_date_create, col_deadline_time_create = st.columns(2)
        with col_deadline_date_create:
            deadline_date_create = st.date_input("Deadline Date (Optional)", value=st.session_state["head_deadline_date_create_form_value"], key="head_deadline_date_create_form")
        with col_deadline_time_create:
            deadline_time_create = st.time_input("Deadline Time (Optional)", value=st.session_state["head_deadline_time_create_form_value"], key="head_deadline_time_create_form")

        deadline_str_create = ""
        if deadline_date_create and deadline_time_create:
            deadline_str_create = f"{deadline_date_create.strftime('%Y-%m-%d')} {deadline_time_create.strftime('%H:%M')}"
        elif deadline_date_create:
            deadline_str_create = f"{deadline_date_create.strftime('%Y-%m-%d')} 23:59"

        if submit_button_pressed:
            if title.strip() and desc.strip() and assignees:
                for assignee in assignees:
                    add_pending_task(title, desc, assignee, username, deadline_str_create)
                # Clear the temporary values used for inputs
                st.session_state["head_task_title_form_value"] = ""
                st.session_state["head_task_desc_form_value"] = ""
                st.session_state["head_assignees_form_value"] = []
                st.session_state["head_deadline_date_create_form_value"] = None
                st.session_state["head_deadline_time_create_form_value"] = None
                st.rerun() # Rerun to display cleared form and pending message
            else:
                st.error("Please fill in all fields and select at least one coordinator.")
    
    st.markdown("---")

    # --- All Tasks Overview and Management ---
    st.subheader("📊 All Tasks Overview & Management")

    # Filters
    col_filter_status, col_filter_assignee, col_spacer = st.columns([1, 1, 1])
    with col_filter_status:
        status_filter = st.selectbox("Filter by Status", ["All", "Pending", "Done", "Unassigned"], key="head_status_filter_display")
    with col_filter_assignee:
        assignee_filter = st.selectbox("Filter by Assignee", ["All"] + coordinators + ["Unassigned"], key="head_assignee_filter_display")

    filtered_tasks = all_tasks
    if status_filter != "All":
        if status_filter == "Unassigned":
            filtered_tasks = [t for t in filtered_tasks if t.get("assigned_to") == "Unassigned"]
        else:
            filtered_tasks = [t for t in filtered_tasks if t.get("status") == status_filter]

    if assignee_filter != "All":
        filtered_tasks = [t for t in filtered_tasks if t.get("assigned_to") == assignee_filter]

    display_tasks = []
    for task in filtered_tasks:
        display_task = task.copy()
        if display_task['id'] in st.session_state["pending_task_updates"]:
            for col, val in st.session_state["pending_task_updates"][display_task['id']].items():
                display_task[col] = val
        display_tasks.append(display_task)

    display_tasks = [t for t in display_tasks if t['id'] not in st.session_state["pending_task_deletions"]]

    def task_sort_key(task):
        deadline_val = task.get('deadline')
        try:
            deadline_dt = datetime.strptime(deadline_val, "%Y-%m-%d %H:%M") if deadline_val else datetime.max
        except ValueError:
            deadline_dt = datetime.max
        status_order = 0 if task.get('status') == 'Pending' else 1
        timestamp_val = task.get('timestamp')
        try:
            timestamp_dt = datetime.strptime(timestamp_val, "%Y-%m-%d %H:%M") if timestamp_val else datetime.min
        except ValueError:
            timestamp_dt = datetime.min
        return (deadline_dt, status_order, timestamp_dt)

    display_tasks.sort(key=task_sort_key)


    if not display_tasks:
        st.info("No tasks match the current filters.")
    else:
        for i, task in enumerate(display_tasks):
            with st.container(border=True):
                st.markdown(f"**Task: {task.get('title', 'N/A')}** (ID: {task.get('id', 'N/A')})")
                st.markdown(f"📄 Description: {task.get('description', 'N/A')}")

                # --- Task Actions (Inputs directly manipulate session state) ---
                col_status, col_assignee, col_deadline_edit = st.columns([1, 1.5, 2])

                with col_status:
                    current_status = task.get('status', 'Pending')
                    new_status = st.radio(
                        f"Status for {task.get('id')}:",
                        ["Pending", "Done"],
                        index=0 if current_status == "Pending" else 1,
                        key=f"status_radio_{task.get('id')}_{i}",
                        horizontal=True
                    )
                    if new_status != current_status:
                        update_pending_task(task["id"], "status", new_status)

                with col_assignee:
                    current_assignee = task.get('assigned_to', 'Unassigned')
                    if coordinators:
                        new_assignee = st.selectbox(
                            f"Assignee for {task.get('id')}:",
                            coordinators + ["Unassigned"],
                            index=(coordinators + ["Unassigned"]).index(current_assignee) if current_assignee in (coordinators + ["Unassigned"]) else 0,
                            key=f"assignee_select_{task.get('id')}_{i}"
                        )
                        if new_assignee != current_assignee:
                            update_pending_task(task["id"], "assigned_to", new_assignee)
                    else:
                        st.text(f"Assigned to: {current_assignee}")
                        st.info("No coordinators available.")

                with col_deadline_edit:
                    deadline_val = task.get('deadline')
                    current_deadline_dt = None
                    current_deadline_date = None
                    current_deadline_time = None

                    if deadline_val:
                        try:
                            current_deadline_dt = datetime.strptime(deadline_val, "%Y-%m-%d %H:%M")
                            current_deadline_date = current_deadline_dt.date()
                            current_deadline_time = current_deadline_dt.time()
                            if current_deadline_dt < datetime.now():
                                st.markdown(f"🚨 **Current Deadline: {deadline_val} (OVERDUE!)**")
                            else:
                                st.markdown(f"📅 Current Deadline: {deadline_val}")
                        except ValueError:
                            st.markdown(f"📅 Current Deadline: Invalid Format")
                    else:
                        st.markdown("📅 **Current Deadline: No Deadline**")

                    new_deadline_date = st.date_input("Date:", value=current_deadline_date, key=f"deadline_date_edit_{task.get('id')}_{i}", help="Leave empty for no deadline")
                    new_deadline_time = st.time_input("Time:", value=current_deadline_time, key=f"deadline_time_edit_{task.get('id')}_{i}", help="Leave empty for no deadline")

                    new_deadline_str = ""
                    if new_deadline_date and new_deadline_time:
                        new_deadline_str = f"{new_deadline_date.strftime('%Y-%m-%d')} {new_deadline_time.strftime('%H:%M')}"
                    elif new_deadline_date:
                        new_deadline_str = f"{new_deadline_date.strftime('%Y-%m-%d')} 23:59"

                    # Compare with the original value from the sheet, not the session state pending update
                    original_deadline_val = next((t.get('deadline') for t in all_tasks if t['id'] == task['id']), '')
                    if new_deadline_str != original_deadline_val:
                        update_pending_task(task["id"], "deadline", new_deadline_str)

                # Delete button (separated for safety)
                st.markdown("---")
                if st.button(f"🗑️ Delete Task {task.get('id')}", key=f"delete_btn_{task.get('id')}_{i}", type="secondary"):
                    delete_pending_task(task["id"])
                    st.rerun()

# Entry point
def main():
    # Custom CSS for styling
    st.markdown("""
    <style>
    .stContainer > div {
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        background-color: #fafafa;
    }
    .stButton > button {
        width: 100%;
    }
    div[data-baseweb="radio"] {
        flex-direction: row;
        gap: 1rem;
    }
    div[data-baseweb="radio"] > label {
        margin-right: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

    if st.session_state["username"] is None:
        st.title("🏢 Task Management System")
        st.markdown("### Welcome! Please log in to continue.")
        login()
    else:
        # Sidebar user info
        st.sidebar.success(f"👤 **{st.session_state['username']}**")
        st.sidebar.info(f"🏷️ Role: {st.session_state['role']}")

        has_pending_changes = bool(
            st.session_state["pending_task_additions"] or
            st.session_state["pending_task_updates"] or
            st.session_state["pending_task_deletions"]
        )

        if has_pending_changes:
            st.sidebar.warning("⚠️ You have unsaved changes!")
            if st.sidebar.button("💾 Save All Changes", key="save_all_changes_btn", type="primary"):
                apply_pending_changes()
                st.success("All changes saved successfully!")
        else:
            st.sidebar.info("No pending changes.")
            if st.sidebar.button("🔄 Refresh Data", key="refresh_data_btn"):
                st.cache_data.clear()
                st.rerun()

        if st.sidebar.button("🚪 Logout", key="logout_btn"):
            st.session_state.clear()
            st.rerun()

        if st.session_state["role"] == "Coordinator":
            coordinator_view()
        elif st.session_state["role"] == "Head":
            head_view()

if __name__ == "__main__":
    main()
