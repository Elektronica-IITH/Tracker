import streamlit as st
import gspread
import os
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid
import time

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
    creds_dict = json.loads(creds_json)
    
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

def ensure_user(username, role):
    """Add new user if not exists"""
    try:
        users = load_users()
        if not any(u['username'] == username for u in users):
            gc = get_gsheet_client()
            user_sheet = gc.open("Task-management").worksheet("users")
            user_sheet.append_row([username, role])
            clear_cache()
            return True
        return False
    except Exception as e:
        st.error(f"Error adding user: {e}")
        return False

def add_task(title, desc, assigned_to, created_by):
    """Add new task"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        task_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        task_sheet.append_row([task_id, title, desc, assigned_to, created_by, "Pending", timestamp])
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Error adding task: {e}")
        return False

def update_task_status(task_id, new_status):
    """Update task status"""
    try:
        gc = get_gsheet_client()
        task_sheet = gc.open("Task-management").worksheet("tasks")
        
        # Find the task row
        cell = task_sheet.find(task_id)
        if cell:
            # Update status column (column 6)
            task_sheet.update_cell(cell.row, 6, new_status)
            clear_cache()
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
        
        # Find the task row
        cell = task_sheet.find(task_id)
        if cell:
            task_sheet.delete_rows(cell.row)
            clear_cache()
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
        
        # Find the task row
        cell = task_sheet.find(task_id)
        if cell:
            # Update assigned_to column (column 4)
            task_sheet.update_cell(cell.row, 4, new_assignee)
            clear_cache()
            return True
        return False
    except Exception as e:
        st.error(f"Error reassigning task: {e}")
        return False

def login():
    """Handle user login"""
    st.sidebar.title("🔐 Login")
    username = st.sidebar.text_input("Username", key="login_username")
    role = st.sidebar.selectbox("Role", ["Coordinator", "Head"], key="login_role")
    
    if st.sidebar.button("Login", key="login_btn"):
        if username.strip():
            is_new = ensure_user(username, role)
            st.session_state["username"] = username
            st.session_state["role"] = role
            
            if is_new:
                st.sidebar.success(f"New user created: {username} ({role})")
            else:
                st.sidebar.success(f"Logged in as {username} ({role})")
            st.rerun()
        else:
            st.sidebar.error("Please enter a username")

def coordinator_view():
    """Coordinator dashboard"""
    st.title("📋 Coordinator Dashboard")
    username = st.session_state["username"]
    
    # Load tasks assigned to this coordinator
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
        
        if st.button("Create Task", key="coord_add_task"):
            if title.strip() and desc.strip():
                success = add_task(title, desc, "Unassigned", username)
                if success:
                    st.success("✅ Task created successfully!")
                    time.sleep(1)
                    st.rerun()
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
                    
                    # Status badge
                    status_color = "🟢" if task['status'] == "Done" else "🟡"
                    st.markdown(f"{status_color} Status: **{task['status']}** | Created by: **{task['created_by']}** | Date: {task.get('timestamp', 'N/A')}")
                
                with col2:
                    if task["status"] == "Pending":
                        if st.button("✅ Mark Done", key=f"done_{task['id']}_{i}"):
                            success = update_task_status(task["id"], "Done")
                            if success:
                                st.success("Task marked as done!")
                                time.sleep(1)
                                st.rerun()
                    else:
                        if st.button("🔄 Reopen", key=f"reopen_{task['id']}_{i}"):
                            success = update_task_status(task["id"], "Pending")
                            if success:
                                st.success("Task reopened!")
                                time.sleep(1)
                                st.rerun()
                
                st.divider()

def head_view():
    """Head dashboard"""
    st.title("👤 Head Dashboard")
    username = st.session_state["username"]
    
    # Load data
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
    
    # Tabs for better organization
    tab1, tab2, tab3 = st.tabs(["📝 Create & Assign", "📊 All Tasks", "⚙️ Manage Tasks"])
    
    with tab1:
        # Create and assign task
        st.subheader("Create & Assign New Task")
        col1, col2 = st.columns(2)
        
        with col1:
            title = st.text_input("Task Title", key="head_task_title")
            desc = st.text_area("Task Description", key="head_task_desc")
        
        with col2:
            if coordinators:
                assignee = st.selectbox("Assign To Coordinator", coordinators, key="head_assignee")
            else:
                st.warning("No coordinators available")
                assignee = None
        
        if st.button("Create & Assign Task", key="head_create_task"):
            if title.strip() and desc.strip() and assignee:
                success = add_task(title, desc, assignee, username)
                if success:
                    st.success(f"✅ Task assigned to {assignee}!")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("Please fill in all fields and select a coordinator")
    
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
            if st.button("🔄 Refresh Data", key="refresh_data"):
                clear_cache()
                st.rerun()
        
        # Apply filters
        filtered_tasks = all_tasks
        if status_filter != "All":
            if status_filter == "Unassigned":
                filtered_tasks = [t for t in filtered_tasks if t["assigned_to"] == "Unassigned"]
            else:
                filtered_tasks = [t for t in filtered_tasks if t["status"] == status_filter]
        
        if assignee_filter != "All":
            filtered_tasks = [t for t in filtered_tasks if t["assigned_to"] == assignee_filter]
        
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
                        
                        # Status and assignment info
                        status_color = "🟢" if task['status'] == "Done" else "🟡" if task['status'] == "Pending" else "🔴"
                        st.markdown(f"{status_color} **{task['status']}** | Assigned to: **{task['assigned_to']}** | Created by: **{task['created_by']}**")
                        st.markdown(f"📅 Created: {task.get('timestamp', 'N/A')}")
                    
                    with col2:
                        # Quick actions
                        if task["assigned_to"] == "Unassigned" and coordinators:
                            quick_assign = st.selectbox("Quick Assign", ["Select..."] + coordinators, key=f"quick_{task['id']}_{i}")
                            if quick_assign != "Select..." and st.button("Assign", key=f"assign_{task['id']}_{i}"):
                                success = reassign_task(task["id"], quick_assign)
                                if success:
                                    st.success(f"Assigned to {quick_assign}!")
                                    time.sleep(1)
                                    st.rerun()
                    
                    st.divider()
    
    with tab3:
        # Manage tasks
        st.subheader("Task Management")
        
        if all_tasks:
            # Select task to manage
            task_options = [f"{t['title']} (ID: {t['id']}) - {t['assigned_to']}" for t in all_tasks]
            selected_task_idx = st.selectbox("Select Task to Manage", range(len(task_options)), 
                                           format_func=lambda x: task_options[x], key="manage_task_select")
            
            if selected_task_idx is not None:
                selected_task = all_tasks[selected_task_idx]
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    # Reassign task
                    if coordinators:
                        new_assignee = st.selectbox("Reassign to", coordinators, 
                                                  index=coordinators.index(selected_task['assigned_to']) if selected_task['assigned_to'] in coordinators else 0,
                                                  key="reassign_select")
                        if st.button("🔄 Reassign Task", key="reassign_btn"):
                            success = reassign_task(selected_task["id"], new_assignee)
                            if success:
                                st.success(f"Task reassigned to {new_assignee}!")
                                time.sleep(1)
                                st.rerun()
                
                with col2:
                    # Change status
                    current_status = selected_task['status']
                    new_status = st.selectbox("Change Status", ["Pending", "Done"], 
                                            index=0 if current_status == "Pending" else 1,
                                            key="status_select")
                    if st.button("📝 Update Status", key="status_btn"):
                        success = update_task_status(selected_task["id"], new_status)
                        if success:
                            st.success(f"Status updated to {new_status}!")
                            time.sleep(1)
                            st.rerun()
                
                with col3:
                    # Delete task
                    st.warning("⚠️ Danger Zone")
                    if st.button("🗑️ Delete Task", key="delete_btn", type="secondary"):
                        success = delete_task(selected_task["id"])
                        if success:
                            st.success("Task deleted!")
                            time.sleep(1)
                            st.rerun()
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
        
        # Auto-refresh option
        auto_refresh = st.sidebar.checkbox("🔄 Auto-refresh (30s)", key="auto_refresh")
        if auto_refresh:
            time.sleep(30)
            st.rerun()
        
        # Route to appropriate view
        if st.session_state["role"] == "Coordinator":
            coordinator_view()
        elif st.session_state["role"] == "Head":
            head_view()

if __name__ == "__main__":
    main()