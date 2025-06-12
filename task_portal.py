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
if "pending_changes" not in st.session_state:
    st.session_state["pending_changes"] = False # Track if changes need saving

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

@st.cache_data(ttl=10) # Reduced TTL for slightly quicker data reflection after save
def load_users():
    """Load users with caching"""
    try:
        gc = get_gsheet_client()
        user_sheet = gc.open("Task-management").worksheet("users")
        return user_sheet.get_all_records()
    except Exception as e:
        st.error(f"Error loading users: {e}")
        return []

@st.cache_data(ttl=5) # Reduced TTL for slightly quicker data reflection after save
def load_tasks():
    """Load tasks with caching"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        return task_sheet.get_all_records()
    except Exception as e:
        st.error(f"Error loading tasks: {e}")
        return []

def mark_changes_pending():
    """Set flag to indicate that changes need to be saved."""
    st.session_state["pending_changes"] = True

def clear_and_rerun():
    """Clear all cached data and rerun the app."""
    st.cache_data.clear()
    st.session_state["pending_changes"] = False # Reset pending changes flag
    st.rerun()

def verify_user_credentials(username, password):
    """Verify user credentials against Google Sheets"""
    users = load_users()
    existing_user = next((user for user in users if user['username'] == username), None)

    if existing_user:
        stored_password = existing_user.get('password', '')
        return stored_password == password, "existing", existing_user.get('role')
    else:
        return True, "new", None # For new users, any password is fine for registration

def ensure_user(username, role, password):
    """Add new user or verify existing user credentials"""
    try:
        is_valid, user_status, existing_role = verify_user_credentials(username, password)

        if user_status == "new":
            gc = get_gsheet_client()
            user_sheet = gc.open("Task-management").worksheet("users")
            user_sheet.append_row([username, role, password])
            mark_changes_pending() # Mark that changes are pending
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

def add_task(title, desc, assigned_to, created_by, deadline):
    """Add new task with a deadline"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        task_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        task_sheet.append_row([task_id, title, desc, assigned_to, created_by, "Pending", timestamp, deadline])
        mark_changes_pending()
        return True
    except Exception as e:
        st.error(f"Error adding task: {e}")
        return False

def find_task_row(task_id):
    """Find task row by ID"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        all_values = task_sheet.get_all_values()
        for i, row in enumerate(all_values):
            if row and str(row[0]) == str(task_id):
                return i + 1
        return None
    except Exception as e:
        st.error(f"Error finding task: {e}")
        return None

def update_task_cell(task_id, col_index, new_value):
    """Update a specific cell for a task given column index (1-based)"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        row_num = find_task_row(task_id)
        if row_num:
            task_sheet.update_cell(row_num, col_index, new_value)
            mark_changes_pending()
            return True
        return False
    except Exception as e:
        st.error(f"Error updating task cell: {e}")
        return False

