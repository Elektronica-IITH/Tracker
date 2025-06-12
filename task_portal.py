import streamlit as st
import gspread
import os
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid
# Removed direct 'time' import as we'll control refreshes explicitly

# Configure page
st.set_page_config(
    page_title="Task Management System",
    page_icon="📋",
    layout="wide"
)

@st.cache_resource
def get_gsheet_client():
    """Initialize Google Sheets client with caching"""
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    # Ensure creds_json is not None or empty
    if not creds_json:
        st.error("GOOGLE_CREDENTIALS_JSON environment variable not set.")
        st.stop() # Stop the app if credentials are missing
    try:
        creds_dict = json.loads(creds_json)
    except json.JSONDecodeError:
        st.error("Invalid JSON in GOOGLE_CREDENTIALS_JSON. Please check the format.")
        st.stop()

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=30)  # Cache for 30 seconds
def load_users():
    """Load users with caching"""
    try:
        gc = get_gsheet_client()
        user_sheet = gc.open("Task-management").worksheet("users")
        return user_sheet.get_all_records()
    except Exception as e:
        st.error(f"Error loading users: {e}")
        return []

@st.cache_data(ttl=10)  # Cache for 10 seconds
def load_tasks():
    """Load tasks with caching"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        return task_sheet.get_all_records()
    except Exception as e:
        st.error(f"Error loading tasks: {e}")
        return []

def clear_cache():
    """Clear all cached data"""
    st.cache_data.clear()

def verify_user_credentials(username, password):
    """Verify user credentials against Google Sheets"""
    users = load_users()
    existing_user = next((user for user in users if user['username'] == username), None)

    if existing_user:
        # User exists, check password
        stored_password = existing_user.get('password', '')
        return stored_password == password, "existing", existing_user.get('role')
    else:
        # New user, any password is acceptable for registration
        return True, "new", None

def ensure_user(username, role, password):
    """Add new user or verify existing user credentials"""
    try:
        is_valid, user_status, existing_role = verify_user_credentials(username, password)

        if user_status == "new":
            # Add new user with password
            gc = get_gsheet_client()
            user_sheet = gc.open("Task-management").worksheet("users")
            user_sheet.append_row([username, role, password])
            clear_cache()
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
        clear_cache()
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
        # Find the row by iterating through the first column (ID)
        for i, row in enumerate(all_values):
            if row and str(row[0]) == str(task_id):
                return i + 1  # Return row number (1-indexed)
        return None
    except Exception as e:
        st.error(f"Error finding task: {e}")
        return None

def update_task_status(task_id, new_status):
    """Update task status"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        row_num = find_task_row(task_id)
        if row_num:
            task_sheet.update_cell(row_num, 6, new_status) # Status is in column 6
            return True
        return False
    except Exception as e:
        st.error(f"Error updating task status: {e}")
        return False

def delete_task(task_id):
    """Delete a task"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        row_num = find_task_row(task_id)
        if row_num:
            task_sheet.delete_rows(row_num)
            return True
        return False
    except Exception as e:
        st.error(f"Error deleting task: {e}")
        return False

def reassign_task(task_id, new_assignee):
    """Reassign task to different coordinator"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        row_num = find_task_row(task_id)
        if row_num:
            task_sheet.update_cell(row_num, 4, new_assignee) # Assigned_to is in column 4
            return True
        return False
    except Exception as e:
        st.error(f"Error reassigning task: {e}")
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
                # No immediate rerun here, let the main function handle routing
                st.rerun() # Rerun to switch to the appropriate view
            else:
                st.sidebar.error(f"Login failed: {message}")
        else:
            st.sidebar.error("Please enter both username and password")

