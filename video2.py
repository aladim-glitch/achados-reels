"""Renderizador v2 de Reels (estilo achadinhos): camera dinamica, cenas problema/solucao,
closes do produto, preco com impacto, musica licenciada com ducking e efeitos sonoros."""
import asyncio
import hashlib
import io
import math
import os
import random
import subprocess
import tempfile
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")
W, H, FPS = 1080, 1920, 30
VOZ = os.environ.get("VOZ", "pt-BR-ThalitaMultilingualNeural")
TAXA = os.environ.get("TAXA_VOZ", "+12%")

# Cores oficiais do perfil @achados_do_genio
LARANJA = (231, 74, 43)
AMARELO = (255, 198, 5)
BRANCO = (255, 255, 255)
ESCURO = (24, 14, 10)
CREME = (255, 243, 230)
VERDE = (22, 163, 74)
VERMELHO = (220, 38, 38)


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------------ fontes
_fc = {}


def fonte(tipo, tam, peso=800):
    k = (tipo, tam, peso)
    if k not in _fc:
        arq = os.path.join(ASSETS, "fonts", "BricolageGrotesque.ttf" if tipo == "titulo" else "Figtree.ttf")
        f = ImageFont.truetype(arq, tam)
        try:
            vals = []
            for a in f.get_variation_axes():
                n = a.get("name", b"")
                n = n.decode() if isinstance(n, bytes) else str(n)
                if "eight" in n:
                    vals.append(max(a["minimum"], min(a["maximum"], peso)))
                elif "ptical" in n:
                    vals.append(a["maximum"])
                else:
                    vals.append(a["default"])
            f.set_variation_by_axes(vals)
        except Exception:
            pass
        _fc[k] = f
    return _fc[k]


