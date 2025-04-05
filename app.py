from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from dotenv import load_dotenv
import bcrypt
from datetime import timedelta
import os

load_dotenv()

app = Flask(__name__)

# MongoDB Configuration - Using a separate database for SmartClassroom
app.config["MONGO_URI"] = os.getenv("DB_CONNECTION_STRING") + "smartclassroom" 
mongo = PyMongo(app)

# JWT Configuration
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET")
jwt = JWTManager(app)

@app.route("/signup", methods=["POST"])
def signup():
    print("Received signup request") 
    data = request.get_json()

    # Validate input fields for common fields
    if not data.get("username") or not data.get("password") or not data.get("name") or not data.get("type"):
        return jsonify({"msg": "All fields (username, password, name, type) are required."}), 400

    username = data["username"]
    password = data["password"]
    name = data["name"]
    user_type = data["type"]

    # Check if the username already exists
    existing_user = mongo.db.users.find_one({"username": username})
    if existing_user:
        return jsonify({"msg": "Username already exists"}), 400

    # Hash password
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    # Prepare the data to be inserted into MongoDB
    user_data = {
        "username": username,
        "password": hashed_password,
        "name": name,
        "type": user_type
    }

    # If the user is a Student, add student details if provided (make them optional)
    if user_type == "Student":
        student_details = {
            "class": data.get("class", ""),
            "registerNumber": data.get("registerNumber", ""),
            "mobileNumber": data.get("mobileNumber", ""),
            "address": data.get("address", ""),
        }
        user_data.update(student_details)

    # Insert user data into the smartclassroom database
    mongo.db.users.insert_one(user_data)

    return jsonify({"msg": "User created successfully!"}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    # Validate input fields
    if not data.get("username") or not data.get("password"):
        return jsonify({"msg": "Username and password are required."}), 400

    username = data["username"]
    password = data["password"]

    # Find the user in the database
    user = mongo.db.users.find_one({"username": username})

    # Check if the password matches
    if user and bcrypt.checkpw(password.encode("utf-8"), user["password"]):
        # Generate JWT token
        access_token = create_access_token(identity=username, expires_delta=timedelta(days=1))
        return jsonify({"access_token": access_token, "user": user["type"], "username": user["username"]}), 200
    else:
        return jsonify({"msg": "Invalid credentials"}), 401
@app.route("/mark-attendance", methods=["POST"])
@jwt_required()
def mark_attendance():
    username = get_jwt_identity()
    data = request.get_json()

    # Check if the class number is provided
    class_number = data.get("class_number")
    if not class_number:
        return jsonify({"msg": "Class number is required."}), 400

    # Find the student in the database
    student = mongo.db.users.find_one({"username": username, "type": "Student"})
    if not student:
        return jsonify({"msg": "Student not found."}), 404

    # Fetch current attendance data from the database
    student_attendance = mongo.db.attendance.find_one({"username": username})
    
    if student_attendance:
        # Check if the attendance for the class has already been marked
        if class_number in student_attendance["attendance"]:
            return jsonify({"msg": f"Attendance for Class {class_number} is already marked."}), 400
        
        # Add the new class to the attendance list
        student_attendance["attendance"].append(class_number)
        mongo.db.attendance.update_one({"username": username}, {"$set": {"attendance": student_attendance["attendance"]}})
    else:
        # If attendance is not found, create a new record
        mongo.db.attendance.insert_one({"username": username, "attendance": [class_number]})

    return jsonify({"msg": f"Attendance for Class {class_number} marked."}), 200

@app.route("/students", methods=["GET"])
@jwt_required()
def get_students():
    # Get the username from the JWT token
    current_user = get_jwt_identity()

    # Find all students in the database (assuming only 'Student' type users are fetched)
    students = mongo.db.users.find({"type": "Student"})
    
    students_list = []
    for student in students:
        # Fetch attendance data for each student
        student_attendance = mongo.db.attendance.find_one({"username": student["username"]})
        attendance_percentage = 0
        if student_attendance:
            attendance_count = len(student_attendance["attendance"])
            attendance_percentage = (attendance_count / 10) * 100  # Assuming 10 classes as a max number for simplicity

        student_data = {
            "username": student["username"],
            "name": student["name"],
            "attendance": round(attendance_percentage, 2),
            "class": student.get("class", "N/A"),
            "registerNumber": student.get("registerNumber", "N/A"),
            "mobileNumber": student.get("mobileNumber", "N/A"),
        }
        
        students_list.append(student_data)
    
    return jsonify(students_list), 200

@app.route("/create-quiz", methods=["POST"])
@jwt_required()
def create_quiz():
    data = request.get_json()

    # Validate required fields
    if not data.get("question") or not data.get("options") or not data.get("correctAnswer"):
        return jsonify({"msg": "Please provide all the fields: question, options, and correctAnswer."}), 400

    question = data["question"]
    options = data["options"]
    
    try:
        correct_answer = int(data["correctAnswer"])  # Convert correct_answer to an integer
    except ValueError:
        return jsonify({"msg": "Correct answer must be a number."}), 400

    # Ensure that correct_answer is one of the options (1-based index)
    if not (1 <= correct_answer <= 4):
        return jsonify({"msg": "Correct answer must be between 1 and 4."}), 400

    quiz = {
        "question": question,
        "options": options,
        "correctAnswer": options[correct_answer - 1],  # Mapping 1-4 to 0-3 index
    }

    # Insert the quiz into MongoDB
    mongo.db.quizzes.insert_one(quiz)

    return jsonify({"msg": "Quiz created successfully!"}), 201



@app.route("/get-quizzes", methods=["GET"])
@jwt_required()
def get_quizzes():
    # Retrieve quizzes from MongoDB
    quizzes = mongo.db.quizzes.find()
    quiz_list = []
    for quiz in quizzes:
        quiz_list.append({
            "question": quiz["question"],
            "options": quiz["options"],
            "correctAnswer": quiz["correctAnswer"]
        })
    
    return jsonify(quiz_list), 200

@app.route("/save-quiz-result", methods=["POST"])
@jwt_required()
def save_quiz_result():
    data = request.get_json()

    student_username = data.get('studentUsername')
    percentage = data.get('percentage')

    if not student_username or not percentage:
        return jsonify({"msg": "Student username and percentage are required."}), 400

    # Save the quiz result to the database (MongoDB)
    result = {
        "studentUsername": student_username,
        "percentage": percentage,
    }

    # Insert result into MongoDB (results collection)
    mongo.db.quiz_results.insert_one(result)

    return jsonify({"msg": "Quiz result saved successfully!"}), 201

@app.route("/get-quiz-results", methods=["GET"])
@jwt_required()
def get_quiz_results():
    # Fetch results from the database
    results = mongo.db.quiz_results.find()
    results_list = []
    for result in results:
        results_list.append({
            "studentUsername": result["studentUsername"],
            "percentage": result["percentage"]
        })
    
    return jsonify(results_list), 200

@app.route("/upload-study-material", methods=["POST"])
def upload_study_material():
    data = request.get_json()

    if not data.get('name') or not data.get('file'):
        return jsonify({"msg": "File name and file data are required."}), 400

    file_name = data['name']
    file_data = data['file']

    # Store the file in MongoDB as Base64
    study_material = {
        "name": file_name,
        "file": file_data  # Store Base64 encoded file
    }

    mongo.db.study_materials.insert_one(study_material)

    return jsonify({"msg": "Study material uploaded successfully!"}), 201

@app.route('/get-timetable', methods=['GET'])
def get_timetable():
    # Fetch timetable from MongoDB
    timetable = mongo.db.timetable.find_one()
    if not timetable:
        return jsonify({"msg": "No timetable found"}), 404
    return jsonify(timetable), 200

@app.route('/save-timetable', methods=['POST'])
def save_timetable():
    data = request.get_json()

    if not data:
        return jsonify({"msg": "No data provided"}), 400

    # Check if a timetable already exists (based on the `_id` or other criteria)
    existing_timetable = mongo.db.timetable.find_one()

    if existing_timetable:
        # If a timetable already exists, update it
        mongo.db.timetable.replace_one({}, data)  # Replacing the existing document
        return jsonify({"msg": "Timetable updated successfully!"}), 200
    else:
        # If no timetable exists, insert a new one
        mongo.db.timetable.insert_one(data)
        return jsonify({"msg": "Timetable saved successfully!"}), 201

@app.route("/get-attendance", methods=["GET"])
@jwt_required()
def get_attendance():
    username = get_jwt_identity()  # Fetching username from JWT

    print(f"Fetching attendance for user: {username}")  # Debugging log

    # Fetch the student's attendance from the database
    student_attendance = mongo.db.attendance.find_one({"username": username})
    
    if student_attendance:
        print(f"Attendance found: {student_attendance['attendance']}")  # Debugging log
        return jsonify({"attendance": student_attendance["attendance"]}), 200
    else:
        print("No attendance found for user")  # Debugging log
        return jsonify({"attendance": []}), 404


if __name__ == "__main__":
    app.run(host=os.getenv("SERVER_HOST"), port=int(os.getenv("SERVER_PORT")), debug=True)
