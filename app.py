from flask import Flask, jsonify, request, session, send_from_directory, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
import hashlib, os, random, secrets, smtplib, re, json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from urllib.parse import urlencode, parse_qs
import urllib.request

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
tickets_col     = db['tickets']
tokens_col      = db['email_tokens']   # verificação de email

# ── EMAIL HELPER ──────────────────────────────────────────
SITE_URL    = os.environ.get('SITE_URL', 'https://firethrone-server.onrender.com')
EMAIL_HOST  = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT  = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER  = os.environ.get('EMAIL_USER', '')
EMAIL_PASS  = os.environ.get('EMAIL_PASS', '')
EMAIL_FROM  = os.environ.get('EMAIL_FROM', EMAIL_USER)

def send_email(to, subject, html_body):
    if not EMAIL_USER or not EMAIL_PASS:
        print(f'[EMAIL SKIP] Para: {to} | {subject}')
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f'FireThrone <{EMAIL_FROM}>'
        msg['To']      = to
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, to, msg.as_string())
    except Exception as e:
        print(f'[EMAIL ERROR] {e}')

def send_verification_email(to_email, username, token):
    link = f'{SITE_URL}/api/auth/verify-email?token={token}'
    html = f'''
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0D0B09;color:#D4B896;border:1px solid #3D2E1E;border-radius:8px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#C8440A,#8B1A1A);padding:24px;text-align:center">
        <h1 style="color:#fff;font-size:28px;margin:0;letter-spacing:4px">🔥 FIRETHRONE</h1>
      </div>
      <div style="padding:32px">
        <h2 style="color:#fff;margin-top:0">Olá, {username}!</h2>
        <p>Obrigado por se cadastrar no FireThrone Network. Clique no botão abaixo para confirmar seu email:</p>
        <div style="text-align:center;margin:28px 0">
          <a href="{link}" style="background:linear-gradient(135deg,#C8440A,#8B1A1A);color:#fff;padding:14px 32px;border-radius:4px;text-decoration:none;font-weight:bold;font-size:16px;letter-spacing:1px">
            ✅ CONFIRMAR EMAIL
          </a>
        </div>
        <p style="font-size:13px;color:#7A6550">Este link expira em 24 horas. Se você não criou uma conta, ignore este email.</p>
      </div>
    </div>'''
    send_email(to_email, '🔥 FireThrone — Confirme seu email', html)

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

# ── FRONT-END ─────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/health')
@app.route('/ping')
def health():
    return jsonify({'status': 'ok'}), 200

# ── AUTH ──────────────────────────────────────────────────
def is_valid_email(email):
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))

@app.route('/api/auth/check-email')
def check_email():
    email = request.args.get('email','').strip().lower()
    exists = bool(users_col.find_one({'email': email}))
    return jsonify({'exists': exists})

