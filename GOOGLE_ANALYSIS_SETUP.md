# Análise Google — ProspectSites

Módulo isolado para buscar perfis públicos, aplicar metodologia própria e versionada, comparar concorrentes, salvar histórico e gerar uma imagem vertical para compartilhamento.

## Estado funcional

- Busca por nome, cidade e refinamento; seleção explícita da empresa.
- Início pelo cadastro de um lead existente, sem repetir a busca de seleção.
- Palavra-chave, localização e profundidade editáveis antes da comparação.
- Trabalho assíncrono com etapas reais e bloqueio de clique duplicado para a mesma análise em andamento.
- Motor de pontuação determinístico `1.0.0`, separado da interface.
- Nota normalizada sobre itens avaliáveis e cobertura mínima de 60%.
- Checklist com 16 itens e cinco estados possíveis.
- SerpApi para detalhes, concorrência, avaliações recentes/respostas e postagens.
- Concorrência limitada ao bairro extraído do endereço; resultados de outras regiões são descartados.
- Histórico no Firestore em `google_profile_analyses`.
- PNG vertical de 1080 × 1350 px, gerado somente no navegador para download e envio pelo WhatsApp.
- O PNG destaca sempre o site profissional e mais uma melhoria real identificada no checklist.
- A imagem não é enviada ao backend nem armazenada no Firestore; o banco guarda apenas os dados estruturados da análise.
- Vínculo manual com lead, sem envio automático de WhatsApp ou e-mail.
- Modo de demonstração identificado quando a chave SerpApi não está configurada.

## Configuração

Adicione somente no backend:

```env
SERPAPI_API_KEY=
SERPAPI_TIMEOUT_SECONDS=30
```

A chave é usada somente pelo servidor e nunca é devolvida pela API nem registrada em logs. A variável `SERPAPI_API_KEY` permanece como fallback; chaves cadastradas pela tela são guardadas na coleção protegida do backend e a listagem pública retorna somente nome, status e uso. Sem nenhuma chave disponível, `/api/google-analysis/capabilities` informa `live_configured: false` e a interface usa fixtures fictícias.

Também é possível cadastrar várias chaves em **Configurações > SerpApi**. Quando uma chave cadastrada atinge o limite ou é recusada, o backend ativa a próxima disponível e repete a consulta. O mesmo mecanismo existe separadamente para **Google Maps/Places**. Falhas comuns de rede não desativam chaves.

## Matriz de cobertura da SerpApi

| Campo ou métrica | Engine/endpoint | Campo real | Limitações | Paginação e custo |
|---|---|---|---|---|
| Busca e seleção | `engine=google_maps&type=search` | `local_results[].title`, `type`, `address`, `rating`, `reviews`, `place_id`, `data_id` | Resultado depende da consulta, localização e momento | Uma busca; o Maps pagina com `start` e exige coordenadas `ll` nas páginas seguintes. A v1 usa a primeira página |
| Detalhes do perfil | `engine=google_maps` com `place_id` ou `type=place` | `place_results`: descrição, telefone, site, horário, endereço, categorias, extensões, imagens | Campos não devolvidos não confirmam ausência; imagens são amostra, não contagem total | Uma busca por análise |
| Posição e concorrentes | `engine=google_maps&type=search` | `local_results[].position`, `rating`, `reviews`, IDs | Uma consulta não representa toda a cidade; anúncios vêm separados e não entram na amostra | Uma busca por análise; v1 usa até os resultados presentes na primeira página |
| Avaliações recentes e respostas | `engine=google_maps_reviews&sort_by=newestFirst&num=20` | `reviews[].iso_date`, `response`, `rating`, `review_id` | O total retornado pode variar; release notes recentes registram correções de paginação e inconsistências | Uma busca por análise; até 20 avaliações na amostra |
| Postagens | `engine=google_maps_posts` | `posts[].posted_at`, `title`, `description` | Exige `data_id`; sem identificador o item fica não verificável | Uma busca por análise; 10 posts por página |
| Produtos e serviços | Não coberto com garantia | — | Menu e opções de serviço não provam cobertura completa de produtos/serviços | Estado `unknown` |
| Fotos | Place Results | `images[]` | A lista não é tratada como contagem total | Estado `unknown`, com tamanho da amostra apenas como evidência |
| Verificação | Não coberto com evidência explícita | — | Resposta do proprietário não prova verificação | Estado `unknown` |
| Área de serviço | Parcial | endereço e campos do Place Result | Endereço ausente não é penalizado, pois pode ser empresa de área de serviço | Estado `unknown` sem evidência suficiente |

