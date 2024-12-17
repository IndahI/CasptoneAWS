from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from boto3.dynamodb.conditions import Key, Attr
import os
import json
import boto3
import uuid
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whitebrim'
app.config.from_object('config.Config')

CORS(app)  # Default: mengizinkan semua origin

#konfigurasi MongoDB
# mongo_client = MongoClient(app.config['MONGO_URI'])
# db = mongo_client['melanoma_scan']
# users_collection = db['users']
# uploads_collection = db['uploads']
# guest_usage_collection = db['guest_usage']

#setting Bedrock
os.environ["AWS_PROFILE"] = "Indah"

bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1"
)

#setting S3
S3_BUCKET = 'upload-images-bucket-detection'
S3_LOCATION = f'http://{S3_BUCKET}.s3.amazonaws.com/'
S3_OUTPUT_BUCKET = 'output-bucket-sagemaker1'
S3_LOCATION_OUTPUT = f'http://{S3_OUTPUT_BUCKET}.s3.amazonaws.com/'

# Correct the region_name parameter
s3_client = boto3.client('s3', region_name='us-east-1')

# Function to get response from Bedrock
def get_bedrock_response(prompt):
    try:
        response = bedrock_client.invoke_model(
            modelId='anthropic.claude-v2',  # Gunakan model yang benar
            contentType='application/json',  # Pengaturan content-type
            accept='application/json',
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 1000,
                "temperature": 0.9
            })
        )
        response_body = response['body'].read().decode('utf-8')
        return json.loads(response_body).get('completion', "Tidak ada jawaban yang diterima.")
    except Exception as e:
        print("Error details:", str(e))  # Log error
        return "Terjadi kesalahan saat mengakses model AI."
    

dynamodb = boto3.resource('dynamodb',region_name='us-east-1')
user_access_table = dynamodb.Table('user_access')
uploads_colletion = dynamodb.Table('uploads')

