from flask import Flask, jsonify, request, session, send_from_directory, redirect
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient, ReturnDocument
from bson import ObjectId
from bson.errors import InvalidId
import bcrypt, os, secrets, re, json, logging
from datetime import datetime, timedelta
from urllib.parse import urlencode
import urllib.request
from functools import wraps

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

_secret = os.environ.get('SECRET_KEY')
if not _secret:
    raise RuntimeError('SECRET_KEY não definida.')
app.secret_key = _secret

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV') != 'development',
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', 'https://firethrone-server.onrender.com')
CORS(app, supports_credentials=True, origins=[ALLOWED_ORIGIN])
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/firethrone')
client    = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db        = client.get_database()

users_col       = db['users']
servers_col     = db['servers']
store_col       = db['store_items']
purchases_col   = db['purchases']
leaderboard_col = db['leaderboard']
news_col        = db['news']
tickets_col     = db['tickets']
tokens_col      = db['email_tokens']

# ─── EMAIL ────────────────────────────────────────────────
SITE_URL      = os.environ.get('SITE_URL', 'https://firethrone-server.onrender.com')
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
EMAIL_FROM    = os.environ.get('EMAIL_FROM', 'firethroneserver@gmail.com')

def send_email(to, subject, html_body):
    if not BREVO_API_KEY:
        logger.warning('[EMAIL SKIP] BREVO_API_KEY não configurada!')
        return False
    try:
        payload = json.dumps({
            'sender': {'name': 'FireThrone', 'email': EMAIL_FROM},
            'to': [{'email': to}],
            'subject': subject,
            'htmlContent': html_body
        }).encode()
        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email', data=payload,
            headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=10).read()
        logger.info('[EMAIL OK] Enviado para %s', to)
        return True
    except urllib.error.HTTPError as e:
        logger.error('[EMAIL ERROR] HTTP %s para %s: %s', e.code, to, e.read().decode())
        return False
    except Exception as e:
        logger.error('[EMAIL ERROR] %s: %s', type(e).__name__, e)
        return False

def send_verification_email(to_email, username, token):
    link = f'{SITE_URL}/api/auth/verify-email?token={token}'
    html = f'''<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0D0B09;color:#D4B896;border:1px solid #3D2E1E;border-radius:8px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#C8440A,#8B1A1A);padding:24px;text-align:center">
        <h1 style="color:#fff;font-size:28px;margin:0;letter-spacing:4px">🔥 FIRETHRONE</h1>
      </div>
      <div style="padding:32px">
        <h2 style="color:#fff;margin-top:0">Olá, {username}!</h2>
        <p>Obrigado por se cadastrar. Confirme seu email clicando no botão abaixo:</p>
        <div style="text-align:center;margin:28px 0">
          <a href="{link}" style="background:linear-gradient(135deg,#C8440A,#8B1A1A);color:#fff;padding:14px 32px;border-radius:4px;text-decoration:none;font-weight:bold;font-size:16px">✅ CONFIRMAR EMAIL</a>
        </div>
        <p style="font-size:12px;color:#7A6550;word-break:break-all">Link: {link}</p>
      </div>
    </div>'''
    return send_email(to_email, '🔥 FireThrone — Confirme seu email', html)

def send_role_notification(to_email, username, new_role):
    info  = ROLE_INFO.get(new_role, {})
    emoji = info.get('emoji', '🎮')
    label = info.get('label', new_role)
    color = info.get('color', '#C8440A')
    html  = f'''<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0D0B09;color:#D4B896;border:1px solid #3D2E1E;border-radius:8px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#C8440A,#8B1A1A);padding:24px;text-align:center">
        <h1 style="color:#fff;font-size:28px;margin:0;letter-spacing:4px">🔥 FIRETHRONE</h1>
      </div>
      <div style="padding:32px;text-align:center">
        <h2 style="color:#fff">Olá, {username}!</h2>
        <p>Seu cargo foi atualizado no FireThrone Network:</p>
        <div style="margin:24px auto;padding:20px;background:rgba(200,68,10,.1);border:2px solid {color};border-radius:12px;display:inline-block;min-width:200px">
          <div style="font-size:3rem">{emoji}</div>
          <div style="font-size:1.6rem;font-weight:bold;color:{color};margin-top:8px;letter-spacing:2px">{label.upper()}</div>
        </div>
        <p style="font-size:13px;color:#7A6550">Acesse o site para ver seus novos privilégios.</p>
      </div>
    </div>'''
    return send_email(to_email, f'🔥 FireThrone — Cargo atualizado: {label}', html)

# ─── SISTEMA DE CARGOS ────────────────────────────────────
VALID_ROLES = {'player', 'vip', 'moderator', 'admin', 'owner'}

ROLE_HIERARCHY = {'owner': 5, 'admin': 4, 'moderator': 3, 'vip': 2, 'player': 1}

