import os
import qrcode
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Stock, Piloto, Movimiento

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'iame_ultra_secret_2026')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración para Render (MySQL) o Local (SQLite)
if os.environ.get("DB_HOST"):
    uri = f"mysql+pymysql://{os.environ.get('DB_USER')}:{os.environ.get('DB_PASS')}@{os.environ.get('DB_HOST')}/{os.environ.get('DB_NAME')}"
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///iame_test.db'

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

# --- RUTAS PRINCIPALES ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('admin_home' if user.role == 'admin' else 'puesto_control'))
        flash('Credenciales incorrectas', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- PANEL OPERARIO (PUESTO DE CONTROL) ---
@app.route('/puesto')
@login_required
def puesto_control():
    return render_template('puesto_control.html')

@app.route('/perfil/<int:n_kart>')
@login_required
def ver_perfil(n_kart):
    p = Piloto.query.get_or_404(n_kart)
    return render_template('puesto_control_perfil.html', p=p)

@app.route('/generar_qr/<int:n_kart>')
def generar_qr(n_kart):
    # Usamos DOMINIO_REAL de las variables de entorno de Render
    dominio = os.environ.get('DOMINIO_REAL', 'localhost:5000')
    img = qrcode.make(f"https://{dominio}/perfil/{n_kart}")
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# --- INICIALIZACIÓN MÁGICA ---
with app.app_context():
    db.create_all()
    # Crear admin por defecto si no existe
    if not User.query.filter_by(username='admin').first():
        pw = generate_password_hash('iame2026')
        new_admin = User(username='admin', password=pw, role='admin')
        db.session.add(new_admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- CONFIGURACIÓN DE ITEMS ---
ITEMS_CONFIG = {
    'nafta_20l': '⛽ Nafta 20L', 
    'neumaticos_mg_rojas': '🔴 MG Rojas',
    'neumaticos_mg_cadete': '🔵 MG Cadete', 
    'neumaticos_lluvia': '🌧️ Lluvia', 
    'sensor': '📡 Sensor'
}

# --- FUNCIONES DE SOPORTE ---
def safe_int(val):
    try: return int(val) if val else 0
    except (ValueError, TypeError): return 0

def registrar_movimiento(tipo, item, cantidad, kart, detalle=""):
    # El campo piloto_dni de la DB ahora guarda siempre el N° de Kart para el historial
    mov = Movimiento(tipo=tipo, usuario=current_user.username, item=item, cantidad=cantidad, piloto_dni=str(kart), detalle=detalle)
    db.session.add(mov)

def get_consumido(numero_kart, item_key):
    # Consulta de consumos basada en el identificador único: N° de Kart
    total = db.session.query(db.func.sum(Movimiento.cantidad)).filter_by(piloto_dni=str(numero_kart), item=item_key, tipo='CONSUMO').scalar()
    return total if total else 0

def obtener_items_permitidos(role):
    if role in ['admin', 'control']: return ITEMS_CONFIG
    elif role == 'nafta': return {'nafta_20l': ITEMS_CONFIG['nafta_20l']}
    elif role == 'gomas': return {k: v for k, v in ITEMS_CONFIG.items() if 'neumaticos' in k}
    elif role == 'sensor': return {'sensor': ITEMS_CONFIG['sensor']}
    else: return {}

def inicializar_sistema():
    """Crea los usuarios base y los items de stock si no existen en la DB."""
    usuarios_base = {
        'admin': 'admin123', 'control': 'control123', 'nafta': 'nafta123', 
        'gomas': 'gomas123', 'pista': 'pista123', 'sensor': 'sensor123'
    }
    for usr, pwd in usuarios_base.items():
        if not User.query.filter_by(username=usr).first():
            db.session.add(User(username=usr, password=generate_password_hash(pwd), role=usr))

    for key, name in ITEMS_CONFIG.items():
        if not db.session.get(Stock, key):
            db.session.add(Stock(item_key=key, nombre_legible=name, cantidad=0))
    db.session.commit()

# --- BLOQUE DE INICIALIZACIÓN ---
with app.app_context():
    db.create_all()
    inicializar_sistema()

# --- DECORADORES ---
@app.before_request
def make_session_permanent():
    session.permanent = True

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- RUTAS ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        u = User.query.filter_by(username=request.form['username']).first()
        if u and check_password_hash(u.password, request.form['password']):
            login_user(u)
            return redirect(url_for('admin_home') if u.role == 'admin' else url_for('stand_home'))
        error = "Datos incorrectos"
    return render_template('login.html', error=error)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def admin_home():
    if current_user.role != 'admin': return redirect(url_for('stand_home'))
    pilotos = Piloto.query.order_by(Piloto.numero_piloto).all()
    return render_template('admin_panel.html', pilotos=pilotos)

@app.route('/admin/crear', methods=['POST'])
@login_required
def admin_crear():
    if current_user.role != 'admin': return "Acceso Denegado", 403
    try:
        nuevo = Piloto(
            numero_piloto=safe_int(request.form['numero']), 
            nombre=request.form['nombre'], 
            dni=request.form.get('categoria', 'S/C')[:20], # Guardamos categoría en el campo dni
            equipo=request.form.get('equipo', '')
        )
        db.session.add(nuevo)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(url_for('admin_home'))

@app.route('/admin/editar/<int:id>', methods=['POST'])
@login_required
def admin_editar(id):
    if current_user.role != 'admin': return "Acceso Denegado", 403
    p = Piloto.query.get_or_404(id)
    try:
        p.numero_piloto = safe_int(request.form['numero'])
        p.nombre = request.form['nombre']
        p.dni = request.form.get('categoria', 'S/C')[:20]
        p.equipo = request.form.get('equipo', '')
        db.session.commit()
        flash("Piloto actualizado con éxito", "success")
    except Exception:
        db.session.rollback()
        flash("Error: El número de piloto ya está en uso.", "danger")
    return redirect(url_for('admin_home'))

@app.route('/admin/borrar/<int:id>')
@login_required
def admin_borrar(id):
    if current_user.role != 'admin': return "Acceso Denegado", 403
    p = Piloto.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('admin_home'))

# --- GESTIÓN DE USUARIOS ---
@app.route('/admin/usuarios')
@login_required
def admin_usuarios():
    if current_user.role != 'admin': return "Acceso Denegado", 403
    usuarios = User.query.all()
    roles_disponibles = ['admin', 'control', 'nafta', 'gomas', 'sensor', 'pista']
    return render_template('admin_usuarios.html', usuarios=usuarios, roles=roles_disponibles)

@app.route('/admin/usuarios/crear', methods=['POST'])
@login_required
def admin_usuarios_crear():
    if current_user.role != 'admin': return "Acceso Denegado", 403
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    if not User.query.filter_by(username=username).first():
        db.session.add(User(username=username, password=generate_password_hash(password), role=role))
        db.session.commit()
        flash(f"Usuario '{username}' creado con éxito", "success")
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/borrar/<int:id>')
@login_required
def admin_usuarios_borrar(id):
    if current_user.role != 'admin': return "Acceso Denegado", 403
    u = User.query.get_or_404(id)
    if u.username != current_user.username:
        db.session.delete(u)
        db.session.commit()
        flash("Usuario eliminado", "success")
    return redirect(url_for('admin_usuarios'))

# --- STOCK Y CARGA ---
@app.route('/admin/stock', methods=['GET', 'POST'])
@login_required
def admin_stock():
    if current_user.role != 'admin': return "Acceso Denegado", 403
    if request.method == 'POST':
        item = request.form['item_key']
        accion = request.form.get('accion', 'sumar')
        cant = safe_int(request.form.get('cantidad', ''))
        if cant > 0:
            stk = db.session.get(Stock, item)
            if stk:
                if accion == 'sumar':
                    stk.cantidad += cant
                    registrar_movimiento("INGRESO_STOCK", item, cant, detalle="Suma manual")
                elif accion == 'restar':
                    stk.cantidad = max(0, stk.cantidad - cant)
                    registrar_movimiento("RETIRO_STOCK", item, cant, detalle="Resta manual")
                elif accion == 'fijar':
                    viejo = stk.cantidad
                    stk.cantidad = cant
                    registrar_movimiento("CORRECCION_STOCK", item, cant - viejo, detalle=f"Fijado (de {viejo} a {cant})")
                db.session.commit()
    stock = Stock.query.all()
    return render_template('stock.html', stock=stock)

@app.route('/admin/procesar_carga/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_procesar_carga(id):
    if current_user.role != 'admin': return "Acceso Denegado", 403
    p = Piloto.query.get_or_404(id)
    if request.method == 'POST':
        modo = request.form.get('modo', 'sumar')
        for key in ITEMS_CONFIG.keys():
            val = safe_int(request.form.get(key))
            if val > 0:
                actual = getattr(p, key)
                if modo == 'sumar':
                    setattr(p, key, actual + val)
                    registrar_movimiento("CARGA_SALDO", key, val, p.numero_piloto)
                elif modo == 'restar':
                    setattr(p, key, max(0, actual - val))
                    registrar_movimiento("RESTA_SALDO", key, val, p.numero_piloto)
                elif modo == 'fijar':
                    if actual != val:
                        setattr(p, key, val)
                        registrar_movimiento("CORRECCION_SALDO", key, val - actual, p.numero_piloto, detalle=f"Fijado (de {actual} a {val})")
        p.derecho_pista = request.form.get('derecho_pista', p.derecho_pista)
        db.session.commit()
        return redirect(url_for('admin_home'))
    consumos = {key: get_consumido(p.numero_piloto, key) for key in ITEMS_CONFIG.keys()}
    return render_template('admin_carga.html', p=p, items=ITEMS_CONFIG, consumos=consumos, getattr=getattr)

# --- QR Y SMART ROUTER BASADO EN KART ---
@app.route('/qr/<int:numero_kart>')
@login_required
def get_qr(numero_kart):
    # El QR ahora apunta directamente al número de kart
    url = f"https://{DOMINIO_REAL}/smart/{numero_kart}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/smart/<int:numero_kart>')
@login_required
def smart_router(numero_kart):
    # Buscamos al piloto por su número único de kart
    p = Piloto.query.filter_by(numero_piloto=numero_kart).first_or_404()
    role = current_user.role
    if role == 'admin': return redirect(url_for('admin_procesar_carga', id=p.id))
    allowed_items = obtener_items_permitidos(role)
    return render_template('stand_view.html', p=p, items=allowed_items, getattr=getattr, user=current_user)

@app.route('/stand_home')
@login_required
def stand_home():
    return render_template('stand_home.html')

@app.route('/api/descontar_post/<int:id>/<item>', methods=['POST'])
@login_required
def api_descontar_post(id, item):
    allowed = obtener_items_permitidos(current_user.role)
    if item not in allowed: return "No autorizado", 403
    p = Piloto.query.get_or_404(id)
    stk = db.session.get(Stock, item)
    saldo_piloto = getattr(p, item)
    if saldo_piloto > 0 and stk and stk.cantidad > 0:
        setattr(p, item, saldo_piloto - 1)
        stk.cantidad -= 1
        # Registro de consumo asociado al número de kart
        registrar_movimiento("CONSUMO", item, 1, p.numero_piloto, detalle=f"Retiro en puesto: {current_user.role}")
        db.session.commit()
        flash(f"Retiro exitoso de {ITEMS_CONFIG[item]}", "success")
    else:
        flash("Sin saldo o sin stock disponible", "danger")
    return redirect(url_for('smart_router', numero_kart=p.numero_piloto))

# --- EXPORTACIÓN CON HORARIO ARGENTINA ---
@app.route('/admin/exportar')
@login_required
def admin_exportar():
    if current_user.role != 'admin': return "Acceso Denegado", 403
    pilotos = Piloto.query.all()
    data_saldos = []
    for p in pilotos:
        data_saldos.append({
            'N_Kart': p.numero_piloto, 'Nombre': p.nombre, 'Categoría': p.dni, 'Equipo': p.equipo,
            'Nafta': p.nafta_20l, 'Gomas Rojas': p.neumaticos_mg_rojas, 'Gomas Cadete': p.neumaticos_mg_cadete,
            'Lluvia': p.neumaticos_lluvia, 'Sensor': p.sensor, 'Pista': p.derecho_pista
        })
    df_saldos = pd.DataFrame(data_saldos)

    movimientos = Movimiento.query.order_by(Movimiento.fecha.desc()).all()
    data_movs = []
    for m in movimientos:
        # Ajuste de horario: UTC a Argentina (UTC-3)
        fecha_arg = (m.fecha - timedelta(hours=3)).strftime('%d/%m/%Y %H:%M:%S') if m.fecha else ''
        data_movs.append({
            'Fecha (ARG)': fecha_arg,
            'Acción': m.tipo,
            'Usuario': m.usuario,
            'Item': ITEMS_CONFIG.get(m.item, m.item),
            'Cantidad': m.cantidad,
            'N° Kart': m.piloto_dni or 'N/A',
            'Detalle': m.detalle or ''
        })
    df_movs = pd.DataFrame(data_movs)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_saldos.to_excel(writer, index=False, sheet_name='Saldos Actuales')
        df_movs.to_excel(writer, index=False, sheet_name='Auditoría Movimientos')
    output.seek(0)
    
    hora_arg = datetime.now() - timedelta(hours=3)
    nombre_archivo = f"reporte_iame_{hora_arg.strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(output, download_name=nombre_archivo, as_attachment=True)

if __name__ == '__main__':
    # host='0.0.0.0' permite acceso desde el celular si estás en la misma red Wi-Fi
    app.run(host='0.0.0.0', debug=True, port=5000)
