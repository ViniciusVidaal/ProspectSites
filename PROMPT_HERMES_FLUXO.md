# Fluxo Hermes + ProspectSites — prompt para o Codex do Hermes

```text
Você está no projeto Hermes. Prepare o fluxo comercial abaixo integrando o
ProspectSites por API e usando Playwright somente para a Análise Google e o
download do PNG original. Antes de executar, inspecione o projeto e adapte aos
pontos reais de extensão. Preserve sessões, credenciais, prompts, memória,
automações, mensagens e pontes existentes. Use uma integração isolada e
desativada por padrão. Não modifique o núcleo do Hermes se não for indispensável;
nesse caso apresente o trecho, risco e reversão e aguarde autorização.

A equipe inicia manualmente o contato. Abrir o WhatsApp no ProspectSites marca
o lead como enviado; não prova que uma mensagem foi enviada. Não crie histórico
ou afirme envio sem evidência. O Hermes mantém as conexões e responde no mesmo
WhatsApp que recebeu a mensagem. O ProspectSites não envia mensagens.

CONEXÃO

O backend do ProspectSites usa PROSPECTSITES_CRM_URL e uma chave privada
PROSPECTSITES_CRM_SECRET, enviada no cabeçalho X-Hermes-Secret. O site usa uma
URL de frontend separada. Não invente endereços nem compartilhe ou registre
segredos. Confira a versão e as rotas no contrato em
HERMES_INTEGRATION_CONTRACT.md do repositório ProspectSites. Se URL ou chave
não estiverem configuradas, mantenha a integração desligada e informe o que
falta. Se o sistema tiver login, use apenas uma conta autorizada.

1. IDENTIFICAR O LEAD PELA API

Ao receber uma resposta individual, normalize o número com DDI e consulte
POST /api/crm/integrations/hermes/prospects/lookup com {"phone":"..."}.
Ignore grupos, listas de transmissão e identificadores que não sejam telefone
confirmado. Verifique matches e requires_confirmation. Se não houver exatamente
um resultado confiável, se a busca estiver incompleta ou se o telefone estiver
ausente, pare a automação desse lead e peça ajuda à equipe, sem inventar uma
empresa nem revelar dados de outro cliente. Guarde place_id, nome, telefone e
o identificador da conexão WhatsApp. A busca ativa é limitada aos primeiros
500 registros e arquivados antigos podem não ter telefone: não trate uma
ausência ou correspondência parcial como prova de identidade.

Entenda o segmento apenas a partir de dados confiáveis da empresa. Se houver
dúvida necessária para a conversa, pergunte de modo natural sobre a atividade
ou produto principal. Não afirme informações incertas.

2. CARD NO KANBAN PELA API

Consulte GET /api/crm/integrations/hermes/stages para obter as etapas realmente
salvas. O fluxo pretendido, nesta ordem, é:
- Aguardando resposta: a equipe fez o contato e aguarda retorno.
- Em atendimento: o cliente respondeu e o atendimento começou.
- Análise aceita: o cliente aceitou a análise gratuita.
- Em negociação: após a análise, a conversa comercial avançou.
- Encaminhado à equipe: há interesse e uma pessoa assumirá o atendimento.
- Perdido: oportunidade encerrada; não usar somente por falta de resposta.

Esses nomes ainda precisam ser confirmados no quadro de produção. Nunca crie,
renomeie ou exclua colunas automaticamente. Se a etapa desejada não existir,
pare e avise a equipe. Não mapeie uma venda como concluída por conta própria.

Para criar/localizar o card e movê-lo, envie POST
/api/crm/integrations/hermes/events com event=lead.stage.changed, event_id
único e estável, instance identificado, e data contendo phone, lead_place_id,
stage_id e reason. Use o place_id confirmado pela busca. Repita o MESMO
event_id ao retentar; confira accepted, duplicate e o estado retornado.
Consulte o estado novamente após alteração quando a API permitir. Falhas não
podem bloquear o WhatsApp; mantenha fila própria e não perca eventos pendentes
após reinício. Sem alteração confirmada, não afirme ao operador que moveu.

Não envie mensagens, histórico, QR Code ou autenticação do WhatsApp ao CRM.
Apenas os dados necessários para identificar e atualizar o card.

3. OFERECER A ANÁLISE

Conduza o atendimento conforme as regras existentes do Hermes. Ofereça uma
análise gratuita e só inicie depois da aceitação explícita do cliente. Ao
aceitar, mova o card para Análise aceita se essa etapa existir.

4. PLAYWRIGHT PARA A IMAGEM ORIGINAL

Use um navegador isolado e autorizado na VPS para abrir o frontend. Vá à aba
Análise Google, escolha Lead existente, busque pelo nome ou telefone, carregue
mais perfis arquivados quando necessário e selecione pelo place_id confirmado
pela API, não apenas pelo texto da empresa. Confira nome e telefone na tela;
se o número estiver ausente ou não corresponder, ou se o lead não aparecer,
pare e solicite ajuda. Não selecione outra empresa por aproximação.

Clique em Usar este lead e confira a empresa na tela seguinte. Não altere as
configurações. Clique uma única vez em Iniciar análise e acompanhe o estado de
carregamento até concluir ou surgir erro. Aguarde até 3 minutos; use esperas por
elementos/estado e não apenas atrasos fixos. Se ocorrer timeout, falha de rede,
modo demonstração ou relatório parcial sem dados suficientes, não envie nada;
verifique o estado antes de repetir, pois outra execução pode gastar cota.
Não dispare análises duplicadas por causa de uma página lenta.

No relatório, confirme novamente nome e identificador; o elemento .ga-report
possui data-lead-place-id e data-demo. Exija que o identificador seja igual ao
place_id confirmado e data-demo seja false. Antes de baixar, confira a
correspondência com a conversa e que o cliente aceitou a análise. Use o botão
Baixar imagem PNG e aguarde o evento de download terminar; valide que o arquivo
é PNG, não está vazio e corresponde à empresa. Este é o PNG original do site,
não o resumo alternativo da API. Se falhar ou estiver ambíguo, pare e avise.

Após todas as conferências, o Hermes pode enviar o PNG ao cliente pelo mesmo
WhatsApp e para o mesmo contato. Nunca enviar durante testes. Não criar atalhos
que enviem uma análise demonstrativa ou de outra empresa.

5. ANDAMENTO E TRANSFERÊNCIA

Quando a conversa comercial avançar, use Em negociação. Quando houver interesse
real e uma pessoa da equipe for avisada para assumir, use Encaminhado à equipe.
Notifique a equipe com o mínimo necessário: empresa, telefone, conexão utilizada,
resumo e próximo passo. Não afirme venda, pagamento ou contratação sem prova.
Se o lead não responder, não marque Perdido automaticamente: aguarde regra da
equipe. Evite respostas simultâneas depois que o atendimento for transferido.

6. VALIDAÇÃO E ENTREGA

Antes de ativar, teste com dados fictícios e um único WhatsApp piloto. Não envie
mensagens reais, não reinicie serviços e não publique sem aprovação explícita.
Verifique preservação do Hermes, autenticação, duplicidade, divergência de
telefone, etapas inexistentes, timeout, falha do navegador, análise em modo
demonstração, correspondência do relatório e download do PNG. Informe o que
passou, o que depende de conexão real, arquivos alterados e plano de reversão.
Não compartilhe senhas, tokens, QR Codes ou dados reais na resposta.
```

Este roteiro descreve a integração desejada; a publicação do ProspectSites, a
configuração da chave e a conexão com a VPS do Hermes ainda precisam ser
confirmadas antes de qualquer ativação.
