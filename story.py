"""Arte do Story (1080x1920) que acompanha cada Reel.

A API do Instagram nao permite figurinha de link em Stories, entao a arte deixa um espaco
livre (marcado pela seta) para a pessoa colar a figurinha de link manualmente no app.
Mesmo padrao de comunicacao dos Reels: chamada comercial e selo "Publicidade", sem citar afiliados.
"""
from PIL import Image, ImageDraw

from video2 import (AMARELO, BRANCO, ESCURO, LARANJA, W, Reel, brl, colar, fonte, pilula,
                    texto_img)

# area onde a figurinha de link deve ser colada (fora da faixa de resposta do Instagram)
ZONA_LINK = (1590, 1740)


def quebrar(texto, max_chars=16, max_linhas=2):
    linhas, atual = [], ""
    for w in texto.upper().split():
        if len(atual) + len(w) + (1 if atual else 0) <= max_chars:
            atual = f"{atual} {w}".strip()
        else:
            if atual:
                linhas.append(atual)
            if len(linhas) == max_linhas:
                return linhas
            atual = w[:max_chars]
    if atual and len(linhas) < max_linhas:
        linhas.append(atual)
    return linhas


def seta_baixo(cor=AMARELO, w=90, h=80):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.36, 0, w * 0.64, h * 0.5], fill=cor)
    d.polygon([(0, h * 0.45), (w, h * 0.45), (w / 2, h)], fill=cor)
    return im


def gerar_story(produto, roteiro, saida):
    r = Reel(produto, roteiro)
    fr = r.fundo(2.0)
    fr.alpha_composite(r._header)

    # titulo
    titulo = quebrar(roteiro.get("titulo_tela") or produto["nome"])
    colar(fr, texto_img(titulo, fonte("titulo", 88, 800), stroke=6), W / 2, 330 + (len(titulo) - 1) * 44)

    # foto do produto
    y_card = 800
    card = r.card_frame("principal", zoom=1.03, alvo=(620, 560))
    colar(fr, r.sombra_card(card.width, card.height), W / 2, y_card + 30)
    colar(fr, card, W / 2, y_card)
    colar(fr, r.selo, W / 2 + card.width / 2 - 10, y_card - card.height / 2 + 40, escala=0.62, rot=-14)

    # preco antigo riscado + preco atual
    f_de = fonte("texto", 50, 800)
    y_de = y_card + card.height / 2 + 60
    de = texto_img([f"De {brl(produto['preco_original'])}"], f_de, cor=(255, 236, 220))
    colar(fr, de, W / 2, y_de)
    d = ImageDraw.Draw(fr)
    d.line([(W / 2 - de.width / 2 + 14, y_de - 6), (W / 2 + de.width / 2 - 14, y_de - 6)], fill=(255, 236, 220), width=6)
    colar(fr, r._caixa_preco(), W / 2, y_de + 175, escala=0.72)

    # chamada + seta apontando para o espaco da figurinha
    cta = pilula("TOQUE NO LINK E GARANTA O SEU", fonte("texto", 42, 900), BRANCO, LARANJA, pad=(32, 14))
    colar(fr, cta, W / 2, ZONA_LINK[0] - 105)
    colar(fr, seta_baixo(w=70, h=60), W / 2, ZONA_LINK[0] - 38)

    # moldura discreta da area do link (fica coberta pela figurinha)
    z0, z1 = ZONA_LINK
    marca = Image.new("RGBA", fr.size, (0, 0, 0, 0))
    ImageDraw.Draw(marca).rounded_rectangle([W / 2 - 330, z0, W / 2 + 330, z1], 60, outline=(255, 255, 255, 120), width=5)
    fr.alpha_composite(marca)

    fr.convert("RGB").save(saida, quality=92)
    return saida
