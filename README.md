# Prospect Sites

Painel React + API FastAPI para encontrar perfis comerciais no Google com potencial
para criação de site.

## Regra de qualificação

Uma empresa é salva quando:

- possui mais de 50 avaliações no Google;
- tem telefone cadastrado, quando disponível;
- não possui site; ou o campo de site aponta para Instagram, Facebook, LinkedIn,
  Linktree, WhatsApp, TikTok, YouTube, Google Sites, Canva Site, Wix gratuito ou
  plataforma semelhante.

A busca usa diretamente a Google Places API (New), sem scraping de anúncios,
navegador automatizado, CAPTCHA ou SerpApi. Até três páginas de 20 perfis são
consultadas por pesquisa.

## Contato

O usuário escreve a mensagem no painel e pode trabalhar de duas formas:

- `Manual`: abre diretamente o WhatsApp de cada lead;
- `Sessão assistida`: define a quantidade da sessão, o tamanho dos lotes, o
  intervalo entre conversas e a pausa entre lotes.

Na sessão assistida, o painel libera uma conversa por vez e controla a contagem
regressiva. O WhatsApp Web abre com o texto preenchido, mas a confirmação final
do envio permanece manual. O painel permite pausar, retomar ou encerrar a sessão.

## Desenvolvimento local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Em outro terminal:

```powershell
cd frontend
corepack pnpm install
corepack pnpm dev
```

## Variáveis do backend

```text
GOOGLE_PLACES_API_KEY
GOOGLE_SPREADSHEET_ID
GOOGLE_SERVICE_ACCOUNT_JSON
GOOGLE_SHEET_NAME=Leads
FRONTEND_ORIGINS=https://seu-projeto.vercel.app
ADMIN_EMAIL=seuemail@exemplo.com
ADMIN_PASSWORD_HASH=hash_argon2_da_sua_senha
JWT_SECRET=chave_aleatoria_longa
```

Gere o hash da senha localmente, depois de instalar as dependÃªncias:

```powershell
python -c "from pwdlib import PasswordHash; print(PasswordHash.recommended().hash('SUA_SENHA_AQUI'))"
```

Gere tambÃ©m uma chave aleatÃ³ria para assinar as sessÃµes:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Cadastre os dois resultados e o e-mail em `Environment` no Render. A sessÃ£o
administrativa expira depois de 12 horas. Todas as rotas de pesquisa, leads,
mÃ©tricas e arquivamento exigem autenticaÃ§Ã£o.

O frontend usa:

```text
VITE_API_URL=https://seu-backend.onrender.com
```
