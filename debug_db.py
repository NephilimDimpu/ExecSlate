
import database as db
import os

print(f"DB File: {db.DB_FILE}")

# 1. Initialize DB (it happens on import, but ensuring permissions)
print("Initializing DB...")
try:
    db.init_db()
    print("DB Initialized.")
except Exception as e:
    print(f"DB Init Failed: {e}")

# 2. Create User
email = "test_debug@example.com"
print(f"Creating user {email}...")
try:
    user = db.get_user_by_email(email)
    if user:
        print("User exists, skipping create.")
        user_id = user["id"]
    else:
        user_id = db.create_user(email, "hashed_password", "free")
        print(f"User created with ID: {user_id}")
except Exception as e:
    print(f"Create User Failed: {e}")
    user_id = None

# 3. Get User by ID
if user_id:
    print(f"Fetching user ID {user_id}...")
    try:
        user_data = db.get_user_by_id(user_id)
        print(f"User Data: {user_data}")
        
        if user_data is None:
            print("CRITICAL: get_user_by_id returned None!")
        else:
            print(f"Uploads: {user_data['uploads']}")
            print(f"Regens: {user_data['ai_regens']}")
    except Exception as e:
        print(f"Get User Failed: {e}")

# 4. Get User Projects
if user_id:
    print("Fetching projects...")
    try:
        projects = db.get_user_projects(user_id)
        print(f"Projects: {projects}")
    except Exception as e:
        print(f"Get Projects Failed: {e}")
