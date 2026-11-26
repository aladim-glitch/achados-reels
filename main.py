"""Gera um Reel do Achados do Genio: seleciona o produto, monta roteiro e legenda, renderiza.

Uso:
  python main.py --data 2026-11-26 --slot 0            # selecao automatica (slot 0=08h, 1=12h, 2=19h)
  python main.py --produto 58221620099 --slot 0        # forca um produto (teste)
Saida em saida/<data>_<slot>/: reel.mp4, capa.jpg, legenda.txt, meta.json
"""
import argparse
import datetime as dt
import json
import os
import re

import selecao
import story
import video2

BASE = os.path.dirname(os.path.abspath(__file__))
HORARIOS = ["08h", "12h", "19h"]

UNID = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
        "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos",
       "oitocentos", "novecentos"]


def extenso(n):
    n = int(n)
    if n < 20:
        return UNID[n]
    if n < 100:
        d, u = divmod(n, 10)
        return DEZ[d] + ("" if u == 0 else " e " + UNID[u])
    if n == 100:
        return "cem"
    if n < 1000:
        c, r = divmod(n, 100)
        return CEM[c] + ("" if r == 0 else " e " + extenso(r))
    m, r = divmod(n, 1000)
    pre = "mil" if m == 1 else extenso(m) + " mil"
    return pre + ("" if r == 0 else (" e " if r < 100 or r % 100 == 0 else " ") + extenso(r))


def preco_falado(v):
    reais, cent = int(v), int(round((v - int(v)) * 100))
    if cent == 0:
        return f"{extenso(reais)} reais"
    return f"{extenso(reais)} e {extenso(cent)}"


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def nome_curto(nome, max_palavras=6):
    n = re.split(r"[,|\-–(]", nome)[0]
    n = re.sub(r"^\s*(kit\s+)?[\d/]+\s*(unidades?|peças?|pçs?|un)?\s*", lambda m: "Kit " if m.group(1) else "", n, flags=re.I)
    pal = n.split()
    # tira conectores/simbolos soltos no fim (ex.: "Relogio Moderno +", "Kit de")
    while pal and (not re.search(r"\w", pal[-1]) or pal[-1].lower() in {"de", "da", "do", "e", "com", "para", "pra", "+"}):
        pal.pop()
    return " ".join(pal[:max_palavras]).strip() or nome[:40]


GANCHOS = {
    "Casa e cozinha": "Achado pra deixar sua casa mais prática!",
    "Beleza e saúde": "Achado de beleza com preço de outlet!",
    "Moda": "Olha esse achado de moda na Shopee!",
    "Bebês e crianças": "Achado que vai facilitar a rotina com as crianças!",
    "Eletrônicos": "Achado de eletrônico com desconto de verdade!",
    "Games e informática": "Achado pra turbinar seu setup!",
    "Esporte e lazer": "Achado pra quem gosta de se movimentar!",
    "Pet": "Achado pro seu pet!",
    "Papelaria e hobbies": "Achado de papelaria que vale a pena!",
    "Automotivo": "Achado pro seu carro!",
    "Mercado": "Achado de mercado com preço baixo!",
}

HASHTAGS = {
    "Casa e cozinha": "#casaorganizada", "Beleza e saúde": "#beleza", "Moda": "#moda",
    "Bebês e crianças": "#maternidade", "Eletrônicos": "#tecnologia", "Games e informática": "#setupgamer",
    "Esporte e lazer": "#esporte", "Pet": "#pets", "Papelaria e hobbies": "#papelaria",
    "Automotivo": "#carros", "Mercado": "#economia",
}


def falar_preco(p):
    """Frase de preco gerada SEMPRE a partir do preco ao vivo (nunca fixa no roteiro)."""
    po, pp, d = p["preco_original"], p["preco_oferta"], p["desconto_percentual"]
    return {
        "fala": f"De {preco_falado(po)} por apenas {preco_falado(pp)}! São {extenso(d)} por cento de desconto.",
        "legenda": f"De {brl(po)} por apenas {brl(pp)}! {d}% de desconto.",
    }


def linhas_titulo(texto, max_chars=12, max_linhas=2):
    """Quebra o titulo em ate 2 linhas curtas para nao estourar a largura do video."""
    linhas, atual = [], ""
    for w in texto.upper().split():
        if len(atual) + len(w) + (1 if atual else 0) <= max_chars:
            atual = f"{atual} {w}".strip()
        else:
            if atual:
                linhas.append(atual)
            if len(linhas) == max_linhas:
                break
            atual = w[:max_chars]
    if atual and len(linhas) < max_linhas:
        linhas.append(atual)
    return linhas


def titulo_curto(nome, max_chars=24):
    """Nome curto que cabe numa linha do cabecalho (corta em palavra inteira)."""
    res = ""
    for w in nome_curto(nome).split():
        if len(res) + len(w) + (1 if res else 0) > max_chars:
            break
        res = f"{res} {w}".strip()
    pal = res.split()
    while pal and (not re.search(r"\w", pal[-1]) or pal[-1].lower() in {"de", "da", "do", "e", "com", "para", "pra"}):
        pal.pop()
    return " ".join(pal) or nome[:max_chars]


