"""Envia ao webhook do Make os 3 Reels gerados no dia (URL do video, capa, legenda e produto)."""
import glob
import json
import os
import sys
import urllib.request

data = sys.argv[1]
repo = os.environ["GITHUB_REPOSITORY"]
hook = os.environ["MAKE_WEBHOOK"]
base = f"https://github.com/{repo}/releases/download/reels-{data}"

for pasta in sorted(glob.glob(os.path.join("saida", f"{data}_*"))):
    meta = json.load(open(os.path.join(pasta, "meta.json"), encoding="utf-8"))
    p, h = meta["produto"], meta["horario"]
    corpo = {
        "token": os.environ["MAKE_TOKEN"],
        "chave": f"{data}_{h}",
        "data": data,
        "horario": h,
        "produto_id": p["id"],
        "nome": p["nome"],
        "categoria": p["categoria"],
        "link_afiliado": p["link_feed"],
        "preco_oferta": p["preco_oferta"],
        "preco_original": p["preco_original"],
        "desconto": p["desconto_percentual"],
        "avaliacao": p["avaliacao"],
        "video_url": f"{base}/reel-{h}.mp4",
        "capa_url": f"{base}/capa-{h}.jpg",
        "legenda": meta["legenda"],
        "duracao": meta["duracao"],
    }
    req = urllib.request.Request(hook, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(h, p["id"], r.status)
