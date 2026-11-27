"""Reel formato DESCOBERTA (v3.1) - padrao Achados do Genio.

- Produto ocupando a maior parte da tela: foto oficial em tela cheia (nitida) ou recortada sobre
  fundo de estudio nas cores da marca. Sem fundo desfocado.
- Gancho com impacto visual nos 2 primeiros segundos, cortes a cada 1-2 s, legendas sincronizadas.
- Textos dentro das areas seguras do Instagram (fora do topo ~220 px, da base ~380 px e da coluna de botoes).
- Estrutura: impacto (0-2 s) > demonstracao/beneficios > preco real > chamada para acao.
- Cenas de contexto do Pixabay (licenca comercial) quando houver PIXABAY_KEY.
"""
import io
import math
import os
import random
import subprocess
import tempfile
import urllib.request

from PIL import Image, ImageDraw, ImageFilter

import midia
import video2 as v2
from video2 import (AMARELO, BRANCO, ESCURO, FPS, H, LARANJA, VERDE, W, brl, clamp, colar, ease_back, ease_in_out,
                    fonte, pilula, texto_img)

# areas seguras (Instagram Reels): texto entre Y_TOPO e Y_BASE, largura util MAX_TXT centralizada
Y_TOPO, Y_BASE, MAX_TXT = 250, 1540, 880
Y_LEGENDA = 1420


def _gradiente(alto, de, ate, topo=True):
    g = Image.new("L", (1, alto))
    for y in range(alto):
        k = y / max(alto - 1, 1)
        g.putpixel((0, y), int(de + (ate - de) * (k if topo else 1 - k)))
    return g.resize((W, alto))


