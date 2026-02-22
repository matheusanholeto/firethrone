# 🔥 FireThrone — Rust Network

Site completo para servidor de Rust com frontend, backend Python (Flask) e banco de dados SQLite.

---

## 📁 Estrutura do Projeto

```
firethrone/
├── frontend/
│   └── index.html          ← Site completo (abrir no navegador)
├── backend/
│   ├── app.py              ← API Flask (Python)
│   └── requirements.txt    ← Dependências Python
└── database/
    └── schema.sql          ← Schema + dados iniciais
```

---

## 🚀 Como Rodar

### 1. Instalar Python
Baixe em: https://python.org (versão 3.10+)

### 2. Instalar dependências do backend
```bash
cd firethrone/backend
pip install -r requirements.txt
```

### 3. Iniciar o servidor backend
```bash
python app.py
```
O backend roda em: `http://localhost:5000`

### 4. Abrir o frontend
Abra o arquivo `frontend/index.html` no navegador.

---

## 🔑 Login de Admin (para testar)

| Campo    | Valor         |
|----------|---------------|
| Usuário  | `Admin`       |
| Senha    | `admin123`    |

> **Nota:** Na primeira execução, o banco de dados é criado automaticamente com dados de exemplo.

---

## ⚙️ Funcionalidades

| Funcionalidade         | Descrição |
|------------------------|-----------|
| 🖥️ Servidores ao vivo  | Lista de servidores com status, jogadores e barra de capacidade |
| 🔐 Login / Cadastro    | Sistema de autenticação com sessão |
| 🛒 Loja VIP            | Compra de itens com créditos (VIP, Kits, Cosméticos) |
| 🏆 Ranking             | Leaderboard com kills, mortes, horas, raids — ordenável |
| 📰 Notícias            | Feed de updates, wipes e eventos |
| 👤 Perfil              | Estatísticas do jogador logado |
| 🔧 Painel Admin        | Gestão de usuários e servidores (acesso: role=admin) |

---

## 🗄️ Banco de Dados

SQLite — arquivo criado automaticamente em `database/firethrone.db`

Tabelas:
- `users` — jogadores cadastrados
- `servers` — servidores da rede
- `store_items` — itens da loja
- `purchases` — histórico de compras
- `leaderboard` — estatísticas de jogo
- `news` — notícias e atualizações

---

## 🌐 Endpoints da API

```
GET  /api/servers           → lista de servidores
GET  /api/store             → itens da loja
POST /api/store/buy         → comprar item
GET  /api/leaderboard       → ranking (sort=kills|deaths|hours_played|raids_won)
GET  /api/news              → notícias
POST /api/auth/login        → login
POST /api/auth/register     → cadastro
POST /api/auth/logout       → logout
GET  /api/auth/me           → usuário logado
GET  /api/admin/stats       → stats do painel (admin)
GET  /api/admin/users       → lista usuários (admin)
PUT  /api/admin/users/:id   → editar usuário (admin)
GET  /api/admin/servers     → gerenciar servidores (admin)
```

---

## 🎨 Tecnologias

- **Frontend:** HTML5 + CSS3 + JavaScript puro
- **Backend:** Python 3 + Flask
- **Banco:** SQLite (fácil, sem instalação extra)
- **Fontes:** Bebas Neue + Rajdhani + Share Tech Mono

---

## 📦 Para produção futura

- Trocar SQLite por PostgreSQL / MySQL
- Adicionar integração com Steam API para autenticação real
- Implementar integração com Battlemetrics para status ao vivo dos servidores
- Adicionar sistema de pagamento (Mercado Pago / Stripe)
- Deploy: Railway, Render, ou VPS própria