# ------------------------------------------------------------------ easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_back(t):
    t = clamp(t)
    c1 = 1.9
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_in_out(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


# ------------------------------------------------------------------ utilidades graficas
def colar(base, im, cx, cy, escala=1.0, alpha=1.0, rot=0.0):
    if im is None or escala <= 0.01 or alpha <= 0.01:
        return
    if escala != 1.0:
        im = im.resize((max(1, int(im.width * escala)), max(1, int(im.height * escala))), Image.BILINEAR)
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1.0:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    base.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def texto_img(linhas, f, cor=BRANCO, stroke=0, stroke_cor=ESCURO, esp=1.05, cores=None, sombra=True, alinhamento="c"):
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    larg = max(tmp.textlength(l, font=f) for l in linhas) + stroke * 2 + 30
    alt = int(f.size * esp)
    im = Image.new("RGBA", (int(larg), alt * len(linhas) + stroke * 2 + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, l in enumerate(linhas):
        tw = d.textlength(l, font=f)
        x = (larg - tw) / 2 if alinhamento == "c" else stroke + 10
        c = cores[i % len(cores)] if cores else cor
        d.text((x, 10 + stroke + i * alt), l, font=f, fill=c, stroke_width=stroke, stroke_fill=stroke_cor)
    if sombra:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh.putalpha(im.getchannel("A").point(lambda v: int(v * 0.55)))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        out = Image.new("RGBA", (im.width + 12, im.height + 16), (0, 0, 0, 0))
        out.alpha_composite(sh, (8, 14))
        out.alpha_composite(im, (0, 0))
        return out
    return im


def pilula(texto, f, fundo, cor, pad=(36, 16), icone=None):
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = d.textlength(texto, font=f)
    ic = 0 if not icone else int(f.size * 1.1)
    w, h = int(tw + pad[0] * 2 + ic), int(f.size * 1.25 + pad[1] * 2)
    im = Image.new("RGBA", (w + 20, h + 24), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([8, 14, w + 8, h + 14], h // 2, fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w, h], h // 2, fill=fundo)
    x = pad[0]
    if icone == "check":
        s = f.size * 0.9
        cy = h / 2
        d.ellipse([x, cy - s / 2, x + s, cy + s / 2], fill=BRANCO)
        d.line([(x + s * .25, cy), (x + s * .45, cy + s * .2), (x + s * .78, cy - s * .22)], fill=fundo, width=max(4, int(s * .14)), joint="curve")
        x += ic
    elif icone == "x":
        s = f.size * 0.9
        cy = h / 2
        d.ellipse([x, cy - s / 2, x + s, cy + s / 2], fill=VERMELHO)
        m = s * .28
        d.line([(x + m, cy - s / 2 + m), (x + s - m, cy + s / 2 - m)], fill=BRANCO, width=max(4, int(s * .13)))
        d.line([(x + m, cy + s / 2 - m), (x + s - m, cy - s / 2 + m)], fill=BRANCO, width=max(4, int(s * .13)))
        x += ic
    d.text((x, pad[1] + f.size * 0.05), texto, font=f, fill=cor)
    return im


def logo_circular(tam):
    im = Image.open(os.path.join(ASSETS, "logo_instagram.jpg")).convert("RGB")
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
    im = im.resize((tam, tam), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 80, 2))
    m = Image.new("L", (tam * 4, tam * 4), 0)
    ImageDraw.Draw(m).ellipse([6, 6, tam * 4 - 6, tam * 4 - 6], fill=255)
    out = Image.new("RGBA", (tam + 12, tam + 12), (0, 0, 0, 0))
    ImageDraw.Draw(out).ellipse([0, 0, tam + 11, tam + 11], fill=BRANCO)
    im = im.convert("RGBA")
    im.putalpha(m.resize((tam, tam), Image.LANCZOS))
    out.alpha_composite(im, (6, 6))
    return out


def estrela(d, cx, cy, ro, cor):
    ri = ro * 0.43
    pts = [(cx + (ro if k % 2 == 0 else ri) * math.sin(math.pi * k / 5),
            cy - (ro if k % 2 == 0 else ri) * math.cos(math.pi * k / 5)) for k in range(10)]
    d.polygon(pts, fill=cor)


def selo_desconto(pct, s=300):
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = []
    for k in range(36):
        ang = math.pi * 2 * k / 36
        rr = s / 2 - 6 - (0 if k % 2 == 0 else 18)
        pts.append((s / 2 + rr * math.cos(ang), s / 2 + rr * math.sin(ang)))
    d.polygon(pts, fill=AMARELO)
    d.ellipse([34, 34, s - 34, s - 34], outline=ESCURO, width=4)
    f = fonte("titulo", 92, 800)
    t = f"-{pct}%"
    tw = d.textlength(t, font=f)
    d.text(((s - tw) / 2, s / 2 - 70), t, font=f, fill=ESCURO)
    f2 = fonte("texto", 40, 900)
    tw = d.textlength("OFF", font=f2)
    d.text(((s - tw) / 2, s / 2 + 26), "OFF", font=f2, fill=LARANJA)
    return im


def borrar_horizontal(img, forca):
    if forca < 0.05:
        return img
    k = 1 + forca * 22
    return img.resize((max(8, int(W / k)), H), Image.BILINEAR).resize((W, H), Image.BILINEAR)


# ------------------------------------------------------------------ audio
async def _tts(texto, arq):
    import edge_tts
    try:
        com = edge_tts.Communicate(texto, VOZ, rate=TAXA, boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(texto, VOZ, rate=TAXA)
    pal = []
    with open(arq, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                pal.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7))
    return pal


def duracao(arq):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def sfx(pasta):
    wh = os.path.join(pasta, "whoosh.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=0.38:c=pink:a=0.9",
                    "-af", "highpass=f=600,lowpass=f=7000,afade=t=in:d=0.2:curve=exp,afade=t=out:st=0.2:d=0.18,volume=0.55",
                    "-ar", "48000", "-ac", "2", wh], check=True)
    ding = os.path.join(pasta, "ding.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=1568:d=0.6", "-f", "lavfi", "-i", "sine=f=2349:d=0.6",
                    "-filter_complex", "[0][1]amix=inputs=2,afade=t=out:st=0.03:d=0.55:curve=exp,volume=0.9",
                    "-ar", "48000", "-ac", "2", ding], check=True)
    return wh, ding


def musica_para(produto_id):
    pasta = os.path.join(ASSETS, "musica")
    faixas = sorted(f for f in os.listdir(pasta) if f.endswith(".mp3"))
    h = int(hashlib.md5(str(produto_id).encode()).hexdigest(), 16)
    return os.path.join(pasta, faixas[h % len(faixas)])


# ------------------------------------------------------------------ reel
class Reel:
    def __init__(self, produto, roteiro):
        self.p, self.r = produto, roteiro
        self.pasta = tempfile.mkdtemp(prefix="reel2_")
        req = urllib.request.Request(produto["imagem"], headers={"User-Agent": "Mozilla/5.0"})
        self.foto = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGB")
        self.views = roteiro.get("views") or {"principal": None, "z1": [0.2, 0.2, 0.8, 0.8], "z2": [0.0, 0.0, 0.6, 0.6], "z3": [0.4, 0.4, 1.0, 1.0]}
        self._cards = {}
        self.rnd = random.Random(int(produto["id"]))
        self._preparar_fundo()
        self.logo_p = logo_circular(88)
        self.logo_g = logo_circular(300)
        self.selo = selo_desconto(produto["desconto_percentual"])
        self._header = self._montar_header()
        self._cache = {}
        self.particulas = [(self.rnd.uniform(0, W), self.rnd.uniform(0, H), self.rnd.uniform(3, 9), self.rnd.uniform(20, 70), self.rnd.uniform(0, 6.28)) for _ in range(46)]

    # ---------- preparacao
    def _preparar_fundo(self):
        f = self.foto
        esc = max((W + 160) / f.width, (H + 160) / f.height)
        bg = f.resize((int(f.width * esc), int(f.height * esc)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(38))
        cor = Image.new("RGB", (1, bg.height))
        for y in range(bg.height):
            k = y / bg.height
            cor.putpixel((0, y), tuple(int((246, 96, 44)[i] + ((150, 28, 14)[i] - (246, 96, 44)[i]) * k ** 1.2) for i in range(3)))
        self.bg = Image.blend(bg, cor.resize(bg.size), 0.86).convert("RGBA")
        # raios
        R = 1500
        raios = Image.new("L", (R, R), 0)
        d = ImageDraw.Draw(raios)
        for k in range(18):
            a0 = k * 20
            d.pieslice([0, 0, R, R], a0, a0 + 9, fill=70)
        mask = Image.new("L", (R, R), 0)
        ImageDraw.Draw(mask).ellipse([R * .1, R * .1, R * .9, R * .9], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(160))
        raios = Image.composite(raios, Image.new("L", (R, R), 0), mask)
        self.raios = Image.new("RGBA", (R, R), AMARELO + (0,))
        self.raios.putalpha(raios)
        # fundo do CTA
        cta = Image.new("RGB", (1, H))
        for y in range(H):
            t = y / H
            cta.putpixel((0, y), tuple(int(LARANJA[i] + ((180, 40, 20)[i] - LARANJA[i]) * t) for i in range(3)))
        self.bg_cta = cta.resize((W, H)).convert("RGBA")

    def _montar_header(self):
        im = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
        im.alpha_composite(self.logo_p, (56, 140))
        t = texto_img(["@achados_do_genio"], fonte("texto", 40, 800), sombra=True, alinhamento="l")
        im.alpha_composite(t, (160, 150))
        pub = pilula("Publicidade", fonte("texto", 28, 800), BRANCO, LARANJA, pad=(20, 7))
        im.alpha_composite(pub, (W - pub.width - 40, 160))
        return im

    def card(self, view, alvo=(860, 900)):
        k = (view, alvo)
        if k not in self._cards:
            box = self.views.get(view)
            f = self.foto
            if box:
                f = f.crop((int(box[0] * f.width), int(box[1] * f.height), int(box[2] * f.width), int(box[3] * f.height)))
            esc = min(alvo[0] / f.width, alvo[1] / f.height)
            cw, ch = int(f.width * esc), int(f.height * esc)
            big = f.resize((int(cw * 1.35), int(ch * 1.35)), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 60, 2))
            self._cards[k] = (big, cw, ch)
        return self._cards[k]

    def card_frame(self, view, zoom=1.0, pan=(0.0, 0.0), alvo=(860, 900), raio=44, borda=10):
        big, cw, ch = self.card(view, alvo)
        # area visivel (em pixels de big) encolhe com o zoom
        aw, ah = big.width / zoom, big.height / zoom
        cx = big.width / 2 + pan[0] * (big.width - aw) / 2
        cy = big.height / 2 + pan[1] * (big.height - ah) / 2
        reg = big.crop((int(cx - aw / 2), int(cy - ah / 2), int(cx + aw / 2), int(cy + ah / 2))).resize((cw, ch), Image.BILINEAR)
        out = Image.new("RGBA", (cw + borda * 2, ch + borda * 2), (0, 0, 0, 0))
        ImageDraw.Draw(out).rounded_rectangle([0, 0, out.width - 1, out.height - 1], raio + borda, fill=BRANCO)
        m = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, cw - 1, ch - 1], raio, fill=255)
        reg = reg.convert("RGBA")
        reg.putalpha(m)
        out.alpha_composite(reg, (borda, borda))
        return out

    def sombra_card(self, w, h):
        k = ("sombra", w, h)
        if k not in self._cache:
            b = 34
            s = Image.new("RGBA", (w + b * 4, h + b * 4), (0, 0, 0, 0))
            ImageDraw.Draw(s).rounded_rectangle([b * 2, b * 2, b * 2 + w, b * 2 + h], 54, fill=(20, 5, 0, 150))
            self._cache[k] = s.filter(ImageFilter.GaussianBlur(b))
        return self._cache[k]

    def cached(self, k, fn):
        if k not in self._cache:
            self._cache[k] = fn()
        return self._cache[k]

    # ---------- camadas comuns
    def fundo(self, t, escuro=0):
        dx = int(80 + 60 * math.sin(t * 0.35))
        dy = int(80 + 50 * math.cos(t * 0.27))
        fr = self.bg.crop((dx, dy, dx + W, dy + H))
        rot = self.raios.rotate(t * 9 % 360, resample=Image.BILINEAR)
        fr.alpha_composite(rot, (int(W / 2 - rot.width / 2), int(960 - rot.height / 2)))
        d = ImageDraw.Draw(fr)
        for (x, y, r, v, ph) in self.particulas:
            yy = (y - v * t) % H
            a = int(110 + 110 * math.sin(t * 3 + ph))
            d.ellipse([x - r, yy - r, x + r, yy + r], fill=(255, 235, 180, a))
        if escuro:
            fr.alpha_composite(Image.new("RGBA", (W, H), (10, 4, 2, int(escuro))))
        return fr

    def brilho(self, im, prog):
        """Faixa de brilho diagonal passando sobre a imagem (prog 0..1)."""
        if not 0 < prog < 1:
            return im
        w, h = im.size
        faixa = Image.new("L", (w, h), 0)
        x = -w * 0.6 + prog * w * 2.2
        ImageDraw.Draw(faixa).polygon([(x, 0), (x + w * .18, 0), (x + w * .18 - h * .5, h), (x - h * .5, h)], fill=150)
        faixa = faixa.filter(ImageFilter.GaussianBlur(18))
        a = ImageOps.invert(Image.new("L", (w, h), 255))
        faixa = Image.composite(faixa, a, im.getchannel("A"))
        luz = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        luz.putalpha(faixa)
        out = im.copy()
        out.alpha_composite(luz)
        return out

    # ---------- cenas
    def cena_hook(self, t, tl, fr_info):
        fr = self.fundo(t)
        linhas = fr_info.get("tela") or [self.r.get("titulo_tela", "")]
        f = fonte("titulo", 118, 800)
        txt = self.cached(("hook", tuple(linhas)), lambda: texto_img(linhas, f, cores=[BRANCO, AMARELO], stroke=6, stroke_cor=ESCURO))
        a = ease_back(tl / 0.22)
        colar(fr, txt, W / 2, 420, escala=0.55 + 0.45 * a + 0.4 * (1 - clamp(tl / 0.22)), rot=-3 * (1 - a) + 1.2 * math.sin(tl * 5) * 0.4)
        # produto entra de baixo com impacto
        ap = ease_back((tl - 0.15) / 0.45)
        card = self.card_frame("principal", zoom=1.0 + 0.05 * tl, alvo=(820, 820))
        y = 1060 + (1 - ap) * 900
        colar(fr, self.sombra_card(card.width, card.height), W / 2, y + 30)
        colar(fr, card, W / 2, y, rot=4 * (1 - ap))
        asl = ease_back((tl - 0.55) / 0.35)
        colar(fr, self.selo, W / 2 + 350, 700, escala=asl, rot=-14 + 5 * math.sin(t * 3))
        return fr

    def cena_problema(self, t, tl, dur, fr_info):
        fr = self.fundo(t, escuro=150)
        # produto escondido, so o contorno borrado ao fundo
        itens = fr_info.get("itens", [])
        f = fonte("titulo", 86, 800)
        n = max(1, len(itens))
        passo = min(0.9, (dur - 0.3) / n)
        for i, it in enumerate(itens):
            a = ease_back((tl - i * passo) / 0.3)
            if a <= 0:
                continue
            pil = self.cached(("prob", it), lambda it=it: pilula(it, f, BRANCO, ESCURO, pad=(40, 20), icone="x"))
            lado = -1 if i % 2 == 0 else 1
            x = W / 2 + lado * (1 - a) * 700
            colar(fr, pil, x, 560 + i * 200, rot=lado * 2.5 * (1 - clamp(tl - i * passo)))
        q = self.cached("prob_q", lambda: texto_img(["?"], fonte("titulo", 340, 800), cor=AMARELO, stroke=8))
        colar(fr, q, W / 2, 560 + n * 200 + 150, escala=0.9 + 0.1 * math.sin(tl * 6), alpha=clamp(tl / 0.3), rot=8 * math.sin(tl * 2))
        return fr

    def _topo_titulo(self, fr, fr_info, tl, y=420):
        rot = fr_info.get("rotulo")
        if rot:
            p = self.cached(("rot", rot), lambda: pilula(rot, fonte("texto", 44, 900), AMARELO, ESCURO, pad=(30, 10)))
            colar(fr, p, W / 2, y - 120, escala=ease_back(tl / 0.25))
        linhas = fr_info.get("tela") or [self.r.get("titulo_tela", "")]
        f = fonte("titulo", 104, 800)
        txt = self.cached(("sol", tuple(linhas)), lambda: texto_img(linhas, f, cor=BRANCO, stroke=6))
        colar(fr, txt, W / 2, y + 10 + (len(linhas) - 1) * 50, escala=0.7 + 0.3 * ease_back((tl - 0.08) / 0.3))
        sub = fr_info.get("sub")
        if sub:
            s = self.cached(("sub", sub), lambda: texto_img([sub], fonte("texto", 50, 800), cor=CREME))
            colar(fr, s, W / 2, y + 100 + (len(linhas) - 1) * 105, alpha=clamp((tl - 0.3) / 0.3))
        return y + 160 + (len(linhas) - 1) * 105

    def cena_solucao(self, t, tl, dur, fr_info):
        fr = self.fundo(t)
        base_y = self._topo_titulo(fr, fr_info, tl)
        a = ease_back(tl / 0.45)
        card = self.card_frame("principal", zoom=1.02 + 0.06 * tl / max(dur, 1), alvo=(800, 800 if base_y < 700 else 720))
        card = self.brilho(card, (tl - 0.35) / 0.8)
        cy = base_y + 60 + card.height / 2
        colar(fr, self.sombra_card(card.width, card.height), W / 2, cy + 30, escala=0.6 + 0.4 * a)
        colar(fr, card, W / 2, cy, escala=0.6 + 0.4 * a)
        colar(fr, self.selo, W / 2 + 350, cy - card.height / 2 + 30, escala=ease_back((tl - 0.4) / 0.3) * 0.85, rot=-12 + 5 * math.sin(t * 3))
        return fr

    def cena_detalhe(self, t, tl, dur, fr_info, segs):
        fr = self.fundo(t)
        nome = self.cached("nome_det", lambda: texto_img([self.r.get("titulo_tela", "")], fonte("titulo", 64, 800), cor=BRANCO, stroke=4))
        colar(fr, nome, W / 2, 330)
        idx = min(len(segs) - 1, int(tl / (dur / len(segs))))
        view, chip = segs[idx]
        tseg = tl - idx * (dur / len(segs))
        dseg = dur / len(segs)
        pans = [(-0.6, -0.4), (0.6, 0.3), (-0.3, 0.6), (0.5, -0.5)]
        p0 = pans[idx % len(pans)]
        k = tseg / dseg
        card = self.card_frame(view, zoom=1.05 + 0.22 * ease_in_out(k), pan=(p0[0] * (1 - 2 * k), p0[1] * (1 - 2 * k)), alvo=(860, 860))
        entra = ease_out(tseg / 0.22)
        x = W / 2 + (1 - entra) * W * (1 if idx % 2 == 0 else -1)
        colar(fr, self.sombra_card(card.width, card.height), x, 900 + 30)
        colar(fr, card, x, 900, rot=(1 - entra) * (6 if idx % 2 == 0 else -6))
        pil = self.cached(("chip", chip), lambda: pilula(chip, fonte("texto", 56, 900), VERDE, BRANCO, pad=(34, 14), icone="check"))
        colar(fr, pil, W / 2, 900 + card.height / 2 + 10, escala=ease_back((tseg - 0.15) / 0.3))
        # contador de itens (1/3, 2/3...)
        d = ImageDraw.Draw(fr)
        for i in range(len(segs)):
            cx = W / 2 + (i - (len(segs) - 1) / 2) * 34
            d.ellipse([cx - 8, 1440 - 8, cx + 8, 1440 + 8], fill=AMARELO if i == idx else (255, 255, 255, 120))
        return fr

    def cena_preco(self, t, tl, dur, fr_info):
        fr = self.fundo(t)
        card = self.card_frame("principal", zoom=1.04 + 0.03 * math.sin(tl * 2), alvo=(560, 560))
        colar(fr, self.sombra_card(card.width, card.height), W / 2, 640 + 24, escala=1.0)
        colar(fr, card, W / 2, 640, rot=2 * math.sin(tl * 2.5))
        colar(fr, self.selo, W / 2 + 290, 420, escala=ease_back(tl / 0.3) * (1 + 0.06 * math.sin(tl * 8)), rot=-14 + 8 * math.sin(t * 3))
        p = self.p
        # preco antigo riscado
        fo = fonte("texto", 64, 800)
        antigo = self.cached("antigo", lambda: texto_img([f"De {brl(p['preco_original'])}"], fo, cor=CREME, stroke=0))
        colar(fr, antigo, W / 2, 985, alpha=clamp(tl / 0.25))
        risco = clamp((tl - 0.25) / 0.3)
        if risco > 0:
            d = ImageDraw.Draw(fr)
            x0 = W / 2 - antigo.width / 2 + 20
            d.line([x0, 993, x0 + (antigo.width - 50) * risco, 979], fill=VERMELHO, width=10)
        # preco novo com impacto
        a = ease_back((tl - 0.5) / 0.35)
        if a > 0:
            caixa = self.cached("caixa_preco", lambda: self._caixa_preco())
            caixa_b = self.brilho(caixa, (tl - 0.9) / 0.7)
            colar(fr, caixa_b, W / 2, 1230, escala=0.4 + 0.6 * a + 0.04 * math.sin(tl * 7) * clamp(tl - 0.9))
        nota = self.cached("nota", lambda: self._nota())
        colar(fr, nota, W / 2, 1420, alpha=clamp((tl - 0.9) / 0.3))
        return fr

    def _caixa_preco(self):
        f1 = fonte("texto", 40, 900)
        f2 = fonte("titulo", 170, 800)
        txt = brl(self.p["preco_oferta"])
        d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        tw = d.textlength(txt, font=f2)
        w, h = int(tw + 110), 290
        im = Image.new("RGBA", (w + 30, h + 40), (0, 0, 0, 0))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([10, 20, w + 10, h + 20], 46, fill=(0, 0, 0, 140))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w, h], 46, fill=AMARELO)
        lab = "POR APENAS"
        lw = d.textlength(lab, font=f1)
        d.text(((w - lw) / 2, 22), lab, font=f1, fill=LARANJA)
        d.text(((w - tw) / 2, 62), txt, font=f2, fill=ESCURO)
        return im

    def _nota(self):
        p = self.p
        f = fonte("texto", 44, 800)
        txt = f"{p['avaliacao']:.1f}".replace(".", ",") + " de 5 na Shopee"
        d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        tw = d.textlength(txt, font=f)
        w, h = int(tw + 120), 80
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w - 1, h - 1], 40, fill=(24, 14, 10, 220))
        estrela(d, 50, 40, 24, AMARELO)
        d.text((88, 12), txt, font=f, fill=BRANCO)
        return im

    def cena_cta(self, t, tl, fr_info=None):
        fr = self.bg_cta.copy()
        rot = self.raios.rotate(t * 12 % 360, resample=Image.BILINEAR)
        fr.alpha_composite(rot, (int(W / 2 - rot.width / 2), int(620 - rot.height / 2)))
        a = ease_back(tl / 0.4)
        pulso = 1 + 0.05 * math.sin(tl * 7)
        anel = clamp((tl % 1.0) / 1.0)
        d = ImageDraw.Draw(fr)
        r = 170 + anel * 120
        d.ellipse([W / 2 - r, 620 - r, W / 2 + r, 620 + r], outline=(255, 255, 255, int(200 * (1 - anel))), width=8)
        colar(fr, self.logo_g, W / 2, 620, escala=a * pulso)
        linhas = (fr_info or {}).get("tela") or ["ACESSE O"]
        t1 = self.cached(("cta1", tuple(linhas)), lambda: texto_img(linhas, fonte("titulo", 104, 800), cores=[BRANCO, AMARELO], stroke=5))
        y1 = 930 + (len(linhas) - 1) * 40
        colar(fr, t1, W / 2, y1, escala=ease_back((tl - 0.1) / 0.3))
        y2 = y1 + 110 + len(linhas) * 55
        t2 = self.cached("cta2", lambda: pilula("LINK DA BIO", fonte("titulo", 112, 800), AMARELO, ESCURO, pad=(50, 16)))
        colar(fr, t2, W / 2, y2, escala=ease_back((tl - 0.2) / 0.3) * pulso)
        # seta apontando para o perfil (bio fica no topo)
        sy = y2 + 170 - 26 * abs(math.sin(tl * 5))
        d = ImageDraw.Draw(fr)
        d.polygon([(W / 2, sy - 60), (W / 2 - 50, sy), (W / 2 - 18, sy), (W / 2 - 18, sy + 60), (W / 2 + 18, sy + 60), (W / 2 + 18, sy), (W / 2 + 50, sy)], fill=BRANCO)
        t3 = self.cached("cta3", lambda: texto_img(["@achados_do_genio"], fonte("texto", 52, 800), cor=BRANCO))
        colar(fr, t3, W / 2, sy + 160, alpha=clamp((tl - 0.3) / 0.3))
        t4 = self.cached("cta4", lambda: pilula("Publicidade", fonte("texto", 30, 700), (255, 255, 255, 235), LARANJA, pad=(22, 6)))
        colar(fr, t4, W / 2, 1600)
        return fr

    # ---------- legendas
    def legenda(self, fr, t, blocos):
        for grupo in blocos:
            if grupo[0][0] <= t < grupo[-1][1] + 0.1:
                f = fonte("texto", 76, 900)
                d = ImageDraw.Draw(fr)
                pal = [g[2] for g in grupo]
                larg = sum(d.textlength(p + " ", font=f) for p in pal)
                camada = Image.new("RGBA", (int(larg + 60), 130), (0, 0, 0, 0))
                dc = ImageDraw.Draw(camada)
                x = 30
                for (a0, a1, p) in grupo:
                    ativo = a0 <= t < a1 + 0.04
                    dc.text((x, 18), p, font=f, fill=AMARELO if ativo else BRANCO, stroke_width=9, stroke_fill=ESCURO)
                    x += dc.textlength(p + " ", font=f)
                if camada.width > W - 60:
                    camada = camada.resize((W - 60, int(camada.height * (W - 60) / camada.width)), Image.BILINEAR)
                a = ease_back((t - grupo[0][0]) / 0.16)
                colar(fr, camada, W / 2, 1560, escala=0.75 + 0.25 * a)
                return

    # ---------- montagem
    def frame(self, t, linha, blocos, cortes):
        atual = linha[0]
        for fr_ in linha:
            if fr_["ini"] <= t:
                atual = fr_
        tl = t - atual["ini"]
        dur = atual["fim_cena"] - atual["ini"]
        c = atual["cena"]
        if c == "hook":
            img = self.cena_hook(t, max(0, t), atual)
        elif c == "problema":
            img = self.cena_problema(t, tl, dur, atual)
        elif c == "solucao":
            img = self.cena_solucao(t, tl, dur, atual)
        elif c == "detalhe":
            segs = [tuple(x) for x in atual.get("itens", [["principal", ""]])]
            img = self.cena_detalhe(t, tl, dur, atual, segs)
        elif c == "preco":
            img = self.cena_preco(t, tl, dur, atual)
        else:
            img = self.cena_cta(t, tl, atual)
        if c != "cta":
            img.alpha_composite(self._header)
            self.legenda(img, t, blocos)
        # efeitos de corte: whip, flash e punch
        for (tc, tipo) in cortes:
            dt = t - tc
            if tipo == "whip" and -0.1 < dt < 0.12:
                img = borrar_horizontal(img, 1 - abs(dt) / 0.12)
            if tipo in ("flash", "preco") and 0 <= dt < 0.16:
                img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - dt / 0.16)))))
            if 0 <= dt < 0.25:
                z = 1 + (0.09 if tipo == "preco" else 0.05) * (1 - dt / 0.25)
                cw, ch = int(W / z), int(H / z)
                sx = self.rnd.randint(-10, 10) if tipo == "preco" else 0
                sy = self.rnd.randint(-10, 10) if tipo == "preco" else 0
                x0, y0 = (W - cw) // 2 + sx, (H - ch) // 2 + sy
                img = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)
        return img.convert("RGB")

    def capa(self):
        fr = self.fundo(1.0)
        card = self.card_frame("principal", zoom=1.03, alvo=(760, 760))
        colar(fr, self.sombra_card(card.width, card.height), W / 2, 1150 + 30)
        colar(fr, card, W / 2, 1150)
        linhas = self.r.get("capa_titulo") or [self.r.get("titulo_tela", "").upper()]
        f = fonte("titulo", 132, 800)
        y = 330
        for i, l in enumerate(linhas):
            cor_f, cor_t = (AMARELO, ESCURO) if i == len(linhas) - 1 else (None, BRANCO)
            if cor_f:
                p = pilula(l, f, cor_f, cor_t, pad=(34, 4))
                colar(fr, p, W / 2, y + i * 150 + 10, rot=-2)
            else:
                colar(fr, texto_img([l], f, cor=cor_t, stroke=6), W / 2, y + i * 150)
        colar(fr, self.selo, W / 2 + 330, 820, rot=-14)
        preco = pilula(brl(self.p["preco_oferta"]), fonte("titulo", 96, 800), BRANCO, LARANJA, pad=(40, 6))
        colar(fr, preco, W / 2, 1560, rot=2)
        fr.alpha_composite(self._header)
        return fr.convert("RGB")


