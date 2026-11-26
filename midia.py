"""Materiais audiovisuais automaticos para os Reels (sem envio manual).

Ordem de prioridade aplicada:
  1. Videos oficiais da Shopee para afiliados  -> sem API acessivel hoje (decisao do usuario: seguir sem).
  2. Videos de fornecedores com autorizacao    -> nao ha API que comprove autorizacao; nao usado.
  3. Bancos de video com licenca comercial     -> Pixabay API (cenas de CONTEXTO, nunca "demonstracao" do produto).
  4. Imagem oficial do anuncio -> video        -> recorte do produto (IA local, rembg) + movimento de camera.

Regras: nada de marca d'agua de terceiros, nada sem licenca, nada de demonstracao falsa gerada por IA.
"""
import hashlib
import json
import os
import random
import subprocess
import urllib.parse
import urllib.request
from collections import deque

from PIL import Image, ImageFilter

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, ".cache_midia")
W, H, FPS = 1080, 1920, 30
UA = {"User-Agent": "Mozilla/5.0 (achados-reels)"}

# cenas de contexto por categoria (termos genericos, sem marcas)
BROLL_CATEGORIA = {
    "Casa e cozinha": ["organized home", "kitchen cooking", "cleaning house"],
    "Beleza e saúde": ["skincare routine", "woman applying cream", "self care"],
    "Moda": ["fashion style street", "getting dressed", "gift box"],
    "Bebês e crianças": ["baby playing", "mother and baby", "kids playing home"],
    "Eletrônicos": ["smartphone hands", "technology desk", "charging phone"],
    "Games e informática": ["gaming setup", "computer desk", "typing keyboard"],
    "Esporte e lazer": ["workout home", "running outdoor", "camping"],
    "Pet": ["dog playing", "cat at home", "puppy"],
    "Papelaria e hobbies": ["drawing art", "studying desk", "writing notebook"],
    "Automotivo": ["car driving", "car interior", "washing car"],
    "Mercado": ["snack time", "coffee break", "family breakfast"],
}


# ------------------------------------------------------------------ recorte do produto
_sessao = None


def _mascara_ok(alpha):
    """Recorte so vale se for uma peca limpa: area razoavel e pouco fragmentada."""
    pequeno = alpha.resize((96, 96)).point(lambda v: 255 if v > 128 else 0)
    px = pequeno.load()
    fg = [(x, y) for y in range(96) for x in range(96) if px[x, y]]
    if not fg:
        return False, 0
    frac = len(fg) / (96 * 96)
    vistos, maior, comps = set(), 0, 0
    for s in fg:
        if s in vistos:
            continue
        comps += 1
        fila, n = deque([s]), 0
        vistos.add(s)
        while fila:
            x, y = fila.popleft()
            n += 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if 0 <= q[0] < 96 and 0 <= q[1] < 96 and px[q] and q not in vistos:
                    vistos.add(q)
                    fila.append(q)
        maior = max(maior, n)
    # aceita ate 3 pecas grandes (ex.: relogio + corrente + pulseira), mas nao "farelos"
    principais = maior / len(fg)
    ok = 0.08 <= frac <= 0.80 and (principais >= 0.55 or comps <= 4)
    return ok, round(frac, 3)


def recortar_produto(foto):
    """Devolve (RGBA recortado e aparado, info) ou (None, info) se o recorte nao for confiavel."""
    global _sessao
    try:
        from rembg import new_session, remove
    except ImportError:
        return None, {"recorte": "rembg indisponivel"}
    if _sessao is None:
        _sessao = new_session("isnet-general-use")
    out = remove(foto.convert("RGB"), session=_sessao, post_process_mask=True)
    alpha = out.getchannel("A")
    ok, frac = _mascara_ok(alpha)
    if not ok:
        return None, {"recorte": "rejeitado", "area": frac}
    out = out.crop(out.getbbox())
    return out, {"recorte": "ok", "area": frac}


# ------------------------------------------------------------------ banco de videos (Pixabay)
def _get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def buscar_cenas(termos, quantidade=2, semente=0):
    """Busca cenas de contexto no Pixabay (licenca comercial, sem atribuicao obrigatoria).
    Precisa da variavel PIXABAY_KEY. Sem chave, devolve lista vazia (o video usa so a foto)."""
    chave = os.environ.get("PIXABAY_KEY", "").strip()
    if not chave:
        return []
    os.makedirs(CACHE, exist_ok=True)
    rnd = random.Random(semente)
    achados = []
    for termo in termos:
        url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(
            {"key": chave, "q": termo, "safesearch": "true", "per_page": 20, "video_type": "film", "order": "popular"})
        try:
            hits = _get_json(url).get("hits", [])
        except Exception as e:
            print("pixabay falhou:", termo, e)
            continue
        rnd.shuffle(hits)
        for h in hits:
            v = h.get("videos", {})
            # prefere versao com boa resolucao; vertical se existir (corta no centro de qualquer forma)
            opcoes = [v[k] for k in ("medium", "large", "small") if v.get(k, {}).get("url")]
            if not opcoes or h.get("duration", 0) < 4:
                continue
            esc = max(opcoes, key=lambda o: (o["height"] >= o["width"], min(o.get("height", 0), 1920)))
            arq = os.path.join(CACHE, f"pixabay_{h['id']}.mp4")
            if not os.path.exists(arq):
                try:
                    urllib.request.urlretrieve(esc["url"], arq)
                except Exception as e:
                    print("download falhou:", h["id"], e)
                    continue
            achados.append({"arquivo": arq, "fonte": "Pixabay", "id": h["id"], "autor": h.get("user", ""),
                            "termo": termo, "pagina": h.get("pageURL", "")})
            break
        if len(achados) >= quantidade:
            break
    return achados


class LeitorClip:
    """Le um video quadro a quadro ja cortado em 1080x1920 (vertical), em loop se acabar."""

    def __init__(self, arquivo, inicio=0.0, escurecer=0.0):
        self.arq, self.ini, self.esc = arquivo, inicio, escurecer
        self.proc, self.n = None, 0

    def _abrir(self):
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{self.ini:.2f}", "-i", self.arq,
                                      "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     stdout=subprocess.PIPE)

    def quadro(self):
        if self.proc is None:
            self._abrir()
        dados = self.proc.stdout.read(W * H * 3)
        if len(dados) < W * H * 3:
            self.fechar()
            self.ini = 0.0
            self._abrir()
            dados = self.proc.stdout.read(W * H * 3)
        im = Image.frombytes("RGB", (W, H), dados).convert("RGBA")
        if self.esc:
            im.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * self.esc))))
        return im

    def fechar(self):
        if self.proc:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc = None
