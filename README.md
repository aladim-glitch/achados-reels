# Achados do Gênio – Reels automáticos

Gera e publica 3 Reels por dia (08h, 12h, 19h – Brasília) com produtos do catálogo de afiliados Shopee.

## Fluxo
1. **GitHub Actions** (`.github/workflows/reels.yml`, 06h): `main.py` seleciona 3 produtos
   (`selecao.py`: rodízio das 11 categorias, maior pontuação, sem repetir, preço/disponibilidade
   conferidos no catálogo ao vivo do site), escreve roteiro e legenda e renderiza (`video2.py`).
2. Os MP4 vão para um *release* do dia; `entregar.py` envia cada um ao webhook do Make.
3. **Make – cenário 1 "Receber Reels prontos"**: valida token, ignora produto já registrado
   e grava no data store "Achados do Gênio - Publicações" com status `renderizado`.
4. **Make – cenário 2 "Publicar e medir"** (a criar após conectar o Instagram): nos horários,
   publica o Reel do horário, grava link do post e, no fim do dia, atualiza métricas.

## Rodar localmente
```
python main.py --data 2026-11-30 --slot 0 --produto 58221634701
```
Requer Python 3.12, FFmpeg e `pip install -r requirements.txt`.

## Roteiros
`roteiros/<id>.json` define gancho, problema, solução, closes (`views` = recortes da foto) e capa.
O preço e o desconto NUNCA ficam no roteiro: são lidos ao vivo na hora de renderizar.
Sem roteiro, `main.py` usa um modelo automático só com dados verificáveis.

## Padrão de comunicação (todas as produções)
- Chamadas comerciais no fechamento, em rodízio (`CTAS` em `main.py`): "Confira essa oferta no link da bio!",
  "Garanta o seu! Acesse o link da bio.", "Acesse o link da bio e garanta o seu!".
- Narração e vídeo **não** mencionam afiliados nem comissões.
- Publicidade identificada de forma discreta e legível: selo "Publicidade" no topo do vídeo e no fechamento;
  legenda com "Publicidade." e `#publi`.
- Links de afiliado originais preservados: o site (link da bio) usa os links `shope.ee/an_redir` do catálogo,
  e o data store do Make registra o `link_afiliado` de cada Reel publicado.

## Licenças
- Músicas: Mixkit Stock Music Free License (uso comercial em redes sociais), ver `assets/musica/LICENCA.txt`.
- Fontes: Bricolage Grotesque e Figtree (SIL Open Font License).
- Imagens: foto oficial do anúncio na Shopee (programa de afiliados).