# ------------------------------------------------------------------ pipeline
def montar_frases(produto, roteiro, falar_preco):
    frases = []
    for fr in roteiro["frases"]:
        fr = dict(fr)
        if fr["cena"] == "preco":
            fr.update(falar_preco(produto))
        frases.append(fr)
    return frases


def narrar(frases, pasta):
    t, partes, linha = 0.05, [], []
    import time
    for i, fr in enumerate(frases):
        arq = os.path.join(pasta, f"f{i}.mp3")
        for tentativa in range(6):
            try:
                pal = asyncio.run(_tts(fr["fala"], arq))
                break
            except Exception:
                if tentativa == 5:
                    raise
                time.sleep(5 * (tentativa + 1))
        time.sleep(0.8)
        dur = duracao(arq)
        ini_f = pal[0][0] if pal else 0.0
        fim_f = min(pal[-1][1], dur) if pal else dur
        # comeca a fala no inicio da cena (corta silencio inicial do TTS)
        partes.append((arq, max(0.0, t - ini_f + 0.02)))
        fala_dur = fim_f - ini_f
        linha.append({**fr, "ini": t, "fala_ini": t + 0.02, "fala_fim": t + 0.02 + fala_dur})
        extra = 0.55 if fr["cena"] == "preco" else 0.12
        t = t + 0.02 + fala_dur + extra
    for i, fr in enumerate(linha):
        fr["fim_cena"] = linha[i + 1]["ini"] if i + 1 < len(linha) else t + 0.9
    total = t + 0.9
    return partes, linha, total