@app.route('/')
def index():
    user_logged_in = 'email' in session  # Cek apakah pengguna sudah login
    username = None  # Default username jika tidak login

    if user_logged_in:
        email = session.get('email')
        print(f"Email dari sesi: {email}")  # Debugging untuk melihat nilai email
        table = dynamodb.Table('user')
        response = table.query(
            KeyConditionExpression=Key('email').eq(email)
        )
        items = response.get('Items', [])
        print(f"Items dari DynamoDB: {items}")  # Debugging untuk melihat hasil query

        if items:
            username = items[0].get('username')  # Ambil username dari hasil query

    return render_template('index.html', user_logged_in=user_logged_in, username=username)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Ambil input dari form
        username = request.form['username']  # Input username dari form
        password = request.form['password']  # Input password dari form

        # Akses tabel DynamoDB
        table = dynamodb.Table('user')

        # Cari email berdasarkan username menggunakan scan
        response = table.scan(
            FilterExpression=Key('username').eq(username)  # Filter berdasarkan username
        )
        items = response.get('Items', [])

        if items:
            # Jika username ditemukan, ambil email dan password yang tersimpan
            stored_email = items[0]['email']
            stored_password = items[0]['password']
            stored_username = items[0]['username']
            print(stored_password)  # Hapus ini di produksi untuk keamanan

            # Validasi password
            if password == stored_password:
                session['username'] = username
                session['email'] = stored_email
                return redirect(url_for('index'))  # Redirect dengan username

        # Jika login gagal
        return render_template("login.html", error="Username atau password salah.")

    # Jika request GET, tampilkan halaman login
    return render_template("login.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
         
        table = dynamodb.Table('user')
        
        table.put_item(
                Item={
                    'email': email,
                    'username': username,
                    'password': password
                }
            )
        msg = "Registration Complete. Please Login to your account !"
    
        return redirect (url_for('login'))
    return render_template('register.html')

@app.route('/index')
def home():
    username=session.get("username")
    return render_template("index.html", username=username)

def get_guest_usage():
    table = dynamodb.Table('guest_usage')  # Tabel DynamoDB untuk menyimpan data guest usage
    try:
        response = table.get_item(Key={'_id': 'guest_usage'})  # Ambil item dengan _id = 'guest_usage'
        item = response.get('Item', {})
        uploads = item.get('uploads', 0)  # Jumlah upload
        interactions = item.get('chatbot_interactions', 0)  # Jumlah interaksi chatbot
        return uploads, interactions
    except Exception as e:
        print(f"Error getting guest usage: {e}")
        return 0, 0  # Default jika data tidak ditemukan atau ada error

def update_guest_usage(uploads, interactions):
    table = dynamodb.Table('guest_usage')  # Tabel DynamoDB untuk menyimpan data guest usage
    try:
        table.put_item(
            Item={
                '_id': 'guest_usage',  # ID tetap untuk data tamu
                'uploads': uploads,  # Jumlah upload
                'chatbot_interactions': interactions  # Jumlah interaksi chatbot
            }
        )
    except Exception as e:
        print(f"Error updating guest usage: {e}")


#Helper 
def get_guest_uploads_count():
    return session.get('guest_uploads', 0)

def get_guest_chatbot_interactions():
    return session.get('guest_chatbot_interactions', 0)

#deklarasi fungsi manggil data dari file chatbot.json
def load_chatbot_data():
    with open('chatbot.json', 'r', encoding='utf-8') as f:
        return json.load(f)

#ngambil data dari json
chatbot_data = load_chatbot_data()


def check_and_update_access(user_id, feature):
    response = user_access_table.get_item(Key={'username': user_id})
    if 'Item' in response:
        access_info = response['Item']
    else:
        access_info = {'username': user_id, 'chatbot_access' : 0, 'detection_access' : 0}
    
    if feature=='chatbot':
        if access_info['chatbot_access'] >= 3:
            return False
        access_info['chatbot_access'] +=1
    elif feature=='detection' :
        if access_info['detection_access'] >= 3:
            return False
        access_info['detection_access'] +=1

    user_access_table.put_item(Item=access_info)
    return True

def get_answer(question, data):
    for item in data["data"]:
        if item['question'].lower() == question.lower():
            return item["answer"]
    return "I'm Sorry, I dont't understand that question."


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    user_logged_in = 'user_id' in session  # Cek apakah pengguna sudah login
    username = None  # Default jika tidak login

    if user_logged_in:
        # Ambil username dari sesi (opsional, tergantung struktur sesi)
        user_id = session.get('email')
        table = dynamodb.Table('user')
        response = table.query(
            KeyConditionExpression=Key('email').eq(email)
        )
        items = response.get('Items', [])
        if items:
            username = items[0].get('username', 'Pengguna')

    if request.method == 'POST':
        # Ambil input dari form
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        feedback = request.form['feedback']  # Kritik dan Saran

        # Buat contactId unik
        contact_id = str(uuid.uuid4())  # UUID sebagai contactId

        # Simpan data ke tabel DynamoDB contact
        contact_table = dynamodb.Table('contactuser')
        contact_table.put_item(
            Item={ 
                'name': name,             # Nama pengirim
                'email': email,           # Email pengirim
                'phone': phone,           # Telepon pengirim
                'feedback': feedback,     # Kritik dan Saran
            }
        )

        # Flash pesan keberhasilan
        flash('Pesan Anda berhasil dikirim. Kami akan segera merespon!', 'success')
        return redirect(url_for('contact'))

    return render_template('contact.html', user_logged_in=user_logged_in, username=username)

@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    user_logged_in = 'user_id' in session
    guest_uploads, guest_chatbot_interactions = get_guest_usage()
   
    if request.method == 'POST':
        if not user_logged_in and guest_chatbot_interactions >= 3:
            return jsonify({'error': 'You have reached the usage limit for the Chatbot. Please log in or register to continue.'}), 403

        user_message = request.form['message'].strip()
        if user_message:
            # Get response from Bedrock
            response = get_bedrock_response(user_message)

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
    #Cek apakah pengguna sudah login
    user_logged_in = 'user_id' in session
    return render_template('about.html', user_logged_in=user_logged_in)


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))


