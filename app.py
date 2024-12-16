from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
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

s3_client = boto3.client('s3')

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
            print(stored_password)  # Hapus ini di produksi untuk keamanan
            
            # Validasi password
            if password == stored_password:
                return redirect(url_for('index', name=username))  # Redirect dengan username
            
        # Jika login gagal
        return render_template("login.html", error="Username atau password salah.")
    
    # Jika request GET, tampilkan halaman login
    return render_template("login.html")


@app.route('/index')
def home():
    return render_template('index.html')

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
    # user_logged_in = 'user_id' in session  # Cek apakah user login
    # user_id = session.get('user_id', 'guest')  # Default user_id untuk tamu
    # guest_uploads, guest_chatbot_interactions = get_guest_usage()  # Ambil batasan tamu

    if 'username' in session : 
        username =session['username']
        access_granted = True
    else :
        if 'guest_id' not in session:
            session['guest_id'] = str(uuid.uuid4())
        username =session['guest_id']
        access_granted = check_and_update_access(username, 'chatbot')
    
    if not access_granted : 
        if request.method == 'POST':
            return jsonify({"message": "Anda telah mencapai batas penggunaan. Silakan login untuk melanjutkan.", "redirect":url_for('login')}), 403
    
    if request.method == 'POST':
        # Cek batas interaksi chatbot untuk tamu
        # if not user_logged_in and guest_chatbot_interactions >= 3:
        #     flash('Anda telah mencapai batas penggunaan chatbot. Silakan login untuk melanjutkan.', 'warning')
        #     return redirect(url_for('login'))

        # Ambil pesan pengguna dari form
        user_message = request.form['message'].strip()
        if user_message:
            # Cari respons chatbot
            response = chatbot_data.get(user_message.lower(), "Bot tidak mengerti pertanyaan Anda.")
            
            # Simpan log interaksi ke tabel DynamoDB
            chatbot_table = dynamodb.Table('chatbot')
            chatbot_table.put_item(
                Item={
                    'chatId': str(uuid.uuid4()),  # ID unik untuk setiap log
                    'userId': username,           # ID pengguna (guest jika tamu)
                    'message': user_message,     # Pesan pengguna
                    'response': response,        # Respons chatbot
                    'timestamp': int(time.time())  # Waktu interaksi dalam detik
                }
            )

            # Tambahkan interaksi ke tamu jika belum login
            # if not user_logged_in:
            #     guest_chatbot_interactions += 1
            #     update_guest_usage(guest_uploads, guest_chatbot_interactions)

            # Kembalikan respons chatbot
            return jsonify({'response': response})
    # Render halaman chatbot
    return render_template('chatbot.html', username=username)

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
        # Periksa batas unggahan untuk tamu atau pengguna
        if not user_logged_in:
            if not check_and_update_access('guest', 'upload'):
                flash('Please login or register to upload more images.', 'warning')
                modal_open = True
            else:
                guest_uploads += 1
                update_guest_usage(guest_uploads, _)
        else:
            if not check_and_update_access(session.get('username'), 'upload'):
                flash('Anda Telah Mencapai batas unggahan.', 'warning')
                modal_open = True

        if modal_open:
            return render_template(
                'detection-1.html',
                user_logged_in=user_logged_in,
                modal_open=modal_open,
                guest_uploads=guest_uploads
            )

        # Proses unggahan gambar
        image = request.files['image']
        if image:
            filename = secure_filename(image.filename)
            try:
                # Unggah file ke S3
                s3_client.upload_fileobj(
                    image,
                    S3_BUCKET,
                    filename,
                )
                image_url = f'{S3_LOCATION}{filename}'

                # Simpan detail unggahan ke tabel DynamoDB `upload`
                upload_table = dynamodb.Table('upload')
                upload_data = {
                    'username': session.get('username', 'guest'),
                    'upload_time': int(time.time()),
                    'filename': filename,
                    'url': image_url
                }
                upload_table.put_item(Item=upload_data)

                session['uploaded_image'] = filename

                flash('Gambar berhasil diunggah', 'success')
                return redirect(url_for('detection_result', user_logged_in=user_logged_in,filename=filename))
            except NoCredentialsError:
                flash('Kredensial tidak tersedia.', 'danger')

    return render_template(
        'detection-1.html',
        user_logged_in=user_logged_in,
        modal_open=modal_open,
        guest_uploads=guest_uploads
    )

@app.route('/detection/result/<filename>')
def detection_result():
    #Cek apakah pengguna sudah login
    user_logged_in = 'user_id' in session
    
    # Construct the S3 URL directly using the filename
    uploaded_image = f'{S3_LOCATION}{filename}'

    if not uploaded_image:
        flash('No image uploaded!', 'danger')
        return redirect(url_for('detection'))

    return render_template('detection-2.html', uploaded_image=uploaded_image, user_logged_in=user_logged_in)

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
