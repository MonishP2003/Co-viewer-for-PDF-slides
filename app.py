from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_socketio import SocketIO, emit, join_room
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
import fitz  
import io
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = 'uploads'
socketio = SocketIO(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


rooms = {}
users = {}
files = {}

if not os.path.exists(app.config['UPLOAD_FOLDER']): 
    os.makedirs(app.config['UPLOAD_FOLDER'])

class User(UserMixin):
    def __init__(self, id, username, password, role):
        self.id = id
        self.username = username
        self.password = password
        self.role = role

users_db = {
}

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

@login_manager.user_loader
def load_user(user_id):
    for user in users_db.values():
        if user.id == user_id:
            return user
    return None

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        if username in users_db:
            flash('Username already exists. Please choose a different username.')
        else:
            new_id = str(len(users_db) + 1)
            new_user = User(new_id, username, password, role)
            users_db[username] = new_user
            flash('Registration successful! Please log in.')
            print(users_db)  
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/index')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        if username in users_db and users_db[username].password == password:
            user = users_db[username]
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if current_user.role != 'faculty':
        return 'Unauthorized', 403
    try:
        if 'file' not in request.files:
            return 'No file part', 400
        file = request.files['file']
        if file.filename == '':
            return 'No selected file', 400
        if file:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            room = request.form['room']
            files[room] = filepath
            rooms[room] = 1  
            socketio.emit('page_update', {'page': rooms[room]}, room=room)
            return 'File uploaded successfully', 200
    except Exception as e:
        print(f"Error uploading file: {e}")
        return 'Internal Server Error', 500

@app.route('/pdf/<room>/<int:page>')
@login_required
def pdf_page(room, page):
    try:
        if room not in files:
            return 'No file uploaded', 400
        doc = fitz.open(files[room])
        page = doc.load_page(page - 1)  
        pix = page.get_pixmap()
        img_data = pix.tobytes("png")
        return send_file(io.BytesIO(img_data), mimetype='image/png')
    except Exception as e:
        print(f"Error loading PDF page: {e}")
        return 'Internal Server Error', 500

@socketio.on('join')
@login_required
def on_join(data):
    room = data['room']
    join_room(room)
    if room not in rooms:
        rooms[room] = 1  
        users[room] = request.sid  
    emit('page_update', {'page': rooms[room]}, room=room)

@socketio.on('change_page')
@login_required
def on_change_page(data):
    room = data['room']
    page = data['page']
    if current_user.role == 'faculty':  
        rooms[room] = page
        emit('page_update', {'page': page}, room=room)
    elif current_user.role == 'student':  
        emit('page_update', {'page': page}, room=request.sid)

@socketio.on('request_presenter_page')
@login_required
def on_request_presenter_page(data):
    room = data['room']
    if room in rooms:
        emit('page_update', {'page': rooms[room]}, room=request.sid)

if __name__ == '__main__':
    socketio.run(app, debug=True)
