# Levantamento de Requisitos — Desafio Prático 1

**Pipeline de Recomendação e Dashboard de Conteúdos Educacionais**
FIC_DEV — Programador de Sistemas com IA · Fundamentos de Dados para IA
Enunciado v1.0/2026 · Equipe de 3 · Carga recomendada: 12 h
Levantamento feito em 11/09/2026.

---

## 1. Fontes e procedência

Pasta do Drive: `https://drive.google.com/drive/folders/1RNEcsMZpaONJHFJ2ucxc-ItQ53oi49Sn`
(pública, nome `Desafio_1_Tarde`). Os cinco arquivos estão copiados em
[`documentacao/fontes/`](fontes/) para o levantamento ser rastreável até a origem.

| Arquivo | Papel |
|---|---|
| `Desafio_1_Fundamentos_de_Dados_para_IA.docx` | **Enunciado — fonte autoritativa** |
| `Desafio_1_Fundamentos_de_Dados_para_IA.pdf` | Enunciado, **incompleto** (ver aviso abaixo) |
| `catalogo.csv` | Fonte 1 — catálogo de conteúdos |
| `interacoes.json` | Fonte 2 — interações dos usuários |
| `comentarios.json` | Fonte 3 — comentários e avaliações |

> ### ⚠️ O PDF está truncado
> O PDF tem 8 páginas e **termina no meio do RF13**. Faltam nele: o restante do RF13
> (a composição mínima do dashboard), o **RF14 inteiro**, e as seções **8 a 12** —
> arquitetura mínima, práticas de DataOps, registro do uso de IA, lista de entregáveis e
> formato da apresentação.
>
> **Quem trabalhar a partir do PDF vai entregar o desafio incompleto.** Use o `.docx`.

---

## 2. Situação-problema

Uma plataforma fictícia de educação tem seus dados espalhados em arquivos de formatos
diferentes. Isso impede identificar os conteúdos mais procurados, analisar comportamento dos
usuários, avaliar a qualidade do material e recomendar conteúdos relacionados.

**Produto esperado:** um pipeline reprodutível que integre ingestão, PostgreSQL, MongoDB,
armazenamento vetorial, recomendações e um dashboard no Apache Superset.

---

## 3. Requisitos funcionais

Coluna "Pronto quando" = critério objetivo de aceite. Coluna "Onde" = módulo previsto na
arquitetura proposta na seção 8 deste documento.

