from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_cors import CORS
import sqlite3
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import os
import time
from config import Config
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)
app.config.from_object('config.Config')

# Configure Gemini API
print(f"API Key length: {len(Config.GEMINI_API_KEY) if Config.GEMINI_API_KEY else 0}")

# Configure Gemini API
if not Config.GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found")
else:
    genai.configure(api_key=Config.GEMINI_API_KEY)
    try:
        model = genai.GenerativeModel('gemini-pro')
        print("Successfully initialized Gemini model")
    except Exception as e:
        print(f"Error initializing Gemini model: {str(e)}")

# Ensure upload folder exists
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

def get_db():
    db = sqlite3.connect(Config.SQLITE_DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        # Create tables
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                upload_time INTEGER NOT NULL,
                filename TEXT NOT NULL,
                url TEXT NOT NULL
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS guest_usage (
                id INTEGER PRIMARY KEY,
                uploads INTEGER DEFAULT 0,
                chatbot_interactions INTEGER DEFAULT 0,
                last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS user_access (
                username TEXT PRIMARY KEY,
                chatbot_access INTEGER DEFAULT 0,
                detection_access INTEGER DEFAULT 0
            )
        ''')
        db.commit()

# Initialize database
init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def get_ai_response(prompt):
    try:
        if not Config.GEMINI_API_KEY:
            print("Error: GEMINI_API_KEY not configured")
            return {'status': 'error', 'message': 'API key not configured'}

        # Add context about the chatbot's purpose
        context = """You are MelanomaScan's AI assistant, specialized in providing information about melanoma skin cancer. 
        Your responses should be informative, accurate, and focused on melanoma-related topics.
        Always maintain a professional yet friendly tone, and if you're unsure about something, 
        recommend consulting with a healthcare professional.
        Provide your responses in Bahasa Indonesia."""
        
        # Combine context and user prompt
        full_prompt = f"{context}\n\nUser question: {prompt}"
        
        print(f"Sending request to Gemini API with prompt length: {len(full_prompt)}")
        
        # Get response from Gemini
        response = model.generate_content(full_prompt)
        
        print(f"Received response from Gemini API")
        
        if response and response.text:
            return {'status': 'success', 'message': response.text}
        else:
            print("No text in response from Gemini")
            return {'status': 'error', 'message': 'No response generated'}
    except Exception as e:
        print(f"Error getting AI response: {str(e)}")
        print(f"Error type: {type(e)}")
        print(f"Full error details: {repr(e)}")
        return {'status': 'error', 'message': 'Maaf, saya sedang mengalami kesulitan teknis. Silakan coba lagi nanti.'}

@app.route('/')
def index():
    user_logged_in = 'username' in session
    username = session.get('username') if user_logged_in else None
    return render_template("index.html", user_logged_in=user_logged_in, username=username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('index'))
        
    # Check for registration success
    if session.pop('registration_success', False):
        flash('Registrasi berhasil! Silakan login ke akun Anda.', 'success')
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            session['email'] = user['email']
            flash('Login berhasil!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Username atau password salah!', 'danger')
            return redirect(url_for('login'))

    return render_template("login.html", user_logged_in=False)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
         
        db = get_db()
        
        # Check if email already exists
        existing_email = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if existing_email:
            flash('Email sudah terdaftar. Silakan gunakan email lain.', 'danger')
            return render_template('register.html', user_logged_in=False)
            
        # Check if username already exists
        existing_username = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if existing_username:
            flash('Username sudah digunakan. Silakan pilih username lain.', 'danger')
            return render_template('register.html', user_logged_in=False)
        
        try:
            db.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', 
                      (username, email, generate_password_hash(password)))
            db.commit()
            
            # Store registration success in session instead of flash
            session['registration_success'] = True
            return redirect(url_for('login'))
        except Exception as e:
            db.rollback()
            flash('Terjadi kesalahan saat registrasi. Silakan coba lagi.', 'danger')
            print(f"Registration error: {str(e)}")
            return render_template('register.html', user_logged_in=False)
            
    return render_template('register.html', user_logged_in=False)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/index')
def home():
    user_logged_in = 'username' in session
    username = session.get('username') if user_logged_in else None
    return render_template("index.html", user_logged_in=user_logged_in, username=username)

def get_guest_usage():
    db = get_db()
    # Create guest_usage table if it doesn't exist
    db.execute('''
        CREATE TABLE IF NOT EXISTS guest_usage (
            id INTEGER PRIMARY KEY,
            uploads INTEGER DEFAULT 0,
            chatbot_interactions INTEGER DEFAULT 0,
            last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Get or create guest usage record
    usage = db.execute('SELECT * FROM guest_usage WHERE id = 1').fetchone()
    if not usage:
        db.execute('INSERT INTO guest_usage (id, uploads, chatbot_interactions) VALUES (1, 0, 0)')
        db.commit()
        return 0, 0
    
    # Reset counters if it's been more than 24 hours
    if usage['last_reset']:
        last_reset = datetime.fromisoformat(usage['last_reset'].replace('Z', '+00:00'))
        if (datetime.now() - last_reset).days >= 1:
            db.execute('''
                UPDATE guest_usage 
                SET uploads = 0, 
                    chatbot_interactions = 0, 
                    last_reset = CURRENT_TIMESTAMP 
                WHERE id = 1
            ''')
            db.commit()
            return 0, 0
    
    return usage['uploads'], usage['chatbot_interactions']

def update_guest_usage(uploads, interactions):
    db = get_db()
    db.execute('''
        UPDATE guest_usage 
        SET uploads = ?, 
            chatbot_interactions = ?,
            last_reset = CASE 
                WHEN (julianday('now') - julianday(last_reset)) >= 1 
                THEN CURRENT_TIMESTAMP 
                ELSE last_reset 
            END
        WHERE id = 1
    ''', (uploads, interactions))
    db.commit()

def get_guest_uploads_count():
    return get_guest_usage()[0]
    
def get_guest_chatbot_interactions():
    return get_guest_usage()[1]

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    user_logged_in = 'username' in session
    username = session.get('username') if user_logged_in else None
    
    if request.method == 'POST':
        name = request.form['name']       # Nama pengirim
        email = request.form['email']     # Email pengirim
        phone = request.form['phone']     # Telepon pengirim
        feedback = request.form['feedback']  # Kritik dan Saran

        # Create contact table if it doesn't exist
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS contactuser (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                feedback TEXT NOT NULL,
                contact_time INTEGER NOT NULL
            )
        ''')
        
        # Save contact data
        db.execute(
            'INSERT INTO contactuser (name, email, phone, feedback, contact_time) VALUES (?, ?, ?, ?, ?)',
            (name, email, phone, feedback, int(time.time()))
        )
        db.commit()

        # Flash success message
        flash('Pesan Anda berhasil dikirim. Kami akan segera merespon!', 'success')
        return redirect(url_for('contact'))

    return render_template('contact.html', username=username, user_logged_in=user_logged_in)

@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    user_logged_in = 'username' in session
    guest_uploads, guest_chatbot_interactions = get_guest_usage()
   
    if request.method == 'POST':
        if not user_logged_in and guest_chatbot_interactions >= 3:
            return jsonify({
                'status': 'error',
                'message': 'Anda telah mencapai batas penggunaan Chatbot. Silakan login atau daftar untuk melanjutkan.'
            }), 403

        user_message = request.form['message'].strip()
        if user_message:
            # Get response from Gemini API
            result = get_ai_response(user_message)
            
            if result['status'] == 'success':
                if not user_logged_in:
                    guest_chatbot_interactions += 1
                    update_guest_usage(guest_uploads, guest_chatbot_interactions)
                return jsonify(result)
            else:
                return jsonify(result), 500

    return render_template('chatbot.html', user_logged_in=user_logged_in)

@app.route('/about')
def about():
    #Cek apakah pengguna sudah login
    user_logged_in = 'username' in session
    return render_template('about.html', user_logged_in=user_logged_in)


@app.route('/detection', methods=['GET', 'POST'])
def detection():
    user_logged_in = 'username' in session
    guest_uploads, _ = get_guest_usage()
    modal_open = False

    if request.method == 'POST':
        if not user_logged_in and guest_uploads >= 3:
            flash('You have reached the upload limit. Please log in or register to continue.', 'danger')
            return redirect(url_for('detection'))

        if 'image' not in request.files:
            flash('No image selected', 'danger')
            return redirect(request.url)

        image = request.files['image']
        if image.filename == '':
            flash('No image selected', 'danger')
            return redirect(request.url)

        if image and allowed_file(image.filename):
            original_filename = secure_filename(image.filename)
            try:
                # Ensure uploads directory exists
                os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
                
                # Save the file
                image_path = os.path.join(Config.UPLOAD_FOLDER, original_filename)
                image.save(image_path)

                # Update session with the uploaded image filename
                session['uploaded_image'] = original_filename

                # Save upload details to SQLite
                db = get_db()
                db.execute('INSERT INTO uploads (username, upload_time, filename, url) VALUES (?, ?, ?, ?)', 
                          (session.get('username', 'guest'), int(time.time()), original_filename, image_path))
                db.commit()

                if not user_logged_in:
                    guest_uploads += 1
                    update_guest_usage(guest_uploads, get_guest_chatbot_interactions())

                flash('Image uploaded successfully', 'success')
                return redirect(url_for('detection_result', filename=original_filename))
            except Exception as e:
                flash(f"Error uploading image: {str(e)}", 'danger')
                return redirect(request.url)

    return render_template('detection-1.html', 
                         user_logged_in=user_logged_in,
                         modal_open=modal_open,
                         guest_uploads=guest_uploads)

@app.route('/detection/result/<filename>')
def detection_result(filename):
    user_logged_in = 'username' in session
    
    # Get the relative URL for the uploaded image
    image_url = url_for('static', filename=f'uploads/{filename}')
    
    if not os.path.exists(os.path.join(Config.UPLOAD_FOLDER, filename)):
        flash('No image uploaded!', 'danger')
        return redirect(url_for('detection'))

    return render_template('detection-2.html', 
                         uploaded_image=image_url,
                         filename=filename,
                         user_logged_in=user_logged_in)

@app.route('/detection/result/analyze/<filename>', methods=['GET'])
def detection_result_get(filename):
    user_logged_in = 'username' in session
    
    # Get the relative URL for the uploaded image
    image_url = url_for('static', filename=f'uploads/{filename}')
    
    if not os.path.exists(os.path.join(Config.UPLOAD_FOLDER, filename)):
        flash('No image uploaded!', 'danger')
        return redirect(url_for('detection'))

    # Fetch the detection result from the local uploads folder
    detection_result = None
    try:
        # Construct the detection result filename based on the uploaded image filename
        result_filename = f"{filename.split('.')[0]}_result.txt"
        
        # Read the detection result file content
        with open(os.path.join(Config.UPLOAD_FOLDER, result_filename), 'r') as f:
            detection_result_raw = f.read()  # Read the result text

        # Parse the classification result from the raw text
        detection_result = "Unknown"
        for line in detection_result_raw.splitlines():
            if "Classification:" in line:  # Look for the classification line
                detection_result = line.split(":", 1)[1].strip()  # Extract the value after the colon
                break  # Stop parsing after finding the classification result

    except Exception as e:
        flash(f"Error fetching detection result: {str(e)}", 'danger')
        detection_result = "Error retrieving the result."

    # Pass the uploaded image URL and detection result to the template
    return render_template('detection-3.html', 
                         uploaded_image=image_url,
                         filename=filename,
                         detection_result=detection_result,
                         user_logged_in=user_logged_in)

@app.route('/proxy/analyze', methods=['GET'])
def proxy_analyze():
    filename = request.args.get('filename')
    if not filename:
        return jsonify({'error': 'No filename provided'}), 400
        
    try:
        # Get the full path to the uploaded image
        image_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        if not os.path.exists(image_path):
            return jsonify({'error': 'Image not found'}), 404
            
        # TODO: Implement local image analysis here
        # For now, create a dummy result
        result_filename = f"{filename.split('.')[0]}_result.txt"
        result_path = os.path.join(Config.UPLOAD_FOLDER, result_filename)
        
        with open(result_path, 'w') as f:
            f.write("Classification: Melanoma\nConfidence: 0.95")
            
        return jsonify({
            'success': True,
            'message': 'Analysis complete',
            'result': {
                'classification': 'Melanoma',
                'confidence': 0.95
            }
        }), 200
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete-image/<filename>', methods=['DELETE'])
def delete_image(filename):
    try:
        # Delete the file from the local uploads folder
        os.remove(os.path.join(Config.UPLOAD_FOLDER, filename))
        return jsonify({'success': True, 'message': 'File deleted successfully', 'redirect_url': url_for('detection')}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

def check_and_update_access(user_id, feature):
    db = get_db()
    
    # Create user_access table if it doesn't exist
    db.execute('''
        CREATE TABLE IF NOT EXISTS user_access (
            username TEXT PRIMARY KEY,
            chatbot_access INTEGER DEFAULT 0,
            detection_access INTEGER DEFAULT 0
        )
    ''')
    
    # Get or create user access record
    access = db.execute('SELECT * FROM user_access WHERE username = ?', (user_id,)).fetchone()
    if not access:
        db.execute('INSERT INTO user_access (username, chatbot_access, detection_access) VALUES (?, 0, 0)', (user_id,))
        db.commit()
        access = db.execute('SELECT * FROM user_access WHERE username = ?', (user_id,)).fetchone()
    
    # Update access count based on feature
    if feature == 'chatbot':
        if access['chatbot_access'] >= 3:
            return False
        db.execute('UPDATE user_access SET chatbot_access = ? WHERE username = ?', 
                  (access['chatbot_access'] + 1, user_id))
    elif feature == 'detection':
        if access['detection_access'] >= 3:
            return False
        db.execute('UPDATE user_access SET detection_access = ? WHERE username = ?', 
                  (access['detection_access'] + 1, user_id))
    
    db.commit()
    return True

if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)
