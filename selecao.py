"""Selecao automatica de produtos do Achados do Genio.

Regras:
- 3 produtos por dia, um por horario (08h, 12h, 19h).
- Categorias em rodizio: cada dia continua de onde o anterior parou, cobrindo as 11.
- Dentro da categoria, o produto com maior potencial (pontuacao do catalogo,
  ajustada pelo desconto e preco atuais do site).
- Nunca repete produto ja publicado (estado/publicados.json).
- Confere disponibilidade e preco no catalogo ao vivo do site e se a imagem abre.
"""
import csv
import datetime as dt
import json
import os
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
CATALOGO = os.path.join(BASE, "catalogo.csv")
PUBLICADOS = os.path.join(BASE, "estado", "publicados.json")
SITE_JSON = "https://achadosdogenio.com.br/data/todos.json"
INICIO = dt.date(2026, 11, 26)  # dia 0 do rodizio

CATEGORIAS = [
    "Casa e cozinha", "Beleza e saúde", "Moda", "Bebês e crianças", "Eletrônicos",
    "Games e informática", "Esporte e lazer", "Pet", "Papelaria e hobbies",
    "Automotivo", "Mercado",
]
UA = {"User-Agent": "Mozilla/5.0 (achados-reels)"}
# ID de afiliado da Shopee (publico: aparece em todo link de afiliado) e sub_id que separa
# os cliques vindos dos Reels/Stories/direct dos cliques do site no painel de afiliados.
AFILIADO_ID = os.environ.get("SHOPEE_AFILIADO_ID", "18377480689")
SUB_ID = "reels"


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def carregar_catalogo():
    with open(CATALOGO, encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f))
    for p in linhas:
        for k in ("preco_original", "preco_oferta", "avaliacao", "pontuacao_estimada"):
            p[k] = float(p[k] or 0)
        p["desconto_percentual"] = int(float(p["desconto_percentual"] or 0))
    return linhas


def carregar_site():
    """Catalogo ao vivo do site: id -> (preco, preco_original, desconto, link)."""
    dados = json.loads(_get(SITE_JSON).decode("utf-8"))
    return {str(p[0]): {"preco": p[2], "original": p[3], "desconto": p[4], "link": p[7]} for p in dados}


def link_afiliado(link, sub_id=SUB_ID):
    """Devolve o link shope.ee/an_redir com affiliate_id e sub_id corretos.
    Sem affiliate_id a Shopee abre o produto sem atribuir o clique ao afiliado."""
    partes = urllib.parse.urlsplit(link)
    origem = urllib.parse.parse_qs(partes.query).get("origin_link", [""])[0]
    if partes.netloc != "shope.ee" or partes.path != "/an_redir" or not origem:
        raise ValueError(f"link fora do padrao an_redir: {link}")
    q = urllib.parse.urlencode({"origin_link": origem, "affiliate_id": AFILIADO_ID, "sub_id": sub_id})
    return f"https://shope.ee/an_redir?{q}"


def carregar_publicados():
    if os.path.exists(PUBLICADOS):
        with open(PUBLICADOS, encoding="utf-8") as f:
            return json.load(f)
    return []


def registrar_publicado(produto, data, slot, variante=None):
    pub = carregar_publicados()
    pub.append({"id": produto["id"], "data": str(data), "slot": slot, "categoria": produto["categoria"],
                "variante": variante or {}})
    os.makedirs(os.path.dirname(PUBLICADOS), exist_ok=True)
    with open(PUBLICADOS, "w", encoding="utf-8") as f:
        json.dump(pub, f, ensure_ascii=False, indent=1)


def imagem_ok(url):
    try:
        return len(_get(url, timeout=15)) > 5000
    except Exception:
        return False


def categoria_do_slot(data, slot):
    dia = (data - INICIO).days
    return CATEGORIAS[(dia * 3 + slot) % len(CATEGORIAS)]


