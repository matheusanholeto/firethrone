from flask import Flask, jsonify, request, session
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
import hashlib, os, random
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'firethrone-secret-2024')
CORS(app, supports_credentials=True, origins='*')

# ── MONGODB ───────────────────────────────────────────────
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/firethrone')
client = MongoClient(MONGO_URI)
db = client.get_database()

users_col       = db['users']
servers_col     = db['servers']
store_col       = db['store_items']
purchases_col   = db['purchases']
leaderboard_col = db['leaderboard']
news_col        = db['news']

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def fix_id(doc):
    if doc and '_id' in doc:
        doc['id'] = str(doc.pop('_id'))
    return doc

def seed_db():
    if users_col.count_documents({}) > 0:
        return
    admin_id = users_col.insert_one({
        'username': 'Admin', 'email': 'admin@firethrone.gg',
        'password_hash': hash_password('admin123'),
        'role': 'admin', 'balance': 99999,
        'avatar': '/static/default_avatar.png',
        'created_at': datetime.utcnow()
    }).inserted_id
    servers_col.insert_many([
        {'name': 'FireThrone - Main', 'ip': '45.33.32.156', 'port': 28015, 'map': 'Procedural Map', 'max_players': 200, 'current_players': 87, 'status': 'online', 'wipe_schedule': 'Monthly', 'modded': False, 'description': 'Servidor principal vanilla.', 'tags': ['vanilla','pvp','monthly']},
        {'name': 'FireThrone - 2x Solo/Duo', 'ip': '45.33.32.157', 'port': 28015, 'map': 'Barren', 'max_players': 150, 'current_players': 63, 'status': 'online', 'wipe_schedule': 'Bi-Weekly', 'modded': True, 'description': 'Servidor 2x para solo e duo.', 'tags': ['2x','solo','duo']},
        {'name': 'FireThrone - 5x Build', 'ip': '45.33.32.158', 'port': 28015, 'map': 'Hapis Island', 'max_players': 100, 'current_players': 41, 'status': 'online', 'wipe_schedule': 'Weekly', 'modded': True, 'description': 'Modo criativo com 5x de recursos.', 'tags': ['5x','build']},
        {'name': 'FireThrone - Battlefield', 'ip': '45.33.32.159', 'port': 28015, 'map': 'Procedural Map', 'max_players': 300, 'current_players': 0, 'status': 'restarting', 'wipe_schedule': 'Weekly', 'modded': True, 'description': 'PvP puro, sem base building.', 'tags': ['pvp','arena']}
    ])
    store_col.insert_many([
        {'name': 'VIP Bronze',   'description': 'Acesso ao kit bronze, prioridade na fila e tag exclusiva.', 'category': 'vip', 'price': 1500, 'featured': False, 'active': True},
        {'name': 'VIP Prata',    'description': 'Tudo do Bronze + kit prata, home duplo e canal VIP.',       'category': 'vip', 'price': 2900, 'featured': False, 'active': True},
        {'name': 'VIP Ouro',     'description': 'Tudo do Prata + kit ouro, /tpr ilimitado e skin exclusiva.','category': 'vip', 'price': 4900, 'featured': True,  'active': True},
        {'name': 'VIP Diamante', 'description': 'Pacote completo. Todos os benefícios + suporte prioritário.','category': 'vip', 'price': 8900, 'featured': True,  'active': True},
    ])
    news_col.insert_many([
        {'title': 'Wipe Mensal — 1° de Março', 'content': 'O wipe mensal acontecerá no dia 1° de Março às 15h (BRT).', 'author_name': 'Admin', 'category': 'wipe', 'published': True, 'created_at': datetime.utcnow()},
        {'title': 'Nova Atualização: Battlefield Server', 'content': 'O servidor Battlefield foi completamente reformulado.', 'author_name': 'Admin', 'category': 'update', 'published': True, 'created_at': datetime.utcnow()},
        {'title': 'Evento: Raid Weekend', 'content': 'Este fim de semana os custos de explosivos foram reduzidos em 50%.', 'author_name': 'Admin', 'category': 'event', 'published': True, 'created_at': datetime.utcnow()},
    ])
    print('Banco populado com dados iniciais!')

