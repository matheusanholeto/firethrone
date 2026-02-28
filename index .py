"""
fix.py — Redefine a senha do admin no MongoDB (FireThrone)

Uso:
  MONGO_URI=mongodb+srv://... python fix.py
  ou
  python fix.py  (usa localhost por padrão)

Variáveis de ambiente opcionais:
  MONGO_URI      — URI do MongoDB (padrão: localhost)
  ADMIN_USERNAME — Username do admin (padrão: Admin)
  NOVA_SENHA     — Nova senha (padrão: admin123)
"""
import os
import bcrypt
from pymongo import MongoClient

MONGO_URI      = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/firethrone')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'Admin')
NOVA_SENHA     = os.environ.get('NOVA_SENHA', 'admin123')

client = MongoClient(MONGO_URI)
db     = client.get_database()

nova_hash = bcrypt.hashpw(NOVA_SENHA.encode(), bcrypt.gensalt()).decode()

resultado = db['users'].update_one(
    {'username': ADMIN_USERNAME},
    {'$set': {'password_hash': nova_hash}}
)

if resultado.matched_count:
    print(f'[OK] Senha do usuário "{ADMIN_USERNAME}" atualizada com sucesso!')
    print(f'     Nova senha: {NOVA_SENHA}')
else:
    print(f'[ERRO] Usuário "{ADMIN_USERNAME}" não encontrado no banco.')
    print('       Verifique o ADMIN_USERNAME e a MONGO_URI.')
