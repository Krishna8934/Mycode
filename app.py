import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# ---------- DATABASE SETUP ----------
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            problem_no TEXT,
            title TEXT,
            code TEXT,
            image TEXT,
            notes TEXT,
            date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
    print("✅ Database initialized.")

# ---------- ROUTES ----------

@app.route('/')
def index():
    conn = get_db()
    posts = conn.execute('SELECT posts.*, users.username FROM posts JOIN users ON posts.user_id = users.id ORDER BY id DESC').fetchall()
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        try:
            conn = get_db()
            conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                         (username, email, password))
            conn.commit()
            flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Email already exists or error occurred.', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET','POST'])
def upload():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        problem_no = request.form['problem_no']
        title = request.form['title']
        code = request.form['code']
        notes = request.form['notes']
        file = request.files['image']
        filename = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        date = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = get_db()
        conn.execute('INSERT INTO posts (user_id, problem_no, title, code, image, notes, date) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (session['user_id'], problem_no, title, code, filename, notes, date))
        conn.commit()
        flash('Post uploaded successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('upload.html')

@app.route('/p/<int:post_id>')
def post(post_id):
    conn = get_db()
    post = conn.execute('SELECT posts.*, users.username FROM posts JOIN users ON posts.user_id = users.id WHERE posts.id = ?', (post_id,)).fetchone()
    if not post:
        flash('Post not found', 'danger')
        return redirect(url_for('index'))
    return render_template('post.html', post=post)

# ---------- MAIN ----------
if __name__ == '__main__':
    if not os.path.exists('database.db'):
        init_db()
    app.run(debug=True)
