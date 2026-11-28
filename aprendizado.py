"""Testes A/B e aprendizado com os dados REAIS de desempenho.

Cada Reel sorteia uma variante (gancho, voz, formato/duracao, edicao, chamada final, trilha).
Depois de 24/48/72 h, metricas.py grava os numeros reais em estado/metricas.json. Aqui:
  - valores ainda pouco testados (< MIN_AMOSTRAS) sao testados primeiro;
  - valores com desempenho muito baixo (< 50% da melhor media, com >= 3 amostras) saem do sorteio;
  - 30% das vezes exploramos; no resto usamos a opcao com melhor media.
Sem dados, a escolha e aleatoria. Nenhum resultado e inventado.
"""
import json
import math
import os
import random

BASE = os.path.dirname(os.path.abspath(__file__))
METRICAS = os.path.join(BASE, "estado", "metricas.json")
EXPLORAR = 0.30
MIN_AMOSTRAS = 2
CORTE_BAIXO = 0.5

# Ganchos ligados ao beneficio/preco REAL do produto (sem frases genericas repetitivas)
GANCHOS = [
    {"id": "roteiro"},  # gancho escrito para o produto no roteiro (beneficio especifico)
    {"id": "menos_de", "requer": "preco_ate_100"},
    {"id": "parece_caro"},
    {"id": "usaria"},
    {"id": "resolve", "requer": "problema"},
]
VOZES = [
    {"id": "thalita", "voz": "pt-BR-ThalitaMultilingualNeural", "taxa": "+15%"},
    {"id": "francisca", "voz": "pt-BR-FranciscaNeural", "taxa": "+18%"},
    {"id": "antonio", "voz": "pt-BR-AntonioNeural", "taxa": "+15%"},
]
FORMATOS = [
    {"id": "direto"},            # gancho > demonstracao/beneficios > preco > chamada (12-16 s)
    {"id": "problema_solucao"},  # gancho > problema rapido > beneficios > preco > chamada (15-18 s)
]
EDICOES = [
    {"id": "rapida"},  # cortes a cada ~1 s
    {"id": "media"},   # cortes a cada ~1,5-2 s
]
CTAS = [
    {"id": "quero", "fala": "Comenta QUERO que eu te mando o link!", "tela": ["COMENTA", "QUERO"], "botao": "TE MANDO O LINK",
     "legenda": "💬 Comenta QUERO que eu te mando o link!"},
    {"id": "salva", "fala": "Salva pra não perder esse achadinho!", "tela": ["SALVA PRA", "NÃO PERDER"], "botao": "LINK NA BIO",
     "legenda": "📌 Salva pra não perder esse achadinho!"},
    {"id": "envia", "fala": "Manda pra alguém que precisa disso!", "tela": ["MANDA PRA", "QUEM PRECISA"], "botao": "LINK NA BIO",
     "legenda": "📤 Manda pra alguém que precisa disso!"},
    {"id": "compraria", "fala": "Você compraria? Comenta aqui!", "tela": ["VOCÊ", "COMPRARIA?"], "botao": "COMENTA AQUI",
     "legenda": "🤔 Você compraria? Comenta aqui!"},
    {"id": "site", "fala": "Mais ofertas no achados do gênio ponto com ponto bê erre!", "tela": ["MAIS OFERTAS", "NO SITE"],
     "botao": "ACHADOSDOGENIO.COM.BR", "legenda": "🛍️ Tem muito mais achadinho esperando por você!"},
]
TRILHAS = [{"id": t} for t in ("mixkit-288", "mixkit-801", "mixkit-1147", "mixkit-837", "mixkit-158")]


def carregar_metricas():
    if os.path.exists(METRICAS):
        with open(METRICAS, encoding="utf-8") as f:
            return json.load(f)
    return {}


def pontuacao_post(m):
    """Desempenho real do post: visualizacoes em 24 h quando a Meta fornece; senao engajamento."""
    for cp in ("24h", "48h", "72h"):
        snap = m.get(cp) or {}
        if snap.get("views") is not None:
            return float(snap["views"]), "views"
    snap = m.get("24h") or m.get("48h") or m.get("72h") or {}
    if not snap:
        return None, None
    eng = (snap.get("likes") or 0) + 3 * (snap.get("comments") or 0) + 5 * (snap.get("saved") or 0) + 5 * (snap.get("shares") or 0)
    return float(eng), "engajamento"


