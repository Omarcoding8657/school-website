from flask import Flask, jsonify, make_response, request, render_template
from flask_socketio import SocketIO, emit, join_room
import random
import json
import os
from datetime import datetime

# ---------------------- Flask Setup ----------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STUDENTS_FILE = os.path.join(BASE_DIR, "students.json")

# Store active chat users
active_users = {}

# ---------------------- JSON Helpers ----------------------
def load_students():
    try:
        with open(STUDENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                out = {}
                for item in data:
                    key = str(item.get("id", len(out) + 1))
                    out[key] = item
                return out
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {}

def save_students(students_dict):
    with open(STUDENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(students_dict, f, indent=2, ensure_ascii=False)

def allow_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

# ---------------------- Web Pages ----------------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/game")
def game():
    return render_template("games.html")

@app.route("/chat")
def chat_page():
    return render_template("chat.html")

# ---------------------- API Routes ----------------------
@app.route("/api")
def api_root():
    return "Server is active. Try <code>/api/students</code>, <code>/api/random_student</code>, <code>/api/student/&lt;id&gt;</code> and <code>/api/count</code>."

@app.route("/api/students")
def all_students():
    students = load_students()
    resp = make_response(jsonify(list(students.values())), 200)
    return allow_cors(resp)

@app.route("/api/random_student")
def random_student():
    students = load_students()
    if not students:
        return allow_cors(make_response(jsonify({"error": "No students found"}), 404))
    choice = random.choice(list(students.values()))
    return allow_cors(make_response(jsonify(choice), 200))

@app.route("/api/student/<int:student_id>")
def student_by_id(student_id):
    students = load_students()
    key = str(student_id)
    data = students.get(key)
    if not data:
        return allow_cors(make_response(jsonify({"error": "Student not found"}), 404))
    return allow_cors(make_response(jsonify(data), 200))

@app.route("/api/student_by_name/<name>")
def get_student_by_name(name):
    students = load_students()
    for student in students.values():
        if student["name"].lower() == name.lower():
            return jsonify(student)
    return make_response(jsonify({"error": "Student not found"}), 404)

@app.route("/api/student")
def student_by_query():
    students = load_students()
    sid = request.args.get("id", "").strip()
    if not sid:
        return allow_cors(make_response(jsonify({"error": "Missing id"}), 400))
    try:
        sid_int = int(sid)
    except Exception:
        return allow_cors(make_response(jsonify({"error": "Invalid id"}), 400))
    data = students.get(str(sid_int))
    if not data:
        return allow_cors(make_response(jsonify({"error": "Student not found"}), 404))
    return allow_cors(make_response(jsonify(data), 200))

@app.route("/api/count")
def student_count():
    students = load_students()
    return allow_cors(make_response(jsonify(len(students)), 200))

@app.route("/check_user", methods=["POST"])
def check_user():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    if not email:
        return jsonify({"exists": False})
    students = load_students()
    exists = any((s.get("email") or "").strip().lower() == email for s in students.values())
    return jsonify({"exists": exists})

@app.route("/students", methods=["GET"])
def get_students():
    with open(STUDENTS_FILE, "r", encoding="utf-8") as f:
        students = json.load(f)
    return jsonify(students)

@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No JSON received"}), 400

    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    if not name or not email:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    students = load_students()

    for s in students.values():
        if (s.get("email") or "").strip().lower() == email:
            return jsonify({"status": "exists"})

    existing_ids = [int(k) for k in students.keys() if k.isdigit()]
    next_id = max(existing_ids, default=0) + 1
    key = str(next_id)

    student_entry = {
        "id": next_id,
        "name": name,
        "email": email,
        "age": data.get("age") or "",
        "dob": data.get("dob") or "",
        "image": data.get("image") or "",
        "city": data.get("city") or "",
        "favorite_color": data.get("favorite_color") or "",
        "hobbies": data.get("hobbies") or []
    }

    students[key] = student_entry
    save_students(students)
    return jsonify({"status": "success", "student": student_entry}), 201

@app.route("/api/delete_student/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):
    students = load_students()
    key = str(student_id)

    if key not in students:
        return jsonify({"status": "error", "message": "Student not found"}), 404

    deleted_student = students.pop(key)
    save_students(students)

    return jsonify({"status": "success", "deleted": deleted_student})

# ---------------------- Chat Socket.IO Events ----------------------
@socketio.on('join')
def handle_join(data):
    username = data['username']
    active_users[request.sid] = username
    join_room('chat')

    emit('system_message', {
        'message': f'{username} joined the chat'
    }, room='chat')

    emit('user_count', {
        'count': len(active_users)
    }, broadcast=True)

@socketio.on('message')
def handle_message(data):
    username = active_users.get(request.sid, 'Anonymous')
    timestamp = datetime.now().strftime('%H:%M')

    emit('message', {
        'username': username,
        'message': data['message'],
        'timestamp': timestamp
    }, room='chat', broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    username = active_users.pop(request.sid, None)
    if username:
        emit('system_message', {
            'message': f'{username} left the chat'
        }, room='chat')

        emit('user_count', {
            'count': len(active_users)
        }, broadcast=True)

# ---------------------- Run Server ----------------------
if __name__ == '__main__':
    socketio.run(app, debug=True)