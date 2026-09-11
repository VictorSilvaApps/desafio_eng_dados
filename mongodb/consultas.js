// As cinco operações do RF07, em mongosh.
//
// Uso:
//   mongosh desafio --file mongodb/consultas.js
//
// Os mesmos comandos estão em src/carga/mongo.py, que é o caminho que o
// pipeline executa. Este arquivo existe porque o RF07 pede as consultas
// entregues como script, e porque é aqui que dá para experimentar sem
// subir o pipeline inteiro.
//
// O que está nesta coleção e por quê: só comentários. São o único dado do
// desafio com forma de documento (texto livre + array de tags). Catálogo,
// interações e recomendações ficaram no PostgreSQL, onde precisam de
// chave estrangeira e JOIN. Cada documento traz `categoria` e `tipo`
// copiados do catálogo — desnormalização deliberada, sem a qual a
// operação 5 dependeria de dado do outro banco.

const colecao = db.comentarios;

print('=== documentos na coleção: ' + colecao.countDocuments({}) + ' ===\n');


// ── 1. Inserir ───────────────────────────────────────────────
// O `_id` determinístico torna a reinserção idempotente: rodar duas vezes
// substitui o documento em vez de criar um segundo.
print('1. inserir (upsert de um comentário de exemplo)');
printjson(colecao.replaceOne(
    { _id: '999-999' },
    {
        _id: '999-999',
        usuario_id: 999,
        conteudo_id: 999,
        avaliacao: 5,
        comentario: 'Documento de exemplo inserido por mongodb/consultas.js.',
        tags: ['exemplo', 'teste'],
        data: '2026-09-11',
        categoria: 'Engenharia de Dados',
        tipo: 'Artigo',
        titulo: 'Exemplo'
    },
    { upsert: true }
));


// ── 2. Consultar os comentários de um conteúdo ───────────────
// O id é escolhido a partir do próprio dado: nem todo conteúdo tem
// comentário (625 dos 1000 têm), e fixar um id no script faria a
// demonstração sair vazia dependendo do que foi carregado.
const maisComentado = colecao.aggregate([
    { $group: { _id: '$conteudo_id', n: { $sum: 1 } } },
    { $sort: { n: -1 } },
    { $limit: 1 }
]).toArray()[0];

print('\n2. comentários do conteudo_id = ' + maisComentado._id +
      ' (' + maisComentado.n + ' comentários)');
colecao.find({ conteudo_id: maisComentado._id })
       .sort({ data: -1 })
       .forEach(d => print('   [' + d.avaliacao + '] usuário ' + d.usuario_id +
                           ' — ' + d.comentario));


// ── 3. Localizar por tag ─────────────────────────────────────
// `tags` é array; o índice sobre array resolve sem $unwind.
print('\n3. comentários com a tag "lgpd" (5 primeiros)');
colecao.find({ tags: 'lgpd' })
       .limit(5)
       .forEach(d => print('   conteudo ' + d.conteudo_id +
                           ' | tags: ' + d.tags.join(', ')));


// ── 4. Filtrar por nota ──────────────────────────────────────
// Notas 1 e 2 interessam mais que a média: a distribuição é enviesada
// para cima (média 4,15, com 79% das notas em 4 ou 5).
print('\n4. avaliações baixas (1 a 2), 5 primeiras');
colecao.find({ avaliacao: { $gte: 1, $lte: 2 } })
       .limit(5)
       .forEach(d => print('   [' + d.avaliacao + '] ' + d.categoria +
                           ' — ' + d.comentario.substring(0, 60)));

print('\n   total de avaliações baixas: ' +
      colecao.countDocuments({ avaliacao: { $lte: 2 } }));


// ── 5. Agregar quantidade por categoria ──────────────────────
print('\n5. comentários por categoria');
colecao.aggregate([
    { $group: {
        _id: '$categoria',
        comentarios: { $sum: 1 },
        nota_media: { $avg: '$avaliacao' },
        insatisfeitos: { $sum: { $cond: [{ $lte: ['$avaliacao', 2] }, 1, 0] } }
    }},
    { $project: {
        _id: 0,
        categoria: '$_id',
        comentarios: 1,
        nota_media: { $round: ['$nota_media', 2] },
        insatisfeitos: 1
    }},
    { $sort: { comentarios: -1 } }
]).forEach(r => print('   ' + r.categoria.padEnd(26) +
                      ' ' + String(r.comentarios).padStart(5) +
                      ' comentários | média ' + r.nota_media +
                      ' | ' + r.insatisfeitos + ' nota <= 2'));


// Remove o documento de exemplo da operação 1, para a coleção voltar ao
// estado carregado pelo pipeline.
colecao.deleteOne({ _id: '999-999' });
print('\n=== fim ===');