def roteiro_auto(p):
    """Roteiro sem IA: usa so dados verificaveis do catalogo (nada inventado)."""
    curto = titulo_curto(p["nome"])
    gancho = GANCHOS.get(p["categoria"], "Olha esse achado da Shopee!")
    return {
        "titulo_tela": curto,
        "capa_titulo": [w.upper() for w in [" ".join(curto.split()[:2]), " ".join(curto.split()[2:4]) or "NA SHOPEE", f"-{p['desconto_percentual']}%"]],
        "beneficios": [],
        "frases": [
            {"cena": "hook", "tela": ["ACHADO", "DO DIA!"], "fala": gancho, "legenda": gancho},
            {"cena": "solucao", "rotulo": "OLHA ISSO", "tela": linhas_titulo(curto), "fala": f"{curto}, direto da Shopee.",
             "legenda": f"{curto}, direto da Shopee."},
            {"cena": "detalhe", "itens": [["principal", f"Nota {p['avaliacao']:.1f}".replace(".", ",") + " de 5"], ["z1", "Achado da Shopee"]],
             "fala": "E com nota " + ("máxima" if p["avaliacao"] >= 4.95 else "alta") + " de quem já comprou.",
             "legenda": "E com nota " + ("máxima" if p["avaliacao"] >= 4.95 else "alta") + " de quem já comprou."},
            {"cena": "preco"},
            {"cena": "cta", "fala": "Confira no link da bio!", "legenda": "Confira no link da bio!"},
        ],
    }


# Padrao de comunicacao do Achados do Genio (vale para TODAS as producoes):
# chamadas comerciais, sem citar afiliados/comissoes; publicidade identificada de forma discreta.
CTAS = [
    {"fala": "Confira essa oferta no link da bio!", "legenda": "Confira essa oferta no link da bio!",
     "tela": ["CONFIRA ESSA", "OFERTA"]},
    {"fala": "Garanta o seu! Acesse o link da bio.", "legenda": "Garanta o seu! Acesse o link da bio.",
     "tela": ["GARANTA", "O SEU"]},
    {"fala": "Acesse o link da bio e garanta o seu!", "legenda": "Acesse o link da bio e garanta o seu!",
     "tela": ["ACESSE O"]},
]


# "Comente QUERO": o cenario 3 do Make responde no direct com o link do produto.
# Liga com a variavel CTA_COMENTARIO=1 (no GitHub: Settings > Variables) somente depois que o cenario 3 estiver ativo.
CTA_QUERO = {"fala": "Comenta QUERO que eu te mando o link no direct!",
             "legenda": "Comenta QUERO que eu te mando o link no direct!",
             "tela": ["COMENTA", "QUERO"], "botao": "LINK NO DIRECT"}


def cta_comentario_ligado():
    return os.environ.get("CTA_COMENTARIO", "").strip() == "1"


def cta_padrao(p):
    import hashlib
    if cta_comentario_ligado():
        return CTA_QUERO
    return CTAS[int(hashlib.md5(str(p["id"]).encode()).hexdigest(), 16) % len(CTAS)]


def carregar_roteiro(p):
    arq = os.path.join(BASE, "roteiros", f"{p['id']}.json")
    if os.path.exists(arq):
        with open(arq, encoding="utf-8") as f:
            r = json.load(f)
    else:
        r = roteiro_auto(p)
    # aplica sempre a chamada comercial padrao no fechamento
    for fr in r["frases"]:
        if fr["cena"] == "cta":
            fr.update(cta_padrao(p))
    return r


def legenda_instagram(p, r):
    curto = r.get("titulo_tela") or nome_curto(p["nome"])
    linhas = [f"🧞 {curto}", "",
              f"💸 De {brl(p['preco_original'])} por {brl(p['preco_oferta'])} ({p['desconto_percentual']}% OFF)",
              f"⭐ Nota {p['avaliacao']:.1f}".replace(".", ",") + " de 5 na Shopee"]
    for b in r.get("beneficios", []):
        linhas.append(f"✅ {b}")
    busca = r.get("busca") or " ".join(curto.split()[:3]).lower()
    if cta_comentario_ligado():
        linhas += ["", "💬 Comenta QUERO que eu te mando o link no direct!"]
    linhas += ["", "🛒 Garanta o seu: acesse o link da bio", f"🔎 No site, busque por \"{busca}\"", "",
               "Publicidade. Preço e estoque sujeitos a alteração.", "",
               " ".join(["#publi", "#achadosdashopee", "#achadinhos", HASHTAGS.get(p["categoria"], "#promocao"),
                         "#achadosdogenio"])]
    return "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(dt.date.today()))
    ap.add_argument("--slot", type=int, default=0)
    ap.add_argument("--produto")
    ap.add_argument("--registrar", action="store_true", help="marca o produto como usado (producao)")
    a = ap.parse_args()
    data = dt.date.fromisoformat(a.data)
    p = selecao.selecionar(data, a.slot, a.produto)
    r = carregar_roteiro(p)
    pasta = os.path.join(BASE, "saida", f"{data}_{HORARIOS[a.slot]}")
    os.makedirs(pasta, exist_ok=True)
    info = video2.renderizar(p, r, os.path.join(pasta, "reel.mp4"), os.path.join(pasta, "capa.jpg"), falar_preco)
    leg = legenda_instagram(p, r)
    with open(os.path.join(pasta, "legenda.txt"), "w", encoding="utf-8") as f:
        f.write(leg)
    # Story do Reel: arte + link de afiliado original para a figurinha de link (colada no app)
    story.gerar_story(p, r, os.path.join(pasta, "story.jpg"))
    with open(os.path.join(pasta, "link.txt"), "w", encoding="utf-8") as f:
        f.write(p["link_feed"])
    meta = {"data": str(data), "horario": HORARIOS[a.slot], "produto": p, "roteiro": r, "legenda": leg, **info}
    with open(os.path.join(pasta, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if a.registrar:
        selecao.registrar_publicado(p, data, a.slot)
    print(json.dumps({"pasta": pasta, "produto": p["id"], "categoria": p["categoria"], "duracao": info["duracao"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