Fontes oficiais consultadas em 16/11/2026: SerpApi Google Maps Local Results, Place Results, Google Maps Reviews, Google Maps Posts e página de preços. Os termos e limites podem mudar.

## Consumo e estimativa de custo

Cada consulta bem-sucedida consome uma busca do plano, salvo quando a SerpApi serve um cache gratuito compatível.

- Busca para selecionar a empresa: 1 busca.
- Detalhes do perfil: 1 busca.
- Comparação competitiva: 1 busca.
- Avaliações recentes: 1 busca.
- Postagens: 1 busca.
- Fluxo completo: até **5 buscas**.
- Início por lead já identificado: até **4 buscas**.

Preços públicos consultados:

| Plano | Buscas/mês | Mensalidade | Custo nominal por busca | Fluxo completo nominal |
|---|---:|---:|---:|---:|
| Free | 250 | US$ 0 | US$ 0 | até 50 análises completas, sujeito ao limite/hora |
| Starter | 1.000 | US$ 25 | US$ 0,025 | aproximadamente US$ 0,125 |
| Developer | 5.000 | US$ 75 | US$ 0,015 | aproximadamente US$ 0,075 |
| Production | 15.000 | US$ 150 | US$ 0,010 | aproximadamente US$ 0,050 |

O relatório registra `searches_used`. A estimativa exibida no backend usa o equivalente ao Starter; o custo efetivo depende do plano, cache e franquia. Nenhuma contratação, pagamento ou alteração de plano foi realizada.

## Metodologia 1.0.0

Pesos, total 100: categoria principal 8; categorias adicionais 5; descrição 7; telefone 6; site 6; horário 7; localização/área de serviço 6; produtos e serviços 7; atributos 4; fotos 7; verificação 5; postagens 6; nota 7; volume de avaliações 7; recência 7; respostas 5.

Estados avaliáveis recebem fator `1` (Em dia), `0,5` (Pode melhorar) ou `0` (Ausência confirmada). `Não foi possível verificar` e `Não se aplica` saem do denominador.

```text
nota = 100 × pontos obtidos / pontos máximos avaliáveis
cobertura = pesos avaliáveis / 100
```

Abaixo de 60% de cobertura, a interface mostra “dados insuficientes para uma nota confiável”. Os pesos são da ProspectSites e não são fatores oficiais do Google.

## Falhas parciais

Detalhes do perfil são necessários para criar o relatório real. Concorrência, avaliações e postagens são consultadas separadamente; se uma delas falhar, o relatório preserva os outros dados, marca os itens afetados como não verificáveis e registra a limitação.

## Persistência, retenção e isolamento

O projeto atual não possui autenticação de usuário nem modelo de contas. Para não criar uma falsa promessa de isolamento, esta versão usa `tenant_key: default`, igual ao acesso global já existente. Antes de oferecer a aplicação a múltiplas contas, implemente autenticação/autorização e derive `tenant_key` exclusivamente no servidor.

Os termos de retenção e exportação da SerpApi ainda precisam de validação jurídica/contratual antes do uso comercial. Não trate o histórico como autorização para armazenamento indefinido.

## Limitações atuais

- Integração real não foi executada sem uma chave SerpApi configurada.
- O Maps Search da v1 usa a primeira página e oferece profundidade de 10 ou 20 resultados; páginas adicionais exigem coordenadas `ll`.
- A situação de verificação, total de fotos e produtos/serviços permanecem desconhecidos sem evidência adequada.
- Jobs e deduplicação em andamento vivem no processo. Reiniciar o backend perde o estado transitório; relatórios salvos permanecem no Firestore.
- Não existe autenticação no projeto atual; a aba herda o mesmo acesso do painel.
- Nenhum deploy foi executado.

## Operação

1. Instale dependências com `pip install -r requirements.txt`.
2. Configure as variáveis já exigidas pelo ProspectSites e, para modo real, `SERPAPI_API_KEY`.
3. Inicie FastAPI e Vite conforme o README principal.
4. Abra **Análise Google** na barra lateral.

Nunca coloque a chave em `VITE_*`, no frontend, em commits ou relatórios.
