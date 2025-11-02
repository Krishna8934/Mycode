import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# ---------- DATABASE SETUP ----------
def get_db():
    # Render ke environment variable se connect hoga
    conn = psycopg2.connect(os.environ['DATABASE_URL'], sslmode='require')
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Create tables if they don't exist
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        problem_no TEXT,
        title TEXT,
        code TEXT,
        image TEXT,
        notes TEXT,
        date TEXT
    );
    ''')
    conn.commit()
    cur.close()
    conn.close()
    print("✅ PostgreSQL database initialized.")


# ---------- ROUTES ----------
@app.route('/')
def index():
    q = request.args.get('q', '').strip()
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if q:
        query = '''
            SELECT posts.*, users.username
            FROM posts
            JOIN users ON posts.user_id = users.id
            WHERE users.username ILIKE %s
               OR posts.title ILIKE %s
               OR posts.notes ILIKE %s
               OR posts.problem_no ILIKE %s
            ORDER BY posts.id DESC;
        '''
        search_term = f'%{q}%'
        cur.execute(query, (search_term, search_term, search_term, search_term))
    else:
        cur.execute('''
            SELECT posts.*, users.username 
            FROM posts 
            JOIN users ON posts.user_id = users.id 
            ORDER BY posts.id DESC;
        ''')
    posts = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', posts=posts)


@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute('INSERT INTO users (username, email, password) VALUES (%s, %s, %s)', 
                        (username, email, password))
            conn.commit()
            cur.close()
            conn.close()
            flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            print(e)
            flash('Email already exists or error occurred.', 'danger')
    return render_template('register.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['csrf_token'] = secrets.token_hex(16)
            session['is_admin'] = 0
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
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO posts (user_id, problem_no, title, code, image, notes, date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (session['user_id'], problem_no, title, code, filename, notes, date))
        conn.commit()
        cur.close()
        conn.close()

        flash('Post uploaded successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('upload.html')


@app.route('/p/<int:post_id>')
def post(post_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT posts.*, users.username 
        FROM posts 
        JOIN users ON posts.user_id = users.id 
        WHERE posts.id = %s
    ''', (post_id,))
    post = cur.fetchone()
    cur.close()
    conn.close()

    if not post:
        flash('Post not found', 'danger')
        return redirect(url_for('index'))
    return render_template('post.html', post=post)


@app.route('/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM posts WHERE id = %s', (post_id,))
    post = cur.fetchone()

    if not post:
        flash('Post not found.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('index'))

    if post['user_id'] != session['user_id']:
        flash('You are not authorized to delete this post.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('index'))

    cur.execute('DELETE FROM posts WHERE id = %s', (post_id,))
    conn.commit()
    cur.close()
    conn.close()

    flash('Post deleted successfully!', 'info')
    return redirect(url_for('index'))


# ---------- MAIN ----------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