ROLE_INFO = {
    'owner':     {'emoji': '👑', 'label': 'Owner',     'color': '#FFD700', 'description': 'Dono — poder total sobre o site'},
    'admin':     {'emoji': '🛡️', 'label': 'Admin',     'color': '#ff6b6b', 'description': 'Administrador — edita o site completo'},
    'moderator': {'emoji': '🔰', 'label': 'Moderador', 'color': '#4FC3F7', 'description': 'Modera tickets e usuários'},
    'vip':       {'emoji': '⭐', 'label': 'VIP',       'color': '#C8440A', 'description': 'Jogador premium'},
    'player':    {'emoji': '🎮', 'label': 'Player',    'color': '#7A6550', 'description': 'Jogador padrão'},
}

ROLE_PERMISSIONS = {
    'owner':     {'all'},
    'admin':     {'edit_site','manage_users','manage_servers','manage_store','manage_news','manage_tickets'},
    'moderator': {'manage_users','manage_tickets'},
    'vip':       set(),
    'player':    set(),
}

def get_role_level(role): return ROLE_HIERARCHY.get(role, 0)
def has_permission(role, perm):
    p = ROLE_PERMISSIONS.get(role, set())
    return 'all' in p or perm in p

# ─── HELPERS ──────────────────────────────────────────────
def hash_password(pw): return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
def check_password(pw, hashed):
    try: return bcrypt.checkpw(pw.encode(), hashed.encode())
    except: return False

def safe_oid(v):
    try: return ObjectId(v)
    except: return None

def fix_id(doc):
    if doc and '_id' in doc:
        doc['id'] = str(doc.pop('_id'))
    return doc

def is_valid_email(e): return bool(re.match(r'^[^\@\s]+@[^\@\s]+\.[^\@\s]+$', e))

MAX_NAME = 50; MAX_SUBJECT = 120; MAX_MESSAGE = 2000

# ─── DECORADORES ──────────────────────────────────────────
def _get_current_user():
    uid = session.get('user_id')
    if not uid: return None
    oid = safe_oid(uid)
    return users_col.find_one({'_id': oid}) if oid else None

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user or get_role_level(user.get('role','player')) < get_role_level('admin'):
            return jsonify({'error': 'Acesso negado'}), 403
        return f(*args, **kwargs)
    return decorated

def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user or user.get('role') != 'owner':
            return jsonify({'error': 'Apenas o Owner pode realizar esta ação'}), 403
        return f(*args, **kwargs)
    return decorated

