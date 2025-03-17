import mysql.connector
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

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = ''
app.config['MAIL_PASSWORD'] = ''
mail = Mail(app)

# MySQL database connection
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='blockchain'
    )

# Create users table if not exists
def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_details (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(15) NOT NULL,
            course_name VARCHAR(255) NOT NULL,
            course_id VARCHAR(100) NOT NULL,
            institution_name VARCHAR(255) NOT NULL,
            institution_city VARCHAR(255) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            isVerified VARCHAR(50) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL,
            verified_at TIMESTAMP NULL,
            deleted_at TIMESTAMP NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blockchain (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_detail_id INT NOT NULL,
            encrypted_data TEXT NOT NULL,
            previous_hash VARCHAR(64),
            current_hash VARCHAR(64),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_detail_id) REFERENCES user_details(id)
        )
    ''')

    conn.commit()
    conn.close()

# Database interaction functions
def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(username, password, role):
    hashed_password = sha256(password.encode()).hexdigest()  # Hash the password
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (username, hashed_password, role))
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
        return redirect(url_for('dashboard_user'))
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
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                       (user_data['name'], user_data['email'], user_data['phone'], user_data['course_name'], user_data['course_id'],
                        user_data['institution_name'], user_data['institution_city'], user_data['start_date'], user_data['end_date']))
        user_detail_id = cursor.lastrowid
        created_at = dt.datetime.now().strftime('%d/%m/%Y')

        # Serialize user_data to JSON with sorted keys
        serialized_data = json.dumps(user_data, sort_keys=True)
        encrypted_data = sha256(serialized_data.encode('utf-8')).hexdigest()

        # Blockchain-related hashing
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT current_hash FROM blockchain ORDER BY id DESC LIMIT 1')
        last_hash = cursor.fetchone()
        previous_hash = last_hash['current_hash'] if last_hash else '0'

        current_hash = sha256((previous_hash + encrypted_data).encode()).hexdigest()
        cursor.execute('INSERT INTO blockchain (user_detail_id, encrypted_data, previous_hash, current_hash) VALUES (%s, %s, %s, %s)',
                       (user_detail_id, encrypted_data, previous_hash, current_hash))

        conn.commit()

        cursor.execute('SELECT encrypted_data FROM blockchain WHERE user_detail_id = %s', (user_detail_id,))
        blockchain_record = cursor.fetchone()
        qr_data = blockchain_record['encrypted_data'] if blockchain_record and blockchain_record.get('encrypted_data') else ''

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

@app.route('/about')
def about():
    return render_template('about_us.html')

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
    cursor = conn.cursor(dictionary=True)
    blockchain_query = "SELECT * FROM blockchain WHERE encrypted_data = %s"
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

    # OTP verified successfully, now update the database
    user_email = session.get('user_email')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)  # Use dictionary=True

    # Update the isVerified column to 'verified' and set the verified_at timestamp
    verified_at = dt.datetime.now()
    update_query = '''
    UPDATE user_details
    SET isVerified = 'verified', verified_at = %s
    WHERE email = %s
    '''
    cursor.execute(update_query, (verified_at, user_email))
    conn.commit()

    # Fetch the user's details from the database
    select_query = '''
    SELECT name, course_name, course_id, start_date, end_date, institution_name, institution_city, created_at
    FROM user_details
    WHERE email = %s
    '''
    cursor.execute(select_query, (user_email,))
    user_data = cursor.fetchone()

    # Fetch the blockchain QR code data
    blockchain_query = 'SELECT encrypted_data FROM blockchain WHERE user_detail_id = (SELECT id FROM user_details WHERE email = %s)'
    cursor.execute(blockchain_query, (user_email,))
    blockchain_record = cursor.fetchone()

    print("Blockchain record:", blockchain_record)
    qr_data = blockchain_record['encrypted_data'] if blockchain_record and blockchain_record.get('encrypted_data') else ''
    
    conn.close()

    if not user_data:
        flash('Error fetching user details. Please try again later.', 'danger')
        return redirect(url_for('verify_certificate'))

    # Prepare data for certificate_verified.html
    certificate_data = {
        "name": user_data['name'],  # Use dictionary keys
        "course_name": user_data['course_name'],
        "course_id": user_data['course_id'],
        "start_date": user_data['start_date'].strftime('%Y-%m-%d'),
        "end_date": user_data['end_date'].strftime('%Y-%m-%d'),
        "institution_name": user_data['institution_name'],
        "institution_city": user_data['institution_city'],
        "created_at": user_data['created_at'].strftime('%Y-%m-%d'),
        "verified_at": verified_at.strftime('%Y-%m-%d'),
        "date": dt.datetime.now().strftime('%Y-%m-%d'),
        "signature": ''.join(random.choices(string.ascii_uppercase + string.digits, k=15)),  # Random signature
        "qr_data": qr_data,  # QR code data
    }

    # Clear the session after successful OTP verification
    session.clear()  # This will clear all session data

    # Explicitly pass the certificate data to the template
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

if __name__ == '__main__':
    initialize_database()
    app.run(debug=True)