| RF | Título | O que o sistema deve fazer | Pronto quando | Onde |
|---|---|---|---|---|
| **RF01** | Inicialização e configuração | Rodar por `python -m src.main`; ler config JSON/YAML com caminhos de entrada e parâmetros de conexão de PostgreSQL, MongoDB e banco vetorial; manter senhas fora do código; anunciar início e término | `python -m src.main` roda ponta a ponta sem argumento obrigatório; `grep` por senha no código não retorna nada | `src/config.py`, `src/main.py`, `config.yaml`, `.env` |
| **RF02** | Leitura das fontes | Ler no mínimo o CSV do catálogo, o JSON de interações e o JSON de comentários; informar nome e quantidade de registros de cada fonte | Log mostra as 3 fontes com contagem (1000 cada) | `src/ingestao/leitura.py` |
| **RF03** | Validação | Classificar **cada** registro em válido / inválido / incompleto / duplicado e registrar o **motivo** dos não-válidos. Cobrir: campos obrigatórios, validade de identificadores, formato de datas, domínio de categóricos, faixa das avaliações, numéricos negativos ou incompatíveis, e referências a usuários/conteúdos inexistentes | Todo registro sai com uma classificação; todo não-válido sai com motivo textual; ver **G2** | `src/ingestao/validacao.py` |
| **RF04** | Tratamento e padronização | Remover espaços, uniformizar maiúsculas/minúsculas, padronizar categorias/tipos/níveis, converter datas para formato único, converter numéricos, tratar ausentes, eliminar duplicidades, **preservar os arquivos originais** e gravar os tratados em diretório próprio | `dados/brutos/` intacto (hash igual ao original); `dados/processados/` populado; decisões registradas no README | `src/ingestao/tratamento.py` |
| **RF05** | Resumo da ingestão | Gerar resumo **em JSON** com: lidos, válidos, inválidos, incompletos, duplicados, corrigidos, carregados por banco, e tempo total | Arquivo JSON gravado com as 8 chaves e exibido no console | `src/ingestao/resumo.py` |
| **RF06** | Persistência no PostgreSQL | Entidades no mínimo equivalentes a **usuário, conteúdo, categoria, interação, recomendação**; PKs, FKs, bloqueio de duplicidade de identificador, integridade dos relacionamentos, **carga em transação**, consulta dos registros. Entregar o script SQL de criação | `sql/criar_banco.sql` cria tudo do zero; `INSERT` duplicado é rejeitado pela constraint; falha no meio da carga faz rollback | `sql/criar_banco.sql`, `src/carga/postgres.py` |
| **RF07** | Persistência no MongoDB | Guardar comentários/avaliações; cada documento mantém identificação de usuário e conteúdo. Permitir: inserir, consultar comentários de um conteúdo, localizar por tag, filtrar por nota, agregar quantidade por categoria. **Justificar a escolha** do que foi para o Mongo | As 5 operações rodam e estão em `mongodb/consultas.js`; justificativa no README | `mongodb/consultas.js`, `src/carga/mongo.py` |
| **RF08** | Embeddings | Gerar representação textual de título + descrição; um embedding por conteúdo válido; associar ao `conteudo_id`; armazenar em PostgreSQL com **pgvector**; evitar duplicar embedding do mesmo conteúdo; registrar o modelo usado | 1000 vetores gravados; rodar duas vezes não duplica; coluna/tabela guarda o nome do modelo | `src/vetorial/embeddings.py` |
| **RF09** | Busca semântica | Receber consulta em linguagem natural e devolver os conteúdos mais semelhantes, com posição, id, título, categoria, tipo e similaridade/distância. Quantidade configurável. **Demonstrar 3 consultas diferentes** | 3 consultas registradas com saída; `limite` vem da config | `src/vetorial/busca.py` |
| **RF10** | Recomendações | Gerar recomendações por usuário considerando conteúdos visualizados, curtidos/bem avaliados, e **removendo os já concluídos**. Apresentar usuário, conteúdo, pontuação, posição e data de geração. Usar a fórmula do enunciado | Fórmula implementada conforme **G3/G4**; nenhum conteúdo concluído aparece na lista | `src/recomendacao/motor.py` |
| **RF11** | Persistência das recomendações | Gravar no PostgreSQL: usuário, conteúdo, pontuação final, posição, data/hora da geração | Tabela `recomendacao` populada e consultável | `sql/criar_banco.sql`, `src/recomendacao/motor.py` |
| **RF12** | Métricas e KPIs | Calcular no mínimo **2 métricas operacionais** e **2 KPIs de decisão**. Para cada KPI informar nome, objetivo, fórmula, fonte, periodicidade e interpretação. Expor os resultados em **tabelas ou views** do PostgreSQL para o Superset | `documentacao/kpis.md` com os 6 campos por KPI; views criadas | `sql/consultas.sql`, `documentacao/kpis.md` |
| **RF13** | Dashboard no Superset | Sobre os dados consolidados no PostgreSQL, no mínimo: **3 cartões de indicadores, 1 gráfico de barras, 1 gráfico de linhas, 2 filtros interativos**. Responder a **2 perguntas de negócio** definidas pela equipe. **Justificar a escolha de cada gráfico** | Dashboard montado, exportado para `dashboard/`, com evidências em `dashboard/evidencias/` | `src/dashboard/montar.py` |
| **RF14** | Registro de execução | Registrar início/término, arquivos processados, registros lidos, registros rejeitados, falhas de conexão, falhas de embedding, falhas de persistência e tempo de cada etapa principal. O registro deve permitir identificar **origem e causa provável** de cada problema | Log de uma execução completa mostra as 8 categorias | `src/log.py` |

---

## 4. Requisitos não-funcionais

**Seção 9 — DataOps.** Código em diretórios; `README.md`; dependências registradas;
parâmetros de conexão separados do código; registro das etapas; tratamento básico de erros;
instruções de reprodução; controle de versão.

**Seção 10 — Uso de IA.** A IA pode ser usada à vontade, mas a equipe continua responsável
por testar, compreender e justificar tudo. Exige um registro em `documentacao/uso_da_ia.md`
com: ferramenta utilizada, exemplos de solicitações, decisões apoiadas pela IA, **erros ou
inadequações encontrados nas respostas**, e alterações feitas pela equipe.

