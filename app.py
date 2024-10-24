import os
import sqlite3
import pythoncom
import win32com.client as win32
from flask import Flask, render_template, redirect, request, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import time
import random
import string

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Inicializa o banco de dados
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                      id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      name TEXT, 
                      email TEXT UNIQUE, 
                      password TEXT,
                      is_admin INTEGER DEFAULT 0)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS tickets (
                      id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      subject TEXT, 
                      message TEXT, 
                      image TEXT, 
                      status TEXT DEFAULT 'aberto',
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Insere o usuário admin
    email = 'lucas.gomes@kuehne-nagel.com'
    password = generate_password_hash('Ldfg1020')
    name = 'Lucas Gomes'
    is_admin = 1  # Define como admin

    try:
        cursor.execute("INSERT INTO users (name, email, password, is_admin) VALUES (?, ?, ?, ?)",
                       (name, email, password, is_admin))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Se o usuário já existir, não faz nada

    conn.close()

# Inicializa o banco de dados
init_db()

# Rota para a página inicial (login)
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# Rota para a página de login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()  # Remove espaços
        password = request.form['password'].strip()  # Remove espaços

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            # Debug: imprimir informações do usuário e hash da senha
            print(f"Usuário encontrado: {user}")
            print(f"Hash da senha: {user[3]}")
            print(f"Senha fornecida: {password}")

            if check_password_hash(user[3], password):
                session['user_id'] = user[0]
                session['user_name'] = user[1]
                session['user_email'] = user[2]
                session['is_admin'] = user[4]
                return redirect(url_for('dashboard'))
            else:
                flash("Email ou senha inválidos", "danger")
                return redirect(url_for('login'))
        else:
            flash("Email ou senha inválidos", "danger")
            return redirect(url_for('login'))

    return render_template('login.html')

# Rota para o cadastro de usuários
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
            conn.commit()
            flash("Usuário cadastrado com sucesso!", "success")
        except sqlite3.IntegrityError:
            flash("Email já cadastrado!", "danger")
        conn.close()

        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard', methods=['GET'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']

    # Verificação se o usuário é um administrador
    is_admin = session.get('is_admin', False)
    if is_admin:
        return redirect(url_for('admin_dashboard'))  # Redireciona para o painel do administrador

    page = request.args.get('page', 1, type=int)  # Captura a página atual
    per_page = 4  # Número de tickets por página
    offset = (page - 1) * per_page  # Cálculo do offset

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Consulta para buscar os últimos 4 tickets do usuário
    cursor.execute("""
        SELECT id, subject, message, status 
        FROM tickets 
        WHERE user_id = ? 
        ORDER BY id DESC 
        LIMIT ? OFFSET ?
    """, (user_id, per_page, offset))

    tickets = cursor.fetchall()

    # Consulta para contar o total de tickets do usuário
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE user_id = ?", (user_id,))
    total_tickets = cursor.fetchone()[0]

    conn.close()

    # Calcular total de páginas
    total_pages = (total_tickets + per_page - 1) // per_page  # Arredonda para cima

    return render_template('dashboard.html', tickets=tickets, total_pages=total_pages, current_page=page)

@app.route('/admin_dashboard', methods=['GET'])
def admin_dashboard():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))

    page = request.args.get('page', 1, type=int)  # Captura a página atual
    per_page = 3  # Número de tickets por página
    offset = (page - 1) * per_page  # Cálculo do offset

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Consulta para buscar apenas os tickets em aberto e em andamento, ordenados pelos mais antigos
    cursor.execute("""
        SELECT tickets.id, users.name, tickets.subject, tickets.message, tickets.status 
        FROM tickets 
        JOIN users ON tickets.user_id = users.id 
        WHERE tickets.status IN ('aberto', 'em andamento') 
        ORDER BY tickets.id ASC 
        LIMIT ? OFFSET ?
    """, (per_page, offset))

    tickets = cursor.fetchall()

    # Consulta para contar o total de tickets em aberto e em andamento
    cursor.execute("""
        SELECT COUNT(*) 
        FROM tickets 
        WHERE status IN ('aberto', 'em andamento')
    """)
    total_tickets = cursor.fetchone()[0]

    conn.close()

    # Calcular total de páginas
    total_pages = (total_tickets + per_page - 1) // per_page  # Arredonda para cima

    return render_template('admin_dashboard.html', tickets=tickets, total_pages=total_pages, current_page=page)



