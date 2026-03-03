import os
import qrcode
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, flash, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Importación de modelos (aseguráte que tu archivo se llame models.py)
from models import db, User, Stock, Piloto, Movimiento

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'iame_super_secreto_local')
DOMINIO_REAL = os.environ.get('DOMINIO_REAL', '127.0.0.1:5000')

# Configuración de Base de Datos (Render MySQL vs Local SQLite)
if os.environ.get("DB_HOST"):
    DB_USER = os.environ.get("DB_USER")
    DB_PASS = os.environ.get("DB_PASS")
    DB_HOST = os.environ.get("DB_HOST")
    DB_NAME = os.environ.get("DB_NAME")
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True, 'pool_size': 10}
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'iame_local.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

# --- INICIALIZACIÓN DE EXTENSIONES ---
db.init_app(app)

login_manager = LoginManager()
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

def registrar_movimiento(tipo, item, cantidad, piloto_dni=None, detalle=""):
    mov = Movimiento(tipo=tipo, usuario=current_user.username, item=item, cantidad=cantidad, piloto_dni=piloto_dni, detalle=detalle)
    db.session.add(mov)

def get_consumido(piloto_dni, item_key):
    total = db.session.query(db.func.sum(Movimiento.cantidad)).filter_by(piloto_dni=piloto_dni, item=item_key, tipo='CONSUMO').scalar()
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

# --- BLOQUE DE INICIALIZACIÓN (CRÍTICO PARA RENDER) ---
with app.app_context():
    db.create_all()         # Asegura que las tablas existan
    inicializar_sistema()   # Asegura que los usuarios y stock existan

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
            dni=request.form['dni'], 
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
        p.dni = request.form['dni']
        p.equipo = request.form.get('equipo', '')
        db.session.commit()
        flash("Piloto actualizado con éxito", "success")
    except Exception:
        db.session.rollback()
        flash("Error: El número de piloto ya está en uso.", "danger")
    return redirect(url_for('admin_home'))

@app.route('/admin/importar', methods=['POST'])
@login_required
def admin_importar():
    if current_user.role != 'admin': return "Acceso Denegado", 403
    if 'archivo_excel' not in request.files: return redirect(url_for('admin_home'))
    file = request.files['archivo_excel']
    if file and file.filename.endswith('.xlsx'):
        try:
            diccionario_hojas = pd.read_excel(file, sheet_name=None, engine='openpyxl')
            importados = 0
            for nombre_hoja, df in diccionario_hojas.items():
                df.columns = df.columns.astype(str).str.strip().str.lower() 
                for index, row in df.iterrows():
                    col_num = row.get('n de kart', row.get('n_kart', row.get('numero', row.get('kart', 0))))
                    col_nombre = str(row.get('piloto', row.get('nombre', 'Sin Nombre')))
                    dni = str(row.get('dni', row.get('documento', '0')))
                    equipo = str(row.get('equipo', nombre_hoja))
                    numero = safe_int(col_num)
                    if numero > 0 and not Piloto.query.filter_by(numero_piloto=numero).first():
                        nuevo = Piloto(numero_piloto=numero, nombre=col_nombre, dni=dni, equipo=equipo)
                        db.session.add(nuevo)
                        importados += 1
            db.session.commit()
            flash(f'Éxito: Se importaron {importados} pilotos.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar el Excel: {str(e)}', 'danger')
    return redirect(url_for('admin_home'))

