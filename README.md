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

O usuário escreve a mensagem no painel e clica em `Abrir WhatsApp` no lead
desejado. O WhatsApp abre com o texto preenchido, mas o envio permanece manual.
Ao abrir a conversa, o lead é marcado como enviado no Google Sheets e o contador
de mensagens do painel é atualizado.

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
```

O frontend usa:

```text
VITE_API_URL=https://seu-backend.onrender.com
```