> O campo "erros encontrados" é obrigatório e não é retórico — precisa de exemplo real.
> Anotar as falhas **enquanto** acontecem; reconstruir isso no fim é inviável.

**Seção 11 — Entregáveis obrigatórios.** Código de ingestão; arquivos de dados; modelo
conceitual e lógico; scripts do PostgreSQL; documentos e consultas do MongoDB; busca vetorial;
recomendação; **exportação do dashboard**; documentação de instalação e execução.

**Seção 12 — Apresentação.** Máximo 10 min: 2′ problema e arquitetura · 3′ ingestão e
armazenamento · 2′ busca vetorial e recomendação · 2′ dashboard e descobertas · 1′
dificuldades, limitações e uso da IA. **Qualquer integrante** pode ser chamado a explicar
qualquer parte.

---

## 5. Perfil real dos dados

Medido sobre os arquivos em `fontes/`, não suposto. Script de conferência descrito na seção 9.

### 5.1 `catalogo.csv` — 1000 registros, 9 colunas

`conteudo_id`, `titulo`, `tipo`, `categoria`, `nivel`, `carga_horaria_min`,
`data_publicacao`, `descricao`, `autor`.

- 1000 ids únicos · **0** campos vazios · **0** datas fora do ISO · **0** cargas não-inteiras
- `carga_horaria_min`: 5 a 3590 (média 307,3)
- `data_publicacao`: 2024-01-01 a 2026-06-30
- `tipo`: Artigo 272 · Podcast 256 · Vídeo 238 · Curso 234
- `categoria`: 8 valores — IA 137, BI 136, DevOps & Cloud 132, Segurança & Governança 127,
  Eng. de Dados 125, Banco de Dados 124, Ciência de Dados 114, Programação & Software 105
- `nivel`: Intermediário 339 · Básico 338 · Avançado 323
- 20 autores distintos · `descricao` entre 286 e 348 caracteres (boa para embedding)

### 5.2 `interacoes.json` — 1000 registros

- Schema **uniforme** (1 só formato), nenhum campo ausente
- `usuario_id` 1–150, os 150 presentes · `conteudo_id` **0 órfãos**
- **0** duplicatas exatas · **2** pares (usuário, conteúdo) repetidos
- `tipo_interacao`: visualização 351 · início 187 · conclusão 154 · curtida 129 ·
  compartilhamento 90 · avaliação 89
- `data_hora` 2026-01-01 a 2026-08-25, **0** fora do ISO
- `percentual_conclusao` 1,1–100 (nenhum fora da faixa) · `tempo_consumido` 1–3367 (média 144,9)
- `avaliacao_atribuida`: **nula em 644** — legítimo, só há nota quando houve avaliação
- Coerência confirmada: as 154 interações do tipo `conclusão` têm todas `percentual = 100`
- 98 dos 150 usuários concluíram ao menos um conteúdo

### 5.3 `comentarios.json` — 1000 registros

- Schema uniforme · `conteudo_id` **0 órfãos** · `usuario_id` 1–150
- **0** duplicatas exatas · **6** pares (usuário, conteúdo) repetidos
- `avaliacao` 1–5, **enviesada para cima**: 5→464, 4→327, 3→134, 2→43, 1→32 (média **4,15**)
- `data` 2026-01-15 a 2026-08-25, **0** fora do ISO
- 62 tags distintas, **sempre exatamente 3 por documento**
- ⚠️ **Só 22 textos de comentário distintos em 1000 registros** — texto sintético reciclado

### 5.4 Cruzamentos

- 150 usuários distintos no total, **contíguos de 1 a 150**
- **625** dos 1000 conteúdos têm interação; **625** têm comentário
- **135 conteúdos não têm nem interação nem comentário** → caso de *cold start* real

---

## 6. Lacunas, ambiguidades e riscos

A parte que mais importa: o que o enunciado não resolve e a equipe precisa decidir.

### G1 — Não existe fonte de usuários
O RF06 exige a entidade `usuario`, mas **nenhum dos três arquivos fornece dados de usuário** —
só o `usuario_id` referenciado.
**Decisão proposta:** derivar a tabela dos ids distintos das duas fontes JSON (1–150, contíguos),
com `usuario_id` como PK e colunas derivadas (data da primeira e da última interação).
Registrar como decisão explícita no README — é uma lacuna do enunciado, não um esquecimento.