def coordinator_view():
    """Coordinator dashboard"""
    st.title("📋 Coordinator Dashboard")
    username = st.session_state["username"]

    all_tasks = load_tasks()
    my_tasks = [t for t in all_tasks if t["assigned_to"] == username]

    # Statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Tasks", len(my_tasks))
    with col2:
        pending_count = len([t for t in my_tasks if t["status"] == "Pending"])
        st.metric("Pending", pending_count)
    with col3:
        done_count = len([t for t in my_tasks if t["status"] == "Done"])
        st.metric("Completed", done_count)

    # Add task for all coordinators (unassigned)
    with st.expander("➕ Create General Task"):
        st.info("Tasks created here will be unassigned and can be assigned by Heads to specific coordinators.")
        title = st.text_input("Task Title", key="coord_task_title")
        desc = st.text_area("Task Description", key="coord_task_desc")
        deadline_date = st.date_input("Deadline Date", datetime.now().date(), key="coord_deadline_date")
        deadline_time = st.time_input("Deadline Time", datetime.now().time(), key="coord_deadline_time")

        # Combine date and time for deadline string
        deadline_str = f"{deadline_date.strftime('%Y-%m-%d')} {deadline_time.strftime('%H:%M')}"

        if st.button("Create Task", key="coord_add_task"):
            if title.strip() and desc.strip():
                success = add_task(title, desc, "Unassigned", username, deadline_str)
                if success:
                    st.success("✅ Task created successfully! Data will refresh on save.")
                    # Do not rerun here; wait for explicit save if needed
                else:
                    st.error("Failed to create task.")
            else:
                st.error("Please fill in all fields")

    # Display assigned tasks
    st.subheader("🗂 My Assigned Tasks")

    if not my_tasks:
        st.info("No tasks assigned to you yet.")
    else:
        # Filter options
        status_filter = st.selectbox("Filter by Status", ["All", "Pending", "Done"], key="coord_filter")

        filtered_tasks = my_tasks if status_filter == "All" else [t for t in my_tasks if t["status"] == status_filter]

        for i, task in enumerate(filtered_tasks):
            with st.container():
                col1, col2 = st.columns([4, 1])

                with col1:
                    st.markdown(f"**{task['title']}**")
                    st.markdown(f"📄 {task['description']}")

                    status_color = "🟢" if task['status'] == "Done" else "🟡"
                    st.markdown(f"{status_color} Status: **{task['status']}** | Created by: **{task['created_by']}**")
                    # Display deadline
                    deadline_display = task.get('deadline', 'N/A')
                    if deadline_display != 'N/A' and deadline_display < datetime.now().strftime("%Y-%m-%d %H:%M"):
                         st.markdown(f"🚨 **Deadline: {deadline_display} (OVERDUE!)**")
                    else:
                        st.markdown(f"📅 Deadline: {deadline_display}")
                    st.markdown(f"Created On: {task.get('timestamp', 'N/A')}")

                with col2:
                    if task["status"] == "Pending":
                        if st.button("✅ Mark Done", key=f"done_{task['id']}_{i}"):
                            success = update_task_status(task["id"], "Done")
                            if success:
                                st.success("Task marked as done! Data will refresh on save.")
                                # Do not rerun here
                            else:
                                st.error("Failed to update status.")
                    else:
                        if st.button("🔄 Reopen", key=f"reopen_{task['id']}_{i}"):
                            success = update_task_status(task["id"], "Pending")
                            if success:
                                st.success("Task reopened! Data will refresh on save.")
                                # Do not rerun here
                            else:
                                st.error("Failed to reopen task.")

                st.divider()

