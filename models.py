from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='operario') # 'admin' o 'operario'

class Stock(db.Model):
    __tablename__ = 'stock'
    item_key = db.Column(db.String(50), primary_key=True) # ej: 'nafta', 'neumatico_rojo'
    nombre_legible = db.Column(db.String(100))
    cantidad = db.Column(db.Integer, default=0)

class Piloto(db.Model):
    __tablename__ = 'piloto'
    # Primary Key manual: El número de kart
    numero_piloto = db.Column(db.Integer, primary_key=True, autoincrement=False)
    nombre = db.Column(db.String(100), nullable=False)
    dni = db.Column(db.String(20))
    equipo = db.Column(db.String(100))
    # Saldos de insumos
    nafta_20l = db.Column(db.Integer, default=0)
    neumaticos_mg_rojas = db.Column(db.Integer, default=0)
    neumaticos_mg_cadete = db.Column(db.Integer, default=0)
    neumaticos_lluvia = db.Column(db.Integer, default=0)
    sensor = db.Column(db.Integer, default=0)
    derecho_pista = db.Column(db.String(20), default="Debe")
    
    # Relación para auditoría
    movimientos = db.relationship('Movimiento', backref='piloto_rel', lazy=True)

class Movimiento(db.Model):
    __tablename__ = 'movimientos'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    tipo = db.Column(db.String(50)) # 'CARGA' (Admin) o 'RETIRO' (Operario)
    item_key = db.Column(db.String(50))
    cantidad = db.Column(db.Integer)
    piloto_id = db.Column(db.Integer, db.ForeignKey('piloto.numero_piloto'))
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'))    usuario = db.Column(db.String(50))
    piloto_dni = db.Column(db.String(20), nullable=True)
    item = db.Column(db.String(50))
    cantidad = db.Column(db.Integer)
    detalle = db.Column(db.String(200))
