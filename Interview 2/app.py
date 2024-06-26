from flask import Flask, request, jsonify, session, redirect, url_for, send_from_directory, render_template
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import os
import subprocess
import tempfile

app = Flask(__name__)
app.secret_key = 'your_secret_key'
CORS(app, supports_credentials=True)

# Veritabanı bağlantısı
def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="bites_interview",
        user="kgans",  
        password="123456"  
    )
    return conn

# Ana sayfa route'u
@app.route('/')
def home():
    return render_template('index.html')

# Kullanıcı kaydı
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    password = data['password']
    is_admin = data.get('is_admin', False)

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)", (username, hashed_password, is_admin))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": "Kayıt başarılı"})
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"status": "error", "message": "Kullanıcı adı zaten mevcut"}), 400
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        print(f"Error: {e}")  # Hata mesajını terminale yazdırma
        return jsonify({"status": "error", "message": f"Kayıt işlemi sırasında bir hata oluştu: {str(e)}"}), 400

# Kullanıcı girişi
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data['username']
    password = data['password']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password, is_admin FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password_hash(user[0], password):
        session['user_id'] = username
        session['is_admin'] = user[1]
        session['test_completed'] = False  # Oturumu sıfırlamak
        if user[1]:  # Admin kullanıcı ise
            return jsonify({"status": "success", "message": "Giriş başarılı", "redirect_url": "/admin"})
        else:
            return jsonify({"status": "success", "message": "Giriş başarılı", "redirect_url": "/selection"})
    else:
        return jsonify({"status": "error", "message": "Kullanıcı adı veya şifre yanlış"}), 401

# Kullanıcı adını getiren route
@app.route('/get_username', methods=['GET'])
def get_username():
    if 'user_id' in session:
        return jsonify({"status": "success", "username": session['user_id']})
    else:
        return jsonify({"status": "error", "message": "Kullanıcı oturumu bulunamadı"}), 401

# Kullanıcı cevaplarını getiren route (admin için)
@app.route('/admin_answers', methods=['GET'])
def admin_answers():
    if 'is_admin' in session and session['is_admin']:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ua.user_id, q.question_text, ua.selected_option
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            ORDER BY ua.user_id, ua.question_id
        """)
        answers = cursor.fetchall()
        cursor.close()
        conn.close()

        answers_list = []
        for row in answers:
            answer = {
                'user_id': row[0],
                'question_text': row[1],
                'selected_option': row[2]
            }
            answers_list.append(answer)
        return jsonify({"status": "success", "answers": answers_list})
    else:
        return jsonify({"status": "error", "message": "Yetkisiz erişim"}), 403

# Kod çalıştırma route'u
@app.route('/run_code', methods=['POST'])
def run_code():
    data = request.get_json()
    code = data['code']
    language = data['language']
    
    if language == 'python':
        extension = 'py'
    elif language == 'javascript':
        extension = 'js'
    else:
        return jsonify({"status": "error", "message": "Desteklenmeyen dil"}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}') as temp_file:
        temp_file.write(code.encode('utf-8'))
        temp_file_path = temp_file.name

    try:
        if language == 'python':
            result = subprocess.run(['python', temp_file_path], capture_output=True, text=True, check=True)
        elif language == 'javascript':
            result = subprocess.run(['node', temp_file_path], capture_output=True, text=True, check=True)
        
        os.remove(temp_file_path)
        return jsonify({"status": "success", "output": result.stdout})
    except subprocess.CalledProcessError as e:
        os.remove(temp_file_path)
        return jsonify({"status": "error", "output": e.stderr}), 400

# Kod gönderme route'u
@app.route('/submit_code', methods=['POST'])
def submit_code():
    data = request.get_json()
    code = data['code']
    language = data['language']
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({"status": "error", "message": "Kullanıcı oturumu bulunamadı"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO user_code (user_id, code, language)
            VALUES (%s, %s, %s)
        """, (user_id, code, language))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": "Kod başarıyla gönderildi"})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"status": "error", "message": f"Kod gönderilirken bir hata oluştu: {str(e)}"}), 500

# Logout işlemi
@app.route('/logout', methods=['GET'])
def logout():
    session.pop('user_id', None)
    session.pop('is_admin', None)
    session.pop('test_completed', None)  # Oturumdaki işaretçiyi temizle
    return jsonify({"status": "success", "message": "Başarıyla çıkış yapıldı"})

# Seçim sayfası route'u
@app.route('/selection')
def selection():
    return render_template('interview.html')

# Admin sayfası route'u
@app.route('/admin')
def admin():
    if 'is_admin' in session and session['is_admin']:
        return render_template('admin.html')
    return redirect(url_for('home'))

# Soruları getirme route'u
@app.route('/questions', methods=['GET'])
def get_questions():
    if session.get('test_completed'):
        return jsonify({"status": "error", "message": "Testi zaten tamamladınız, tekrar giriş yapamazsınız"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, question_text, option_a, option_b, option_c, option_d FROM questions ORDER BY id ASC")
    questions = cursor.fetchall()
    cursor.close()
    conn.close()

    questions_list = []
    for row in questions:
        question = {
            'id': row[0],
            'question_text': row[1],
            'options': {
                'A': row[2],
                'B': row[3],
                'C': row[4],
                'D': row[5]
            }
        }
        questions_list.append(question)
    return jsonify(questions_list)

# Kullanıcı cevaplarını kaydetme route'u
@app.route('/submit', methods=['POST'])
def submit_answers():
    data = request.get_json()
    answers = data.get('answers', {})
    user_id = session.get('user_id')

    if not user_id:
        print("Kullanıcı oturumu bulunamadı")
        return jsonify({"status": "error", "message": "Kullanıcı oturumu bulunamadı"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for question_id, selected_option in answers.items():
            print(f"Kaydedilen cevap - Kullanıcı ID: {user_id}, Soru ID: {question_id}, Seçenek: {selected_option}")
            cursor.execute("""
                INSERT INTO user_answers (user_id, question_id, selected_option)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, question_id)
                DO UPDATE SET selected_option = EXCLUDED.selected_option
            """, (user_id, question_id, selected_option))
        conn.commit()
        cursor.close()
        conn.close()
        
        # Test tamamlandığını oturumda işaretle
        session['test_completed'] = True
        
        return jsonify({"status": "success", "message": "Cevaplar başarıyla kaydedildi"})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        print(f"Error: {e}")
        return jsonify({"status": "error", "message": f"Cevaplar kaydedilirken bir hata oluştu: {str(e)}"}), 500

# Test sayfasına erişim kontrolü
@app.route('/test')
def test():
    if session.get('test_completed'):
        return redirect(url_for('selection'))
    return render_template('test.html')

# HTML dosyalarını sunma
@app.route('/<path:path>')
def serve_file(path):
    return send_from_directory('templates', path)

@app.errorhandler(Exception)
def handle_exception(e):
    response = {
        "status": "error",
        "message": str(e)
    }
    print(f"Error: {e}")  # Terminalde hata mesajını yazdırma
    return jsonify(response), 500

if __name__ == '__main__':
    app.run(debug=True)