class ReelDescoberta:
    def __init__(self, produto, roteiro, cenas=None):
        self.p, self.r = produto, roteiro
        self.pasta = tempfile.mkdtemp(prefix="reel3_")
        req = urllib.request.Request(produto["imagem"], headers={"User-Agent": "Mozilla/5.0"})
        self.foto = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGB")
        self.recorte, self.info_recorte = midia.recortar_produto(self.foto)
        self.views = roteiro.get("views") or {"principal": None}
        self.rnd = random.Random(int(produto["id"]))
        self.cenas = cenas or []
        self.clips = [midia.LeitorClip(c["arquivo"], inicio=1.0, escurecer=0.25) for c in self.cenas]
        self._cache = {}
        self._header = self._montar_header()
        self.selo = v2.selo_desconto(produto["desconto_percentual"], s=230)
        # sombras de leitura (topo e base) para o texto nao depender de fundo desfocado
        self.sombra_topo = Image.new("RGBA", (W, 700), (0, 0, 0, 0))
        self.sombra_topo.putalpha(_gradiente(700, 170, 0))
        self.sombra_base = Image.new("RGBA", (W, 760), (0, 0, 0, 0))
        self.sombra_base.putalpha(_gradiente(760, 0, 190))
        self.estudio = self._fundo_estudio()

    # ---------- base
    def _montar_header(self):
        im = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
        im.alpha_composite(v2.logo_circular(70), (60, 240))
        im.alpha_composite(texto_img(["@achados_do_genio"], fonte("texto", 34, 800), sombra=True, alinhamento="l"), (146, 250))
        pub = pilula("Publicidade", fonte("texto", 26, 800), BRANCO, LARANJA, pad=(18, 6))
        im.alpha_composite(pub, (W - pub.width - 60, 256))
        return im

    def _fundo_estudio(self):
        """Fundo limpo de estudio nas cores da marca (luz radial), para o produto recortado."""
        base = Image.new("RGB", (1, H))
        for y in range(H):
            k = y / H
            base.putpixel((0, y), tuple(int((250, 112, 52)[i] + ((168, 36, 18)[i] - (250, 112, 52)[i]) * k) for i in range(3)))
        base = base.resize((W, H)).convert("RGBA")
        luz = Image.new("L", (W, H), 0)
        ImageDraw.Draw(luz).ellipse([W * 0.05, H * 0.28, W * 0.95, H * 0.72], fill=150)
        luz = luz.filter(ImageFilter.GaussianBlur(160))
        camada = Image.new("RGBA", (W, H), (255, 214, 150, 0))
        camada.putalpha(luz)
        base.alpha_composite(camada)
        return base

    def cached(self, k, fn):
        if k not in self._cache:
            self._cache[k] = fn()
        return self._cache[k]

    def _foco_principal(self):
        """Centro do produto na foto (pelo recorte), para enquadrar a tela cheia."""
        if self.recorte is not None and "bbox" in self.info_recorte:
            x0, y0, x1, y1 = self.info_recorte["bbox"]
            return (x0 + x1) / 2 / self.foto.width, (y0 + y1) / 2 / self.foto.height
        return 0.5, 0.5

    def tela_cheia(self, view, k, z0=1.0, z1=1.12, desloc=0.25):
        """Foto oficial em tela cheia 9:16, nitida, com movimento de camera (k = 0..1)."""
        def base():
            f = self.foto
            box = self.views.get(view)
            if box:
                cx, cy = (box[0] + box[2]) / 2 * f.width, (box[1] + box[3]) / 2 * f.height
                hh = max((box[3] - box[1]) * f.height, (box[2] - box[0]) * f.width * 16 / 9)
            else:
                fx, fy = self._foco_principal()
                cx, cy, hh = fx * f.width, fy * f.height, f.height
            hh = min(hh, f.height)
            ww = min(hh * 9 / 16, f.width)
            hh = ww * 16 / 9
            x0 = min(max(0, cx - ww / 2), f.width - ww)
            y0 = min(max(0, cy - hh / 2), f.height - hh)
            reg = f.crop((int(x0), int(y0), int(x0 + ww), int(y0 + hh)))
            return reg.resize((int(W * 1.3), int(H * 1.3)), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 60, 2))
        big = self.cached(("tc", view), base)
        z = z0 + (z1 - z0) * ease_in_out(clamp(k))
        ww, hh = big.width / (1.3 * z) * 1.0, big.height / (1.3 * z)
        ox = (big.width - ww) * (0.5 + desloc * (k - 0.5))
        oy = (big.height - hh) * 0.5
        return big.crop((int(ox), int(oy), int(ox + ww), int(oy + hh))).resize((W, H), Image.BILINEAR).convert("RGBA")

    def produto(self, alvo):
        def faz():
            im = self.recorte
            esc = min(alvo[0] / im.width, alvo[1] / im.height)
            im = im.resize((int(im.width * esc), int(im.height * esc)), Image.LANCZOS)
            pad = 70
            out = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
            sombra = Image.new("RGBA", out.size, (0, 0, 0, 0))
            sombra.paste((40, 10, 0, 255), (pad + 10, pad + 34), im.getchannel("A").point(lambda v: int(v * 0.6)))
            out.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(26)))
            out.alpha_composite(im, (pad, pad))
            return out
        return self.cached(("prod", alvo), faz)

    def fundo_contexto(self, idx, k):
        if self.clips:
            return self.clips[idx % len(self.clips)].quadro()
        return self.tela_cheia("principal", k)

    def leitura(self, fr, topo=True, base=True):
        if topo:
            fr.alpha_composite(self.sombra_topo, (0, 0))
        if base:
            fr.alpha_composite(self.sombra_base, (0, H - 760))
        return fr

    def texto(self, chave, linhas, tam, cores=None):
        def faz():
            t = texto_img(linhas, fonte("titulo", tam, 800), cores=cores or [BRANCO, AMARELO, BRANCO], stroke=7)
            if t.width > MAX_TXT:
                t = t.resize((MAX_TXT, int(t.height * MAX_TXT / t.width)), Image.LANCZOS)
            return t
        return self.cached(("txt", chave, tuple(linhas), tam), faz)

    # ---------- cenas
    def cartao(self, alvo):
        """Foto oficial INTEIRA (produto reconhecivel), cantos arredondados."""
        def faz():
            f = self.foto
            esc = min(alvo[0] / f.width, alvo[1] / f.height)
            cw, ch = int(f.width * esc), int(f.height * esc)
            out = Image.new("RGBA", (cw + 16, ch + 16), (0, 0, 0, 0))
            ImageDraw.Draw(out).rounded_rectangle([0, 0, cw + 15, ch + 15], 44, fill=BRANCO)
            m = Image.new("L", (cw, ch), 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, cw - 1, ch - 1], 38, fill=255)
            reg = f.resize((cw, ch), Image.LANCZOS).convert("RGBA")
            reg.putalpha(m)
            out.alpha_composite(reg, (8, 8))
            return out
        return self.cached(("cartao", alvo), faz)

    def produto_inteiro(self, alvo):
        return self.produto(alvo) if self.recorte is not None else self.cartao(alvo)

    def etiqueta_nome(self):
        nome = (self.r.get("titulo_tela") or self.p["nome"]).strip()
        return self.cached("nome", lambda: pilula(nome, fonte("texto", 44, 900), (255, 255, 255, 240), ESCURO, pad=(28, 10)))

    def cena_hook(self, t, tl, dur, info):
        # impacto com o produto INTEIRO e reconhecivel desde o 1o quadro ("soco" de zoom) + gancho
        soco = 1.15 - 0.15 * ease_back(clamp(tl / 0.45))
        fr = self.estudio.copy()
        colar(fr, self.produto_inteiro((860, 760)), W / 2, 1150 + 8 * math.sin(tl * 3), escala=soco, rot=1.2 * math.sin(tl * 2.5))
        self.leitura(fr, base=False)
        linhas = info.get("tela") or ["OLHA ISSO!"]
        colar(fr, self.texto("hook", linhas, 108), W / 2, 530 + (len(linhas) - 1) * 44, escala=ease_back(clamp(tl / 0.22)))
        return fr

    def cena_problema(self, t, tl, dur, info):
        fr = self.fundo_contexto(1, clamp(tl / max(dur, 0.1)))
        fr.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 110)))
        for i, it in enumerate(info.get("itens", [])):
            ti = tl - 0.1 - i * 0.35
            if ti >= 0:
                p = self.cached(("prob", it), lambda it=it: pilula(it, fonte("texto", 66, 900), (255, 255, 255, 245), ESCURO, pad=(36, 16)))
                colar(fr, p, W / 2, 760 + i * 160, escala=ease_back(clamp(ti / 0.22)), rot=-2 + 4 * (i % 2))
        return fr

    def cena_solucao(self, t, tl, dur, info):
        k = clamp(tl / max(dur, 0.1))
        meio = dur / 2
        if self.recorte is not None and tl < meio:
            fr = self.estudio.copy()
            colar(fr, self.produto((1020, 1020)), W / 2 + 18 * math.sin(tl * 1.6), 1020,
                  escala=(0.9 + 0.1 * ease_back(clamp(tl / 0.3))) * (1 + 0.05 * k), rot=1.5 * math.sin(tl * 2))
        else:
            fr = self.tela_cheia("principal" if self.recorte is not None else next(iter(self.views)), k, 1.05, 1.18, 0.4)
        self.leitura(fr, base=True)
        rot_ = info.get("rotulo")
        if rot_:
            p = self.cached(("rot", rot_), lambda: pilula(rot_, fonte("texto", 40, 900), AMARELO, ESCURO, pad=(24, 8)))
            colar(fr, p, W / 2, 380, escala=ease_back(clamp(tl / 0.2)))
        linhas = info.get("tela") or []
        if linhas:
            colar(fr, self.texto("sol", linhas, 98, [BRANCO, BRANCO]), W / 2, 530 + (len(linhas) - 1) * 46,
                  escala=ease_back(clamp((tl - 0.06) / 0.22)))
        return fr

    def cena_detalhe(self, t, tl, dur, info, segs):
        n = len(segs)
        d = dur / n
        i = min(int(tl / d), n - 1)
        view, rot_ = segs[i]
        ti = tl - i * d
        if view == "principal" and self.recorte is not None:
            fr = self.estudio.copy()
            colar(fr, self.produto((1040, 1040)), W / 2, 1000, escala=1.02 + 0.06 * clamp(ti / d), rot=1.2 * math.sin(ti * 2.4))
        else:
            fr = self.tela_cheia(view, clamp(ti / d), 1.0, 1.15, 0.5 if i % 2 else -0.5)
        self.leitura(fr, topo=False, base=True)
        if rot_:
            chip = self.cached(("chip", rot_), lambda: pilula(rot_, fonte("texto", 56, 900), VERDE, BRANCO, pad=(32, 12)))
            colar(fr, chip, W / 2, 1270, escala=ease_back(clamp(ti / 0.2)))
        return fr

    def cena_preco(self, t, tl, dur, info):
        fr = self.estudio.copy()
        colar(fr, self.produto_inteiro((860, 680)), W / 2, 780 + 8 * math.sin(tl * 3), escala=0.96 + 0.04 * ease_back(clamp(tl / 0.3)))
        colar(fr, self.selo, W / 2 + 300, 470, escala=ease_back(clamp((tl - 0.25) / 0.3)), rot=-12)
        de = self.cached("de", lambda: texto_img([f"De {brl(self.p['preco_original'])}"], fonte("texto", 54, 800), cor=(255, 236, 222)))
        y = 1170
        colar(fr, de, W / 2, y, alpha=clamp(tl / 0.2))
        if tl > 0.15:
            ImageDraw.Draw(fr).line([(W / 2 - de.width / 2 + 14, y - 4), (W / 2 + de.width / 2 - 14, y - 4)], fill=(255, 236, 222), width=6)
        pr = self.cached("pr", lambda: pilula(f"HOJE: {brl(self.p['preco_oferta'])}", fonte("titulo", 108, 800), AMARELO, ESCURO, pad=(40, 10)))
        colar(fr, pr, W / 2, 1300, escala=ease_back(clamp((tl - 0.4) / 0.28)), rot=-2)
        return fr

    def cena_cta(self, t, tl, info):
        fr = self.estudio.copy()
        colar(fr, self.produto_inteiro((720, 600)), W / 2, 660 + 8 * math.sin(tl * 3), escala=0.92 + 0.08 * ease_back(clamp(tl / 0.3)))
        linhas = info.get("tela") or ["CONFIRA"]
        colar(fr, self.texto("cta", linhas, 112, [BRANCO, AMARELO]), W / 2, 1080, escala=ease_back(clamp((tl - 0.05) / 0.28)))
        botao = info.get("botao") or "LINK NA BIO"
        b = self.cached(("bt", botao), lambda: pilula(botao, fonte("titulo", 76 if len(botao) < 16 else 56, 800), AMARELO, ESCURO, pad=(40, 14)))
        colar(fr, b, W / 2, 1260, escala=ease_back(clamp((tl - 0.18) / 0.28)) * (1 + 0.04 * math.sin(tl * 7)))
        site = self.cached("site", lambda: texto_img(["achadosdogenio.com.br"], fonte("texto", 44, 800)))
        colar(fr, site, W / 2, 1380, alpha=clamp((tl - 0.45) / 0.3))
        return fr

    # ---------- legendas (dentro da area segura)
    def legenda(self, fr, t, blocos):
        for grupo in blocos:
            if grupo[0][0] <= t < grupo[-1][1] + 0.1:
                f = fonte("texto", 74, 900)
                d = ImageDraw.Draw(fr)
                larg = sum(d.textlength(g[2] + " ", font=f) for g in grupo)
                camada = Image.new("RGBA", (int(larg + 60), 130), (0, 0, 0, 0))
                dc = ImageDraw.Draw(camada)
                x = 30
                for (a0, a1, p) in grupo:
                    dc.text((x, 18), p, font=f, fill=AMARELO if a0 <= t < a1 + 0.04 else BRANCO, stroke_width=9, stroke_fill=ESCURO)
                    x += dc.textlength(p + " ", font=f)
                if camada.width > MAX_TXT:
                    camada = camada.resize((MAX_TXT, int(camada.height * MAX_TXT / camada.width)), Image.BILINEAR)
                colar(fr, camada, W / 2, Y_LEGENDA, escala=0.8 + 0.2 * ease_back((t - grupo[0][0]) / 0.14))
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
            img = self.cena_hook(t, max(0, t), atual["fim_cena"], atual)
        elif c == "problema":
            img = self.cena_problema(t, tl, dur, atual)
        elif c == "solucao":
            img = self.cena_solucao(t, tl, dur, atual)
        elif c == "detalhe":
            img = self.cena_detalhe(t, tl, dur, atual, [tuple(x) for x in atual.get("itens", [["principal", ""]])])
        elif c == "preco":
            img = self.cena_preco(t, tl, dur, atual)
        else:
            img = self.cena_cta(t, tl, atual)
        img.alpha_composite(self._header)
        if c in ("hook", "problema", "detalhe", "preco"):
            # nome do produto sempre visivel: quem assiste sabe o que esta sendo anunciado
            colar(img, self.etiqueta_nome(), W / 2, 360)
        if c not in ("cta", "preco"):
            self.legenda(img, t, blocos)
        for (tc, tipo) in cortes:
            dt = t - tc
            if tipo == "whip" and -0.08 < dt < 0.1:
                img = v2.borrar_horizontal(img, 1 - abs(dt) / 0.1)
            if tipo in ("flash", "preco") and 0 <= dt < 0.1:
                img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(160 * (1 - dt / 0.1)))))
            if 0 <= dt < 0.2:
                z = 1 + (0.08 if tipo == "preco" else 0.05) * (1 - dt / 0.2)
                cw, ch = int(W / z), int(H / z)
                x0, y0 = (W - cw) // 2, (H - ch) // 2
                img = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)
        return img.convert("RGB")

    def capa(self, linhas):
        """Capa: produto grande + ate 2 linhas curtas (dentro da area central do grid 4:5 tambem)."""
        fr = self.estudio.copy()
        colar(fr, self.produto_inteiro((960, 900)), W / 2, 1100)
        self.leitura(fr, base=False)
        colar(fr, self.texto("capa", linhas[:2], 128, [BRANCO, AMARELO]), W / 2, 520 + (min(len(linhas), 2) - 1) * 52, rot=-2)
        fr.alpha_composite(self._header)
        return fr.convert("RGB")

    def fechar(self):
        for c in self.clips:
            c.fechar()


