"""Reel formato DESCOBERTA (v3): conteudo de descoberta de produto, nao panfleto.

- Cenas reais de contexto (banco de video com licenca comercial) quando houver chave do Pixabay.
- Produto recortado da foto oficial (IA local), com movimento de camera e profundidade.
- Closes em tela cheia, cortes rapidos, legendas dinamicas.
- Beneficio primeiro, preco so no fim; chamada para comentar, salvar e compartilhar.
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
                    ease_out, fonte, pilula, texto_img)


class ReelDescoberta:
    def __init__(self, produto, roteiro, cenas=None):
        self.p, self.r = produto, roteiro
        self.pasta = tempfile.mkdtemp(prefix="reel3_")
        req = urllib.request.Request(produto["imagem"], headers={"User-Agent": "Mozilla/5.0"})
        self.foto = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGB")
        self.recorte, self.info_recorte = midia.recortar_produto(self.foto)
        self.views = roteiro.get("views") or {"principal": None, "z1": [0.15, 0.15, 0.85, 0.85]}
        self.rnd = random.Random(int(produto["id"]))
        self.cenas = cenas or []
        self.clips = [midia.LeitorClip(c["arquivo"], inicio=1.0, escurecer=0.30) for c in self.cenas]
        self._cache = {}
        self._preparar_fundo()
        self._header = self._montar_header()
        self.selo = v2.selo_desconto(produto["desconto_percentual"], s=230)

    # ---------- base
    def _preparar_fundo(self):
        f = self.foto
        esc = max((W + 200) / f.width, (H + 200) / f.height)
        bg = f.resize((int(f.width * esc), int(f.height * esc)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(30))
        escuro = Image.new("RGB", bg.size, (12, 8, 6))
        self.bg = Image.blend(bg, escuro, 0.45).convert("RGBA")
        vin = Image.new("L", (W, H), 0)
        ImageDraw.Draw(vin).ellipse([-300, -200, W + 300, H + 200], fill=255)
        vin = vin.filter(ImageFilter.GaussianBlur(220))
        self.vinheta = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.vinheta.putalpha(vin.point(lambda v: int((255 - v) * 0.55)))

    def _montar_header(self):
        im = Image.new("RGBA", (W, 260), (0, 0, 0, 0))
        im.alpha_composite(v2.logo_circular(76), (48, 140))
        im.alpha_composite(texto_img(["@achados_do_genio"], fonte("texto", 36, 800), sombra=True, alinhamento="l"), (140, 150))
        pub = pilula("Publicidade", fonte("texto", 26, 800), BRANCO, LARANJA, pad=(18, 6))
        im.alpha_composite(pub, (W - pub.width - 40, 156))
        return im

    def cached(self, k, fn):
        if k not in self._cache:
            self._cache[k] = fn()
        return self._cache[k]

    def fundo_foto(self, t):
        dx = int(100 + 80 * math.sin(t * 0.4))
        dy = int(100 + 70 * math.cos(t * 0.3))
        return self.bg.crop((dx, dy, dx + W, dy + H))

    def fundo(self, t, idx):
        if self.clips:
            fr = self.clips[idx % len(self.clips)].quadro()
        else:
            fr = self.fundo_foto(t)
        fr.alpha_composite(self.vinheta)
        return fr

    # ---------- produto
    def produto(self, alvo):
        """Produto recortado (com sombra) ou, se o recorte nao for confiavel, a foto em cartao."""
        def faz():
            if self.recorte is not None:
                im = self.recorte
                esc = min(alvo[0] / im.width, alvo[1] / im.height)
                im = im.resize((int(im.width * esc), int(im.height * esc)), Image.LANCZOS)
                pad = 60
                out = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
                sombra = Image.new("RGBA", out.size, (0, 0, 0, 0))
                a = im.getchannel("A").point(lambda v: int(v * 0.55))
                sombra.paste((0, 0, 0, 255), (pad + 14, pad + 26), a)
                out.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(22)))
                out.alpha_composite(im, (pad, pad))
                return out
            f = self.foto
            esc = min(alvo[0] / f.width, alvo[1] / f.height)
            cw, ch = int(f.width * esc), int(f.height * esc)
            card = Image.new("RGBA", (cw + 16, ch + 16), (0, 0, 0, 0))
            ImageDraw.Draw(card).rounded_rectangle([0, 0, cw + 15, ch + 15], 48, fill=BRANCO)
            m = Image.new("L", (cw, ch), 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, cw - 1, ch - 1], 40, fill=255)
            reg = f.resize((cw, ch), Image.LANCZOS).convert("RGBA")
            reg.putalpha(m)
            card.alpha_composite(reg, (8, 8))
            return card
        return self.cached(("prod", alvo), faz)

    def close(self, view, t_rel, dur):
        """Close em tela cheia de um trecho da foto oficial, com Ken Burns."""
        def base():
            box = self.views.get(view)
            f = self.foto
            x0, y0, x1, y1 = (box or [0, 0, 1, 1])
            x0, x1 = x0 * f.width, x1 * f.width
            y0, y1 = y0 * f.height, y1 * f.height
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            # expande para 9:16 dentro da foto
            hh = max(y1 - y0, (x1 - x0) * 16 / 9)
            ww = hh * 9 / 16
            if hh > f.height:
                hh = f.height
                ww = hh * 9 / 16
            x0 = min(max(0, cx - ww / 2), f.width - ww)
            y0 = min(max(0, cy - hh / 2), f.height - hh)
            reg = f.crop((int(x0), int(y0), int(x0 + ww), int(y0 + hh)))
            return reg.resize((int(W * 1.15), int(H * 1.15)), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 50, 2))
        big = self.cached(("close", view), base)
        k = ease_in_out(clamp(t_rel / max(dur, 0.1)))
        z = 1.0 + 0.12 * k
        ww, hh = big.width / (1.15 * z) * 1.0, big.height / (1.15 * z)
        ox = (big.width - ww) * (0.35 + 0.3 * k)
        oy = (big.height - hh) * (0.5 - 0.2 * k)
        return big.crop((int(ox), int(oy), int(ox + ww), int(oy + hh))).resize((W, H), Image.BILINEAR).convert("RGBA")

    # ---------- cenas
    def cena_hook(self, t, tl, info):
        fr = self.fundo(t, 0)
        a = ease_back(clamp(tl / 0.35))
        prod = self.produto((780, 760))
        flut = 14 * math.sin(tl * 3.2)
        colar(fr, prod, W / 2, 1080 + flut, escala=0.6 + 0.4 * a, rot=-4 * (1 - a) + 1.5 * math.sin(tl * 2))
        linhas = info.get("tela") or ["OLHA ISSO!"]
        txt = self.cached(("hook", tuple(linhas)), lambda: texto_img(linhas, fonte("titulo", 112, 800), cores=[BRANCO, AMARELO, BRANCO], stroke=7))
        colar(fr, txt, W / 2, 470, escala=ease_back(clamp(tl / 0.25)))
        return fr

    def cena_problema(self, t, tl, dur, info):
        fr = self.fundo(t, 1)
        fr.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 70)))
        itens = info.get("itens", [])
        for i, it in enumerate(itens):
            ti = tl - 0.15 - i * 0.45
            if ti < 0:
                continue
            p = self.cached(("prob", it), lambda it=it: pilula(it, fonte("texto", 62, 900), (255, 255, 255, 240), ESCURO, pad=(34, 14)))
            colar(fr, p, W / 2, 760 + i * 150, escala=ease_back(clamp(ti / 0.25)), rot=-2 + 4 * (i % 2))
        return fr

    def cena_solucao(self, t, tl, dur, info):
        fr = self.fundo(t, 0)
        k = clamp(tl / max(dur, 0.1))
        # sem recorte a foto inteira vira cartao: menor e mais baixa para nao cobrir o titulo
        alvo, y = ((900, 900), 1000) if self.recorte is not None else ((740, 740), 1130)
        prod = self.produto(alvo)
        colar(fr, prod, W / 2 + 30 * math.sin(tl * 1.4), y + 10 * math.sin(tl * 2.6),
              escala=(0.85 + 0.15 * ease_back(clamp(tl / 0.35))) * (1 + 0.08 * k), rot=2 * math.sin(tl * 1.7))
        rot_ = info.get("rotulo")
        if rot_:
            p = self.cached(("rot", rot_), lambda: pilula(rot_, fonte("texto", 40, 900), AMARELO, ESCURO, pad=(24, 8)))
            colar(fr, p, W / 2, 330, escala=ease_back(clamp(tl / 0.2)))
        linhas = info.get("tela") or []
        if linhas:
            tt = self.cached(("sol", tuple(linhas)), lambda: texto_img(linhas, fonte("titulo", 96, 800), stroke=6))
            colar(fr, tt, W / 2, 440 + (len(linhas) - 1) * 40, escala=ease_back(clamp((tl - 0.08) / 0.25)))
        if info.get("sub"):
            s = self.cached(("sub", info["sub"]), lambda: texto_img([info["sub"]], fonte("texto", 44, 800), cor=(255, 240, 225)))
            colar(fr, s, W / 2, 540 + (len(linhas) - 1) * 80, alpha=clamp((tl - 0.2) / 0.3))
        return fr

    def cena_detalhe(self, t, tl, dur, info, segs):
        n = len(segs)
        d = dur / n
        i = min(int(tl / d), n - 1)
        view, rot_ = segs[i]
        ti = tl - i * d
        if view == "principal" and self.recorte is not None:
            fr = self.fundo(t, i)
            colar(fr, self.produto((860, 860)), W / 2, 1000, escala=1 + 0.06 * ti, rot=1.5 * math.sin(ti * 2))
        else:
            fr = self.close(view, ti, d)
            fr.alpha_composite(self.vinheta)
        if rot_:
            chip = self.cached(("chip", rot_), lambda: pilula(rot_,fonte("texto", 52, 900), VERDE, BRANCO, pad=(30, 12)))
            colar(fr, chip, W / 2, 1300, escala=ease_back(clamp(ti / 0.22)))
        return fr

    def cena_preco(self, t, tl, dur, info):
        fr = self.fundo(t, 0)
        colar(fr, self.produto((620, 620)), W / 2, 820 + 8 * math.sin(tl * 3), escala=0.95 + 0.05 * ease_back(clamp(tl / 0.3)))
        colar(fr, self.selo, W / 2 + 280, 560, escala=ease_back(clamp((tl - 0.3) / 0.3)), rot=-12)
        de = self.cached("de", lambda: texto_img([f"De {brl(self.p['preco_original'])}"], fonte("texto", 50, 800), cor=(255, 230, 215)))
        y = 1190
        colar(fr, de, W / 2, y, alpha=clamp(tl / 0.25))
        dd = ImageDraw.Draw(fr)
        if tl > 0.15:
            dd.line([(W / 2 - de.width / 2 + 14, y - 4), (W / 2 + de.width / 2 - 14, y - 4)], fill=(255, 230, 215), width=6)
        pr = self.cached("pr", lambda: pilula(f"HOJE: {brl(self.p['preco_oferta'])}", fonte("titulo", 104, 800), AMARELO, ESCURO, pad=(40, 10)))
        colar(fr, pr, W / 2, 1320, escala=ease_back(clamp((tl - 0.45) / 0.3)), rot=-2)
        return fr

    def cena_cta(self, t, tl, info):
        fr = self.fundo(t, 1)
        fr.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 90)))
        colar(fr, self.produto((520, 520)), W / 2, 560 + 8 * math.sin(tl * 3), escala=0.9 + 0.1 * ease_back(clamp(tl / 0.3)))
        linhas = info.get("tela") or ["CONFIRA"]
        t1 = self.cached(("cta1", tuple(linhas)), lambda: texto_img(linhas, fonte("titulo", 112, 800), cores=[BRANCO, AMARELO], stroke=6))
        colar(fr, t1, W / 2, 1010, escala=ease_back(clamp((tl - 0.1) / 0.3)))
        botao = info.get("botao") or "LINK DA BIO"
        b = self.cached(("cta2", botao), lambda: pilula(botao, fonte("titulo", 84, 800), AMARELO, ESCURO, pad=(44, 14)))
        colar(fr, b, W / 2, 1180, escala=ease_back(clamp((tl - 0.2) / 0.3)) * (1 + 0.04 * math.sin(tl * 7)))
        extra = self.cached("cta3", lambda: pilula("SALVA E MANDA PRA QUEM PRECISA", fonte("texto", 40, 900), (255, 255, 255, 235), LARANJA, pad=(26, 10)))
        colar(fr, extra, W / 2, 1330, alpha=clamp((tl - 0.45) / 0.3))
        site = self.cached("cta4", lambda: texto_img(["achadosdogenio.com.br"], fonte("texto", 46, 800)))
        colar(fr, site, W / 2, 1440, alpha=clamp((tl - 0.6) / 0.3))
        return fr

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
            img = self.cena_detalhe(t, tl, dur, atual, [tuple(x) for x in atual.get("itens", [["principal", ""]])])
        elif c == "preco":
            img = self.cena_preco(t, tl, dur, atual)
        else:
            img = self.cena_cta(t, tl, atual)
        img.alpha_composite(self._header)
        if c != "cta":
            v2.Reel.legenda(self, img, t, blocos)
        for (tc, tipo) in cortes:
            dt = t - tc
            if tipo == "whip" and -0.1 < dt < 0.12:
                img = v2.borrar_horizontal(img, 1 - abs(dt) / 0.12)
            if tipo in ("flash", "preco") and 0 <= dt < 0.12:
                img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(170 * (1 - dt / 0.12)))))
            if 0 <= dt < 0.22:
                z = 1 + (0.08 if tipo == "preco" else 0.05) * (1 - dt / 0.22)
                cw, ch = int(W / z), int(H / z)
                x0, y0 = (W - cw) // 2, (H - ch) // 2
                img = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)
        return img.convert("RGB")

    def capa(self, linhas):
        """Capa limpa: produto em destaque + ate 3 palavras."""
        fr = self.fundo_foto(1.0)
        fr.alpha_composite(self.vinheta)
        colar(fr, self.produto((860, 860)), W / 2, 1180)
        txt = texto_img(linhas[:2], fonte("titulo", 132, 800), cores=[BRANCO, AMARELO], stroke=8)
        colar(fr, txt, W / 2, 460 + (min(len(linhas), 2) - 1) * 55, rot=-2)
        fr.alpha_composite(self._header)
        return fr.convert("RGB")

    def fechar(self):
        for c in self.clips:
            c.fechar()


def renderizar(produto, roteiro, saida_mp4, saida_capa, falar_preco, voz=None, taxa=None, cenas=None, capa_linhas=None):
    if voz:
        v2.VOZ = voz
    if taxa:
        v2.TAXA = taxa
    reel = ReelDescoberta(produto, roteiro, cenas)
    frases = v2.montar_frases(produto, roteiro, falar_preco)
    partes, linha, total = v2.narrar(frases, reel.pasta)
    if not 8 <= total <= 30:
        raise RuntimeError(f"Duracao fora do alvo: {total:.1f}s")
    cortes = v2.cortes_da_linha(linha)
    musica = v2.musica_para(produto["id"])
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
    return {"duracao": round(total, 2), "musica": os.path.basename(musica), "formato_video": "descoberta_v3",
            "recorte": reel.info_recorte, "cenas_banco": [{k: c[k] for k in ("fonte", "id", "autor", "termo", "pagina")} for c in (cenas or [])],
            "linha_do_tempo": [{"cena": f["cena"], "ini": round(f["ini"], 2), "fim": round(f["fim_cena"], 2)} for f in linha]}
