import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from hashlib import sha256
import datetime as dt
import os
import base64
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from flask_mail import Mail, Message
import random
import string
import json
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = 'your_secret_key'  # Replace with a secure key

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'nithin2004gowda@gmail.com'
app.config['MAIL_PASSWORD'] = 'yivvfowjfpyrbhil'
mail = Mail(app)

# SQLite database connection
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Create tables if not exist
def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create user_details table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            course_name TEXT NOT NULL,
            course_id TEXT NOT NULL,
            institution_name TEXT NOT NULL,
            institution_city TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            isVerified TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            verified_at TIMESTAMP,
            deleted_at TIMESTAMP
        )
    ''')

    # Create blockchain table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blockchain (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_detail_id INTEGER NOT NULL,
            encrypted_data TEXT NOT NULL,
            previous_hash TEXT,
            current_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_detail_id) REFERENCES user_details(id)
        )
    ''')

    conn.commit()
    conn.close()

# Database interaction functions
def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(username, password, role):
    hashed_password = sha256(password.encode()).hexdigest()  # Hash the password
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', (username, hashed_password, role))
    conn.commit()
    conn.close()

@app.route('/')
def home():
    return render_template('login_register.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = sha256(request.form.get('password').encode()).hexdigest()
    role = request.form.get('role')

    user = get_user_by_username(username)
    if user and user['password'] == password and user['role'] == role:
        # Store username and role in the session
        session['username'] = username
        session['role'] = role
        flash(f"Login successful as {role.capitalize()}!", 'success')

        if role == 'admin':
            return redirect(url_for('dashboard_admin'))
        return redirect(url_for('index'))
    else:
        flash('Invalid username, password, or role. Please try again.', 'danger')
        return render_template('login_register.html', username=username, role=role)  # Pass the entered details back

@app.route('/dashboard_admin')
def dashboard_admin():
    username = session.get('username', 'Admin')  # Default to 'admin' if session is empty
    return render_template('admin_dashboard.html', username=username)

@app.route('/dashboard_user')
def dashboard_user():
    username = session.get('username', 'User')  # Default to 'user' if session is empty
    user_data = session.get('user_data', {})  # Get user data from the session

    return render_template('user_dashboard.html', username=username, user_data=user_data)

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')

    if get_user_by_username(username):
        flash('Username already exists. Please choose a different one.', 'danger')
    else:
        add_user(username, password, role)
        flash(f'Registration successful as {role.capitalize()}. Please log in.', 'success')

    return redirect(url_for('home'))

@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if request.method == 'POST':
        user_data = {
            'name': request.form.get('name'),
            'email': request.form.get('email'),
            'phone': request.form.get('phone'),
            'course_name': request.form.get('course_name'),
            'course_id': request.form.get('course_id'),
            'institution_name': request.form.get('institution_name'),
            'institution_city': request.form.get('institution_city'),
            'start_date': request.form.get('start_date'),
            'end_date': request.form.get('end_date')
        }

        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert into user_details table
        cursor.execute('''INSERT INTO user_details (name, email, phone, course_name, course_id, institution_name, institution_city, start_date, end_date)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (user_data['name'], user_data['email'], user_data['phone'], user_data['course_name'], user_data['course_id'],
                        user_data['institution_name'], user_data['institution_city'], user_data['start_date'], user_data['end_date']))
        user_detail_id = cursor.lastrowid
        created_at = dt.datetime.now().strftime('%d/%m/%Y')

        # Serialize user_data to JSON with sorted keys
        serialized_data = json.dumps(user_data, sort_keys=True)
        encrypted_data = sha256(serialized_data.encode('utf-8')).hexdigest()

        # Blockchain-related hashing
        cursor = conn.cursor()
        cursor.execute('SELECT current_hash FROM blockchain ORDER BY id DESC LIMIT 1')
        last_hash = cursor.fetchone()
        previous_hash = last_hash['current_hash'] if last_hash else '0'

        current_hash = sha256((previous_hash + encrypted_data).encode()).hexdigest()
        cursor.execute('INSERT INTO blockchain (user_detail_id, encrypted_data, previous_hash, current_hash) VALUES (?, ?, ?, ?)',
                       (user_detail_id, encrypted_data, previous_hash, current_hash))

        conn.commit()

        cursor.execute('SELECT encrypted_data FROM blockchain WHERE user_detail_id = ?', (user_detail_id,))
        blockchain_record = cursor.fetchone()
        qr_data = blockchain_record['encrypted_data'] if blockchain_record else ''
        conn.close()

        # flash('Certificate data stored and blockchain transaction created successfully!', 'success')

        return render_template('certificate.html',
                               name=user_data['name'],
                               course_name=user_data['course_name'],
                               course_id=user_data['course_id'],
                               start_date=user_data['start_date'],
                               end_date=user_data['end_date'],
                               institution_name=user_data['institution_name'],
                               institution_city=user_data['institution_city'],
                               date=created_at,
                               qr_data=qr_data)
    return render_template('admin_dashboard.html')

# Path to save certificates
CERTIFICATE_FOLDER = os.path.join(app.static_folder, 'certificates')
os.makedirs(CERTIFICATE_FOLDER, exist_ok=True)

@app.route('/save_certificate', methods=['POST'])
def save_certificate():
    data = request.get_json()
    if 'image' in data and 'file_name' in data:
        image_data = data['image']
        file_name = data['file_name']
        file_path = os.path.join(CERTIFICATE_FOLDER, file_name)

        try:
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(image_data))
            return jsonify({"message": "Certificate saved successfully"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Invalid data"}), 400

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/contact')
def contact():
    return render_template('contact_us.html')

def decode_qr(image_path):
    # Read the uploaded image
    image = cv2.imread(image_path)
    decoded_objects = decode(image)
    for obj in decoded_objects:
        return obj.data.decode('utf-8')  # Return the decoded QR data as a string
    return None

def generate_otp():
    """Generate a 6-digit OTP."""
    return random.randint(100000, 999999)

@app.route('/verify_certificate', methods=['POST'])
def verify_certificate():
    if 'certificate_image' not in request.files:
        flash('Please upload a certificate image.', 'danger')
        return render_template('user_dashboard.html', otp_sent=False, user_data=request.form)

    file = request.files['certificate_image']
    if file.filename == '':
        flash('No file selected.', 'danger')
        return render_template('user_dashboard.html', otp_sent=False, user_data=request.form)

    # Ensure the temp directory exists
    temp_dir = './temp'
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # Save the uploaded file temporarily
    temp_path = os.path.join(temp_dir, file.filename)
    file.save(temp_path)

    # Decode the QR code
    qr_data = decode_qr(temp_path)
    if not qr_data:
        flash('Unable to decode QR code. Please upload a valid certificate image.', 'danger')
        return render_template('user_dashboard.html', otp_sent=False, user_data=request.form)

    # Extract user input from form
    user_data = {
        'name': request.form.get('name'),
        'email': request.form.get('email'),
        'phone': request.form.get('phone'),
        'course_name': request.form.get('course_name'),
        'course_id': request.form.get('course_id'),
        'institution_name': request.form.get('institution_name'),
        'institution_city': request.form.get('institution_city'),
        'start_date': request.form.get('start_date'),
        'end_date': request.form.get('end_date'),
    }

    # Store user_data in session to persist across redirects
    session['user_data'] = user_data

    # Serialize user_data to JSON with sorted keys
    serialized_data = json.dumps(user_data, sort_keys=True)
    calculated_encrypted_data = sha256(serialized_data.encode('utf-8')).hexdigest()

    # Verify with blockchain table
    conn = get_db_connection()
    cursor = conn.cursor()
    blockchain_query = "SELECT * FROM blockchain WHERE encrypted_data = ?"
    cursor.execute(blockchain_query, (qr_data,))
    blockchain_record = cursor.fetchone()

    if not blockchain_record:
        flash('QR code is not valid or not found in the blockchain.', 'danger')
        conn.close()
        return render_template('user_dashboard.html', otp_sent=False, user_data=user_data)

    # Compare calculated hash with blockchain record
    if qr_data != calculated_encrypted_data:
        flash('QR code is valid but does not match the provided user data.', 'danger')
        conn.close()
        return render_template('user_dashboard.html', otp_sent=False, user_data=user_data)

    conn.close()

    # Generate OTP and send email if verification is successful
    otp = generate_otp()
    session['otp'] = otp
    session['otp_expiry'] = (dt.datetime.now() + dt.timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    session['user_email'] = user_data['email']

    message = Message(
        'Certificate Verification OTP',
        sender='your_email@gmail.com',
        recipients=[user_data['email']]
    )
    message.body = f"Dear {user_data['name']},\n\nYour OTP for certificate verification is {otp}. This OTP is valid for 5 minutes."
    mail.send(message)

    flash('OTP sent to your email. Please verify.', 'info')
    return render_template('user_dashboard.html', otp_sent=True, email=user_data['email'], user_data=user_data)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    entered_otp = request.form.get('otp')
    stored_otp = session.get('otp')
    otp_expiry = dt.datetime.strptime(session.get('otp_expiry'), '%Y-%m-%d %H:%M:%S')

    if not stored_otp or not entered_otp:
        flash('Invalid OTP.', 'danger')
        return redirect(url_for('verify_certificate'))

    if dt.datetime.now() > otp_expiry:
        flash('OTP has expired. Please try again.', 'danger')
        return redirect(url_for('verify_certificate'))

    if str(stored_otp) != entered_otp:
        flash('Incorrect OTP. Please try again.', 'danger')
        return redirect(url_for('verify_certificate'))

    user_email = session.get('user_email')
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row  # Allow dictionary-like row access
    cursor = conn.cursor()

    verified_at = dt.datetime.now().strftime('%Y-%m-%d')  # SQLite-safe string
    update_query = '''
    UPDATE user_details
    SET isVerified = 'verified', verified_at = ?
    WHERE email = ?
    '''
    cursor.execute(update_query, (verified_at, user_email))
    conn.commit()

    select_query = '''
    SELECT name, course_name, course_id, start_date, end_date, institution_name, institution_city, created_at
    FROM user_details
    WHERE email = ?
    '''
    cursor.execute(select_query, (user_email,))
    user_data = cursor.fetchone()

    blockchain_query = 'SELECT encrypted_data FROM blockchain WHERE user_detail_id = (SELECT id FROM user_details WHERE email = ?)'
    cursor.execute(blockchain_query, (user_email,))
    blockchain_record = cursor.fetchone()

    qr_data = blockchain_record['encrypted_data'] if blockchain_record else ''
    conn.close()

    if not user_data:
        flash('Error fetching user details. Please try again later.', 'danger')
        return redirect(url_for('verify_certificate'))

    # Certificate display data
    certificate_data = {
        "name": user_data['name'],
        "course_name": user_data['course_name'],
        "course_id": user_data['course_id'],
        "start_date": user_data['start_date'],
        "end_date": user_data['end_date'],
        "institution_name": user_data['institution_name'],
        "institution_city": user_data['institution_city'],
        "created_at": user_data['created_at'],
        "verified_at": verified_at,
        "date": dt.datetime.now().strftime('%Y-%m-%d'),
        "signature": ''.join(random.choices(string.ascii_uppercase + string.digits, k=15)),
        "qr_data": qr_data,
    }

    session.clear()


    return render_template('certificate_verified.html', certificate_data=certificate_data)

@app.route('/save_verified_certificate', methods=['POST'])
def save_verified_certificate():
    data = request.get_json()  # Parse the incoming JSON data
    email = data.get('email')  # Get the email address
    pdf_data = data.get('pdf_data')  # Get the Base64 PDF data

    if not email or not pdf_data:
        return jsonify({"message": "Invalid data provided"}), 400

    # Decode the Base64 PDF data
    pdf_folder = os.path.join(app.static_folder, 'verified_certificates')
    os.makedirs(pdf_folder, exist_ok=True)  # Create the directory if it doesn't exist
    pdf_path = os.path.join(pdf_folder, f"{email}_certificate.pdf")

    with open(pdf_path, 'wb') as pdf_file:
        pdf_file.write(base64.b64decode(pdf_data.split(",")[1]))  # Remove the "data:image/png;base64," part and decode

    # Send the email with the attachment
    try:
        message = Message(
            'Certificate Verification Success',
            recipients=[email]
        )
        message.body = (
            "Your certificate has been successfully verified.\n"
            "Please find your verified certificate attached."
        )

        # Attach the PDF
        with open(pdf_path, 'rb') as pdf_file:
            message.attach(f"{email}_certificate.pdf", "application/pdf", pdf_file.read())
        
        # Send the email
        mail.send(message)
        return jsonify({"message": "Certificate saved and emailed successfully"}), 200

    except Exception as e:
        print(f"Error sending email: {e}")
        return jsonify({"message": "Failed to send email."}), 500
    
@app.route('/submit', methods=['POST'])
def submit_form():
    try:
        # Get form data
        name = request.form['name']
        email = request.form['email']
        subject = request.form['subject']
        message_body = request.form['message']

        # Placeholder for To and CC email addresses
        to_email = "akshayarao.parvam@gmail.com"  # Replace with recipient email
        cc_emails = ["akshayarao.theranger1551@gmail.com", "parvam.moments@gmail.com"] 

        # Compose the email
        message = Message(
            subject=f"New Message: {subject}",
            sender=app.config['MAIL_USERNAME'],
            recipients=[to_email],
            cc=cc_emails
        )
        message.html = f"""
        <div style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 20px; max-width: 500px; margin: auto;">
            <h2 style="background-color: #007bff; color: white; padding: 10px; border-radius: 5px;">New Message Received</h2>
            <p><strong>Name:</strong> {name}</p>
            <p><strong>Email:</strong> {email}</p>
            <p><strong>Subject:</strong> {subject}</p>
            <p><strong>Message:</strong><span style="padding: 10px; border: 1px solid #eee; background-color: #f9f9f9; border-radius: 5px;">{message_body}</span></p>
            
        </div>
        """

        # Send the email
        mail.send(message)

        flash('Message sent successfully!', 'success')
        return redirect('/contact')
    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'danger')
        return redirect('/contact')

@app.route('/grade10')
def grade10():
    return render_template('grade10.html')

@app.route('/grade12')
def grade12():
    return render_template('grade12.html')

@app.route('/grade10-verification')
def grade10_verification():
    return render_template('grade10_verification.html')    

@app.route('/grade12-verification')
def grade12_verification():
    return render_template('grade12_verification.html')    

@app.route('/login_register')
def login_register():
    return render_template('login_register.html')


if __name__ == '__main__':
    initialize_database()
    app.run(debug=True)