def head_view():
    """Head dashboard"""
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
        pending_count = len([t for t in all_tasks if t["status"] == "Pending"])
        st.metric("Pending", pending_count)
    with col3:
        done_count = len([t for t in all_tasks if t["status"] == "Done"])
        st.metric("Completed", done_count)
    with col4:
        unassigned_count = len([t for t in all_tasks if t["assigned_to"] == "Unassigned"])
        st.metric("Unassigned", unassigned_count)

    tab1, tab2, tab3 = st.tabs(["📝 Create & Assign", "📊 All Tasks", "⚙️ Manage Tasks"])

    with tab1:
        # Create and assign task
        st.subheader("Create & Assign New Task")
        col1, col2 = st.columns(2)

        with col1:
            title = st.text_input("Task Title", key="head_task_title")
            desc = st.text_area("Task Description", key="head_task_desc")
            deadline_date = st.date_input("Deadline Date", datetime.now().date(), key="head_deadline_date")
            deadline_time = st.time_input("Deadline Time", datetime.now().time(), key="head_deadline_time")

            # Combine date and time for deadline string
            deadline_str = f"{deadline_date.strftime('%Y-%m-%d')} {deadline_time.strftime('%H:%M')}"

        with col2:
            if coordinators:
                # Allow selecting multiple coordinators
                assignees = st.multiselect("Assign To Coordinator(s)", coordinators, key="head_assignee")
            else:
                st.warning("No coordinators available")
                assignees = []

        if st.button("Create & Assign Task", key="head_create_task"):
            if title.strip() and desc.strip() and assignees:
                all_success = True
                for assignee in assignees:
                    success = add_task(title, desc, assignee, username, deadline_str)
                    if not success:
                        all_success = False
                        break
                if all_success:
                    st.success(f"✅ Task(s) assigned to {', '.join(assignees)}! Data will refresh on save.")
                    # Do not rerun here
                else:
                    st.error("Failed to create one or more tasks.")
            else:
                st.error("Please fill in all fields and select at least one coordinator")

    with tab2:
        # View all tasks
        st.subheader("All Tasks Overview")

        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.selectbox("Filter by Status", ["All", "Pending", "Done", "Unassigned"], key="head_status_filter")
        with col2:
            assignee_filter = st.selectbox("Filter by Assignee", ["All"] + coordinators + ["Unassigned"], key="head_assignee_filter")
        with col3:
            # Refresh button will now trigger a full data refresh
            if st.button("🔄 Save Changes & Refresh Data", key="refresh_data"):
                clear_cache()
                st.rerun()

        # Apply filters
        filtered_tasks = all_tasks
        if status_filter != "All":
            if status_filter == "Unassigned":
                filtered_tasks = [t for t in filtered_tasks if t.get("assigned_to") == "Unassigned"]
            else:
                filtered_tasks = [t for t in filtered_tasks if t.get("status") == status_filter]

        if assignee_filter != "All":
            filtered_tasks = [t for t in filtered_tasks if t.get("assigned_to") == assignee_filter]

        # Display tasks
        if not filtered_tasks:
            st.info("No tasks match the current filters.")
        else:
            for i, task in enumerate(filtered_tasks):
                with st.container():
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**{task['title']}**")
                        st.markdown(f"📄 {task['description']}")

                        status_color = "🟢" if task.get('status') == "Done" else "🟡" if task.get('status') == "Pending" else "🔴"
                        st.markdown(f"{status_color} **{task.get('status')}** | Assigned to: **{task.get('assigned_to')}** | Created by: **{task.get('created_by')}**")
                        # Display deadline
                        deadline_display = task.get('deadline', 'N/A')
                        if deadline_display != 'N/A' and deadline_display < datetime.now().strftime("%Y-%m-%d %H:%M"):
                            st.markdown(f"🚨 **Deadline: {deadline_display} (OVERDUE!)**")
                        else:
                            st.markdown(f"📅 Deadline: {deadline_display}")
                        st.markdown(f"Created On: {task.get('timestamp', 'N/A')}")

                    with col2:
                        # Quick assign for unassigned tasks
                        if task.get("assigned_to") == "Unassigned" and coordinators:
                            quick_assign = st.selectbox("Quick Assign", ["Select..."] + coordinators, key=f"quick_{task['id']}_{i}")
                            if quick_assign != "Select...":
                                if st.button("Assign", key=f"assign_{task['id']}_{i}"):
                                    success = reassign_task(task["id"], quick_assign)
                                    if success:
                                        st.success(f"Assigned to {quick_assign}! Data will refresh on save.")
                                        # Do not rerun here
                                    else:
                                        st.error("Failed to assign task.")

                    st.divider()

    with tab3:
        # Manage tasks
        st.subheader("Task Management")

        if all_tasks:
            # Select task to manage
            task_options = [f"{t.get('title', 'N/A')} (ID: {t.get('id', 'N/A')}) - {t.get('assigned_to', 'N/A')}" for t in all_tasks]
            selected_task_display = st.selectbox("Select Task to Manage", task_options, key="manage_task_select")

            if selected_task_display:
                # Find the actual task dictionary from the display string
                selected_task_id = selected_task_display.split("(ID: ")[1].split(")")[0]
                selected_task = next((t for t in all_tasks if t.get('id') == selected_task_id), None)

                if selected_task:
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        # Reassign task
                        if coordinators:
                            current_assignee_index = 0
                            if selected_task.get('assigned_to') in coordinators:
                                current_assignee_index = coordinators.index(selected_task['assigned_to'])
                            new_assignee = st.selectbox("Reassign to", coordinators,
                                                        index=current_assignee_index,
                                                        key="reassign_select")
                            if st.button("🔄 Reassign Task", key="reassign_btn"):
                                success = reassign_task(selected_task["id"], new_assignee)
                                if success:
                                    st.success(f"Task reassigned to {new_assignee}! Data will refresh on save.")
                                    # Do not rerun here
                                else:
                                    st.error("Failed to reassign task.")
                        else:
                            st.info("No coordinators to reassign to.")

                    with col2:
                        # Change status
                        current_status = selected_task.get('status', 'Pending')
                        new_status = st.selectbox("Change Status", ["Pending", "Done"],
                                                    index=0 if current_status == "Pending" else 1,
                                                    key="status_select")
                        if st.button("📝 Update Status", key="status_btn"):
                            success = update_task_status(selected_task["id"], new_status)
                            if success:
                                st.success(f"Status updated to {new_status}! Data will refresh on save.")
                                # Do not rerun here
                            else:
                                st.error("Failed to update status.")

                    with col3:
                        # Delete task
                        st.warning("⚠️ Danger Zone")
                        if st.button("🗑️ Delete Task", key="delete_btn", type="secondary"):
                            success = delete_task(selected_task["id"])
                            if success:
                                st.success("Task deleted! Data will refresh on save.")
                                # Do not rerun here
                            else:
                                st.error("Failed to delete task.")
                else:
                    st.info("Selected task not found (might have been deleted).")
        else:
            st.info("No tasks available to manage.")

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
    </style>
    """, unsafe_allow_html=True)

    if "username" not in st.session_state:
        st.title("🏢 Task Management System")
        st.markdown("### Welcome! Please log in to continue.")
        login()
    else:
        # Sidebar user info
        st.sidebar.success(f"👤 **{st.session_state['username']}**")
        st.sidebar.info(f"🏷️ Role: {st.session_state['role']}")

        if st.sidebar.button("🚪 Logout", key="logout_btn"):
            st.session_state.clear()
            st.rerun()

        # No auto-refresh checkbox, rely on explicit refresh button
        # if auto_refresh:
        #     time.sleep(30)
        #     st.rerun()

        # Route to appropriate view
        if st.session_state["role"] == "Coordinator":
            coordinator_view()
        elif st.session_state["role"] == "Head":
            head_view()

if __name__ == "__main__":
    main()
