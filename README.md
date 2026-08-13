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
navegador automatizado ou serviços de pesquisa paralelos. Até três páginas de 20 perfis são
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
```

O frontend usa:

```text
VITE_API_URL=https://seu-backend.onrender.com
```
# Consulta de CNPJ pela Econodata

O botão **Processar CNPJs** envia o nome de cada empresa sem CNPJ ao endpoint
da Econodata e salva somente o número do CNPJ retornado. A chave permanece no
backend do Render e nunca é enviada ao navegador.

Configure no Render:

```text
ECONODATA_API_URL=https://endpoint-fornecido-pela-econodata
ECONODATA_API_KEY=sua-chave
ECONODATA_AUTH_HEADER=Authorization
ECONODATA_AUTH_SCHEME=Bearer
ECONODATA_QUERY_PARAM=nome
```

Os três últimos valores devem ser ajustados caso o exemplo de requisição
fornecido pela Econodata utilize outro cabeçalho, esquema ou nome de parâmetro.