@app.route('/admin/borrar/<int:id>')
@login_required
def admin_borrar(id):
    if current_user.role != 'admin': return "Acceso Denegado", 403
    p = Piloto.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('admin_home'))

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
                    registrar_movimiento("CARGA_SALDO", key, val, piloto_dni=p.dni)
                elif modo == 'restar':
                    setattr(p, key, max(0, actual - val))
                    registrar_movimiento("RESTA_SALDO", key, val, piloto_dni=p.dni)
                elif modo == 'fijar':
                    if actual != val:
                        setattr(p, key, val)
                        registrar_movimiento("CORRECCION_SALDO", key, val - actual, piloto_dni=p.dni, detalle=f"Fijado (de {actual} a {val})")
        p.derecho_pista = request.form.get('derecho_pista', p.derecho_pista)
        db.session.commit()
        return redirect(url_for('admin_home'))
    consumos = {key: get_consumido(p.dni, key) for key in ITEMS_CONFIG.keys()}
    return render_template('admin_carga.html', p=p, items=ITEMS_CONFIG, consumos=consumos, getattr=getattr)

@app.route('/qr/<int:id>')
@login_required
def get_qr(id):
    url = f"https://{DOMINIO_REAL}/smart/{id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/smart/<int:id>')
@login_required
def smart_router(id):
    p = Piloto.query.get_or_404(id)
    role = current_user.role
    if role == 'admin': return redirect(url_for('admin_procesar_carga', id=id))
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
        registrar_movimiento("CONSUMO", item, 1, piloto_dni=p.dni, detalle=f"Retiro en puesto: {current_user.role}")
        db.session.commit()
        flash(f"Retiro exitoso de {ITEMS_CONFIG[item]}", "success")
    else:
        flash("Sin saldo o sin stock disponible", "danger")
    return redirect(url_for('smart_router', id=id))

@app.route('/admin/exportar')
@login_required
def admin_exportar():
    if current_user.role != 'admin': return "Acceso Denegado", 403
    
    # 1. Preparar la hoja de Saldos (Resumen de Pilotos)
    pilotos = Piloto.query.all()
    data_saldos = []
    for p in pilotos:
        data_saldos.append({
            'N_Kart': p.numero_piloto, 'Nombre': p.nombre, 'DNI': p.dni, 'Equipo': p.equipo,
            'Nafta': p.nafta_20l, 'MG_Rojas': p.neumaticos_mg_rojas, 'MG_Cadete': p.neumaticos_mg_cadete,
            'Lluvia': p.neumaticos_lluvia, 'Sensor': p.sensor, 'Pista': p.derecho_pista
        })
    df_saldos = pd.DataFrame(data_saldos)

    # 2. Preparar la hoja de Movimientos (Auditoría)
    # Ordenamos por fecha descendente (los más nuevos primero)
    movimientos = Movimiento.query.order_by(Movimiento.fecha.desc()).all()
    data_movs = []
    for m in movimientos:
        data_movs.append({
            'Fecha': m.fecha.strftime('%d/%m/%Y %H:%M:%S') if m.fecha else '',
            'Tipo de Acción': m.tipo,
            'Usuario (Operario)': m.usuario,
            'Item': ITEMS_CONFIG.get(m.item, m.item), # Muestra el nombre lindo si existe
            'Cantidad': m.cantidad,
            'DNI Piloto': m.piloto_dni or 'N/A',
            'Detalle Extra': m.detalle or ''
        })
    df_movs = pd.DataFrame(data_movs)

    # 3. Generar el archivo Excel con múltiples hojas
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Guardar la hoja 1
        df_saldos.to_excel(writer, index=False, sheet_name='Saldos IAME')
        
        # Guardar la hoja 2 (si no hay movimientos, creamos una vacía con los títulos)
        if not df_movs.empty:
            df_movs.to_excel(writer, index=False, sheet_name='Auditoría Movimientos')
        else:
            pd.DataFrame(columns=['Fecha', 'Tipo de Acción', 'Usuario (Operario)', 'Item', 'Cantidad', 'DNI Piloto', 'Detalle Extra']).to_excel(writer, index=False, sheet_name='Auditoría Movimientos')
            
    output.seek(0)
    
    # Descargar con la fecha de hoy en el nombre del archivo
    nombre_archivo = f"reporte_iame_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(output, download_name=nombre_archivo, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