@app.route('/new_ticket', methods=['POST'])
def new_ticket():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    subject = request.form['subject']
    message = request.form['message']
    image = None
    
    if 'image' in request.files:
        image_file = request.files['image']
        if image_file.filename != '':
            image_filename = f"ticket_image_{int(time.time())}_{session['user_id']}.png"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            try:
                image_file.save(image_path)
                image = image_filename
            except Exception as e:
                flash(f"Ocorreu um erro ao salvar a imagem: {e}", "danger")
                return redirect(url_for('dashboard'))

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tickets (user_id, subject, message, image) VALUES (?, ?, ?, ?)", 
                   (session['user_id'], subject, message, image))
    conn.commit()
    ticket_id = cursor.lastrowid
    conn.close()

    time.sleep(2)

    try:
        pythoncom.CoInitialize()
        outlook = win32.Dispatch('outlook.application')
        mail = outlook.CreateItem(0)
        mail.To = 'lucas.gomes@kuehne-nagel.com'
        mail.Subject = subject
        mail.Body = f"Mensagem de {session['user_name']} ({session['user_email']}):\n\n{message}"
        
        if image:
            attachment_path = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], image))
            if os.path.exists(attachment_path):
                mail.Attachments.Add(attachment_path)
            else:
                flash("O arquivo de imagem não foi encontrado para anexar.", "danger")
                return redirect(url_for('dashboard'))

        mail.Send()
        pythoncom.CoUninitialize()
        flash("Ticket enviado com sucesso!", "success")
    except Exception as e:
        pythoncom.CoUninitialize()
        flash(f"Ocorreu um erro ao enviar o email: {e}", "danger")

    return redirect(url_for('dashboard'))

@app.route('/update_ticket/<int:ticket_id>', methods=['POST'])
def update_ticket(ticket_id):
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))

    new_status = request.form['status']
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE tickets SET status = ? WHERE id = ?", (new_status, ticket_id))
    conn.commit()
    conn.close()
    
    flash("Status do ticket atualizado!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/view_users', methods=['GET'])
def view_users():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()

    return render_template('view_users.html', users=users)

def generate_random_password(length=8):
    # Inclui apenas letras maiúsculas, minúsculas, números e alguns caracteres especiais
    characters = string.ascii_letters + string.digits + "!@#$%&"
    return ''.join(random.choice(characters) for _ in range(length))

@app.route('/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))

    new_password = generate_random_password()
    hashed_password = generate_password_hash(new_password)

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Atualiza a senha no banco de dados
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_password, user_id))
    conn.commit()

    # Verifica se o email foi recuperado corretamente
    cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
    user_email = cursor.fetchone()
    
    if user_email is None:
        flash("Usuário não encontrado!", "danger")
        conn.close()
        return redirect(url_for('view_users'))

    user_email = user_email[0]
    conn.close()

    try:
        pythoncom.CoInitialize()
        outlook = win32.Dispatch('outlook.application')
        mail = outlook.CreateItem(0)
        mail.To = user_email
        mail.Subject = "Redefinição de Senha"
        mail.Body = f"Sua senha foi redefinida com sucesso! A nova senha é: {new_password}"
        mail.Send()
        pythoncom.CoUninitialize()
        flash(f"Senha redefinida e enviada para {user_email} com sucesso!", "success")
    except Exception as e:
        pythoncom.CoUninitialize()
        flash(f"Ocorreu um erro ao enviar o email: {e}", "danger")

    return redirect(url_for('view_users'))

# Rota para atualizar um usuário
@app.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))

    name = request.form['name']
    email = request.form['email']
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET name = ?, email = ? WHERE id = ?", (name, email, user_id))
    conn.commit()
    conn.close()

    flash("Usuário atualizado com sucesso!", "success")
    return redirect(url_for('view_users'))

# Rota para deletar um usuário
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash("Usuário deletado com sucesso!", "success")
    return redirect(url_for('view_users'))

# Rota para logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)