# ── AUTH ──────────────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username','').strip()
    email    = data.get('email','').strip()
    password = data.get('password','')
    if not username or not email or not password:
        return jsonify({'error': 'Preencha todos os campos'}), 400
    if users_col.find_one({'$or': [{'username': username}, {'email': email}]}):
        return jsonify({'error': 'Usuário ou email já cadastrado'}), 409
    result = users_col.insert_one({
        'username': username, 'email': email,
        'password_hash': hash_password(password),
        'role': 'player', 'balance': 0,
        'avatar': '/static/default_avatar.png',
        'created_at': datetime.utcnow()
    })
    session['user_id'] = str(result.inserted_id)
    return jsonify({'message': 'Cadastro realizado!', 'user': {'id': str(result.inserted_id), 'username': username, 'role': 'player', 'balance': 0}})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data       = request.json
    identifier = data.get('identifier','').strip()
    password   = data.get('password','')
    user = users_col.find_one({
        '$or': [{'username': identifier}, {'email': identifier}],
        'password_hash': hash_password(password)
    })
    if not user:
        return jsonify({'error': 'Credenciais inválidas'}), 401
    session['user_id'] = str(user['_id'])
    return jsonify({'user': {'id': str(user['_id']), 'username': user['username'], 'role': user['role'], 'balance': user['balance'], 'avatar': user.get('avatar','')}})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logout realizado'})

@app.route('/api/auth/me')
def me():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'user': None})
    user = users_col.find_one({'_id': ObjectId(uid)}, {'password_hash': 0})
    return jsonify({'user': fix_id(user)})

# ── SERVERS ───────────────────────────────────────────────
@app.route('/api/servers')
def get_servers():
    servers = list(servers_col.find())
    result = []
    for s in servers:
        s = fix_id(s)
        if s['status'] == 'online':
            s['current_players'] = max(0, min(s['current_players'] + random.randint(-5,5), s['max_players']))
        result.append(s)
    return jsonify({'servers': result})

# ── STORE ─────────────────────────────────────────────────
@app.route('/api/store')
def get_store():
    items = list(store_col.find({'active': True}).sort([('featured', -1), ('price', 1)]))
    return jsonify({'items': [fix_id(i) for i in items]})

@app.route('/api/sync/kits', methods=['POST'])
def sync_kits():
    secret = request.headers.get('X-Sync-Secret', '')
    if secret != os.environ.get('SYNC_SECRET', 'firethrone-sync-secret'):
        return jsonify({'error': 'Não autorizado'}), 401
    data = request.json
    if not data or 'kits' not in data:
        return jsonify({'error': 'Dados inválidos'}), 400
    kits = data['kits']
    store_col.update_many({'category': 'vip'}, {'$set': {'active': False}})
    for kit in kits:
        name   = kit.get('Name', '')
        desc   = kit.get('Description', '') or f'Kit VIP {name}'
        price  = kit.get('Cost', 0)
        image  = kit.get('KitImage', '')
        hidden = kit.get('IsHidden', False)
        if hidden or not name:
            continue
        store_col.update_one(
            {'name': name, 'category': 'vip'},
            {'$set': {'description': desc, 'price': price, 'image': image, 'active': True, 'category': 'vip', 'featured': False}},
            upsert=True
        )
    return jsonify({'message': f'{len(kits)} kits sincronizados com sucesso!'})

@app.route('/api/store/buy', methods=['POST'])
def buy_item():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Faça login para comprar'}), 401
    data    = request.json
    item_id = data.get('item_id')
    item    = store_col.find_one({'_id': ObjectId(item_id), 'active': True})
    user    = users_col.find_one({'_id': ObjectId(uid)})
    if not item:
        return jsonify({'error': 'Item não encontrado'}), 404
    if user['balance'] < item['price']:
        return jsonify({'error': 'Saldo insuficiente'}), 400
    users_col.update_one({'_id': ObjectId(uid)}, {'$inc': {'balance': -item['price']}})
    purchases_col.insert_one({'user_id': uid, 'item_id': item_id, 'amount_paid': item['price'], 'status': 'completed', 'created_at': datetime.utcnow()})
    new_balance = users_col.find_one({'_id': ObjectId(uid)})['balance']
    return jsonify({'message': f'"{item["name"]}" comprado com sucesso!', 'new_balance': new_balance})

