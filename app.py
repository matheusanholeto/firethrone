from flask import Flask, jsonify, request, session, g
from flask_cors import CORS
import sqlite3, hashlib, os, json
from datetime import datetime, timedelta
import random

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'firethrone-secret-2024')
CORS(app, supports_credentials=True, origins='*')

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firethrone.db')

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    schema = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    db = get_db()
    with open(schema, 'r') as f:
        db.executescript(f.read())
    db.commit()
    db.close()

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def row_to_dict(row):
    return dict(row) if row else None

# ── AUTH ──────────────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username','').strip()
    email = data.get('email','').strip()
    password = data.get('password','')
    if not username or not email or not password:
        return jsonify({'error': 'Preencha todos os campos'}), 400
    db = get_db()
    existing = db.execute('SELECT id FROM users WHERE username=? OR email=?', (username, email)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': 'Usuário ou email já cadastrado'}), 409
    db.execute('INSERT INTO users (username, email, password_hash) VALUES (?,?,?)',
               (username, email, hash_password(password)))
    db.commit()
    user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    db.close()
    session['user_id'] = user['id']
    return jsonify({'message': 'Cadastro realizado!', 'user': {'id': user['id'], 'username': user['username'], 'role': user['role'], 'balance': user['balance']}})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    identifier = data.get('identifier','').strip()
    password = data.get('password','')
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE (username=? OR email=?) AND password_hash=?',
                      (identifier, identifier, hash_password(password))).fetchone()
    db.close()
    if not user:
        return jsonify({'error': 'Credenciais inválidas'}), 401
    session['user_id'] = user['id']
    return jsonify({'user': {'id': user['id'], 'username': user['username'], 'role': user['role'], 'balance': user['balance'], 'avatar': user['avatar']}})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logout realizado'})

@app.route('/api/auth/me')
def me():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'user': None})
    db = get_db()
    user = db.execute('SELECT id, username, role, balance, avatar, email, created_at FROM users WHERE id=?', (uid,)).fetchone()
    db.close()
    return jsonify({'user': row_to_dict(user)})

# ── SERVERS ───────────────────────────────────────────────
@app.route('/api/servers')
def get_servers():
    db = get_db()
    servers = db.execute('SELECT * FROM servers').fetchall()
    # Simulate live player count fluctuation
    result = []
    for s in servers:
        srv = dict(s)
        if srv['status'] == 'online':
            srv['current_players'] = max(0, srv['current_players'] + random.randint(-5, 5))
            srv['current_players'] = min(srv['current_players'], srv['max_players'])
        result.append(srv)
    db.close()
    return jsonify({'servers': result})

@app.route('/api/servers/<int:sid>')
def get_server(sid):
    db = get_db()
    server = db.execute('SELECT * FROM servers WHERE id=?', (sid,)).fetchone()
    db.close()
    if not server:
        return jsonify({'error': 'Servidor não encontrado'}), 404
    return jsonify({'server': row_to_dict(server)})

# ── STORE ─────────────────────────────────────────────────
@app.route('/api/store')
def get_store():
    db = get_db()
    items = db.execute('SELECT * FROM store_items WHERE active=1 ORDER BY featured DESC, category, price').fetchall()
    db.close()
    return jsonify({'items': [dict(i) for i in items]})

@app.route('/api/sync/kits', methods=['POST'])
def sync_kits():
    # Chave secreta para autenticar o servidor Rust
    secret = request.headers.get('X-Sync-Secret', '')
    if secret != 'firethrone-sync-secret':
        return jsonify({'error': 'Não autorizado'}), 401

    data = request.json
    if not data or 'kits' not in data:
        return jsonify({'error': 'Dados inválidos'}), 400

    kits = data['kits']
    db = get_db()

    # Desativa todos os itens VIP atuais
    db.execute("UPDATE store_items SET active=0 WHERE category='vip'")

    for kit in kits:
        name = kit.get('Name', '')
        description = kit.get('Description', '') or f'Kit VIP {name}'
        price = kit.get('Cost', 0)
        image = kit.get('KitImage', '')
        is_hidden = kit.get('IsHidden', False)

        if is_hidden or not name:
            continue

        # Verifica se já existe
        existing = db.execute("SELECT id FROM store_items WHERE name=? AND category='vip'", (name,)).fetchone()
        if existing:
            db.execute("""UPDATE store_items SET description=?, price=?, image=?, active=1
                          WHERE name=? AND category='vip'""",
                       (description, price, image, name))
        else:
            db.execute("""INSERT INTO store_items (name, description, category, price, image, active)
                          VALUES (?,?,?,?,?,1)""",
                       (name, description, 'vip', price, image))

    db.commit()
    db.close()
    return jsonify({'message': f'{len(kits)} kits sincronizados com sucesso!'})

