# CRM Kanban — preparação para Hermes/Baileys

O CRM é um módulo isolado do ProspectSites. O Kanban, as etapas, os contatos e o
histórico funcionam sem depender de um provedor específico de WhatsApp.

## Arquitetura

- Frontend: React + Vite.
- Backend: FastAPI.
- Persistência: Firestore.
- Sessões e mensagens do WhatsApp: Hermes, usando Baileys.
- Entrada de eventos: `POST /api/crm/integrations/hermes/events`.

O ProspectSites não abre sessões Baileys e não guarda credenciais do WhatsApp. O
Hermes continua responsável por QR Code, reconexão, envio e recebimento. O CRM
recebe somente eventos normalizados.

## Variável do backend

Configure no Render e no Hermes com o mesmo valor, sem versionar o segredo:

```text
HERMES_WEBHOOK_SECRET=segredo_aleatorio_longo
```

O Hermes pode enviar o segredo no header `X-Hermes-Secret` ou em
`Authorization: Bearer <secret>`.

Quando um contato aceitar a análise gratuita, o Hermes pode recuperar o perfil
ativo ou arquivado pelo `place_id` em:

```text
GET /api/crm/integrations/hermes/prospects/{place_id}
```

O mesmo segredo é obrigatório. O endpoint é somente de leitura e não salva uma
Análise Google; ele devolve apenas os dados mínimos necessários para reabrir o
perfil na plataforma.

## Eventos aceitos

- `message.upsert`: cria/atualiza o contato e persiste uma mensagem.
- `contact.upsert`: cria/atualiza o contato mesmo sem mensagem.
- `connection.update`: atualiza o estado de uma das quatro conexões.
- `lead.stage.changed`: movimenta o cartão e registra autor e motivo.
- `heartbeat`: confirma que o Hermes está online.

Todos os eventos exigem `event_id` único. Reenvios do mesmo evento são aceitos,
mas não duplicam mensagens nem movimentações.

## Coleções do CRM

```text
crm_whatsapp_instances
crm_contacts
crm_conversations
crm_messages
crm_stages
crm_activities
crm_integration_events
```

As coleções e os fluxos das abas de prospecção, mensagens e configurações não
são modificados pelo CRM.

## Ordem de ativação

1. Validar o Kanban e suas etapas sem o Hermes.
2. Configurar `HERMES_WEBHOOK_SECRET` no backend.
3. Cadastrar apenas `whatsapp-01` no CRM.
4. Enviar eventos simulados seguindo `HERMES_INTEGRATION_CONTRACT.md`.
5. Conectar um WhatsApp real no Hermes.
6. Validar deduplicação, histórico e movimentação automática.
7. Ativar os demais números, um de cada vez.

## Limitações atuais

- O CRM ainda não envia mensagens; esta versão recebe histórico e automações.
- Arquivos de mídia são registrados pelo tipo, mas não são copiados para o CRM.
- O vínculo com leads existentes usa telefone normalizado e busca limitada.
- O Hermes/Baileys precisa permanecer em execução para manter as sessões online.
- Login e autorização de usuários do ProspectSites serão tratados em etapa própria.
