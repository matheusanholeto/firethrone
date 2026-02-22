-- FireThrone Database Schema

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    steam_id TEXT,
    avatar TEXT DEFAULT '/static/default_avatar.png',
    role TEXT DEFAULT 'player', -- player, vip, admin
    balance INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ip TEXT NOT NULL,
    port INTEGER NOT NULL,
    map TEXT DEFAULT 'Procedural Map',
    max_players INTEGER DEFAULT 200,
    current_players INTEGER DEFAULT 0,
    status TEXT DEFAULT 'online', -- online, offline, restarting
    wipe_schedule TEXT DEFAULT 'Monthly',
    last_wipe DATETIME,
    next_wipe DATETIME,
    modded INTEGER DEFAULT 0,
    description TEXT,
    tags TEXT -- JSON array
);

CREATE TABLE IF NOT EXISTS store_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'vip', -- vip, kits, cosmetics, commands
    price INTEGER NOT NULL,
    image TEXT,
    featured INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    item_id INTEGER REFERENCES store_items(id),
    amount_paid INTEGER NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, completed, refunded
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS leaderboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    server_id INTEGER REFERENCES servers(id),
    kills INTEGER DEFAULT 0,
    deaths INTEGER DEFAULT 0,
    hours_played REAL DEFAULT 0,
    resources_gathered INTEGER DEFAULT 0,
    raids_won INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author_id INTEGER REFERENCES users(id),
    category TEXT DEFAULT 'update', -- update, wipe, event, maintenance
    published INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Seed data
INSERT OR IGNORE INTO servers (name, ip, port, map, max_players, current_players, status, wipe_schedule, modded, description, tags) VALUES
('FireThrone - Main', '45.33.32.156', 28015, 'Procedural Map', 200, 87, 'online', 'Monthly', 0, 'Servidor principal vanilla. PvP intenso, economia balanceada.', '["vanilla","pvp","monthly"]'),
('FireThrone - 2x Solo/Duo', '45.33.32.157', 28015, 'Barren', 150, 63, 'online', 'Bi-Weekly', 1, 'Servidor 2x para solo e duo. Recursos dobrados, raids equilibradas.', '["2x","solo","duo","modded"]'),
('FireThrone - 5x Build', '45.33.32.158', 28015, 'Hapis Island', 100, 41, 'online', 'Weekly', 1, 'Modo criativo com 5x de recursos. Foque no building.', '["5x","build","creative"]'),
('FireThrone - Battlefield', '45.33.32.159', 28015, 'Procedural Map', 300, 0, 'restarting', 'Weekly', 1, 'PvP puro, sem base building. Arena de combate constante.', '["pvp","arena","weekly"]');

INSERT OR IGNORE INTO store_items (name, description, category, price, featured) VALUES
('VIP Bronze', 'Acesso ao kit bronze, prioridade na fila e tag exclusiva no chat.', 'vip', 1500, 0),
('VIP Prata', 'Tudo do Bronze + kit prata, home duplo e acesso ao canal VIP.', 'vip', 2900, 0),
('VIP Ouro', 'Tudo do Prata + kit ouro, /tpr ilimitado e skin exclusiva.', 'vip', 4900, 1),
('VIP Diamante', 'Pacote completo. Todos os benefícios + suporte prioritário.', 'vip', 8900, 1),
('Kit Guerreiro', 'AK47 + armadura de metal completa + suprimentos para 3 dias.', 'kits', 990, 0),
('Kit Construtor', 'Hammer + recursos x500 + planos de base + c4 x2.', 'kits', 790, 0),
('Kit Médico', 'Syringes x10 + bandagens x20 + comida x30.', 'kits', 490, 0),
('Skin Facemask Neon', 'Skin exclusiva FireThrone para Facemask.', 'cosmetics', 350, 0),
('Skin AK Dourada', 'Skin dourada exclusiva para AK-47.', 'cosmetics', 590, 1),
('1000 Créditos', 'Recarga de 1000 créditos na sua conta.', 'credits', 1000, 0);

INSERT OR IGNORE INTO users (username, email, password_hash, role, balance) VALUES
('Admin', 'admin@firethrone.gg', 'hashed_admin_pw', 'admin', 99999),
('SurvivorKing', 'survivor@test.com', 'hashed_pw', 'vip', 2500),
('RustLord99', 'rustlord@test.com', 'hashed_pw', 'player', 500),
('NightRaider', 'night@test.com', 'hashed_pw', 'vip', 1200),
('IronBuilder', 'iron@test.com', 'hashed_pw', 'player', 300);

INSERT OR IGNORE INTO leaderboard (user_id, server_id, kills, deaths, hours_played, resources_gathered, raids_won) VALUES
(2, 1, 1842, 234, 482.5, 984320, 67),
(3, 1, 1567, 445, 312.0, 745800, 43),
(4, 1, 1234, 189, 567.0, 1200450, 89),
(5, 1, 987, 312, 245.0, 567200, 31),
(1, 1, 756, 98, 890.0, 2345000, 120);

INSERT OR IGNORE INTO news (title, content, author_id, category) VALUES
('Wipe Mensal — 1° de Março', 'O wipe mensal acontecerá no dia 1° de Março às 15h (BRT). Todos os mapas serão resetados. Blueprints mantidos no servidor Main.', 1, 'wipe'),
('Nova Atualização: Battlefield Server', 'O servidor Battlefield foi completamente reformulado. Novo mapa, novos eventos e recompensas dobradas no fim de semana.', 1, 'update'),
('Evento: Raid Weekend', 'Este fim de semana os custos de explosivos foram reduzidos em 50%. Aproveite para dominar seus inimigos!', 1, 'event');