### G2 — Dados limpos versus RF03/RF05
Os três arquivos estão **limpos**: zero órfãos, zero duplicatas exatas, zero datas inválidas,
zero valores fora de faixa, zero campos ausentes. Rodar RF03 sobre eles produz um resumo com
todos os contadores em zero, o que **parece** validação não implementada.

**Decisão proposta**, em três partes:
1. Escrever os validadores como **funções puras** (`registro -> (classificacao, motivo)`),
   independentes de banco e de arquivo.
2. Prová-los com **testes unitários sobre registros sintéticos inválidos** — um por regra do
   RF03. É isso que demonstra a validação na apresentação, não o dado real.
3. Reportar honestamente no resumo: os **6 pares repetidos** de `comentarios.json` e os **2**
   de `interacoes.json` são os únicos candidatos reais a "duplicado".

> **Cuidado:** não classifique duplicidade pelo **texto** do comentário. Como só há 22 textos
> distintos em 1000 registros (5.3), essa regra marcaria ~978 registros como duplicados.
> A chave natural é o par **(usuario_id, conteudo_id)**.
>
> **Cuidado 2:** `avaliacao_atribuida` nula em 644 interações é **semanticamente correto**.
> Tratar como "incompleto" infla o contador e distorce o resumo.

### G3 — Faixa de classificação contraditória (RF10)
O enunciado escreve a faixa "Estável" como `40 > Pontuação < 70` — impossível de satisfazer.
Cruzando com `Positivo (>= 70)` e `Negativo (<= 40 ou Iconc = 0)`, a intenção é clara.

**Decisão proposta:**

```
Positivo   P >= 70
Estável    40 < P < 70
Negativo   P <= 40  ou  Iconc == 0
```

### G4 — `Ivis` tem duas definições no enunciado
O texto permite calcular o Índice de Visualizações "por similaridade vetorial via pgvector"
**ou** "pela proporção de tempo consumido na mesma categoria".

**Decisão proposta:** usar a **via pgvector** — centroide dos embeddings dos conteúdos que o
usuário consumiu, comparado por cosseno com o embedding do candidato, normalizado para 0–1.
Reaproveita o RF08, é mais defensável na apresentação e conecta as duas metades do desafio.
Para os usuários sem histórico, cair para a proporção por categoria e registrar o fallback.

### G5 — `src/` versus a árvore da seção 11
O RF01 determina execução por `python -m src.main`, mas a árvore sugerida na seção 11 não tem
`src/` (usa `ingestao/`, `recomendacao/`…).
**Decisão tomada:** atender os dois. Código em `src/`, e as pastas de artefato da seção 11
(`sql/`, `mongodb/`, `dashboard/`, `documentacao/`, `dados/`) mantidas como o enunciado pede.
O RF01 é requisito obrigatório; a seção 11 se diz "organização **sugerida**". Registrar no README.

### G6 — O Superset não é da equipe
O Superset roda em contêiner a partir de `/home/ficdevia-11-noturno/superset_lab/superset`,
**sem permissão de leitura** para o usuário atual. Dá para usar pela UI e pela API em `:8088`,
mas **não** para alterar o `docker-compose`. Toda a automação precisa passar pela API REST.

### G7 — Cold start na recomendação
375 conteúdos não têm interação e 135 não têm interação nem comentário (5.4). Um motor que
dependa só de histórico nunca os recomenda. A escolha por embeddings (G4) mitiga isso, porque
a similaridade textual existe para os 1000 conteúdos. Vale citar na apresentação como limitação
tratada.

### G8 — Avaliações enviesadas
Média 4,15 com 79% de notas 4 ou 5. Um KPI de "satisfação média" vai dar sempre alto e
discriminar pouco. Preferir **distribuição** ou **proporção de notas ≤ 2** como indicador de
qualidade — informa mais do que a média.

---

## 7. Infraestrutura verificada nesta máquina

Tudo abaixo foi testado em 11/09/2026, não é suposição.

