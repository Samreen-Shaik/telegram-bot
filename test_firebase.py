import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase with your service account credentials
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred)

# Connect to Firestore
db = firestore.client()

# Try to fetch all users from the "users" collection
try:
    users_ref = db.collection("users").get()
    print(f"✅ Connected! Users in database: {len(users_ref)}")
except Exception as e:
    print(f"❌ Error connecting to Firebase: {e}")