@app.route('/api/store/buy', methods=['POST'])
def buy_item():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Faça login para comprar'}), 401
    data = request.json
    item_id = data.get('item_id')
    db = get_db()
    item = db.execute('SELECT * FROM store_items WHERE id=? AND active=1', (item_id,)).fetchone()
    user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not item:
        db.close()
        return jsonify({'error': 'Item não encontrado'}), 404
    if user['balance'] < item['price']:
        db.close()
        return jsonify({'error': 'Saldo insuficiente'}), 400
    db.execute('UPDATE users SET balance=balance-? WHERE id=?', (item['price'], uid))
    db.execute('INSERT INTO purchases (user_id, item_id, amount_paid, status) VALUES (?,?,?,?)',
               (uid, item_id, item['price'], 'completed'))
    db.commit()
    new_balance = db.execute('SELECT balance FROM users WHERE id=?', (uid,)).fetchone()['balance']
    db.close()
    return jsonify({'message': f'"{item["name"]}" comprado com sucesso!', 'new_balance': new_balance})

# ── LEADERBOARD ───────────────────────────────────────────
@app.route('/api/leaderboard')
def get_leaderboard():
    server_id = request.args.get('server_id', 1)
    sort_by = request.args.get('sort', 'kills')
    allowed = ['kills', 'deaths', 'hours_played', 'resources_gathered', 'raids_won']
    if sort_by not in allowed:
        sort_by = 'kills'
    db = get_db()
    rows = db.execute(f'''
        SELECT u.username, u.avatar, u.role, l.*
        FROM leaderboard l
        JOIN users u ON l.user_id = u.id
        WHERE l.server_id=?
        ORDER BY l.{sort_by} DESC
        LIMIT 50
    ''', (server_id,)).fetchall()
    db.close()
    return jsonify({'leaderboard': [dict(r) for r in rows]})

# ── NEWS ──────────────────────────────────────────────────
@app.route('/api/news')
def get_news():
    db = get_db()
    news = db.execute('''
        SELECT n.*, u.username as author_name
        FROM news n JOIN users u ON n.author_id = u.id
        WHERE n.published=1 ORDER BY n.created_at DESC LIMIT 10
    ''').fetchall()
    db.close()
    return jsonify({'news': [dict(n) for n in news]})

# ── ADMIN ─────────────────────────────────────────────────
def require_admin():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=? AND role=?', (uid, 'admin')).fetchone()
    db.close()
    return user

@app.route('/api/admin/stats')
def admin_stats():
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    db = get_db()
    total_users = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
    total_purchases = db.execute('SELECT COUNT(*) as c FROM purchases WHERE status="completed"').fetchone()['c']
    total_revenue = db.execute('SELECT COALESCE(SUM(amount_paid),0) as s FROM purchases WHERE status="completed"').fetchone()['s']
    online_servers = db.execute('SELECT COUNT(*) as c FROM servers WHERE status="online"').fetchone()['c']
    total_players = db.execute('SELECT COALESCE(SUM(current_players),0) as s FROM servers WHERE status="online"').fetchone()['s']
    recent_users = db.execute('SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC LIMIT 10').fetchall()
    db.close()
    return jsonify({
        'stats': {
            'total_users': total_users,
            'total_purchases': total_purchases,
            'total_revenue': total_revenue,
            'online_servers': online_servers,
            'total_players': total_players
        },
        'recent_users': [dict(u) for u in recent_users]
    })

@app.route('/api/admin/servers', methods=['GET', 'POST', 'PUT'])
def admin_servers():
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    db = get_db()
    if request.method == 'GET':
        servers = db.execute('SELECT * FROM servers').fetchall()
        db.close()
        return jsonify({'servers': [dict(s) for s in servers]})
    if request.method == 'POST':
        d = request.json
        db.execute('INSERT INTO servers (name, ip, port, map, max_players, status, wipe_schedule, modded, description) VALUES (?,?,?,?,?,?,?,?,?)',
                   (d['name'], d['ip'], d['port'], d.get('map','Procedural Map'), d.get('max_players',200),
                    d.get('status','online'), d.get('wipe_schedule','Monthly'), d.get('modded',0), d.get('description','')))
        db.commit()
        db.close()
        return jsonify({'message': 'Servidor criado!'})
    if request.method == 'PUT':
        d = request.json
        db.execute('UPDATE servers SET name=?, status=?, current_players=? WHERE id=?',
                   (d['name'], d['status'], d['current_players'], d['id']))
        db.commit()
        db.close()
        return jsonify({'message': 'Servidor atualizado!'})

@app.route('/api/admin/users')
def admin_users():
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    db = get_db()
    users = db.execute('SELECT id, username, email, role, balance, created_at, last_seen FROM users ORDER BY created_at DESC').fetchall()
    db.close()
    return jsonify({'users': [dict(u) for u in users]})

@app.route('/api/admin/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    d = request.json
    db = get_db()
    db.execute('UPDATE users SET role=?, balance=? WHERE id=?', (d['role'], d['balance'], uid))
    db.commit()
    db.close()
    return jsonify({'message': 'Usuário atualizado!'})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