def medias_por_dimensao(metricas):
    posts = [(pontuacao_post(m), {**(m.get("variante") or {}), **({"categoria": m["categoria"]} if m.get("categoria") else {})})
             for m in metricas.values()]
    tem_views = any(t == "views" for (s, t), _ in posts if s is not None)
    alvo = "views" if tem_views else "engajamento"
    res = {}
    for (s, t), var in posts:
        if s is None or t != alvo:
            continue
        for dim, val in var.items():
            if isinstance(val, (str, int)) and dim != "extra":
                res.setdefault(dim, {}).setdefault(str(val), []).append(s)
    return res, alvo


def escolher(dim, ids, rnd, medias):
    dados = medias.get(dim, {})
    pouco = [i for i in ids if len(dados.get(i, [])) < MIN_AMOSTRAS]
    if pouco:
        return rnd.choice(pouco), "testando"
    media = {i: sum(dados[i]) / len(dados[i]) for i in ids}
    melhor = max(ids, key=lambda i: media[i])
    # nao repete automaticamente o que foi mal
    vivos = [i for i in ids if not (len(dados[i]) >= 3 and media[i] < CORTE_BAIXO * media[melhor])] or [melhor]
    if rnd.random() < EXPLORAR:
        return rnd.choice(vivos), "explorando"
    return melhor, "melhor_resultado"


def sortear_variante(semente, contexto):
    """contexto: {"problema": bool, "preco": float}"""
    rnd = random.Random(semente)
    medias, _ = medias_por_dimensao(carregar_metricas())
    ok = {"problema": contexto.get("problema"), "preco_ate_100": contexto.get("preco", 999) <= 100}
    ganchos = [g["id"] for g in GANCHOS if not g.get("requer") or ok[g["requer"]]]
    formatos = [f["id"] for f in FORMATOS if f["id"] == "direto" or contexto.get("problema")]
    var, motivo = {}, {}
    for dim, ids in (("gancho", ganchos), ("voz", [v["id"] for v in VOZES]), ("formato", formatos),
                     ("edicao", [e["id"] for e in EDICOES]), ("cta", [c["id"] for c in CTAS]),
                     ("trilha", [t["id"] for t in TRILHAS])):
        var[dim], motivo[dim] = escolher(dim, ids, rnd, medias)
    if var["gancho"] == "resolve":  # gancho fala de problema: precisa da cena do problema
        var["formato"], motivo["formato"] = "problema_solucao", "coerencia_gancho"
    return var, motivo


def texto_gancho(gid, produto, roteiro):
    """Frase e texto de tela do gancho, sempre com dados reais do produto."""
    hook = next((f for f in roteiro["frases"] if f["cena"] == "hook"), {})
    if gid == "menos_de":
        teto = int(math.ceil((produto["preco_oferta"] + 0.01) / 10.0) * 10)
        return f"Olha o que eu encontrei por menos de {teto} reais!", ["MENOS DE", f"R$ {teto}!"]
    if gid == "parece_caro":
        return "Parece caro, mas olha o preço!", ["PARECE CARO...", "OLHA O PREÇO!"]
    if gid == "usaria":
        casa = produto["categoria"] in ("Casa e cozinha", "Pet", "Bebês e crianças")
        return ("Você usaria isso na sua casa?", ["VOCÊ USARIA", "ISSO EM CASA?"]) if casa else \
               ("Você usaria isso no dia a dia?", ["VOCÊ USARIA", "ISSO?"])
    if gid == "resolve":
        return "Esse achadinho resolve um problema que muita gente tem.", ["RESOLVE UM", "PROBLEMA COMUM"]
    return hook.get("fala"), hook.get("tela")


def voz(vid):
    return next(v for v in VOZES if v["id"] == vid)


def cta(cid):
    return next(c for c in CTAS if c["id"] == cid)