def permission_required(perm):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = _get_current_user()
            if not user or not has_permission(user.get('role','player'), perm):
                return jsonify({'error': 'Permissão negada'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ─── SEED ─────────────────────────────────────────────────
def seed_db():
    if users_col.count_documents({}) == 0:
        users_col.insert_one({
            'username':'Admin','email':'admin@firethrone.gg',
            'password_hash': hash_password('admin123'),
            'role':'owner','balance':99999,
            'avatar':'/static/default_avatar.png',
            'email_verified':True,'created_at':datetime.utcnow()
        })
    if servers_col.count_documents({}) == 0:
        servers_col.insert_many([
            {'name':'FireThrone - Main',        'ip':'45.33.32.156','port':28015,'map':'Procedural Map','max_players':200,'current_players':87, 'status':'online',    'wipe_schedule':'Monthly',  'modded':False,'description':'Servidor principal vanilla.','tags':['vanilla','pvp']},
            {'name':'FireThrone - 2x Solo/Duo', 'ip':'45.33.32.157','port':28015,'map':'Barren',        'max_players':150,'current_players':63, 'status':'online',    'wipe_schedule':'Bi-Weekly','modded':True, 'description':'2x para solo e duo.',        'tags':['2x','solo']},
            {'name':'FireThrone - 5x Build',    'ip':'45.33.32.158','port':28015,'map':'Hapis Island',  'max_players':100,'current_players':41, 'status':'online',    'wipe_schedule':'Weekly',   'modded':True, 'description':'5x recursos.',               'tags':['5x','build']},
            {'name':'FireThrone - Battlefield', 'ip':'45.33.32.159','port':28015,'map':'Procedural Map','max_players':300,'current_players':0,  'status':'restarting','wipe_schedule':'Weekly',   'modded':True, 'description':'PvP puro.',                  'tags':['pvp']},
        ])
    if store_col.count_documents({}) == 0:
        store_col.insert_many([
            {'name':'VIP Bronze',  'description':'Kit bronze, prioridade na fila e tag exclusiva.','category':'vip','price':1500,'featured':False,'active':True},
            {'name':'VIP Prata',   'description':'Tudo do Bronze + kit prata e home duplo.',       'category':'vip','price':2900,'featured':False,'active':True},
            {'name':'VIP Ouro',    'description':'Tudo do Prata + kit ouro e /tpr ilimitado.',     'category':'vip','price':4900,'featured':True, 'active':True},
            {'name':'VIP Diamante','description':'Pacote completo. Todos os benefícios.',           'category':'vip','price':8900,'featured':True, 'active':True},
        ])
    if news_col.count_documents({}) == 0:
        news_col.insert_many([
            {'title':'Wipe Mensal — 1° de Março',    'content':'Wipe no dia 1° de Março às 15h (BRT).','author_name':'Admin','category':'wipe',  'published':True,'created_at':datetime.utcnow()},
            {'title':'Nova Atualização: Battlefield','content':'Servidor Battlefield reformulado.',    'author_name':'Admin','category':'update','published':True,'created_at':datetime.utcnow()},
            {'title':'Evento: Raid Weekend',         'content':'Explosivos 50% mais baratos!',          'author_name':'Admin','category':'event', 'published':True,'created_at':datetime.utcnow()},
        ])

def setup_admin_on_start():
    email = os.environ.get('ADMIN_EMAIL')
    pw    = os.environ.get('ADMIN_PASSWORD')
    name  = os.environ.get('ADMIN_USERNAME', 'Admin')
    if not email or not pw:
        logger.warning('[OWNER] ADMIN_EMAIL/ADMIN_PASSWORD não definidos.')
        return
    users_col.update_one({'email': email}, {'$set': {
        'username': name, 'email': email,
        'password_hash': hash_password(pw),
        'role': 'owner', 'balance': 99999,
        'avatar': '/static/default_avatar.png',
        'email_verified': True,
    }}, upsert=True)
    logger.info('[OWNER] Owner configurado: %s', email)

# ─── FRONT-END ────────────────────────────────────────────
@app.route('/')
def index(): return send_from_directory('templates', 'index.html')

@app.route('/health')
@app.route('/ping')
def health(): return jsonify({'status': 'ok'}), 200

# ─── AUTH ─────────────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
@limiter.limit('5 per hour')
def register():
    data = request.json or {}
    firstname = data.get('firstname','').strip()
    lastname  = data.get('lastname','').strip()
    email     = data.get('email','').strip().lower()
    password  = data.get('password','')
    if not firstname or not lastname or not email or not password:
        return jsonify({'error':'Preencha todos os campos'}), 400
    if not is_valid_email(email): return jsonify({'error':'Email inválido'}), 400
    if len(password) < 6: return jsonify({'error':'Senha deve ter no mínimo 6 caracteres'}), 400
    MSG = {'message':'Se este email não estiver cadastrado, você receberá um link de confirmação. Verifique também o SPAM.'}
    if users_col.find_one({'email': email}): return jsonify(MSG), 200
    uid = str(users_col.insert_one({
        'firstname':firstname,'lastname':lastname,
        'username':f'{firstname} {lastname}','email':email,
        'password_hash':hash_password(password),
        'role':'player','balance':0,
        'avatar':'/static/default_avatar.png',
        'email_verified':False,'created_at':datetime.utcnow()
    }).inserted_id)
    token = secrets.token_urlsafe(32)
    tokens_col.insert_one({'user_id':uid,'token':token,'type':'email_verify',
        'expires_at':datetime.utcnow()+timedelta(hours=24),'used':False})
    if not send_verification_email(email, firstname, token):
        logger.error('[REGISTER] Email NÃO enviado para %s', email)
    return jsonify(MSG), 200

@app.route('/api/auth/check-email')
@limiter.limit('30 per minute')
def check_email():
    email = request.args.get('email','').strip().lower()
    if not email or not is_valid_email(email): return jsonify({'exists':False})
    return jsonify({'exists': users_col.find_one({'email':email},{'_id':1}) is not None})

@app.route('/api/auth/resend-verification', methods=['POST'])
@limiter.limit('3 per hour')
def resend_verification():
    email = (request.json or {}).get('email','').strip().lower()
    if not email or not is_valid_email(email): return jsonify({'error':'Email inválido'}), 400
    MSG = {'message':'Se este email estiver cadastrado e não verificado, um novo link foi enviado. Verifique o SPAM.'}
    user = users_col.find_one({'email':email})
    if not user or user.get('email_verified'): return jsonify(MSG), 200
    tokens_col.update_many({'user_id':str(user['_id']),'type':'email_verify','used':False},{'$set':{'used':True}})
    token = secrets.token_urlsafe(32)
    tokens_col.insert_one({'user_id':str(user['_id']),'token':token,'type':'email_verify',
        'expires_at':datetime.utcnow()+timedelta(hours=24),'used':False})
    send_verification_email(email, user.get('firstname') or user.get('username',''), token)
    return jsonify(MSG), 200

@app.route('/api/auth/verify-email')
def verify_email():
    token = request.args.get('token','')
    rec   = tokens_col.find_one({'token':token,'type':'email_verify','used':False})
    if not rec: return redirect('/?already_verified=1')
    if rec['expires_at'] < datetime.utcnow(): return redirect('/?error=token_expired')
    tokens_col.update_one({'_id':rec['_id']},{'$set':{'used':True}})
    oid = safe_oid(rec['user_id'])
    if oid: users_col.update_one({'_id':oid},{'$set':{'email_verified':True}})
    return redirect('/?email_verified=1')

@app.route('/api/auth/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = request.json or {}
    ident = data.get('identifier','').strip().lower()
    pw    = data.get('password','')
    user  = users_col.find_one({'$or':[{'email':ident},{'username':ident}]})
    if not user or not check_password(pw, user.get('password_hash','')):
        return jsonify({'error':'Credenciais inválidas'}), 401
    if not user.get('email_verified'):
        return jsonify({'error':'Confirme seu email antes de entrar.','need_verify':True,'email':user['email']}), 403
    session['user_id'] = str(user['_id'])
    return jsonify({'user':{
        'id':str(user['_id']),'username':user['username'],
        'role':user['role'],'balance':user['balance'],'avatar':user.get('avatar','')
    }})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message':'Logout realizado'})

@app.route('/api/auth/me')
def me():
    uid = session.get('user_id')
    if not uid: return jsonify({'user':None})
    oid = safe_oid(uid)
    if not oid: session.clear(); return jsonify({'user':None})
    user = users_col.find_one({'_id':oid},{'password_hash':0})
    return jsonify({'user':fix_id(user) if user else None})

# ─── ROLES INFO (público) ─────────────────────────────────
@app.route('/api/roles')
def get_roles(): return jsonify({'roles': ROLE_INFO})

# ─── STEAM ────────────────────────────────────────────────
STEAM_OPENID  = 'https://steamcommunity.com/openid/login'
STEAM_API_KEY = os.environ.get('STEAM_API_KEY','')

@app.route('/api/auth/steam')
def steam_login():
    cb = f'{SITE_URL}/api/auth/steam/callback'
    p  = {'openid.ns':'http://specs.openid.net/auth/2.0','openid.mode':'checkid_setup',
          'openid.return_to':cb,'openid.realm':SITE_URL,
          'openid.identity':'http://specs.openid.net/auth/2.0/identifier_select',
          'openid.claimed_id':'http://specs.openid.net/auth/2.0/identifier_select'}
    return redirect(f'{STEAM_OPENID}?{urlencode(p)}')

@app.route('/api/auth/steam/callback')
def steam_callback():
    params = dict(request.args); params['openid.mode'] = 'check_authentication'
    try:
        data = urlencode({k:v[0] if isinstance(v,list) else v for k,v in params.items()}).encode()
        resp = urllib.request.urlopen(urllib.request.Request(STEAM_OPENID,data=data),timeout=10).read().decode()
        if 'is_valid:true' not in resp: return redirect('/?steam_error=invalid')
    except: return redirect('/?steam_error=1')
    steam_id = request.args.get('openid.claimed_id','').split('/')[-1]
    if not steam_id.isdigit(): return redirect('/?steam_error=id')
    username = f'Steam_{steam_id[-6:]}'; avatar = ''
    if STEAM_API_KEY:
        try:
            d = json.loads(urllib.request.urlopen(f'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id}',timeout=8).read())
            p = d['response']['players'][0]; username = p.get('personaname',username); avatar = p.get('avatarfull','')
        except: pass
    user = users_col.find_one({'steam_id':steam_id})
    if not user:
        uid = users_col.insert_one({'username':username,'steam_id':steam_id,'email':'','password_hash':'',
            'role':'player','balance':0,'avatar':avatar,'email_verified':True,'created_at':datetime.utcnow()}).inserted_id
    else:
        uid = user['_id']; users_col.update_one({'_id':uid},{'$set':{'username':username,'avatar':avatar}})
    session['user_id'] = str(uid)
    return redirect('/?steam_ok=1')

# ─── SERVERS / STORE / LEADERBOARD / NEWS ─────────────────
@app.route('/api/servers')
def get_servers():
    return jsonify({'servers':[fix_id(s) for s in servers_col.find()]})

@app.route('/api/store')
def get_store():
    items = list(store_col.find({'active':True}).sort([('featured',-1),('price',1)]))
    return jsonify({'items':[fix_id(i) for i in items]})

@app.route('/api/store/buy', methods=['POST'])
def buy_item():
    uid = session.get('user_id')
    if not uid: return jsonify({'error':'Faça login para comprar'}), 401
    data = request.json or {}
    uid_oid = safe_oid(uid); itm_oid = safe_oid(data.get('item_id'))
    if not uid_oid or not itm_oid: return jsonify({'error':'ID inválido'}), 400
    item = store_col.find_one({'_id':itm_oid,'active':True})
    if not item: return jsonify({'error':'Item não encontrado'}), 404
    updated = users_col.find_one_and_update(
        {'_id':uid_oid,'balance':{'$gte':item['price']}},
        {'$inc':{'balance':-item['price']}}, return_document=ReturnDocument.AFTER)
    if not updated: return jsonify({'error':'Saldo insuficiente'}), 400
    purchases_col.insert_one({'user_id':uid,'item_id':str(itm_oid),'amount_paid':item['price'],
        'status':'completed','created_at':datetime.utcnow()})
    return jsonify({'message':f'"{item["name"]}" comprado!','new_balance':updated['balance']})

@app.route('/api/leaderboard')
def get_leaderboard():
    sort_by = request.args.get('sort','kills')
    if sort_by not in ['kills','deaths','hours_played','resources_gathered','raids_won']: sort_by='kills'
    rows = list(leaderboard_col.find().sort(sort_by,-1).limit(50))
    for r in rows:
        oid = safe_oid(r.get('user_id'))
        if oid:
            u = users_col.find_one({'_id':oid},{'username':1,'avatar':1,'role':1})
            if u: r['username']=u['username']; r['avatar']=u.get('avatar',''); r['role']=u.get('role','player')
        fix_id(r)
    return jsonify({'leaderboard':rows})

@app.route('/api/news')
def get_news():
    news = list(news_col.find({'published':True}).sort('created_at',-1).limit(10))
    return jsonify({'news':[fix_id(n) for n in news]})

@app.route('/api/news', methods=['POST'])
@permission_required('manage_news')
def create_news():
    user = _get_current_user()
    data = request.json or {}
    title = (data.get('title') or '').strip(); content = (data.get('content') or '').strip()
    cat   = data.get('category','update')
    if not title or not content: return jsonify({'error':'Preencha título e conteúdo'}), 400
    if cat not in ('update','wipe','event','maintenance'): cat = 'update'
    news_col.insert_one({'title':title,'content':content,'author_name':user['username'] if user else 'Admin',
        'category':cat,'published':True,'created_at':datetime.utcnow()})
    return jsonify({'message':'Notícia publicada!'}), 201

@app.route('/api/news/<nid>', methods=['PUT','DELETE'])
@permission_required('manage_news')
def manage_news(nid):
    oid = safe_oid(nid)
    if not oid: return jsonify({'error':'ID inválido'}), 400
    if request.method == 'DELETE':
        news_col.delete_one({'_id':oid}); return jsonify({'message':'Notícia removida!'})
    data = request.json or {}
    upd  = {k:data[k] for k in ('title','content','category','published') if k in data}
    if upd: news_col.update_one({'_id':oid},{'$set':upd})
    return jsonify({'message':'Notícia atualizada!'})

# ─── SYNC ─────────────────────────────────────────────────
def _check_sync():
    s = request.headers.get('X-Sync-Secret','') or request.args.get('secret','')
    return s == os.environ.get('SYNC_SECRET','')

@app.route('/api/sync/kits', methods=['POST'])
def sync_kits():
    if not _check_sync(): return jsonify({'error':'Não autorizado'}), 401
    data = request.json or {}
    kits = data.get('kits',[])
    if not data.get('append'): store_col.update_many({'category':'vip'},{'$set':{'active':False}})
    for kit in kits:
        name = kit.get('Name','')
        if kit.get('IsHidden') or not name: continue
        ex = store_col.find_one({'name':name,'category':'vip'}) or {}
        store_col.update_one({'name':name,'category':'vip'},{'$set':{
            'description':kit.get('Description','') or f'Kit {name}',
            'price':ex.get('price',kit.get('Cost',0)),
            'image':kit.get('KitImage','') or ex.get('image',''),
            'active':True,'category':'vip','featured':False,'items':kit.get('Items',[])
        }},upsert=True)
    return jsonify({'message':f'{len(kits)} kits sincronizados!'})

@app.route('/api/sync/kits/items', methods=['POST'])
def sync_kit_items():
    if not _check_sync(): return jsonify({'error':'Não autorizado'}), 401
    kit_name = request.args.get('kit','')
    if not kit_name: return jsonify({'error':'Kit não especificado'}), 400
    data = request.json or {}
    if 'items' not in data: return jsonify({'error':'Dados inválidos'}), 400
    store_col.update_one({'name':kit_name,'category':'vip'},{'$set':{'items':data['items']}})
    return jsonify({'message':'Itens atualizados!'})

@app.route('/api/sync/kits/items/batch', methods=['POST'])
def sync_kit_items_batch():
    if not _check_sync(): return jsonify({'error':'Não autorizado'}), 401
    items = (request.json or {}).get('items',[])
    for item in items:
        kit_name = item.get('kit','')
        if not kit_name: continue
        store_col.update_one({'name':kit_name,'category':'vip'},{'$addToSet':{'items':{
            'shortname':item.get('shortname',''),'name':item.get('name',''),'amount':item.get('amount',1),'image':item.get('image','')
        }}})
    return jsonify({'message':f'{len(items)} itens processados'})

# ─── ADMIN ────────────────────────────────────────────────
@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    rev = list(purchases_col.aggregate([{'$match':{'status':'completed'}},{'$group':{'_id':None,'total':{'$sum':'$amount_paid'}}}]))
    pl  = list(servers_col.aggregate([{'$match':{'status':'online'}},{'$group':{'_id':None,'total':{'$sum':'$current_players'}}}]))
    recent = list(users_col.find({},{'password_hash':0}).sort('created_at',-1).limit(10))
    return jsonify({'stats':{
        'total_users':    users_col.count_documents({}),
        'total_purchases':purchases_col.count_documents({'status':'completed'}),
        'total_revenue':  rev[0]['total'] if rev else 0,
        'online_servers': servers_col.count_documents({'status':'online'}),
        'total_players':  pl[0]['total'] if pl else 0,
    },'recent_users':[fix_id(u) for u in recent]})

@app.route('/api/admin/users')
@admin_required
def admin_users():
    users = list(users_col.find({},{'password_hash':0}).sort('created_at',-1))
    return jsonify({'users':[fix_id(u) for u in users]})

@app.route('/api/admin/users/<uid>', methods=['PUT'])
@admin_required
def update_user(uid):
    actor = _get_current_user()
    if not actor: return jsonify({'error':'Sessão inválida'}), 403
    target_oid = safe_oid(uid)
    if not target_oid: return jsonify({'error':'ID inválido'}), 400
    target = users_col.find_one({'_id':target_oid})
    if not target: return jsonify({'error':'Usuário não encontrado'}), 404

    d       = request.json or {}
    role    = d.get('role')
    balance = d.get('balance')

    # Regras de hierarquia
    actor_level  = get_role_level(actor.get('role','player'))
    target_level = get_role_level(target.get('role','player'))

    if actor.get('role') != 'owner':
        if target_level >= actor_level:
            return jsonify({'error':'Você não pode alterar um usuário de nível igual ou superior'}), 403
        if role and get_role_level(role) >= get_role_level('admin'):
            return jsonify({'error':'Apenas o Owner pode atribuir cargos de Admin ou superior'}), 403

    if role and role not in VALID_ROLES: return jsonify({'error':'Cargo inválido'}), 400
    if balance is not None and (not isinstance(balance,int) or balance < 0):
        return jsonify({'error':'Balance inválido'}), 400

    upd = {}
    if role:              upd['role']    = role
    if balance is not None: upd['balance'] = balance
    if upd: users_col.update_one({'_id':target_oid},{'$set':upd})

    if role and role != target.get('role') and target.get('email'):
        send_role_notification(target['email'], target['username'], role)

    return jsonify({'message':'Usuário atualizado!'})

@app.route('/api/admin/servers', methods=['GET','POST','PUT'])
@admin_required
def admin_servers():
    if request.method == 'GET':
        return jsonify({'servers':[fix_id(s) for s in servers_col.find()]})
    d = request.json or {}
    if request.method == 'POST':
        servers_col.insert_one({'name':d.get('name',''),'ip':d.get('ip',''),'port':d.get('port',28015),
            'map':d.get('map','Procedural Map'),'max_players':d.get('max_players',200),
            'current_players':0,'status':d.get('status','online'),
            'wipe_schedule':d.get('wipe_schedule','Monthly'),
            'modded':d.get('modded',False),'description':d.get('description',''),'tags':[]})
        return jsonify({'message':'Servidor criado!'})
    oid = safe_oid(d.get('id'))
    if not oid: return jsonify({'error':'ID inválido'}), 400
    servers_col.update_one({'_id':oid},{'$set':{'name':d.get('name'),'status':d.get('status'),'current_players':d.get('current_players',0)}})
    return jsonify({'message':'Servidor atualizado!'})

@app.route('/api/admin/store/<item_id>', methods=['PUT'])
@permission_required('manage_store')
def admin_update_store_item(item_id):
    oid = safe_oid(item_id)
    if not oid: return jsonify({'error':'ID inválido'}), 400
    d   = request.json or {}
    upd = {}
    if 'price'    in d: upd['price']    = int(d['price'])
    if 'featured' in d: upd['featured'] = bool(d['featured'])
    if 'image'    in d: upd['image']    = str(d['image'])
    if not upd: return jsonify({'error':'Nada para atualizar'}), 400
    store_col.update_one({'_id':oid},{'$set':upd})
    return jsonify({'message':'Item atualizado!'})

@app.route('/api/admin/test-email')
@admin_required
def admin_test_email():
    to = request.args.get('to','').strip()
    if not to or not is_valid_email(to): return jsonify({'error':'Informe: ?to=email@exemplo.com'}), 400
    html = f'<div style="font-family:Arial;background:#0D0B09;color:#D4B896;padding:24px;border-radius:8px"><h2 style="color:#C8440A">🔥 FireThrone — Teste de Email</h2><p>Configuração funcionando!</p><p>FROM: {EMAIL_FROM}</p><p>URL: {SITE_URL}</p></div>'
    ok   = send_email(to, '🔥 FireThrone — Teste', html)
    return jsonify({'sent':ok,'brevo_key_set':bool(BREVO_API_KEY),'email_from':EMAIL_FROM,'site_url':SITE_URL,
        'message':'Email enviado!' if ok else 'Falha. Verifique BREVO_API_KEY e EMAIL_FROM.'})

# ─── OWNER: GESTÃO DE CARGOS ──────────────────────────────
@app.route('/api/owner/assign-role', methods=['POST'])
@owner_required
def assign_role():
    """Owner atribui qualquer cargo por email."""
    data  = request.json or {}
    email = data.get('email','').strip().lower()
    role  = data.get('role','').strip()
    if not email or not is_valid_email(email): return jsonify({'error':'Email inválido'}), 400
    if role not in VALID_ROLES: return jsonify({'error':f'Cargo inválido. Opções: {", ".join(VALID_ROLES)}'}), 400
    user = users_col.find_one({'email':email})
    if not user: return jsonify({'error':'Nenhum usuário encontrado com este email'}), 404
    old_role = user.get('role','player')
    users_col.update_one({'_id':user['_id']},{'$set':{'role':role}})
    if role != old_role and user.get('email'):
        send_role_notification(user['email'], user['username'], role)
    logger.info('[OWNER] %s: %s → %s', email, old_role, role)
    return jsonify({'message':f'Cargo de {user["username"]} atualizado para {ROLE_INFO[role]["label"]}!',
        'user':{'id':str(user['_id']),'username':user['username'],'email':user['email'],'old_role':old_role,'new_role':role}})

@app.route('/api/owner/staff')
@owner_required
def list_staff():
    """Lista todos os usuários com cargo acima de player."""
    staff = list(users_col.find({'role':{'$in':['owner','admin','moderator','vip']}},{'password_hash':0}).sort('role',1))
    return jsonify({'staff':[fix_id(u) for u in staff]})

@app.route('/api/owner/search-user')
@owner_required
def search_user_by_email():
    """Busca usuário por email para exibir antes de atribuir cargo."""
    email = request.args.get('email','').strip().lower()
    if not email or not is_valid_email(email): return jsonify({'error':'Email inválido'}), 400
    user = users_col.find_one({'email':email},{'password_hash':0})
    if not user: return jsonify({'user':None})
    return jsonify({'user':fix_id(user)})

# ─── TICKETS ──────────────────────────────────────────────
TICKET_CATS = ['Compra / Pagamento','Problema no servidor','Bug / Erro','Conta / Acesso','Abuso / Report','Outro']

@app.route('/api/tickets', methods=['POST'])
@limiter.limit('10 per hour')
def create_ticket():
    uid = session.get('user_id')
    if not uid: return jsonify({'error':'Faça login para abrir um ticket'}), 401
    data    = request.json or {}
    subject = (data.get('subject') or '').strip()
    cat     = (data.get('category') or '').strip()
    msg     = (data.get('message') or '').strip()
    if not subject or not msg or not cat: return jsonify({'error':'Preencha todos os campos'}), 400
    if len(subject) > MAX_SUBJECT: return jsonify({'error':f'Assunto muito longo (máx {MAX_SUBJECT})'}), 400
    if len(msg) > MAX_MESSAGE: return jsonify({'error':f'Mensagem muito longa (máx {MAX_MESSAGE})'}), 400
    if cat not in TICKET_CATS: return jsonify({'error':'Categoria inválida'}), 400
    tid = tickets_col.insert_one({'user_id':uid,'subject':subject,'category':cat,'status':'open','priority':'normal',
        'messages':[{'author_id':uid,'author_role':'user','text':msg,'created_at':datetime.utcnow()}],
        'created_at':datetime.utcnow(),'updated_at':datetime.utcnow()}).inserted_id
    return jsonify({'message':'Ticket aberto!','ticket_id':str(tid)}), 201

@app.route('/api/tickets', methods=['GET'])
def list_tickets():
    uid = session.get('user_id')
    if not uid: return jsonify({'error':'Não autenticado'}), 401
    user     = _get_current_user()
    can_mgmt = user and has_permission(user.get('role','player'),'manage_tickets')
    if can_mgmt:
        sf = request.args.get('status')
        q  = {'status':sf} if sf and sf != 'all' else {}
        tickets = list(tickets_col.find(q).sort('updated_at',-1))
    else:
        tickets = list(tickets_col.find({'user_id':uid}).sort('updated_at',-1))
    result = []
    for t in tickets:
        t = fix_id(t)
        try:
            u = users_col.find_one({'_id':safe_oid(t['user_id'])},{'username':1})
            t['username'] = u['username'] if u else 'Desconhecido'
        except: t['username'] = 'Desconhecido'
        t['message_count'] = len(t.get('messages',[])); t.pop('messages',None)
        result.append(t)
    return jsonify({'tickets':result})

@app.route('/api/tickets/<tid>', methods=['GET'])
def get_ticket(tid):
    uid = session.get('user_id')
    if not uid: return jsonify({'error':'Não autenticado'}), 401
    t_oid = safe_oid(tid)
    if not t_oid: return jsonify({'error':'ID inválido'}), 400
    user     = _get_current_user()
    can_mgmt = user and has_permission(user.get('role','player'),'manage_tickets')
    ticket   = tickets_col.find_one({'_id':t_oid})
    if not ticket: return jsonify({'error':'Ticket não encontrado'}), 404
    if not can_mgmt and ticket['user_id'] != uid: return jsonify({'error':'Acesso negado'}), 403
    ticket = fix_id(ticket)
    for msg in ticket.get('messages',[]):
        try:
            u = users_col.find_one({'_id':safe_oid(msg['author_id'])},{'username':1,'role':1})
            msg['username'] = u['username'] if u else 'Desconhecido'
            msg['role']     = u.get('role','player') if u else 'player'
            msg['created_at'] = msg['created_at'].isoformat() if hasattr(msg.get('created_at'),'isoformat') else str(msg.get('created_at',''))
        except: msg['username']='Desconhecido'; msg['role']='player'
    try:
        owner = users_col.find_one({'_id':safe_oid(ticket['user_id'])},{'username':1})
        ticket['username'] = owner['username'] if owner else 'Desconhecido'
    except: ticket['username'] = 'Desconhecido'
    for k in ('created_at','updated_at'):
        ticket[k] = ticket[k].isoformat() if hasattr(ticket.get(k),'isoformat') else str(ticket.get(k,''))
    return jsonify({'ticket':ticket})

@app.route('/api/tickets/<tid>/reply', methods=['POST'])
def reply_ticket(tid):
    uid = session.get('user_id')
    if not uid: return jsonify({'error':'Não autenticado'}), 401
    t_oid = safe_oid(tid)
    if not t_oid: return jsonify({'error':'ID inválido'}), 400
    user     = _get_current_user()
    can_mgmt = user and has_permission(user.get('role','player'),'manage_tickets')
    ticket   = tickets_col.find_one({'_id':t_oid})
    if not ticket: return jsonify({'error':'Ticket não encontrado'}), 404
    if not can_mgmt and ticket['user_id'] != uid: return jsonify({'error':'Acesso negado'}), 403
    if ticket['status'] == 'closed' and not can_mgmt: return jsonify({'error':'Ticket fechado'}), 400
    text = ((request.json or {}).get('text') or '').strip()
    if not text: return jsonify({'error':'Mensagem vazia'}), 400
    if len(text) > MAX_MESSAGE: return jsonify({'error':f'Mensagem muito longa (máx {MAX_MESSAGE})'}), 400
    new_status = 'in_progress' if can_mgmt and ticket['status']=='open' else ticket['status']
    tickets_col.update_one({'_id':t_oid},{'$push':{'messages':{
        'author_id':uid,'author_role':'staff' if can_mgmt else 'user','text':text,'created_at':datetime.utcnow()
    }},'$set':{'updated_at':datetime.utcnow(),'status':new_status}})
    return jsonify({'message':'Resposta enviada!'})

@app.route('/api/tickets/<tid>/status', methods=['PUT'])
@permission_required('manage_tickets')
def update_ticket_status(tid):
    t_oid = safe_oid(tid)
    if not t_oid: return jsonify({'error':'ID inválido'}), 400
    d   = request.json or {}
    upd = {'updated_at':datetime.utcnow()}
    if d.get('status')   in ('open','in_progress','closed'): upd['status']   = d['status']
    if d.get('priority') in ('normal','high','urgent'):      upd['priority'] = d['priority']
    tickets_col.update_one({'_id':t_oid},{'$set':upd})
    return jsonify({'message':'Ticket atualizado!'})

@app.route('/api/admin/tickets/stats')
@permission_required('manage_tickets')
def admin_ticket_stats():
    return jsonify({
        'open':        tickets_col.count_documents({'status':'open'}),
        'in_progress': tickets_col.count_documents({'status':'in_progress'}),
        'closed':      tickets_col.count_documents({'status':'closed'}),
        'total':       tickets_col.count_documents({}),
    })

if __name__ == '__main__':
    seed_db()
    setup_admin_on_start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)),
            debug=os.environ.get('FLASK_ENV')=='development')
