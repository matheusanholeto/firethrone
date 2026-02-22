import sqlite3, hashlib

senha = hashlib.sha256('admin123'.encode()).hexdigest()
db = sqlite3.connect('firethrone.db')
db.execute(f"UPDATE users SET password_hash = '{senha}' WHERE username = 'Admin'")
db.commit()
db.close()
print('Corrigido!')
