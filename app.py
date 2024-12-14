from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import boto3
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whitebrim'
app.config.from_object('config.Config')

# Configure DynamoDB (ensure AWS credentials are configured properly)
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')  # Adjust region as needed

# Set up DynamoDB tables
users_table = dynamodb.Table('datausers')  # Replace with your actual table name
uploads_table = dynamodb.Table('uploads')  # Replace with your actual table name
guest_usage_table = dynamodb.Table('guest_usage')  # Replace with your actual table name

# Function to get guest usage from DynamoDB
def get_guest_usage():
    response = guest_usage_table.get_item(Key={'id': 'guest_usage'})
    if 'Item' in response:
        return response['Item']['uploads'], response['Item']['last_updated']
    else:
        return 0, None

# Function to update guest usage in DynamoDB
def update_guest_usage(uploads, interactions):
    guest_usage_table.update_item(
        Key={'id': 'guest_usage'},
        UpdateExpression="SET uploads = :uploads, chatbot_interactions = :interactions, last_updated = :last_updated",
        ExpressionAttributeValues={
            ':uploads': uploads,
            ':interactions': interactions,
            ':last_updated': boto3.dynamodb.types.Timestamp.now()  # Optional: store the timestamp
        },
        ReturnValues="UPDATED_NEW",
        Upsert=True  # If the item does not exist, it will create a new one
    )

# Helper function to get guest uploads count from session
def get_guest_uploads_count():
    return session.get('guest_uploads', 0)

# Helper function to get guest chatbot interactions count from session
def get_guest_chatbot_interactions():
    return session.get('guest_chatbot_interactions', 0)

# Load chatbot data from a JSON file
def load_chatbot_data():
    with open('chatbot.json', 'r', encoding='utf-8') as f:
        return json.load(f)

chatbot_data = load_chatbot_data()

# Function to get user data from DynamoDB based on user ID
def get_user_data(username):
    response = users_table.get_item(Key={'username': username})
    if 'Item' in response:
        return response['Item']
    else:
        return None  # Return None if no user data is found

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user_data = get_user_data(username)
        if user_data and check_password_hash(user_data['password'], password):
            session['user_id'] = user_data['userid']
            session['username'] = user_data['username']
            session['email'] = user_data['email']
            session.pop('guest_uploads', None)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))

        flash('Invalid credentials!', 'danger')

    return render_template('login.html')

@app.route('/')
def index():
    user_logged_in = 'user_id' in session
    username = session.get('username', 'Pengunjung')
    email = session.get('email', 'Pengunjung')
    return render_template('index.html', user_logged_in=user_logged_in, username=username, email=email)

@app.route('/contact')
def contact():
    # Cek apakah pengguna sudah login
    user_logged_in = 'user_id' in session
    return render_template('contact.html', user_logged_in=user_logged_in)

@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    user_logged_in = 'user_id' in session
    guest_uploads, guest_chatbot_interactions = get_guest_usage()
    
    if request.method == 'POST':
        if not user_logged_in and guest_chatbot_interactions >= 3:
            return jsonify({'error': 'Anda telah mencapai batas penggunaan Chatbot. Silakan masuk atau daftar untuk menggunakannya lebih lanjut.'}), 403

        user_message = request.form['message'].strip()
        if user_message:
            response = chatbot_data.get(user_message.lower(), "Bot tidak mengerti pertanyaan Anda.")
            
            if not user_logged_in:
                guest_chatbot_interactions += 1
                update_guest_usage(guest_uploads, guest_chatbot_interactions)
            
            return jsonify({'response': response})

    return render_template('chatbot.html', user_logged_in=user_logged_in)

@app.route('/get_response/<message>')
def get_response(message):
    response = chatbot_data.get(message.lower(), "Bot tidak mengerti pertanyaan Anda.")
    return jsonify({'response': response})

@app.route('/about')
def about():
    # Cek apakah pengguna sudah login
    user_logged_in = 'user_id' in session
    return render_template('about.html', user_logged_in=user_logged_in)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']

        if get_user_data(username):
            flash('Username is already taken!', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        users_table.put_item(
            Item={
                'userid': username,  # Assuming 'username' as 'userid'
                'email': email,
                'username': username,
                'password': hashed_password
            }
        )

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/detection', methods=['GET', 'POST'])
def detection():
    user_logged_in = 'user_id' in session
    guest_uploads, _ = get_guest_usage()  # Mendapatkan nilai guest_uploads dari DynamoDB
    modal_open = False

    if request.method == 'POST':
        if not user_logged_in and guest_uploads >= 3:
            flash('Please login or register to upload more images.', 'warning')
            modal_open = True
        else:
            image = request.files['image']
            if image:
                filename = secure_filename(image.filename)
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(image_path)

                upload_data = {
                    'user_id': session.get('user_id'),
                    'filename': filename
                }
                uploads_table.put_item(Item=upload_data)

                session['uploaded_image'] = filename

                if not user_logged_in:
                    guest_uploads += 1
                    update_guest_usage(guest_uploads, _)  # Update database

                flash('Image uploaded successfully!', 'success')
                return redirect(url_for('detection_result', user_logged_in=user_logged_in))

    return render_template(
        'detection-1.html', 
        user_logged_in=user_logged_in, 
        modal_open=modal_open,
        guest_uploads=guest_uploads  # Pass guest_uploads to the template
    )

@app.route('/detection/result')
def detection_result():
    file_name = request.args.get('file_name', 'No file uploaded')
    message = request.args.get('message', 'No message received')
    return render_template('detection-2.html', file_name=file_name, message=message)

@app.route('/delete-image/<filename>', methods=['DELETE'])
def delete_image(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'success': True, 'redirect_url': url_for('detection')}), 200
        else:
            return jsonify({'success': False, 'message': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)