# ── LEADERBOARD ───────────────────────────────────────────
@app.route('/api/leaderboard')
def get_leaderboard():
    sort_by = request.args.get('sort', 'kills')
    if sort_by not in ['kills','deaths','hours_played','resources_gathered','raids_won']:
        sort_by = 'kills'
    rows = list(leaderboard_col.find().sort(sort_by, -1).limit(50))
    result = []
    for r in rows:
        try:
            user = users_col.find_one({'_id': ObjectId(r['user_id'])}, {'username':1,'avatar':1,'role':1})
            if user:
                r['username'] = user['username']
                r['avatar']   = user.get('avatar','')
                r['role']     = user.get('role','player')
        except:
            pass
        result.append(fix_id(r))
    return jsonify({'leaderboard': result})

# ── NEWS ──────────────────────────────────────────────────
@app.route('/api/news')
def get_news():
    news = list(news_col.find({'published': True}).sort('created_at', -1).limit(10))
    return jsonify({'news': [fix_id(n) for n in news]})

# ── ADMIN ─────────────────────────────────────────────────
def require_admin():
    uid = session.get('user_id')
    if not uid:
        return None
    return users_col.find_one({'_id': ObjectId(uid), 'role': 'admin'})

@app.route('/api/admin/stats')
def admin_stats():
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    total_users     = users_col.count_documents({})
    total_purchases = purchases_col.count_documents({'status': 'completed'})
    revenue_agg     = list(purchases_col.aggregate([{'$match': {'status':'completed'}}, {'$group': {'_id': None, 'total': {'$sum': '$amount_paid'}}}]))
    total_revenue   = revenue_agg[0]['total'] if revenue_agg else 0
    online_servers  = servers_col.count_documents({'status': 'online'})
    players_agg     = list(servers_col.aggregate([{'$match': {'status':'online'}}, {'$group': {'_id': None, 'total': {'$sum': '$current_players'}}}]))
    total_players   = players_agg[0]['total'] if players_agg else 0
    recent_users    = list(users_col.find({}, {'password_hash': 0}).sort('created_at', -1).limit(10))
    return jsonify({
        'stats': {'total_users': total_users, 'total_purchases': total_purchases, 'total_revenue': total_revenue, 'online_servers': online_servers, 'total_players': total_players},
        'recent_users': [fix_id(u) for u in recent_users]
    })

@app.route('/api/admin/users')
def admin_users():
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    users = list(users_col.find({}, {'password_hash': 0}).sort('created_at', -1))
    return jsonify({'users': [fix_id(u) for u in users]})

@app.route('/api/admin/users/<uid>', methods=['PUT'])
def update_user(uid):
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    d = request.json
    users_col.update_one({'_id': ObjectId(uid)}, {'$set': {'role': d['role'], 'balance': d['balance']}})
    return jsonify({'message': 'Usuário atualizado!'})

@app.route('/api/admin/servers', methods=['GET', 'POST', 'PUT'])
def admin_servers():
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    if request.method == 'GET':
        servers = list(servers_col.find())
        return jsonify({'servers': [fix_id(s) for s in servers]})
    if request.method == 'POST':
        d = request.json
        servers_col.insert_one({'name': d['name'], 'ip': d['ip'], 'port': d['port'], 'map': d.get('map','Procedural Map'), 'max_players': d.get('max_players',200), 'current_players': 0, 'status': d.get('status','online'), 'wipe_schedule': d.get('wipe_schedule','Monthly'), 'modded': d.get('modded',False), 'description': d.get('description',''), 'tags': []})
        return jsonify({'message': 'Servidor criado!'})
    if request.method == 'PUT':
        d = request.json
        servers_col.update_one({'_id': ObjectId(d['id'])}, {'$set': {'name': d['name'], 'status': d['status'], 'current_players': d['current_players']}})
        return jsonify({'message': 'Servidor atualizado!'})

if __name__ == '__main__':
    seed_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
