import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid

# Google Sheets Auth
@st.cache_resource
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
    return gspread.authorize(creds)

gc = get_gsheet_client()
SHEET_NAME = "Task-management"
task_sheet = gc.open(SHEET_NAME).worksheet("tasks")
user_sheet = gc.open(SHEET_NAME).worksheet("users")

# Load users
def load_users():
    users = user_sheet.get_all_records()
    return users

# Load tasks
def load_tasks():
    return task_sheet.get_all_records()

# Add new user if not exists
def ensure_user(username, role):
    users = load_users()
    if not any(u['username'] == username for u in users):
        user_sheet.append_row([username, role])

# Add task
def add_task(title, desc, assigned_to, created_by):
    task_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    task_sheet.append_row([task_id, title, desc, assigned_to, created_by, "Pending", timestamp])

# Mark task done
def mark_done(task_id):
    cell = task_sheet.find(task_id)
    status_col = 6  # "status"
    task_sheet.update_cell(cell.row, status_col + 1, "Done")

# Auth and role-based routing
def login():
    st.sidebar.title("Login")
    username = st.sidebar.text_input("Username")
    role = st.sidebar.selectbox("Role", ["Coordinator", "Head"])
    if st.sidebar.button("Login"):
        ensure_user(username, role)
        st.session_state["username"] = username
        st.session_state["role"] = role
        st.success(f"Logged in as {username} ({role})")
        st.rerun()

# App logic
def coordinator_view():
    st.title("📋 Coordinator Dashboard")
    username = st.session_state["username"]
    tasks = [t for t in load_tasks() if t["assigned_to"] == username or t["assigned_to"] == "All"]

    with st.expander("➕ Add Task (Global)"):
        title = st.text_input("Title")
        desc = st.text_area("Description")
        if st.button("Add Task"):
            add_task(title, desc, "All", username)
            st.success("Task added.")
            st.rerun()

    st.subheader("🗂 Assigned Tasks")
    for task in tasks:
        with st.container():
            st.markdown(f"**{task['title']}**")
            st.markdown(task["description"])
            st.markdown(f"Status: `{task['status']}` • Assigned by: `{task['created_by']}`")
            if task["status"] != "Done":
                if st.button(f"Mark as Done ✅ - {task['id']}"):
                    mark_done(task["id"])
                    st.success("Marked as done!")
                    st.rerun()

def head_view():
    st.title("👤 Head Dashboard")
    username = st.session_state["username"]
    tasks = load_tasks()
    users = load_users()
    coordinator_names = [u["username"] for u in users if u["role"] == "Coordinator"]

    with st.expander("➕ Add & Assign Task"):
        title = st.text_input("Task Title")
        desc = st.text_area("Description")
        assignee = st.selectbox("Assign To", coordinator_names)
        if st.button("Create Task"):
            add_task(title, desc, assignee, username)
            st.success("Task assigned.")
            st.rerun()

    st.subheader("📊 All Tasks")
    filter_status = st.selectbox("Filter by Status", ["All", "Pending", "Done"])
    filtered = tasks if filter_status == "All" else [t for t in tasks if t["status"] == filter_status]
    for task in filtered:
        with st.container():
            st.markdown(f"**{task['title']}**")
            st.markdown(f"📄 {task['description']}")
            st.markdown(f"Assigned to: `{task['assigned_to']}` • Created by: `{task['created_by']}` • Status: `{task['status']}`")

# Entry point
if "username" not in st.session_state:
    login()
else:
    st.sidebar.success(f"Logged in as {st.session_state['username']} ({st.session_state['role']})")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    if st.session_state["role"] == "Coordinator":
        coordinator_view()
    elif st.session_state["role"] == "Head":
        head_view()
