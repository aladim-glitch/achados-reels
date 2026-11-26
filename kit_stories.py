"""Monta a pagina do dia (notas do Release no GitHub) com a arte do Story e o link de cada Reel.

Uso: python kit_stories.py AAAA-MM-DD > kit.md
A pagina abre no celular: salvar a arte, copiar o link e postar o Story com a figurinha de link.
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
data = sys.argv[1]
repo = os.environ.get("GITHUB_REPOSITORY", "aladim-glitch/achados-reels")
base = f"https://github.com/{repo}/releases/download/reels-{data}"

print(f"# Stories do dia {data}\n")
print("Para cada Reel publicado: salve a arte, abra o Story no Instagram, adicione a figurinha **Link**, "
      "cole o link e posicione a figurinha no espaço indicado pela seta.\n")
for pasta in sorted(glob.glob(os.path.join("saida", f"{data}_*"))):
    meta = json.load(open(os.path.join(pasta, "meta.json"), encoding="utf-8"))
    p, h = meta["produto"], meta["horario"]
    titulo = meta.get("roteiro", {}).get("titulo_tela") or p["nome"]
    print(f"## {h} · {titulo}\n")
    print(f"Postar o Story **logo depois do Reel das {h}**. Texto da figurinha sugerido: `GARANTA O SEU`\n")
    print("Link do produto (copiar):\n")
    print(f"```\n{p['link_feed']}\n```\n")
    print(f"[Baixar arte do Story]({base}/story-{h}.jpg)\n")
    print(f"![Story {h}]({base}/story-{h}.jpg)\n")
