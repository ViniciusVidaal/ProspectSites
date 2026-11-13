# Contrato de integração Hermes → ProspectSites CRM

Versão: `1.0`

## Prompt pronto para enviar ao Codex responsável pelo Hermes

```text
Você está trabalhando no projeto Hermes, que usa Baileys para administrar conexões
do WhatsApp. Prepare uma integração de saída com o CRM do ProspectSites sem
reescrever nem acoplar a lógica central do Hermes.

REGRA DE PRESERVAÇÃO ABSOLUTA DO HERMES:
- Esta tarefa autoriza somente preparar a integração Hermes → ProspectSites.
- Não alterar prompts, personalidade, memória, ferramentas, agentes, decisões,
  automações, banco de dados, sessões, autenticação Baileys, QR Code, envio,
  recebimento, filas existentes, painel, rotas existentes ou comportamento atual.
- Não trocar arquitetura, bibliotecas, padrões ou organização que já funcionam.
- Não renomear, mover, apagar ou refatorar arquivos existentes por conveniência.
- Preferir arquivos novos e um adaptador isolado, desligado por padrão.
- Pontos de captura devem apenas observar eventos já produzidos e encaminhar uma
  cópia normalizada; uma falha no CRM nunca pode afetar o Hermes.
- Se for tecnicamente inevitável alterar uma linha do núcleo, NÃO faça a alteração
  imediatamente. Primeiro pare e apresente: motivo, arquivo, trecho exato, risco,
  alternativa sem alteração e plano de rollback. Aguarde autorização expressa.
- Não executar deploy, migração, restart ou ativação da integração.
- Ao final, provar com testes de regressão que o Hermes continua se comportando
  exatamente como antes quando PROSPECTSITES_CRM_ENABLED=false.

Objetivo:
Criar um adaptador isolado que transforme eventos internos do Hermes/Baileys em
eventos HTTP normalizados e os envie ao ProspectSites. O Hermes continua sendo o
dono das sessões, QR Codes, reconexões, recebimento, envio e análise das conversas.
O ProspectSites será responsável pelo CRM Kanban, contatos, mensagens, etapas e
auditoria.

Endpoint configurável:
POST ${PROSPECTSITES_CRM_URL}/api/crm/integrations/hermes/events

Autenticação:
- Enviar o segredo em `X-Hermes-Secret: ${PROSPECTSITES_CRM_SECRET}`; ou
- `Authorization: Bearer ${PROSPECTSITES_CRM_SECRET}`.
- Nunca colocar URL ou segredo diretamente no código.
- Nunca imprimir segredo, credenciais Baileys ou conteúdo de autenticação nos logs.

Variáveis esperadas no Hermes:
PROSPECTSITES_CRM_URL=
PROSPECTSITES_CRM_SECRET=
PROSPECTSITES_CRM_ENABLED=false

Envelope obrigatório para todos os eventos:
{
  "event": "message.upsert",
  "event_id": "identificador-global-unico",
  "instance": "whatsapp-01",
  "occurred_at": "2026-11-13T15:00:00Z",
  "data": {}
}

Eventos aceitos:

1. message.upsert
data:
{
  "message_id": "id-estavel-da-mensagem-no-baileys",
  "phone": "5511999999999",
  "contact_name": "Nome do contato",
  "text": "Conteúdo ou legenda da mensagem",
  "from_me": false,
  "message_type": "conversation",
  "timestamp": "2026-11-13T15:00:00Z"
}

2. contact.upsert
data:
{
  "phone": "5511999999999",
  "name": "Nome do contato"
}

3. connection.update
data:
{
  "state": "connected"
}
Estados recomendados: connected, connecting, disconnected, qr_required, error.

4. lead.stage.changed
Use esse evento quando a inteligência do Hermes decidir mover o lead.
data:
{
  "phone": "5511999999999",
  "stage": "Em contato",
  "reason": "O lead respondeu e demonstrou interesse"
}
O campo stage pode receber o ID exato ou o nome exato de uma coluna existente.
Não inventar novas colunas automaticamente.

5. heartbeat
data:
{
  "status": "connected"
}

Requisitos obrigatórios:
- Criar um módulo/adaptador independente para essa integração.
- O adaptador deve ser opt-in e não modificar o caminho crítico do Hermes.
- Com PROSPECTSITES_CRM_ENABLED=false, nenhum request, timer, fila ou efeito colateral
  da integração pode ser iniciado.
- Não bloquear o processamento principal do Hermes enquanto o CRM estiver offline.
- Usar timeout curto e fila/retry com backoff exponencial.
- Considerar HTTP 202 como sucesso.
- Tratar resposta `duplicate: true` como sucesso idempotente.
- Cada evento precisa de event_id estável e único. Em retries, reutilizar o mesmo ID.
- A mensagem deve usar o ID real e estável fornecido pelo Baileys.
- Normalizar telefone para dígitos com DDI, sem `@s.whatsapp.net`.
- Ignorar grupos, broadcasts e newsletters nesta primeira versão.
- Preservar direção correta: from_me=true para mensagem enviada pelo número conectado.
- Não enviar conteúdo de credenciais, QR Code, auth state ou chaves de sessão.
- Limitar logs a event, event_id, instance, status HTTP e tentativa.
- Criar testes unitários para serialização, autenticação, retry e deduplicação.
- Manter PROSPECTSITES_CRM_ENABLED=false por padrão até a integração real ser autorizada.

Antes de implementar chamadas reais, me entregue:
1. os arquivos que serão criados ou alterados;
2. o ponto do Hermes/Baileys onde cada evento será capturado;
3. confirmação de como os quatro identificadores de instância serão mapeados;
4. qualquer incompatibilidade entre este contrato e a arquitetura atual do Hermes.
5. confirmação explícita de que nenhuma funcionalidade atual será modificada;
6. os testes de regressão que serão usados para provar essa preservação.

Não faça deploy, não altere produção e não compartilhe segredos nesta etapa.
```

## Respostas do ProspectSites

Novo evento:

```json
{
  "accepted": true,
  "duplicate": false,
  "event_id": "evt-123",
  "result": {}
}
```

Evento repetido:

```json
{
  "accepted": true,
  "duplicate": true,
  "event_id": "evt-123"
}
```

Erros de autenticação usam `401`; segredo não configurado usa `503`; payload
inválido ou etapa inexistente usa `422`.
