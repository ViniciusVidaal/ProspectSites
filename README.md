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
```

O frontend usa:

```text
VITE_API_URL=https://seu-backend.onrender.com
```
# CNPJ gratuito pelo Google Colab

O painel possui o botão **Processar CNPJs no Colab**. Ele abre o notebook
`colab/ProspectSites_CNPJ_Receita.ipynb`, que usa os Dados Abertos de CNPJ da
Receita Federal e grava correspondências fortes na coluna `CNPJ` da planilha.

O processamento não exige SerpApi. Os ZIPs grandes são processados um por vez
no armazenamento temporário do Colab; o Google Drive recebe apenas o banco
regional reduzido e o CSV de sugestões ambíguas para revisão.
