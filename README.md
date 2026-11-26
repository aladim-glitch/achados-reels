# Achados do Gênio – Reels automáticos

Gera e publica 3 Reels por dia (08h, 12h, 19h – Brasília) com achadinhos da Shopee, em formato de
**conteúdo de descoberta** (não panfleto), e aprende com o desempenho real de cada publicação.

## Fluxo
1. **GitHub Actions** (`reels.yml`, 05h): `main.py` seleciona 3 produtos, sorteia a variação de teste,
   busca materiais, escreve roteiro e legenda e renderiza (`video3.py`; `video2.py` é o reserva).
2. Os MP4 vão para um *release* do dia; `entregar.py` envia cada um ao webhook do Make.
3. **Make – cenário 1**: valida e grava no data store com status `renderizado`.
4. **Make – cenário 2**: nos horários, cria o contêiner, espera o processamento e publica.
5. **GitHub Actions** (`metricas.yml`, a cada 4 h): `metricas.py` coleta o desempenho em 24/48/72 h
   (`estado/metricas.json`) e escreve `estado/relatorio.md`. As próximas variações usam esses dados.

## Seleção de produtos (`selecao.py`)
Rodízio das 11 categorias; dentro da categoria vence a maior nota = pontuação do catálogo + desconto ao vivo
+ **potencial de vídeo** (utilidade prática, apelo visual, curiosidade; penaliza peças técnicas/consumíveis)
+ bônus para produto com roteiro próprio. Preço, desconto e link sempre do catálogo ao vivo do site.

## Materiais (`midia.py`), em ordem de prioridade
1. Vídeos oficiais da Shopee para afiliados – sem API acessível hoje (não usado).
2. Vídeos de fornecedores com autorização – sem API que comprove autorização (não usado).
3. **Banco de vídeos com licença comercial (Pixabay API)** – só cenas de **contexto** (ex.: cozinha, rotina de
   skincare), nunca como demonstração do produto. Requer o secret `PIXABAY_KEY`.
4. **Foto oficial do anúncio** – produto recortado por IA local (rembg, sem marca d'água) com movimento de
   câmera, profundidade e closes em tela cheia. Se o recorte não for confiável, usa a foto inteira.
Nada de demonstração falsa gerada por IA.

## Formato do vídeo (`video3.py`)
Gancho em até 2 s → (problema) → benefício → closes → preço no fim → chamada para comentar/salvar/compartilhar
e visitar `achadosdogenio.com.br`. 1080×1920, 10–25 s, legendas dinâmicas, cortes rápidos, capa com pouco texto.

## Testes e aprendizado (`aprendizado.py`)
Cada Reel registra a variação usada: **gancho** (específico do roteiro ou um dos genéricos, ex.: "Como eu não
descobri isso antes?"), **voz** (Thalita, Francisca, Antonio) e **formato** (problema→solução ou direto).
Opções com menos de 2 amostras são testadas primeiro; depois 70% usa a melhor média e 30% explora.
Compara por **visualizações em 24 h** quando a Meta fornece (permissão `instagram_manage_insights`);
senão, por engajamento. Nenhum número é inventado.

## Rodar localmente
```
python main.py --data 2026-12-01 --slot 2 --produto 58212308864 --variante "{\"gancho\":\"descobri\"}"
```
Requer Python 3.12, FFmpeg e `pip install -r requirements.txt`.

## Roteiros
`roteiros/<id>.json`: gancho, problema, solução, closes (`views` = recortes da foto), capa, `seo`, `broll`
(termos de busca de cenas). Preço e desconto NUNCA ficam no roteiro: são lidos ao vivo.

## Padrão de comunicação
- Sem mencionar afiliados/comissões. Publicidade identificada: selo "Publicidade" no vídeo, "Publicidade." e `#publi` na legenda.
- Fechamento "Comenta QUERO" (variável `CTA_COMENTARIO=1`); respostas no direct são manuais.
- Legenda: palavra-chave na 1ª linha, benefícios antes do preço, pedido de salvar/compartilhar, site e 4 hashtags.
- Links de afiliado originais preservados (site e data store do Make).

## Licenças
- Músicas: Mixkit Stock Music Free License (baixadas no workflow, não redistribuídas aqui).
- Cenas de contexto: Pixabay Content License (uso comercial, sem atribuição obrigatória; sem marcas reconhecíveis).
- Fontes: Bricolage Grotesque e Figtree (SIL Open Font License).
- Imagens de produto: foto oficial do anúncio na Shopee.
