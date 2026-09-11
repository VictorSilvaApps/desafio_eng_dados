# Métricas e KPIs — Desafio 1 (RF12)

O RF12 exige no mínimo **2 métricas operacionais** e **2 KPIs de decisão**,
e para cada KPI exige seis campos: nome, objetivo, fórmula, fonte,
periodicidade e interpretação. Todos estão expostos como views em
[`sql/consultas.sql`](../sql/consultas.sql), que é o que o Superset lê.

**A diferença entre os dois grupos**, para a apresentação: métrica
operacional descreve o que aconteceu; KPI existe para embasar uma
decisão. Se ninguém muda nada ao ver o número, ele é métrica, não KPI.

---

## Métricas operacionais

### M1 — Volume de interações

| Campo | |
|---|---|
| **Objetivo** | Acompanhar o uso da plataforma ao longo do tempo e detectar queda ou pico anormal. |
| **Fórmula** | `COUNT(*)` de `interacao`, agrupado por dia e por `tipo_interacao`. |
| **Fonte** | `desafio.interacao` · view `vw_metrica_volume_interacoes`. |
| **Periodicidade** | Diária. |
| **Interpretação** | Série temporal. O que importa é a variação, não o valor absoluto. A base cobre 2026-01-01 a 2026-08-25. |

### M2 — Consumo por categoria

| Campo | |
|---|---|
| **Objetivo** | Saber onde o tempo dos usuários é gasto, por assunto. |
| **Fórmula** | `COUNT(*)`, `COUNT(DISTINCT conteudo_id)`, `SUM(tempo_consumido)` e `AVG(tempo_consumido)` por categoria. |
| **Fonte** | `interacao` × `conteudo` × `categoria` · view `vw_metrica_consumo_por_categoria`. |
| **Periodicidade** | Semanal. |
| **Interpretação** | Volume alto com tempo médio baixo indica conteúdo que atrai clique mas não retém. |

---

## KPIs de decisão

### KPI 1 — Taxa de conclusão

| Campo | |
|---|---|
| **Nome** | Taxa de conclusão |
| **Objetivo** | Identificar onde o aluno começa e não termina, para priorizar revisão de material. |
| **Fórmula** | `conclusões ÷ inícios × 100`, por categoria e nível. `NULLIF` protege contra categoria sem nenhum início. |
| **Fonte** | `desafio.interacao`, tipos `início` e `conclusão` · view `vw_kpi_taxa_conclusao`. |
| **Periodicidade** | Mensal. |
| **Interpretação** | Quanto maior, melhor. A categoria com a menor taxa é a primeira candidata a revisão. Na base atual há 187 inícios e 154 conclusões no total; por categoria o número fica pequeno, então leia a tendência, não a casa decimal. |

> **Limitação honesta.** Nem toda conclusão é precedida de um `início`
> registrado, então a razão pode passar de 100% numa categoria. Isso é
> propriedade do dado, não defeito da view — registrar como observação na
> apresentação em vez de truncar o valor e esconder o problema.

### KPI 2 — Cobertura do catálogo

| Campo | |
|---|---|
| **Nome** | Cobertura do catálogo |
| **Objetivo** | Medir quanto do que foi publicado é efetivamente consumido, para orientar curadoria. |
| **Fórmula** | `conteúdos com ao menos uma interação ÷ total de conteúdos × 100`, por categoria. |
| **Fonte** | `desafio.conteudo` com `LEFT JOIN` em `interacao` · view `vw_kpi_cobertura_catalogo`. |
| **Periodicidade** | Mensal. |
| **Interpretação** | Quanto maior, melhor. Hoje **625 dos 1000** conteúdos têm interação (62,5%), e **135** não têm interação nem comentário. Categoria com cobertura baixa tem material parado: ou promove, ou despublica. |

---

## Um indicador que deliberadamente **não** usamos

**Avaliação média.** É a escolha óbvia para "qualidade" e seria um erro
aqui. A distribuição das notas é enviesada para cima: média **4,15**, com
**79%** das notas em 4 ou 5 (464 notas 5, 327 notas 4, contra 43 notas 2 e
32 notas 1). Um indicador assim varia pouco entre categorias e não
discrimina nada — o painel mostraria "4,1" em toda parte e ninguém
decidiria coisa alguma com isso.

Quando o assunto for qualidade percebida, use a **proporção de notas ≤ 2**
ou a **distribuição inteira**. A agregação por categoria no MongoDB
(`quantidade_por_categoria`, em [`mongodb/consultas.js`](../mongodb/consultas.js))
já devolve `insatisfeitos` junto da média, exatamente por isso.

---

## As duas perguntas de negócio do dashboard (RF13)

O RF13 exige que o painel responda duas perguntas definidas pela equipe.
São estas, cada uma amarrada a um KPI acima:

1. **Em qual categoria e nível os alunos mais abandonam o conteúdo?**
   Respondida pelo KPI 1 no gráfico de barras, com os filtros de categoria
   e nível aplicados.
2. **Que parte do catálogo está publicada e não é consumida?**
   Respondida pelo KPI 2 nos cartões e no gráfico de barras de cobertura.