def mixar_audio(partes, pasta, total, musica, cortes):
    wh, ding = sfx(pasta)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for arq, _ in partes:
        cmd += ["-i", arq]
    n = len(partes)
    cmd += ["-ss", "4", "-i", musica, "-i", wh, "-i", ding]
    im, iw, idg = n, n + 1, n + 2
    f = ""
    for i, (_, p) in enumerate(partes):
        ms = int(p * 1000)
        f += f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{i}];"
    f += "".join(f"[v{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad,atrim=0:{total:.3f},volume=1.5,asplit=2[voz][sc];"
    f += f"[{im}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume=0.42,afade=t=in:d=0.4,afade=t=out:st={total - 1.2:.3f}:d=1.2[mus];"
    f += "[mus][sc]sidechaincompress=threshold=0.02:ratio=6:attack=8:release=300[musd];"
    sons = [(tc, "w") for tc, tipo in cortes if tipo in ("whip", "flash")] + [(tc, "d") for tc, tipo in cortes if tipo == "preco"]
    nw = sum(1 for _, k in sons if k == "w")
    nd = sum(1 for _, k in sons if k == "d")
    rotulos = []
    if nw:
        f += f"[{iw}:a]asplit={nw}" + "".join(f"[w{i}]" for i in range(nw)) + ";"
    if nd:
        f += f"[{idg}:a]asplit={nd}" + "".join(f"[d{i}]" for i in range(nd)) + ";"
    iw_, id_ = 0, 0
    for tc, k in sons:
        ms = int(max(0, tc - 0.15) * 1000) if k == "w" else int(tc * 1000)
        src = f"w{iw_}" if k == "w" else f"d{id_}"
        lab = f"s{len(rotulos)}"
        f += f"[{src}]adelay={ms}|{ms}[{lab}];"
        rotulos.append(lab)
        if k == "w":
            iw_ += 1
        else:
            id_ += 1
    entradas = "[voz][musd]" + "".join(f"[{l}]" for l in rotulos)
    f += f"{entradas}amix=inputs={2 + len(rotulos)}:normalize=0,atrim=0:{total:.3f},loudnorm=I=-14:TP=-1.5:LRA=9[out]"
    wav = os.path.join(pasta, "audio.wav")
    final = cmd + ["-filter_complex", f, "-map", "[out]", "-t", f"{total:.3f}", "-ar", "48000", "-ac", "2", wav]
    final.insert(1, "-nostdin")
    for tentativa in range(3):  # a mixagem ja travou uma vez: limita o tempo e tenta de novo
        try:
            subprocess.run(final, check=True, timeout=240)
            return wav
        except subprocess.TimeoutExpired:
            print(f"mixagem de audio demorou demais, tentativa {tentativa + 1}/3")
    raise RuntimeError("falha na mixagem de audio")


def blocos_legenda(linha):
    blocos = []
    for fr in linha:
        if fr["cena"] == "cta" or not fr.get("legenda"):
            continue
        pal = fr["legenda"].split()
        pesos = [len(p) + 2 for p in pal]
        tot = sum(pesos)
        ini, fim = fr["fala_ini"], fr["fala_fim"]
        acc, tempos = 0, []
        for p, w in zip(pal, pesos):
            a = ini + (fim - ini) * acc / tot
            acc += w
            tempos.append((a, ini + (fim - ini) * acc / tot, p))
        g = []
        for it in tempos:
            g.append(it)
            if len(g) == 3 or it[2][-1:] in ".,!?:":
                blocos.append(g)
                g = []
        if g:
            blocos.append(g)
    return blocos


def cortes_da_linha(linha):
    cortes = []
    for fr in linha[1:]:
        tipo = {"solucao": "flash", "preco": "flash", "cta": "whip"}.get(fr["cena"], "whip")
        cortes.append((fr["ini"], tipo))
        if fr["cena"] == "detalhe":
            n = len(fr.get("itens", [])) or 1
            d = (fr["fim_cena"] - fr["ini"]) / n
            cortes += [(fr["ini"] + d * k, "whip") for k in range(1, n)]
        if fr["cena"] == "preco":
            cortes.append((fr["ini"] + 0.5, "preco"))
    return sorted(cortes)


def renderizar(produto, roteiro, saida_mp4, saida_capa, falar_preco):
    reel = Reel(produto, roteiro)
    frases = montar_frases(produto, roteiro, falar_preco)
    partes, linha, total = narrar(frases, reel.pasta)
    if not 12 <= total <= 30:
        raise RuntimeError(f"Duracao fora do alvo: {total:.1f}s")
    cortes = cortes_da_linha(linha)
    musica = musica_para(produto["id"])
    wav = mixar_audio(partes, reel.pasta, total, musica, cortes)
    reel.capa().save(saida_capa, quality=92)
    blocos = blocos_legenda(linha)
    n = int(total * FPS)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "4500k",
           "-bufsize", "9000k", "-g", "60", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest",
           "-movflags", "+faststart", saida_mp4]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    capa = Image.open(saida_capa).convert("RGB").tobytes()
    for i in range(n):
        # quadro 0 = capa (o Instagram usa thumb_offset=0 como capa do Reel)
        proc.stdin.write(capa if i == 0 else reel.frame(i / FPS, linha, blocos, cortes).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("FFmpeg falhou")
    return {"duracao": round(total, 2), "musica": os.path.basename(musica),
            "linha_do_tempo": [{"cena": f["cena"], "ini": round(f["ini"], 2), "fim": round(f["fim_cena"], 2)} for f in linha]}