# Potencial de viralizacao (heuristica transparente, sem inventar tendencias):
# utilidade pratica, apelo visual e curiosidade costumam render mais em video do que pecas tecnicas/consumiveis.
CURIOSIDADE = {
    "portátil": 6, "portatil": 6, "mini": 5, "magnético": 6, "magnetico": 6, "dobrável": 6, "dobravel": 6,
    "automático": 6, "automatico": 6, "recarregável": 5, "recarregavel": 5, "led": 5, "sem fio": 5,
    "multifuncional": 6, "organizador": 7, "organizadora": 7, "suporte": 4, "dispenser": 6, "porta": 3,
    "luminária": 5, "luminaria": 5, "projetor": 7, "umidificador": 6, "massageador": 6, "aspirador": 6,
    "mop": 6, "escova": 3, "garrafa": 4, "térmica": 4, "termica": 4, "cortador": 5, "fatiador": 6,
    "ralador": 4, "lancheira": 4, "kit": 3, "inteligente": 5, "elétrico": 4, "eletrico": 4, "divisória": 5,
    "divisoria": 5, "ventilador": 5, "relógio": 3, "relogio": 3, "brinquedo": 4, "interativo": 6,
    "comedouro": 4, "bebedouro": 5, "fonte": 3, "gamer": 4, "rgb": 5, "selfie": 5, "tripé": 4, "tripe": 4,
}
SEM_GRACA = {
    "chave": -6, "sonda": -8, "parafuso": -8, "refil": -6, "peça": -5, "peca": -5, "cabo": -4, "adaptador": -3,
    "apostila": -8, "etiqueta": -4, "adesivo": -2, "fusível": -8, "fusivel": -8, "junta": -6, "rolamento": -8,
    "sachê": -3, "sache": -3, "pacote": -2, "unidades": -1,
}


def potencial_viral(nome):
    n = nome.lower()
    return sum(v for k, v in CURIOSIDADE.items() if k in n) + sum(v for k, v in SEM_GRACA.items() if k in n)


def pontuar(p, ao_vivo):
    nota = p["pontuacao_estimada"]
    # desconto atual diferente do catalogo ajusta a nota
    nota += (ao_vivo["desconto"] - p["desconto_percentual"]) * 0.3
    nota += potencial_viral(p["nome"]) * 1.5
    # produto com roteiro proprio (beneficios verificados) rende video melhor
    if os.path.exists(os.path.join(BASE, "roteiros", f"{p['id']}.json")):
        nota += 8
    return nota


def selecionar(data, slot, forcar_id=None):
    catalogo = carregar_catalogo()
    ao_vivo = carregar_site()
    usados = {str(x["id"]) for x in carregar_publicados()}

    if forcar_id:
        candidatos = [p for p in catalogo if p["id"] == str(forcar_id)]
    else:
        cat = categoria_do_slot(data, slot)
        candidatos = [p for p in catalogo if p["categoria"] == cat and p["id"] not in usados]

    validos = []
    for p in candidatos:
        v = ao_vivo.get(p["id"])
        if not v or not v["preco"]:
            continue  # saiu do site = indisponivel
        validos.append((pontuar(p, v), p, v))
    validos.sort(key=lambda x: x[0], reverse=True)

    for nota, p, v in validos:
        if not imagem_ok(p["imagem"]):
            continue
        p = dict(p)
        # preco e link sempre do site ao vivo (fonte mais recente)
        p["preco_oferta"] = float(v["preco"])
        p["preco_original"] = float(v["original"] or p["preco_original"])
        p["desconto_percentual"] = int(v["desconto"] or p["desconto_percentual"])
        p["link_feed"] = link_afiliado(v["link"])
        p["nota_selecao"] = round(nota, 2)
        return p
    raise RuntimeError("Nenhum produto disponivel para esta categoria/horario")


if __name__ == "__main__":
    hoje = dt.date.today()
    for s in range(3):
        p = selecionar(hoje, s)
        print(s, p["categoria"], p["id"], p["preco_oferta"], p["nome"][:60])
