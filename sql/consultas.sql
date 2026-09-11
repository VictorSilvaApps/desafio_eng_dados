-- Métricas, KPIs e views de apoio ao dashboard (RF12 e RF13).
--
-- Uso:
--   psql -d "$DB_NAME" -f sql/consultas.sql
--
-- Tudo é VIEW, não tabela: o Superset consome view, e assim o número que
-- aparece no dashboard é o mesmo que o `psql` devolve, sem etapa de
-- materialização no meio para divergir.
--
-- A definição de negócio de cada KPI (objetivo, fórmula, fonte,
-- periodicidade e interpretação) está em documentacao/kpis.md.

SET search_path TO desafio, public;


-- ═══ MÉTRICAS OPERACIONAIS ═══════════════════════════════════
-- Acompanham o funcionamento da plataforma. Respondem "o que está
-- acontecendo", não "o que devemos fazer".

-- Métrica 1 — volume de interações por dia e tipo.
CREATE OR REPLACE VIEW vw_metrica_volume_interacoes AS
SELECT i.data_hora::date          AS data,
       i.tipo_interacao,
       COUNT(*)                   AS interacoes,
       COUNT(DISTINCT i.usuario_id)  AS usuarios,
       COUNT(DISTINCT i.conteudo_id) AS conteudos
  FROM interacao i
 GROUP BY 1, 2;

COMMENT ON VIEW vw_metrica_volume_interacoes IS
    'RF12 — métrica operacional: volume diário de interações por tipo.';


-- Métrica 2 — consumo por categoria.
CREATE OR REPLACE VIEW vw_metrica_consumo_por_categoria AS
SELECT cat.nome                        AS categoria,
       COUNT(*)                        AS interacoes,
       COUNT(DISTINCT i.conteudo_id)   AS conteudos_distintos,
       COUNT(DISTINCT i.usuario_id)    AS usuarios_distintos,
       ROUND(SUM(i.tempo_consumido))   AS tempo_total_min,
       ROUND(AVG(i.tempo_consumido), 1) AS tempo_medio_min
  FROM interacao i
  JOIN conteudo c   ON c.conteudo_id = i.conteudo_id
  JOIN categoria cat ON cat.categoria_id = c.categoria_id
 GROUP BY 1;

COMMENT ON VIEW vw_metrica_consumo_por_categoria IS
    'RF12 — métrica operacional: consumo agregado por categoria.';


-- ═══ KPIs DE DECISÃO ═════════════════════════════════════════
-- Existem para embasar uma escolha. Cada um responde uma pergunta que
-- leva a uma ação.

-- KPI 1 — Taxa de conclusão: conclusões / inícios.
-- Pergunta: em qual categoria o aluno começa e não termina?
-- Ação: revisar o material da categoria com a menor taxa.
CREATE OR REPLACE VIEW vw_kpi_taxa_conclusao AS
WITH eventos AS (
    SELECT cat.nome AS categoria,
           c.nivel,
           COUNT(*) FILTER (WHERE i.tipo_interacao = 'início')    AS inicios,
           COUNT(*) FILTER (WHERE i.tipo_interacao = 'conclusão') AS conclusoes
      FROM interacao i
      JOIN conteudo c    ON c.conteudo_id = i.conteudo_id
      JOIN categoria cat ON cat.categoria_id = c.categoria_id
     GROUP BY 1, 2
)
SELECT categoria,
       nivel,
       inicios,
       conclusoes,
       -- NULLIF evita divisão por zero quando a categoria não teve início.
       ROUND(100.0 * conclusoes / NULLIF(inicios, 0), 1) AS taxa_conclusao_pct
  FROM eventos;

COMMENT ON VIEW vw_kpi_taxa_conclusao IS
    'RF12 — KPI de decisão: conclusões sobre inícios, por categoria e nível.';