def delete_task(task_id):
    """Delete a task"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        row_num = find_task_row(task_id)
        if row_num:
            task_sheet.delete_rows(row_num)
            mark_changes_pending()
            return True
        return False
    except Exception as e:
        st.error(f"Error deleting task: {e}")
        return False

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
                clear_and_rerun() # Rerun after successful login to route to dashboard
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
    with st.form("create_general_task_form"):
        title = st.text_input("Task Title", key="coord_task_title_form")
        desc = st.text_area("Task Description", key="coord_task_desc_form")
        col_deadline_date, col_deadline_time = st.columns(2)
        with col_deadline_date:
            deadline_date = st.date_input("Deadline Date (Optional)", value=None, key="coord_deadline_date_form")
        with col_deadline_time:
            deadline_time = st.time_input("Deadline Time (Optional)", value=None, key="coord_deadline_time_form")

        deadline_str = ""
        if deadline_date and deadline_time:
            deadline_str = f"{deadline_date.strftime('%Y-%m-%d')} {deadline_time.strftime('%H:%M')}"
        elif deadline_date:
            deadline_str = f"{deadline_date.strftime('%Y-%m-%d')} 23:59" # Default to end of day if only date
        # If both are None, deadline_str remains empty

        if st.form_submit_button("Create Task"):
            if title.strip() and desc.strip():
                success = add_task(title, desc, "Unassigned", username, deadline_str)
                if success:
                    st.success("✅ Task created successfully! Click 'Save Changes' to update.")
                else:
                    st.error("Failed to create task.")
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
        
        # Sort by deadline (if available), then by status (pending first), then by creation timestamp
        def task_sort_key(task):
            deadline_val = task.get('deadline')
            deadline_dt = datetime.strptime(deadline_val, "%Y-%m-%d %H:%M") if deadline_val else datetime.max # Treat no deadline as very far in future
            status_order = 0 if task.get('status') == 'Pending' else 1
            timestamp_val = task.get('timestamp')
            timestamp_dt = datetime.strptime(timestamp_val, "%Y-%m-%d %H:%M") if timestamp_val else datetime.min
            return (deadline_dt, status_order, timestamp_dt)

        filtered_tasks.sort(key=task_sort_key)

        for i, task in enumerate(filtered_tasks):
            with st.container(border=True): # Use border=True for visual separation
                col1, col2 = st.columns([4, 1])

                with col1:
                    st.markdown(f"**{task.get('title', 'N/A')}**")
                    st.markdown(f"📄 {task.get('description', 'N/A')}")

                    status_color = "🟢" if task.get('status') == "Done" else "🟡"
                    st.markdown(f"{status_color} Status: **{task.get('status', 'N/A')}** | Created by: **{task.get('created_by', 'N/A')}**")

                    deadline_val = task.get('deadline')
                    if deadline_val:
                        try:
                            deadline_dt = datetime.strptime(deadline_val, "%Y-%m-%d %H:%M")
                            if deadline_dt < datetime.now():
                                st.markdown(f"🚨 **Deadline: {deadline_val} (OVERDUE!)**")
                            else:
                                st.markdown(f"📅 Deadline: {deadline_val}")
                        except ValueError:
                            st.markdown(f"📅 Deadline: Invalid Date") # Handle malformed dates
                    else:
                        st.markdown("📅 **No Deadline**")

                    st.markdown(f"Created On: {task.get('timestamp', 'N/A')}")

                with col2:
                    if task.get("status") == "Pending":
                        if st.button("✅ Mark Done", key=f"done_{task.get('id')}_{i}"):
                            success = update_task_cell(task["id"], 6, "Done") # Column 6 for status
                            if success:
                                st.success("Task marked as done! Click 'Save Changes' to update.")
                            else:
                                st.error("Failed to update status.")
                    else:
                        if st.button("🔄 Reopen", key=f"reopen_{task.get('id')}_{i}"):
                            success = update_task_cell(task["id"], 6, "Pending") # Column 6 for status
                            if success:
                                st.success("Task reopened! Click 'Save Changes' to update.")
                            else:
                                st.error("Failed to reopen task.")


def head_view():
    """Head dashboard - Consolidated View"""
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
    with st.form("create_assign_task_form"):
        col_title, col_assignees = st.columns(2)
        with col_title:
            title = st.text_input("Task Title", key="head_task_title_form")
        with col_assignees:
            # Allow selecting multiple coordinators
            assignees = st.multiselect("Assign To Coordinator(s)", coordinators, key="head_assignees_form")

        desc = st.text_area("Task Description", key="head_task_desc_form")

        col_deadline_date_create, col_deadline_time_create = st.columns(2)
        with col_deadline_date_create:
            deadline_date_create = st.date_input("Deadline Date (Optional)", value=None, key="head_deadline_date_create_form")
        with col_deadline_time_create:
            deadline_time_create = st.time_input("Deadline Time (Optional)", value=None, key="head_deadline_time_create_form")

        deadline_str_create = ""
        if deadline_date_create and deadline_time_create:
            deadline_str_create = f"{deadline_date_create.strftime('%Y-%m-%d')} {deadline_time_create.strftime('%H:%M')}"
        elif deadline_date_create:
            deadline_str_create = f"{deadline_date_create.strftime('%Y-%m-%d')} 23:59"

        if st.form_submit_button("Create & Assign Task(s)"):
            if title.strip() and desc.strip() and assignees:
                all_success = True
                for assignee in assignees:
                    success = add_task(title, desc, assignee, username, deadline_str_create)
                    if not success:
                        all_success = False
                        break
                if all_success:
                    st.success(f"✅ Task(s) created and assigned to {', '.join(assignees)}! Click 'Save Changes' to update.")
                else:
                    st.error("Failed to create one or more tasks.")
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

    # Sort by deadline (if available), then by status (pending first), then by creation timestamp
    def task_sort_key(task):
        deadline_val = task.get('deadline')
        try:
            deadline_dt = datetime.strptime(deadline_val, "%Y-%m-%d %H:%M") if deadline_val else datetime.max
        except ValueError: # Handle potential malformed deadlines
            deadline_dt = datetime.max
        status_order = 0 if task.get('status') == 'Pending' else 1
        timestamp_val = task.get('timestamp')
        try:
            timestamp_dt = datetime.strptime(timestamp_val, "%Y-%m-%d %H:%M") if timestamp_val else datetime.min
        except ValueError:
            timestamp_dt = datetime.min
        return (deadline_dt, status_order, timestamp_dt)

    filtered_tasks.sort(key=task_sort_key)

    if not filtered_tasks:
        st.info("No tasks match the current filters.")
    else:
        for i, task in enumerate(filtered_tasks):
            with st.container(border=True):
                st.markdown(f"**Task: {task.get('title', 'N/A')}** (ID: {task.get('id', 'N/A')})")
                st.markdown(f"📄 Description: {task.get('description', 'N/A')}")

                status_color = "🟢" if task.get('status') == "Done" else "🟡" if task.get('status') == "Pending" else "🔴"
                st.markdown(f"{status_color} Status: **{task.get('status', 'N/A')}** | Assigned to: **{task.get('assigned_to', 'N/A')}** | Created by: **{task.get('created_by', 'N/A')}**")
                st.markdown(f"Created On: {task.get('timestamp', 'N/A')}")

                # Deadline display and edit
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
                        st.markdown(f"📅 Current Deadline: Invalid Date")
                else:
                    st.markdown("📅 **Current Deadline: No Deadline**")

                st.markdown("---") # Separator for actions below

                # --- Task Actions ---
                col_reassign, col_status, col_deadline_edit, col_delete = st.columns([1, 1, 1.5, 0.5])

                with col_reassign:
                    if coordinators:
                        selected_assignee = selected_assignee = st.selectbox(
                            "Reassign to",
                            ["Keep current"] + coordinators,
                            index=0,
                            key=f"reassign_{task.get('id')}_{i}"
                        )
                        if selected_assignee != "Keep current" and st.button("Apply Reassign", key=f"btn_reassign_{task.get('id')}_{i}"):
                            success = update_task_cell(task["id"], 4, selected_assignee) # Column 4 for assigned_to
                            if success:
                                st.success(f"Task {task['id']} reassigned to {selected_assignee}. Click 'Save Changes' to update.")
                            else:
                                st.error("Failed to reassign task.")
                    else:
                        st.info("No coordinators to reassign to.")

                with col_status:
                    current_status = task.get('status', 'Pending')
                    new_status = st.selectbox(
                        "Change Status",
                        ["Pending", "Done"],
                        index=0 if current_status == "Pending" else 1,
                        key=f"status_select_{task.get('id')}_{i}"
                    )
                    if new_status != current_status and st.button("Apply Status", key=f"btn_status_{task.get('id')}_{i}"):
                        success = update_task_cell(task["id"], 6, new_status) # Column 6 for status
                        if success:
                            st.success(f"Status for task {task['id']} updated to {new_status}. Click 'Save Changes' to update.")
                        else:
                            st.error("Failed to update status.")
                    elif new_status == current_status:
                        st.text("Status not changed.")


                with col_deadline_edit:
                    st.markdown("**Edit Deadline**")
                    new_deadline_date = st.date_input("Date", value=current_deadline_date, key=f"deadline_date_{task.get('id')}_{i}")
                    new_deadline_time = st.time_input("Time", value=current_deadline_time, key=f"deadline_time_{task.get('id')}_{i}")

                    new_deadline_str = ""
                    if new_deadline_date and new_deadline_time:
                        new_deadline_str = f"{new_deadline_date.strftime('%Y-%m-%d')} {new_deadline_time.strftime('%H:%M')}"
                    elif new_deadline_date:
                        new_deadline_str = f"{new_deadline_date.strftime('%Y-%m-%d')} 23:59" # Default to end of day

                    if new_deadline_str != deadline_val and st.button("Apply Deadline", key=f"btn_deadline_{task.get('id')}_{i}"):
                        success = update_task_cell(task["id"], 8, new_deadline_str) # Column 8 for deadline
                        if success:
                            st.success(f"Deadline for task {task['id']} updated. Click 'Save Changes' to update.")
                        else:
                            st.error("Failed to update deadline.")
                    elif new_deadline_str == deadline_val:
                        st.text("Deadline not changed.")


                with col_delete:
                    st.markdown(" ") # Spacer for alignment
                    st.warning("⚠️")
                    if st.button("🗑️ Delete", key=f"delete_{task.get('id')}_{i}", type="secondary"):
                        success = delete_task(task["id"])
                        if success:
                            st.success(f"Task {task['id']} deleted! Click 'Save Changes' to update.")
                        else:
                            st.error("Failed to delete task.")

# Entry point
def main():
    # Custom CSS
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

        if st.session_state["pending_changes"]:
            st.sidebar.warning("You have unsaved changes!")
            if st.sidebar.button("💾 Save All Changes", key="save_all_changes_btn", type="primary"):
                clear_and_rerun()
                st.success("All changes saved successfully!")
        else:
            st.sidebar.info("No pending changes.")
            # Add a refresh button that simply reloads data
            if st.sidebar.button("🔄 Refresh Data", key="refresh_data_btn"):
                clear_and_rerun()


        if st.sidebar.button("🚪 Logout", key="logout_btn"):
            st.session_state.clear()
            clear_and_rerun() # Ensure full clear on logout

        # Route to appropriate view
        if st.session_state["role"] == "Coordinator":
            coordinator_view()
        elif st.session_state["role"] == "Head":
            head_view()

if __name__ == "__main__":
    main()
