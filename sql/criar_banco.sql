-- Modelo de dados do Desafio 1 (RF06 e RF11).
--
-- Roda do zero e é idempotente: todo objeto usa IF NOT EXISTS, então
-- executar duas vezes não quebra nem apaga nada.
--
-- Uso:
--   psql -d "$DB_NAME" -f sql/criar_banco.sql
--
-- Para RECRIAR tudo do zero, descomente a linha abaixo. Ela apaga o
-- schema inteiro do desafio, com os dados dentro. Não afeta as tabelas
-- das aulas, que vivem no schema `public`.
--
-- DROP SCHEMA IF EXISTS desafio CASCADE;

CREATE SCHEMA IF NOT EXISTS desafio;
SET search_path TO desafio, public;

-- A extensão vive no banco, não no schema.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


-- ── categoria ────────────────────────────────────────────────
-- Dimensão derivada dos valores distintos do catálogo.
CREATE TABLE IF NOT EXISTS categoria (
    categoria_id INT  PRIMARY KEY,
    nome         TEXT NOT NULL UNIQUE
);


-- ── usuario ──────────────────────────────────────────────────
-- Lacuna G1: nenhuma das três fontes traz dados de usuário, só o
-- `usuario_id` referenciado. A entidade é exigida pelo RF06, então é
-- derivada dos identificadores distintos das duas fontes JSON. As duas
-- colunas de data são calculadas a partir da atividade do usuário.
CREATE TABLE IF NOT EXISTS usuario (
    usuario_id         INT PRIMARY KEY,
    primeira_atividade TIMESTAMP,
    ultima_atividade   TIMESTAMP
);


-- ── conteudo ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conteudo (
    conteudo_id       INT  PRIMARY KEY,
    titulo            TEXT NOT NULL,
    tipo              TEXT NOT NULL
                      CHECK (tipo IN ('Curso', 'Vídeo', 'Artigo', 'Podcast')),
    categoria_id      INT  NOT NULL REFERENCES categoria (categoria_id),
    nivel             TEXT NOT NULL
                      CHECK (nivel IN ('Básico', 'Intermediário', 'Avançado')),
    carga_horaria_min INT  NOT NULL CHECK (carga_horaria_min > 0),
    data_publicacao   DATE NOT NULL,
    descricao         TEXT,
    autor             TEXT
);

CREATE INDEX IF NOT EXISTS idx_conteudo_categoria ON conteudo (categoria_id);


-- ── interacao ────────────────────────────────────────────────
-- A UNIQUE é a mesma chave que a validação usa para detectar duplicidade.
-- Ela NÃO é (usuario_id, conteudo_id): o mesmo usuário visualizar e depois
-- concluir o mesmo conteúdo são dois fatos legítimos, não uma repetição.
-- O que caracteriza duplicata é repetir tipo e instante.
CREATE TABLE IF NOT EXISTS interacao (
    interacao_id         BIGSERIAL PRIMARY KEY,
    usuario_id           INT       NOT NULL REFERENCES usuario (usuario_id),
    conteudo_id          INT       NOT NULL REFERENCES conteudo (conteudo_id),
    tipo_interacao       TEXT      NOT NULL
                         CHECK (tipo_interacao IN ('visualização', 'início',
                                'conclusão', 'curtida', 'avaliação',
                                'compartilhamento')),
    data_hora            TIMESTAMP NOT NULL,
    tempo_consumido      NUMERIC   CHECK (tempo_consumido >= 0),
    percentual_conclusao NUMERIC   CHECK (percentual_conclusao BETWEEN 0 AND 100),
    -- NULL é legítimo e frequente (644 de 1000): só há nota quando o
    -- usuário avaliou. O CHECK só se aplica quando há valor.
    avaliacao_atribuida  NUMERIC   CHECK (avaliacao_atribuida BETWEEN 1 AND 5),
    UNIQUE (usuario_id, conteudo_id, tipo_interacao, data_hora)
);

CREATE INDEX IF NOT EXISTS idx_interacao_usuario  ON interacao (usuario_id);
CREATE INDEX IF NOT EXISTS idx_interacao_conteudo ON interacao (conteudo_id);
CREATE INDEX IF NOT EXISTS idx_interacao_tipo     ON interacao (tipo_interacao);


-- ── conteudo_embedding ───────────────────────────────────────
-- RF08. O formato das colunas (id, conteudo, embedding) é o que
-- `toolkit.vetorial.criar_tabela_vetorial` e `indexar_textos` esperam —
-- por isso `id` em vez de `conteudo_id`. Aqui ele ganha a FK que o
-- toolkit genérico não teria como criar.
-- `modelo` e `gerado_em` atendem a exigência do RF08 de registrar qual
-- modelo produziu cada vetor.
CREATE TABLE IF NOT EXISTS conteudo_embedding (
    id        INT PRIMARY KEY REFERENCES conteudo (conteudo_id),
    conteudo  TEXT,
    embedding vector(384),
    modelo    TEXT,
    gerado_em TIMESTAMP DEFAULT now()
);

-- O operador do índice precisa casar com o da consulta: um índice
-- vector_l2_ops não é usado por uma busca com <=> (cosseno).
CREATE INDEX IF NOT EXISTS idx_conteudo_embedding_embedding
    ON conteudo_embedding USING hnsw (embedding vector_cosine_ops);


-- ── recomendacao ─────────────────────────────────────────────
-- RF11. A UNIQUE inclui `gerado_em` para permitir guardar o histórico de
-- várias gerações sem conflito, mas impedir a mesma recomendação repetida
-- dentro de uma única execução.
CREATE TABLE IF NOT EXISTS recomendacao (
    recomendacao_id BIGSERIAL PRIMARY KEY,
    usuario_id      INT       NOT NULL REFERENCES usuario (usuario_id),
    conteudo_id     INT       NOT NULL REFERENCES conteudo (conteudo_id),
    pontuacao       NUMERIC   NOT NULL,
    posicao         INT       NOT NULL CHECK (posicao > 0),
    classificacao   TEXT      NOT NULL
                    CHECK (classificacao IN ('Positivo', 'Estável', 'Negativo')),
    gerado_em       TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (usuario_id, conteudo_id, gerado_em)
);

CREATE INDEX IF NOT EXISTS idx_recomendacao_usuario ON recomendacao (usuario_id);