-- KPI 2 — Cobertura do catálogo: conteúdos com engajamento / total.
-- Pergunta: quanto do catálogo publicado está sendo efetivamente usado?
-- Ação: despublicar, revisar ou promover o que ninguém alcança.
-- Hoje 625 dos 1000 conteúdos têm interação, e 135 não têm interação
-- nem comentário — são os candidatos diretos a curadoria.
CREATE OR REPLACE VIEW vw_kpi_cobertura_catalogo AS
SELECT cat.nome                                  AS categoria,
       COUNT(*)                                  AS conteudos,
       COUNT(i.conteudo_id)                      AS com_interacao,
       COUNT(*) - COUNT(i.conteudo_id)           AS sem_interacao,
       ROUND(100.0 * COUNT(i.conteudo_id) / COUNT(*), 1) AS cobertura_pct
  FROM conteudo c
  JOIN categoria cat ON cat.categoria_id = c.categoria_id
  LEFT JOIN (SELECT DISTINCT conteudo_id FROM interacao) i
         ON i.conteudo_id = c.conteudo_id
 GROUP BY 1;

COMMENT ON VIEW vw_kpi_cobertura_catalogo IS
    'RF12 — KPI de decisão: percentual do catálogo com algum engajamento.';


-- ═══ VIEWS DE APOIO AO DASHBOARD (RF13) ══════════════════════

-- Fato desnormalizado. O Superset filtra sobre colunas de uma tabela só;
-- com JOIN dentro da view, os dois filtros interativos do RF13
-- (categoria e nível) funcionam sem SQL no painel.
CREATE OR REPLACE VIEW vw_dashboard_interacoes AS
SELECT i.interacao_id,
       i.data_hora,
       i.data_hora::date        AS data,
       i.usuario_id,
       i.conteudo_id,
       c.titulo,
       cat.nome                 AS categoria,
       c.tipo,
       c.nivel,
       c.carga_horaria_min,
       i.tipo_interacao,
       i.tempo_consumido,
       i.percentual_conclusao,
       i.avaliacao_atribuida
  FROM interacao i
  JOIN conteudo c    ON c.conteudo_id = i.conteudo_id
  JOIN categoria cat ON cat.categoria_id = c.categoria_id;

COMMENT ON VIEW vw_dashboard_interacoes IS
    'RF13 — fato desnormalizado que alimenta os gráficos e os filtros.';


-- Recomendações com título e categoria, para o painel e para conferência.
CREATE OR REPLACE VIEW vw_recomendacoes AS
SELECT r.usuario_id,
       r.conteudo_id,
       c.titulo,
       cat.nome        AS categoria,
       c.tipo,
       c.nivel,
       r.pontuacao,
       r.posicao,
       r.classificacao,
       r.gerado_em
  FROM recomendacao r
  JOIN conteudo c    ON c.conteudo_id = r.conteudo_id
  JOIN categoria cat ON cat.categoria_id = c.categoria_id;

COMMENT ON VIEW vw_recomendacoes IS
    'RF11/RF13 — recomendações persistidas, com os dados do conteúdo.';


-- Cartões de indicador do dashboard: uma linha, um número por coluna.
CREATE OR REPLACE VIEW vw_indicadores_gerais AS
SELECT (SELECT COUNT(*) FROM conteudo)                          AS conteudos,
       (SELECT COUNT(*) FROM usuario)                           AS usuarios,
       (SELECT COUNT(*) FROM interacao)                         AS interacoes,
       (SELECT ROUND(100.0
                     * COUNT(*) FILTER (WHERE tipo_interacao = 'conclusão')
                     / NULLIF(COUNT(*) FILTER (WHERE tipo_interacao = 'início'), 0), 1)
          FROM interacao)                                       AS taxa_conclusao_pct,
       (SELECT ROUND(100.0 * COUNT(DISTINCT i.conteudo_id) / COUNT(DISTINCT c.conteudo_id), 1)
          FROM conteudo c LEFT JOIN interacao i ON i.conteudo_id = c.conteudo_id)
                                                                AS cobertura_pct,
       (SELECT COUNT(*) FROM recomendacao)                      AS recomendacoes;

COMMENT ON VIEW vw_indicadores_gerais IS
    'RF13 — uma linha com os números dos cartões de indicador.';
