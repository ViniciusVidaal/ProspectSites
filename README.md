# Prospect Sites

Painel React + agente Python local para identificar anúncios patrocinados, enriquecer
empresas no Google Places, deduplicar leads no Google Sheets e abrir uma fila
confirmada de mensagens no WhatsApp Web.

## Configuração

1. Compartilhe a planilha com o e-mail da conta de serviço como **Editor**.
2. Copie `.env.example` para `.env` e preencha as três variáveis obrigatórias.
3. Instale e inicie o backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
uvicorn backend.main:app --reload
```

4. Em outro terminal, inicie o painel:

```powershell
cd frontend
npm install
npm run dev
```

Abra `http://localhost:5173`. No primeiro disparo, faça login no WhatsApp Web.
A sessão fica apenas na pasta local `whatsapp-profile`, ignorada pelo Git.

## Produção

O frontend pode ser publicado na Vercel com `VITE_API_URL` apontando para uma URL
HTTPS do agente. O agente precisa rodar em uma máquina com navegador e acesso ao
arquivo da conta de serviço; ele não deve ser implantado na Vercel.

O HTML do Google e do WhatsApp muda com frequência. Se a coleta ou o clique de
envio deixar de funcionar, atualize os seletores em `backend/scraper.py` e
`backend/whatsapp.py`.
