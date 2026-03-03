from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# Inicializamos la base de datos aquí
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(255))
    role = db.Column(db.String(20))

class Stock(db.Model):
    item_key = db.Column(db.String(50), primary_key=True)
    nombre_legible = db.Column(db.String(100))
    cantidad = db.Column(db.Integer, default=0)

class Piloto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_piloto = db.Column(db.Integer, unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    dni = db.Column(db.String(20), nullable=False)
    equipo = db.Column(db.String(100), nullable=False)
    nafta_20l = db.Column(db.Integer, default=0)
    neumaticos_mg_rojas = db.Column(db.Integer, default=0)
    neumaticos_mg_cadete = db.Column(db.Integer, default=0)
    neumaticos_lluvia = db.Column(db.Integer, default=0)
    sensor = db.Column(db.Integer, default=0)
    derecho_pista = db.Column(db.String(20), default="Debe")

class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    tipo = db.Column(db.String(20))
    usuario = db.Column(db.String(50))
    piloto_dni = db.Column(db.String(20), nullable=True)
    item = db.Column(db.String(50))
    cantidad = db.Column(db.Integer)
    detalle = db.Column(db.String(200))