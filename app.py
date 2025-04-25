from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')
DATABASE = os.getenv('DATABASE_PATH', 'deil.db')
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
ALLOWED_EXTENSIONS = {'pdf'}
MAX_PDF_SIZE = 5 * 1024 * 1024  # 5 MB en bytes
MAX_PDF_COUNT = 100  # Límite de 100 PDFs

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     name TEXT NOT NULL,
                     email TEXT UNIQUE NOT NULL,
                     password TEXT NOT NULL,
                     phone TEXT NOT NULL,
                     role TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS tasks (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     title TEXT NOT NULL,
                     number TEXT NOT NULL,
                     reading TEXT NOT NULL,
                     instructions TEXT,
                     status TEXT NOT NULL,
                     assigned_by TEXT,
                     assigned_to TEXT,
                     created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                     pdf_path TEXT,
                     comments TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS history (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     task_id INTEGER,
                     action TEXT NOT NULL,
                     user TEXT NOT NULL,
                     reason TEXT,
                     created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY (task_id) REFERENCES tasks(id))''')
        c.execute('''INSERT OR IGNORE INTO users (name, email, password, phone, role)
                     VALUES (?, ?, ?, ?, ?)''',
                  ('Superusuario', 'Admin_DEIL2025', 'Admin_DEIL2025', '00000000', 'Superusuario'))
        conn.commit()

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def check_file_size(file):
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    return size <= MAX_PDF_SIZE

def check_pdf_count():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM tasks WHERE pdf_path IS NOT NULL')
        count = c.fetchone()[0]
    return count < MAX_PDF_COUNT

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password))
            user = c.fetchone()
            if user:
                session['user_id'] = user['id']
                session['role'] = user['role']
                session['name'] = user['name']
                if user['role'] == 'Superusuario':
                    return redirect(url_for('superusuario_dashboard'))
                elif user['role'] == 'Profesional':
                    return redirect(url_for('profesional_dashboard'))
                elif user['role'] in ['Subdireccion_Investigaciones', 'Subdireccion_Formacion']:
                    return redirect(url_for('investigaciones_dashboard'))
                elif user['role'] == 'Encargada_Despacho':
                    return redirect(url_for('despacho_dashboard'))
            else:
                flash('Correo o contraseña incorrectos', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        role = request.form['role']
        if role == 'Superusuario':
            flash('No puedes registrarte como Superusuario', 'error')
            return redirect(url_for('register'))
        with get_db() as conn:
            c = conn.cursor()
            try:
                c.execute('INSERT INTO users (name, email, password, phone, role) VALUES (?, ?, ?, ?, ?)',
                          (name, email, password, phone, role))
                conn.commit()
                flash('Registro exitoso. Por favor, inicia sesión.', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('El correo ya está registrado', 'error')
    return render_template('register.html')

@app.route('/profesional', methods=['GET', 'POST'])
def profesional():
    if 'user_id' not in session or session.get('role') != 'Profesional':
        flash('Acceso denegado.', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user_name = c.fetchone()[0]
    
    if request.method == 'POST':
        if 'receive_task' in request.form:
            task_id = request.form['receive_task']
            c.execute("UPDATE tasks SET status = 'Amarillo' WHERE id = ?", (task_id,))
            c.execute('INSERT INTO history (task_id, action, user, created_at) VALUES (?, ?, ?, ?)',
                      (task_id, 'Recibido', user_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            flash('Tarea marcada como recibida.', 'success')
            return redirect(url_for('profesional'))
        
        elif 'upload_pdf' in request.form:
            task_id = request.form['upload_pdf']
            file = request.files['pdf']
            if file and file.filename.endswith('.pdf'):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{task_id}_{timestamp}.pdf"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                c.execute("UPDATE tasks SET status = 'Naranja', pdf_path = ? WHERE id = ?", (file_path, task_id))
                c.execute('INSERT INTO history (task_id, action, user, created_at) VALUES (?, ?, ?, ?)',
                          (task_id, 'PDF subido', user_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                
                # Obtener el título y número de la tarea
                c.execute("SELECT title, number FROM tasks WHERE id = ?", (task_id,))
                task = c.fetchone()
                task_title = task[0]
                task_number = task[1]
                
                # Obtener los correos de los usuarios con rol Subdireccion_Investigaciones
                c.execute("SELECT email FROM users WHERE role = 'Subdireccion_Investigaciones'")
                subdireccion_emails = [row[0] for row in c.fetchall()]
                
                # Enviar correo a cada usuario de Subdirección
                if subdireccion_emails:
                    print(f"Enviando correo a Subdirección: {subdireccion_emails}")
                    for email in subdireccion_emails:
                        subject = "Tarea Actualizada - Revisión Requerida - DEIL"
                        body = f"Hola,\n\nEl Profesional {user_name} ha subido un PDF para la tarea:\nTítulo: {task_title}\nNúmero: {task_number}\n\nPor favor, revisa y aprueba en el sistema.\n\nSaludos,\nEquipo DEIL"
                        send_email(email, subject, body)
                else:
                    print("No se encontraron usuarios con rol Subdireccion_Investigaciones")
                
                flash('PDF subido exitosamente.', 'success')
            else:
                flash('Por favor, sube un archivo PDF válido.', 'error')
            return redirect(url_for('profesional'))
    
    c.execute("SELECT * FROM tasks WHERE assigned_to = ? AND status IN ('Verde', 'Amarillo')", (user_name,))
    tasks = c.fetchall()
    tasks = [dict(id=row[0], title=row[1], number=row[2], reading=row[3], instructions=row[4],
                  assigned_to=row[5], status=row[6], created_at=row[7], pdf_path=row[8]) for row in tasks]
    
    conn.close()
    return render_template('profesional.html', user_name=user_name, tasks=tasks)
           

@app.route('/investigaciones', methods=['GET', 'POST'])
def investigaciones_dashboard():
    if 'user_id' not in session or session['role'] not in ['Subdireccion_Investigaciones', 'Subdireccion_Formacion', 'Superusuario']:
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    is_read_only = session['role'] == 'Subdireccion_Formacion'
    if request.method == 'POST' and not is_read_only:
        task_id = request.form.get('task_id')
        action = request.form.get('action')
        with get_db() as conn:
            c = conn.cursor()
            if action == 'aprobar':
                c.execute('UPDATE tasks SET status = ? WHERE id = ?',
                          ('Azul', task_id))
                c.execute('INSERT INTO history (task_id, action, user, created_at) VALUES (?, ?, ?, ?)',
                          (task_id, 'Aprobado', session['name'], datetime.now()))
                conn.commit()
                flash('Tarea aprobada', 'success')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM tasks')
        tasks = c.fetchall()
        c.execute('SELECT name FROM users WHERE role = "Profesional"')
        profesionales = c.fetchall()
    return render_template('investigaciones.html', tasks=tasks, profesionales=profesionales, is_read_only=is_read_only)

@app.route('/assign_task', methods=['POST'])
def assign_task():
    if 'user_id' not in session or session.get('role') != 'Subdireccion_Investigaciones':
        flash('Acceso denegado.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        number = request.form['number']
        reading = request.form['reading']
        instructions = request.form['instructions']
        assigned_to = request.form['assigned_to']
        
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status = 'Verde'
        
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("INSERT INTO tasks (title, number, reading, instructions, assigned_to, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (title, number, reading, instructions, assigned_to, status, created_at))
        conn.commit()
        
        # Obtener el correo del Profesional asignado
        c.execute("SELECT email FROM users WHERE name = ?", (assigned_to,))
        result = c.fetchone()
        if result:
            professional_email = result[0]
            print(f"Intentando enviar correo a: {professional_email}")
            # Enviar correo al Profesional
            subject = "Nueva Tarea Asignada - DEIL"
            body = f"Hola {assigned_to},\n\nSe te ha asignado una nueva tarea:\nTítulo: {title}\nNúmero: {number}\nLectura: {reading}\nInstrucciones: {instructions}\n\nPor favor, revisa el sistema para más detalles.\n\nSaludos,\nEquipo DEIL"
            send_email(professional_email, subject, body)
        else:
            print(f"No se encontró correo para el usuario: {assigned_to}")
        
        flash('Tarea asignada exitosamente.', 'success')
        conn.close()
        return redirect(url_for('investigaciones'))

@app.route('/despacho', methods=['GET', 'POST'])
def despacho_dashboard():
    if 'user_id' not in session or session['role'] not in ['Encargada_Despacho', 'Superusuario']:
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        task_id = request.form.get('task_id')
        action = request.form.get('action')
        with get_db() as conn:
            c = conn.cursor()
            if action == 'finalizar':
                c.execute('UPDATE tasks SET status = ? WHERE id = ?',
                          ('Blanco', task_id))
                c.execute('INSERT INTO history (task_id, action, user, created_at) VALUES (?, ?, ?, ?)',
                          (task_id, 'Finalizada', session['name'], datetime.now()))
                conn.commit()
                flash('Tarea finalizada', 'success')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM tasks WHERE status IN ("Naranja", "Azul")')
        tasks = c.fetchall()
    return render_template('despacho.html', tasks=tasks)

@app.route('/superusuario')
def superusuario_dashboard():
    if 'user_id' not in session or session['role'] != 'Superusuario':
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM tasks')
        tasks = c.fetchall()
        c.execute('SELECT name, role FROM users')
        users = c.fetchall()
    return render_template('superusuario.html', tasks=tasks, users=users)

@app.route('/consultas')
def consultas():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM tasks WHERE status = "Blanco"')
        tasks = c.fetchall()
    return render_template('consultas.html', tasks=tasks)

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=True)

def send_email(recipient_email, subject, body):
    sender_email = "deilorganismolegislativo@gmail.com"  # Reemplaza con tu correo
    sender_password = "jwnd abwa tgmi khrw"  # Reemplaza con la contraseña de aplicación
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipient_email, text)
        server.quit()
        print(f"Correo enviado a {recipient_email}")
    except Exception as e:
        print(f"Error al enviar correo a {recipient_email}: {e}")