@app.route('/detection', methods=['GET', 'POST'])
def detection():
    user_logged_in = 'username' in session
    guest_uploads, _ = get_guest_usage()
    modal_open = False

    if request.method == 'POST':
        # Check upload limits
        if not user_logged_in:
            if not check_and_update_access('guest', 'upload'):
                flash('Please login or register to upload more images.', 'warning')
                modal_open = True
            else:
                guest_uploads += 1
                update_guest_usage(guest_uploads, _)
        else:
            if not check_and_update_access(session.get('username'), 'upload'):
                flash('You have reached your upload limit.', 'warning')
                modal_open = True

        if modal_open:
            return render_template(
                'detection-1.html',
                user_logged_in=user_logged_in,
                modal_open=modal_open,
                guest_uploads=guest_uploads
            )

        # Process the uploaded image
        image = request.files['image']
        if image:
            original_filename = secure_filename(image.filename)
            try:
                # Upload the file to S3
                s3_client.upload_fileobj(
                    image,
                    S3_BUCKET,
                    original_filename,
                )
                # Update session with S3 URL
                s3_filename = f"s3://{S3_BUCKET}/{original_filename}"
                session['uploaded_image'] = s3_filename

                # Save upload details to DynamoDB
                upload_table = dynamodb.Table('upload')
                upload_data = {
                    'username': session.get('username', 'guest'),
                    'upload_time': int(time.time()),
                    'filename': original_filename,
                    'url': s3_filename
                }
                upload_table.put_item(Item=upload_data)

                flash('Image uploaded successfully', 'success')
                return redirect(url_for('detection_result', filename=original_filename, user_logged_in=user_logged_in))
            except NoCredentialsError:
                flash('Credentials not available.', 'danger')

    return render_template(
        'detection-1.html',
        user_logged_in=user_logged_in,
        modal_open=modal_open,
        guest_uploads=guest_uploads
    )

@app.route('/detection/result/<filename>')
def detection_result(filename):
    user_logged_in = 'username' in session
    
    # Construct the S3 URL for the uploaded image (non-presigned)
    uploaded_image = f"s3://{S3_BUCKET}/{filename}"

    if not uploaded_image:
        flash('No image uploaded!', 'danger')
        return redirect(url_for('detection'))

    # Generate the presigned URL for the image from S3
    try:
        s3_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': filename},
            ExpiresIn=3600  # URL expiration time (1 hour)
        )
    except Exception as e:
        flash(f"Error fetching image: {str(e)}", 'danger')
        return redirect(url_for('detection'))

    # Pass both the uploaded image URL (presigned) and filename to the template
    return render_template('detection-2.html', uploaded_image=s3_url, filename=filename, user_logged_in=user_logged_in)

@app.route('/detection/result/analyze/<filename>', methods=['GET'])
def detection_result_get(filename):
    # Generate the presigned URL for the image from the original S3 bucket
    try:
        s3_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': filename},
            ExpiresIn=3600  # URL expiration time (1 hour)
        )
    except Exception as e:
        flash(f"Error fetching image: {str(e)}", 'danger')
        return redirect(url_for('detection'))

    # Fetch the detection result from the 'output-bucket-sagemaker1' bucket
    detection_result = None
    try:
        # Construct the detection result key based on the filename pattern: {filename}_result.txt
        result_key = f"{filename.split('.')[0]}_result.txt" 
        
        # Generate a presigned URL for the detection result
        detection_result_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_OUTPUT_BUCKET, 'Key': result_key},
            ExpiresIn=3600  # URL expiration time (1 hour)
        )

        # Fetch the detection result file content
        response = s3_client.get_object(Bucket=S3_OUTPUT_BUCKET, Key=result_key)
        detection_result_raw = response['Body'].read().decode('utf-8')  # Read and decode the result text

        # Parse the classification result from the raw text
        detection_result = "Unknown"
        for line in detection_result_raw.splitlines():
            if "Classification:" in line:  # Look for the classification line
                detection_result = line.split(":", 1)[1].strip()  # Extract the value after the colon
                break  # Stop parsing after finding the classification result

    except Exception as e:
        flash(f"Error fetching detection result: {str(e)}", 'danger')
        detection_result = "Error retrieving the result."

    # Pass the presigned image URL, detection result, and filename to the next page
    return render_template('detection-3.html', uploaded_image=s3_url, filename=filename, detection_result=detection_result)

@app.route('/delete-image/<filename>', methods=['DELETE'])
def delete_image(filename):
    try:
        # Delete the file from S3
        s3_client.delete_object(Bucket=S3_BUCKET, Key=filename)
        return jsonify({'success': True, 'message': 'File deleted successfully', 'redirect_url': url_for('detection')}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)