@app.route('/api/auth/register', methods=['POST'])
def register():
    data      = request.json or {}
    firstname = data.get('firstname','').strip()
    lastname  = data.get('lastname','').strip()
    email     = data.get('email','').strip().lower()
    password  = data.get('password','')

    if not firstname or not lastname or not email or not password:
        return jsonify({'error': 'Preencha todos os campos'}), 400
    if not is_valid_email(email):
        return jsonify({'error': 'Email inválido'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Senha deve ter no mínimo 6 caracteres'}), 400
    if users_col.find_one({'email': email}):
        return jsonify({'error': 'Email já cadastrado'}), 409

    username = f'{firstname} {lastname}'
    result = users_col.insert_one({
        'firstname': firstname, 'lastname': lastname,
        'username': username, 'email': email,
        'password_hash': hash_password(password),
        'role': 'player', 'balance': 0,
        'avatar': '/static/default_avatar.png',
        'email_verified': False,
        'created_at': datetime.utcnow()
    })
    uid = str(result.inserted_id)

    # Gerar token de verificação
    token = secrets.token_urlsafe(32)
    tokens_col.insert_one({
        'user_id': uid, 'token': token, 'type': 'email_verify',
        'expires_at': datetime.utcnow() + timedelta(hours=24),
        'used': False
    })
    send_verification_email(email, firstname, token)

    return jsonify({'message': 'Conta criada! Verifique seu email para ativar.'}), 201

@app.route('/api/auth/verify-email')
def verify_email():
    token = request.args.get('token','')
    rec   = tokens_col.find_one({'token': token, 'type': 'email_verify', 'used': False})
    if not rec:
        return redirect(f'/?already_verified=1')
    if rec['expires_at'] < datetime.utcnow():
        return redirect(f'/?steam_error=token_expired')
    tokens_col.update_one({'_id': rec['_id']}, {'$set': {'used': True}})
    users_col.update_one({'_id': ObjectId(rec['user_id'])}, {'$set': {'email_verified': True}})
    return redirect(f'/?email_verified=1')

@app.route('/api/auth/login', methods=['POST'])
def login():
    data       = request.json or {}
    identifier = data.get('identifier','').strip().lower()
    password   = data.get('password','')
    user = users_col.find_one({
        '$or': [{'email': identifier}, {'username': identifier}],
        'password_hash': hash_password(password)
    })
    if not user:
        return jsonify({'error': 'Credenciais inválidas'}), 401
    if not user.get('email_verified', False):
        return jsonify({'error': 'Confirme seu email antes de entrar.', 'need_verify': True}), 403
    session['user_id'] = str(user['_id'])
    return jsonify({'user': {
        'id': str(user['_id']), 'username': user['username'],
        'role': user['role'], 'balance': user['balance'],
        'avatar': user.get('avatar','')
    }})

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

# ── STEAM OPENID ──────────────────────────────────────────
STEAM_OPENID = 'https://steamcommunity.com/openid/login'
STEAM_API_KEY = os.environ.get('STEAM_API_KEY', '')

@app.route('/api/auth/steam')
def steam_login():
    callback = f'{SITE_URL}/api/auth/steam/callback'
    params = {
        'openid.ns':         'http://specs.openid.net/auth/2.0',
        'openid.mode':       'checkid_setup',
        'openid.return_to':  callback,
        'openid.realm':      SITE_URL,
        'openid.identity':   'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
    }
    return redirect(f'{STEAM_OPENID}?{urlencode(params)}')

@app.route('/api/auth/steam/callback')
def steam_callback():
    params = dict(request.args)
    params['openid.mode'] = 'check_authentication'
    try:
        data = urlencode({k: v[0] if isinstance(v, list) else v for k, v in params.items()}).encode()
        req  = urllib.request.Request(STEAM_OPENID, data=data)
        resp = urllib.request.urlopen(req, timeout=10).read().decode()
        if 'is_valid:true' not in resp:
            return redirect('/?steam_error=invalid')
    except Exception as e:
        return redirect(f'/?steam_error=1')

    # Extrair Steam ID da URL claimed_id
    claimed = request.args.get('openid.claimed_id', '')
    steam_id = claimed.split('/')[-1]
    if not steam_id.isdigit():
        return redirect('/?steam_error=id')

    # Buscar perfil Steam
    username = f'Steam_{steam_id[-6:]}'
    avatar   = ''
    if STEAM_API_KEY:
        try:
            url  = f'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id}'
            data = json.loads(urllib.request.urlopen(url, timeout=8).read())
            p    = data['response']['players'][0]
            username = p.get('personaname', username)
            avatar   = p.get('avatarfull', '')
        except:
            pass

    # Criar ou atualizar usuário
    user = users_col.find_one({'steam_id': steam_id})
    if not user:
        uid = users_col.insert_one({
            'username': username, 'steam_id': steam_id,
            'email': '', 'password_hash': '',
            'role': 'player', 'balance': 0,
            'avatar': avatar, 'email_verified': True,
            'created_at': datetime.utcnow()
        }).inserted_id
    else:
        uid = user['_id']
        users_col.update_one({'_id': uid}, {'$set': {'username': username, 'avatar': avatar}})

    session['user_id'] = str(uid)
    return redirect('/?steam_ok=1')

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
    secret = request.headers.get('X-Sync-Secret', '') or request.args.get('secret', '')
    if secret != os.environ.get('SYNC_SECRET', 'firethrone-sync-secret'):
        return jsonify({'error': 'Não autorizado'}), 401
    data = request.json
    if not data or 'kits' not in data:
        return jsonify({'error': 'Dados inválidos'}), 400
    kits   = data['kits']
    append = data.get('append', False)
    # Só desativa todos no primeiro chunk (append=False)
    if not append:
        store_col.update_many({'category': 'vip'}, {'$set': {'active': False}})
    for kit in kits:
        name   = kit.get('Name', '')
        desc   = kit.get('Description', '') or f'Kit VIP {name}'
        price  = kit.get('Cost', 0)
        image  = kit.get('KitImage', '')
        items  = kit.get('Items', [])
        hidden = kit.get('IsHidden', False)
        if hidden or not name:
            continue
        # Preserva imagem e preço existentes se não vierem no sync
        existing = store_col.find_one({'name': name, 'category': 'vip'}) or {}
        final_image = image if image else existing.get('image', '')
        final_price = existing.get('price', price)
        store_col.update_one(
            {'name': name, 'category': 'vip'},
            {'$set': {'description': desc, 'price': final_price, 'image': final_image, 'active': True, 'category': 'vip', 'featured': False, 'items': items}},
            upsert=True
        )
    return jsonify({'message': f'{len(kits)} kits sincronizados com sucesso!'})


@app.route('/api/sync/kits/items', methods=['POST'])
def sync_kit_items():
    secret = request.headers.get('X-Sync-Secret', '') or request.args.get('secret', '')
    if secret != os.environ.get('SYNC_SECRET', 'firethrone-sync-secret'):
        return jsonify({'error': 'Não autorizado'}), 401
    kit_name = request.args.get('kit', '')
    if not kit_name:
        return jsonify({'error': 'Kit não especificado'}), 400
    data = request.json
    if not data or 'items' not in data:
        return jsonify({'error': 'Dados inválidos'}), 400
    store_col.update_one(
        {'name': kit_name, 'category': 'vip'},
        {'$set': {'items': data['items']}}
    )
    return jsonify({'message': f'Itens do kit {kit_name} atualizados!'})


@app.route('/api/sync/kits/items/batch', methods=['POST'])
def sync_kit_items_batch():
    secret = request.headers.get('X-Sync-Secret', '') or request.args.get('secret', '')
    if secret != os.environ.get('SYNC_SECRET', 'firethrone-sync-secret'):
        return jsonify({'error': 'Não autorizado'}), 401
    data = request.json
    if not data or 'items' not in data:
        return jsonify({'error': 'Dados inválidos'}), 400
    for item in data['items']:
        kit_name  = item.get('kit', '')
        if not kit_name: continue
        shortname = item.get('shortname', '')
        name      = item.get('name', shortname)
        amount    = item.get('amount', 1)
        image     = item.get('image', '')
        store_col.update_one(
            {'name': kit_name, 'category': 'vip'},
            {'$addToSet': {'items': {'shortname': shortname, 'name': name, 'amount': amount, 'image': image}}}
        )
    return jsonify({'message': f'{len(data["items"])} itens processados'})

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


@app.route('/api/admin/store/<item_id>', methods=['PUT'])
def admin_update_store_item(item_id):
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    d = request.json
    update = {}
    if 'price' in d:
        update['price'] = int(d['price'])
    if 'featured' in d:
        update['featured'] = bool(d['featured'])
    if 'image' in d:
        update['image'] = str(d['image'])
    if not update:
        return jsonify({'error': 'Nada para atualizar'}), 400
    store_col.update_one({'_id': ObjectId(item_id)}, {'$set': update})
    return jsonify({'message': 'Item atualizado!'})


@app.route('/api/admin/setup', methods=['POST'])
def setup_admin():
    # Atualiza ou cria o admin principal
    users_col.update_one(
        {'email': 'matheus.anholetos@gmail.com'},
        {'$set': {
            'username': 'Matheus',
            'email': 'matheus.anholetos@gmail.com',
            'password_hash': hash_password('compass2210'),
            'role': 'admin',
            'balance': 99999,
            'avatar': '/static/default_avatar.png'
        }},
        upsert=True
    )
    return jsonify({'message': 'Admin configurado!'})

def setup_admin_on_start():
    users_col.update_one(
        {'email': 'matheus.anholetos@gmail.com'},
        {'$set': {
            'username': 'Matheus',
            'email': 'matheus.anholetos@gmail.com',
            'password_hash': hash_password('compass2210'),
            'role': 'admin',
            'balance': 99999,
            'email_verified': True,
        }},
        upsert=True
    )

# ── SUPPORT TICKETS ───────────────────────────────────────

TICKET_CATEGORIES = ['Compra / Pagamento', 'Problema no servidor', 'Bug / Erro', 'Conta / Acesso', 'Abuso / Report', 'Outro']

@app.route('/api/tickets', methods=['POST'])
def create_ticket():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Faça login para abrir um ticket'}), 401
    data     = request.json
    subject  = (data.get('subject') or '').strip()
    category = (data.get('category') or '').strip()
    message  = (data.get('message') or '').strip()
    if not subject or not message or not category:
        return jsonify({'error': 'Preencha todos os campos'}), 400
    if category not in TICKET_CATEGORIES:
        return jsonify({'error': 'Categoria inválida'}), 400
    ticket_id = tickets_col.insert_one({
        'user_id':    uid,
        'subject':    subject,
        'category':   category,
        'status':     'open',   # open | in_progress | closed
        'priority':   'normal', # normal | high | urgent
        'messages':   [{'author_id': uid, 'author_role': 'user', 'text': message, 'created_at': datetime.utcnow()}],
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }).inserted_id
    return jsonify({'message': 'Ticket aberto com sucesso!', 'ticket_id': str(ticket_id)}), 201

@app.route('/api/tickets', methods=['GET'])
def list_tickets():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Não autenticado'}), 401
    user = users_col.find_one({'_id': ObjectId(uid)})
    if user and user.get('role') == 'admin':
        status_filter = request.args.get('status')
        query = {}
        if status_filter and status_filter != 'all':
            query['status'] = status_filter
        tickets = list(tickets_col.find(query).sort('updated_at', -1))
    else:
        tickets = list(tickets_col.find({'user_id': uid}).sort('updated_at', -1))
    result = []
    for t in tickets:
        t = fix_id(t)
        try:
            u = users_col.find_one({'_id': ObjectId(t['user_id'])}, {'username': 1})
            t['username'] = u['username'] if u else 'Desconhecido'
        except:
            t['username'] = 'Desconhecido'
        t['message_count'] = len(t.get('messages', []))
        t.pop('messages', None)
        result.append(t)
    return jsonify({'tickets': result})

@app.route('/api/tickets/<ticket_id>', methods=['GET'])
def get_ticket(ticket_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Não autenticado'}), 401
    user = users_col.find_one({'_id': ObjectId(uid)})
    is_admin = user and user.get('role') == 'admin'
    ticket = tickets_col.find_one({'_id': ObjectId(ticket_id)})
    if not ticket:
        return jsonify({'error': 'Ticket não encontrado'}), 404
    if not is_admin and ticket['user_id'] != uid:
        return jsonify({'error': 'Acesso negado'}), 403
    ticket = fix_id(ticket)
    # Enriquecer mensagens com username
    for msg in ticket.get('messages', []):
        try:
            u = users_col.find_one({'_id': ObjectId(msg['author_id'])}, {'username': 1, 'role': 1})
            msg['username'] = u['username'] if u else 'Desconhecido'
            msg['role']     = u.get('role', 'player') if u else 'player'
            msg['created_at'] = msg['created_at'].isoformat() if hasattr(msg.get('created_at'), 'isoformat') else str(msg.get('created_at',''))
        except:
            msg['username'] = 'Desconhecido'
            msg['role']     = 'player'
    try:
        owner = users_col.find_one({'_id': ObjectId(ticket['user_id'])}, {'username': 1})
        ticket['username'] = owner['username'] if owner else 'Desconhecido'
    except:
        ticket['username'] = 'Desconhecido'
    ticket['created_at'] = ticket['created_at'].isoformat() if hasattr(ticket.get('created_at'), 'isoformat') else str(ticket.get('created_at',''))
    ticket['updated_at'] = ticket['updated_at'].isoformat() if hasattr(ticket.get('updated_at'), 'isoformat') else str(ticket.get('updated_at',''))
    return jsonify({'ticket': ticket})

@app.route('/api/tickets/<ticket_id>/reply', methods=['POST'])
def reply_ticket(ticket_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Não autenticado'}), 401
    user = users_col.find_one({'_id': ObjectId(uid)})
    is_admin = user and user.get('role') == 'admin'
    ticket = tickets_col.find_one({'_id': ObjectId(ticket_id)})
    if not ticket:
        return jsonify({'error': 'Ticket não encontrado'}), 404
    if not is_admin and ticket['user_id'] != uid:
        return jsonify({'error': 'Acesso negado'}), 403
    if ticket['status'] == 'closed' and not is_admin:
        return jsonify({'error': 'Ticket fechado'}), 400
    data = request.json
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'Mensagem vazia'}), 400
    msg = {'author_id': uid, 'author_role': 'admin' if is_admin else 'user', 'text': text, 'created_at': datetime.utcnow()}
    new_status = ticket['status']
    if is_admin and ticket['status'] == 'open':
        new_status = 'in_progress'
    tickets_col.update_one(
        {'_id': ObjectId(ticket_id)},
        {'$push': {'messages': msg}, '$set': {'updated_at': datetime.utcnow(), 'status': new_status}}
    )
    return jsonify({'message': 'Resposta enviada!'})

@app.route('/api/tickets/<ticket_id>/status', methods=['PUT'])
def update_ticket_status(ticket_id):
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    data   = request.json
    status = data.get('status')
    priority = data.get('priority')
    update = {'updated_at': datetime.utcnow()}
    if status in ('open', 'in_progress', 'closed'):
        update['status'] = status
    if priority in ('normal', 'high', 'urgent'):
        update['priority'] = priority
    tickets_col.update_one({'_id': ObjectId(ticket_id)}, {'$set': update})
    return jsonify({'message': 'Ticket atualizado!'})

@app.route('/api/admin/tickets/stats')
def admin_ticket_stats():
    if not require_admin():
        return jsonify({'error': 'Acesso negado'}), 403
    return jsonify({
        'open':        tickets_col.count_documents({'status': 'open'}),
        'in_progress': tickets_col.count_documents({'status': 'in_progress'}),
        'closed':      tickets_col.count_documents({'status': 'closed'}),
        'total':       tickets_col.count_documents({}),
    })

if __name__ == '__main__':
    seed_db()
    setup_admin_on_start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