| Recurso | Estado |
|---|---|
| Python | **3.14.4**, único na máquina |
| PostgreSQL | **18.6** no host, escutando em `:5432` |
| pgvector | pacote `postgresql-18-pgvector` **0.8.1** instalado; `CREATE EXTENSION vector` disponível |
| MongoDB | ativo em `127.0.0.1:27017` (`mongosh` e `mongod` no PATH) |
| Superset | ativo em `:8088` (admin/admin), em Docker, **saudável há horas** |
| Rede Superset → Postgres | alcança o host por **`172.17.0.1`** — `host.docker.internal` **não resolve**. Confirmado por teste de socket |
| venv da equipe | `desafio_eng_dados/.venv` já tem torch 2.13.0+cpu, sentence-transformers 6.0.1, pymongo 4.18.1, psycopg2-binary 2.9.13, pandas 3.0.5, scikit-learn 1.9.1, python-dotenv, pyyaml, rich, ruff |
| Modelo de embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (**384 dims**, multilíngue) **já em cache** em `~/.cache/huggingface` — não precisa baixar |

**Restrição de plataforma:** a máquina só tem Python 3.14 e não tem GPU. Pins antigos de libs
de ML não instalam — conferir wheel `cp314`/`abi3` no PyPI antes de aceitar qualquer versão, e
instalar `torch` sempre pelo índice CPU. O ambiente atual já está resolvido; o risco é criar um
venv novo do zero.

---

## 8. Arquitetura proposta

Atende o RF01 e a seção 11 ao mesmo tempo (G5).

```
desafio_dados/
├── README.md                  decisões, limitações, como reproduzir
├── config.yaml                caminhos e parâmetros (RF01)
├── .env / .env.example        segredos — .env fora do Git
├── requirements.txt
├── dados/
│   ├── brutos/                originais, intocados (RF04)
│   └── processados/           saída do tratamento (RF04)
├── src/
│   ├── main.py                orquestra as etapas  →  python -m src.main
│   ├── config.py              carrega config.yaml + .env
│   ├── log.py                 registro de execução (RF14)
│   ├── ingestao/              leitura, validacao, tratamento, resumo (RF02–RF05)
│   ├── carga/                 postgres.py, mongo.py (RF06, RF07)
│   ├── vetorial/              embeddings.py, busca.py (RF08, RF09)
│   ├── recomendacao/          motor.py (RF10, RF11)
│   └── dashboard/             montar.py (RF13)
├── sql/
│   ├── criar_banco.sql        DDL (RF06, RF11)
│   └── consultas.sql          views de KPI (RF12)
├── mongodb/consultas.js       as 5 operações do RF07
├── dashboard/
│   └── evidencias/            export do dashboard + prints (RF13)
├── documentacao/
│   ├── modelo_de_dados.pdf    conceitual e lógico
│   ├── arquitetura.pdf
│   ├── kpis.md                RF12, 6 campos por KPI
│   └── uso_da_ia.md           seção 10
└── tests/                     testes dos validadores (G2)
```

O `toolkit/` já existente neste repositório cobre boa parte do trabalho —
o mapa RF → função está em [`instrucoes_para_ia.md`](instrucoes_para_ia.md), seção 3.

---

## 9. Como reconferir este levantamento

Os números da seção 5 saem de um script de perfilamento que lê os três arquivos de
`fontes/` e imprime contagens, faixas, órfãos, duplicatas e cruzamentos. Ao regerá-lo,
confira especificamente: 1000/1000/1000 registros, 0 órfãos nas duas fontes JSON, 6 e 2 pares
repetidos, 644 avaliações nulas, e 135 conteúdos sem qualquer engajamento.

Para conferir requisito por requisito, use o `.docx` — **não** o PDF (seção 1).

---

## 10. Divisão de trabalho

Sugestão do enunciado (seção 5), com a ressalva de que **todos precisam saber explicar a
solução inteira** (seção 12).

| Integrante | Responsabilidade inicial | RFs |
|---|---|---|
| 1 | Ingestão, tratamento e PostgreSQL | RF01–RF06, RF14 |
| 2 | MongoDB, embeddings e recomendações | RF07–RF11 |
| 3 | Métricas, consultas e dashboard | RF12, RF13 |

Dependência a vigiar: o RF13 depende das views do RF12, que dependem da carga do RF06. Quem
pegar o dashboard fica bloqueado até a ingestão rodar — vale começar pelo Superset conectado a
dados de exemplo e trocar a fonte depois.
