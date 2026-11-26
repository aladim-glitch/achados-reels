"""Testes de variacao e aprendizado com os dados REAIS de desempenho.

Cada Reel sorteia uma variante (gancho, voz, formato). Depois de 24/48/72 h, metricas.py grava
os numeros reais em estado/metricas.json. Aqui escolhemos as proximas variantes:
  - valores ainda pouco testados (< MIN_AMOSTRAS) sao testados primeiro;
  - 30% das vezes exploramos uma opcao aleatoria;
  - no resto, usamos a opcao com melhor resultado medio.
Nada de numeros inventados: sem dados, a escolha e simplesmente rotativa/aleatoria.
"""
import json
import os
import random

BASE = os.path.dirname(os.path.abspath(__file__))
METRICAS = os.path.join(BASE, "estado", "metricas.json")
EXPLORAR = 0.30
MIN_AMOSTRAS = 2

GANCHOS = [
    {"id": "roteiro", "fala": None, "tela": None},  # gancho especifico do roteiro do produto
    {"id": "descobri", "fala": "Como eu não descobri isso antes?", "tela": ["COMO EU NÃO", "DESCOBRI ISSO", "ANTES?"]},
    {"id": "compartilhar", "fala": "Achei isso na Shopee e precisava compartilhar!", "tela": ["ACHEI ISSO", "NA SHOPEE!"]},
    {"id": "parece_caro", "fala": "Parece caro, mas olha quanto custa!", "tela": ["PARECE CARO...", "OLHA O PREÇO!"]},
    {"id": "conhecer", "fala": "Você precisa conhecer esse achadinho!", "tela": ["VOCÊ PRECISA", "CONHECER ISSO"]},
    {"id": "problema_todos", "fala": "Esse produto resolve um problema que todo mundo tem!",
     "tela": ["RESOLVE UM", "PROBLEMA DE", "TODO MUNDO"], "requer_problema": True},
]
VOZES = [
    {"id": "thalita", "voz": "pt-BR-ThalitaMultilingualNeural", "taxa": "+12%"},
    {"id": "francisca", "voz": "pt-BR-FranciscaNeural", "taxa": "+15%"},
    {"id": "antonio", "voz": "pt-BR-AntonioNeural", "taxa": "+12%"},
]
FORMATOS = [
    {"id": "problema_solucao"},  # gancho > problema > beneficio > detalhes > preco > chamada (~18-25 s)
    {"id": "direto"},            # gancho > beneficio > detalhes > preco > chamada (~12-18 s)
]


def carregar_metricas():
    if os.path.exists(METRICAS):
        with open(METRICAS, encoding="utf-8") as f:
            return json.load(f)
    return {}


def pontuacao_post(m):
    """Desempenho real do post. Usa visualizacoes em 24 h quando a Meta fornece; senao engajamento."""
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
    """{dimensao: {valor: [scores]}} usando so posts com a mesma metrica (views ou engajamento)."""
    posts = [(pontuacao_post(m), m.get("variante") or {}) for m in metricas.values()]
    tem_views = any(t == "views" for (s, t), _ in posts if s is not None)
    alvo = "views" if tem_views else "engajamento"
    res = {}
    for (s, t), var in posts:
        if s is None or t != alvo:
            continue
        for dim, val in var.items():
            res.setdefault(dim, {}).setdefault(val, []).append(s)
    return res, alvo


def escolher(dim, opcoes, rnd, medias):
    ids = [o["id"] for o in opcoes]
    dados = medias.get(dim, {})
    pouco = [i for i in ids if len(dados.get(i, [])) < MIN_AMOSTRAS]
    if pouco:
        return rnd.choice(pouco), "testando"
    if rnd.random() < EXPLORAR:
        return rnd.choice(ids), "explorando"
    melhor = max(ids, key=lambda i: sum(dados[i]) / len(dados[i]))
    return melhor, "melhor_resultado"


def sortear_variante(semente, tem_problema):
    rnd = random.Random(semente)
    medias, _ = medias_por_dimensao(carregar_metricas())
    ganchos = [g for g in GANCHOS if tem_problema or not g.get("requer_problema")]
    formatos = FORMATOS if tem_problema else [f for f in FORMATOS if f["id"] == "direto"]
    g, mg = escolher("gancho", ganchos, rnd, medias)
    v, mv = escolher("voz", VOZES, rnd, medias)
    f, mf = escolher("formato", formatos, rnd, medias)
    if g == "problema_todos":  # gancho fala de problema: precisa da cena do problema
        f, mf = "problema_solucao", "coerencia_gancho"
    return {"gancho": g, "voz": v, "formato": f}, {"gancho": mg, "voz": mv, "formato": mf}


def gancho(gid):
    return next(g for g in GANCHOS if g["id"] == gid)


def voz(vid):
    return next(v for v in VOZES if v["id"] == vid)
