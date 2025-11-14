from dotenv import load_dotenv
load_dotenv()

import os
import sqlite3
import psycopg2
import psycopg2.extras
import cloudinary
import cloudinary.uploader

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'


# ---------------- CLOUDINARY CONFIG ----------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)


# ---------------- DATABASE SETUP ----------------

def using_postgres():
    return "DATABASE_URL" in os.environ


def get_db():
    if using_postgres():
        conn = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")
        return conn
    else:
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    try:
        if using_postgres():
            conn = get_db()
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                );
            """)

            cur.execute("""
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
            """)

            conn.commit()
            cur.close()
            conn.close()
            print("✅ PostgreSQL tables ready.")

        else:
            conn = sqlite3.connect("database.db")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    problem_no TEXT,
                    title TEXT,
                    code TEXT,
                    image TEXT,
                    notes TEXT,
                    date TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)

            conn.commit()
            conn.close()
            print("✅ SQLite tables ready.")

    except Exception as e:
        print("❌ Database initialization failed:", e)


with app.app_context():
    init_db()


# ---------------- ROUTES ----------------

@app.route('/')
def index():
    q = request.args.get('q', '').strip()
    conn = get_db()

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if using_postgres() else conn.cursor()

    if q:
        search_term = f"%{q}%"
        query = """
            SELECT posts.*, users.username
            FROM posts JOIN users ON posts.user_id = users.id
            WHERE users.username ILIKE %s
            OR posts.title ILIKE %s
            OR posts.notes ILIKE %s
            OR posts.problem_no ILIKE %s
            ORDER BY posts.id DESC
        """ if using_postgres() else """
            SELECT posts.*, users.username
            FROM posts JOIN users ON posts.user_id = users.id
            WHERE users.username LIKE ?
            OR posts.title LIKE ?
            OR posts.notes LIKE ?
            OR posts.problem_no LIKE ?
            ORDER BY posts.id DESC
        """

        cur.execute(query, (search_term, search_term, search_term, search_term))

    else:
        cur.execute("""
            SELECT posts.*, users.username
            FROM posts JOIN users ON posts.user_id = users.id
            ORDER BY posts.id DESC
        """)

    posts = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', posts=posts)


@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':   # FIXED
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        try:
            conn = get_db()
            cur = conn.cursor()

            query = "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)" \
                    if using_postgres() else \
                    "INSERT INTO users (username, email, password) VALUES (?, ?, ?)"

            cur.execute(query, (username, email, password))
            conn.commit()
            flash("Account created! Please login.", "success")

        except Exception as e:
            print(e)
            flash("Email already exists or error occurred.", "danger")

        return redirect(url_for('login'))

    return render_template('register.html')



@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if using_postgres() else conn.cursor()

        query = "SELECT * FROM users WHERE email = %s" if using_postgres() else "SELECT * FROM users WHERE email = ?"
        cur.execute(query, (email,))

        user = cur.fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Logged in successfully!", "success")
            return redirect(url_for('index'))

        flash("Invalid credentials", "danger")

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('index'))


@app.route('/upload', methods=['GET','POST'])
def upload():
    if 'user_id' not in session:
        flash("Please login first.", "warning")
        return redirect(url_for('login'))

    if request.method == 'POST':
        problem_no = request.form['problem_no']
        title = request.form['title']
        code = request.form['code']
        notes = request.form['notes']
        file = request.files['image']

        image_url = None

        # ----------- CLOUDINARY UPLOAD WITH LOCAL/PROD SEPARATION ------------
        if file and file.filename:
            folder_name = "prod_uploads" if using_postgres() else "local_uploads"

            upload_result = cloudinary.uploader.upload(
                file,
                folder=folder_name
            )

            image_url = upload_result.get("secure_url")

        date = datetime.now().strftime("%Y-%m-%d %H:%M")

        conn = get_db()
        cur = conn.cursor()

        query = """
            INSERT INTO posts (user_id, problem_no, title, code, image, notes, date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """ if using_postgres() else """
            INSERT INTO posts (user_id, problem_no, title, code, image, notes, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        cur.execute(query, (session['user_id'], problem_no, title, code, image_url, notes, date))
        conn.commit()

        flash("Post uploaded successfully!", "success")
        return redirect(url_for('index'))

    return render_template('upload.html')


@app.route('/p/<int:post_id>')
def post(post_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if using_postgres() else conn.cursor()

    query = """
        SELECT posts.*, users.username
        FROM posts JOIN users ON posts.user_id = users.id
        WHERE posts.id = %s
    """ if using_postgres() else """
        SELECT posts.*, users.username
        FROM posts JOIN users ON posts.user_id = users.id
        WHERE posts.id = ?
    """

    cur.execute(query, (post_id,))
    post = cur.fetchone()

    if not post:
        flash("Post not found", "danger")
        return redirect(url_for('index'))

    return render_template('post.html', post=post)


@app.route('/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    if 'user_id' not in session:
        flash("Please login first.", "warning")
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if using_postgres() else conn.cursor()

    query = "SELECT * FROM posts WHERE id = %s" if using_postgres() else "SELECT * FROM posts WHERE id = ?"
    cur.execute(query, (post_id,))
    post = cur.fetchone()

    if not post:
        flash("Post not found.", "danger")
        return redirect(url_for('index'))

    if post['user_id'] != session['user_id']:
        flash("Not authorized.", "danger")
        return redirect(url_for('index'))

    delete_query = "DELETE FROM posts WHERE id = %s" if using_postgres() else "DELETE FROM posts WHERE id = ?"
    cur.execute(delete_query, (post_id,))
    conn.commit()

    flash("Post deleted.", "info")
    return redirect(url_for('index'))


# --------------- MAIN ----------------
if __name__ == '__main__':
    app.run(debug=True)