def cortes_rapidos(linha):
    """Cortes a cada troca de cena e a cada close; hook e solucao ganham corte no meio."""
    cortes = v2.cortes_da_linha(linha)
    for fr in linha:
        if fr["cena"] in ("hook", "solucao"):
            cortes.append(((fr["ini"] + fr["fim_cena"]) / 2 if fr["cena"] == "solucao" else fr["fim_cena"] * 0.55, "whip"))
    return sorted(cortes)


def renderizar(produto, roteiro, saida_mp4, saida_capa, falar_preco, voz=None, taxa=None, cenas=None, capa_linhas=None,
               musica=None, duracao_max=18.5):
    if voz:
        v2.VOZ = voz
    if taxa:
        v2.TAXA = taxa
    reel = ReelDescoberta(produto, roteiro, cenas)
    frases = v2.montar_frases(produto, roteiro, falar_preco)
    partes, linha, total = v2.narrar(frases, reel.pasta)
    if total > duracao_max:  # acelera a narracao para caber em 12-18 s
        v2.TAXA = "+28%"
        partes, linha, total = v2.narrar(frases, reel.pasta)
    if not 8 <= total <= 24:
        raise RuntimeError(f"Duracao fora do alvo: {total:.1f}s")
    cortes = cortes_rapidos(linha)
    musica = musica or v2.musica_para(produto["id"])
    wav = v2.mixar_audio(partes, reel.pasta, total, musica, cortes)
    reel.capa(capa_linhas or ["OLHA ISSO"]).save(saida_capa, quality=92)
    blocos = v2.blocos_legenda(linha)
    n = int(total * FPS)
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "5000k",
           "-bufsize", "10000k", "-g", "60", "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "aac", "-b:a", "128k",
           "-ar", "48000", "-shortest", "-movflags", "+faststart", saida_mp4]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    capa = Image.open(saida_capa).convert("RGB").tobytes()
    try:
        for i in range(n):
            proc.stdin.write(capa if i == 0 else reel.frame(i / FPS, linha, blocos, cortes).tobytes())
    finally:
        proc.stdin.close()
        reel.fechar()
    if proc.wait() != 0:
        raise RuntimeError("FFmpeg falhou")
    return {"duracao": round(total, 2), "musica": os.path.basename(musica), "formato_video": "descoberta_v3.1",
            "recorte": {k: v for k, v in reel.info_recorte.items() if k != "bbox"},
            "cenas_banco": [{k: c[k] for k in ("fonte", "id", "autor", "termo", "pagina")} for c in (cenas or [])],
            "linha_do_tempo": [{"cena": f["cena"], "ini": round(f["ini"], 2), "fim": round(f["fim_cena"], 2)} for f in linha]}
