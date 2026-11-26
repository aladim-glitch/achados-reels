"""Coleta o desempenho REAL dos Reels em 24, 48 e 72 h e gera o relatorio de aprendizado.

Roda no GitHub Actions (metricas.yml). Precisa do secret IG_TOKEN (mesmo token do Make).
- Curtidas e comentarios: sempre disponiveis.
- Visualizacoes, alcance, salvamentos, compartilhamentos e tempo medio assistido: exigem a permissao
  instagram_manage_insights no token. Sem ela, o erro fica registrado e o aprendizado usa engajamento.
Saidas: estado/metricas.json (dados) e estado/relatorio.md (resumo por variacao).
"""
import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import aprendizado
import selecao

IG = "17841475216696724"
API = "https://graph.facebook.com/v23.0"
BASE = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(BASE, "estado", "metricas.json")
RELATORIO = os.path.join(BASE, "estado", "relatorio.md")
CHECKPOINTS = (24, 48, 72)
INSIGHTS = ["views", "reach", "saved", "shares", "total_interactions", "ig_reels_avg_watch_time"]
BRT = dt.timezone(dt.timedelta(hours=-3))


def chamar(caminho, **params):
    url = f"{API}/{caminho}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {os.environ['IG_TOKEN']}"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", str(e))
        except Exception:
            msg = str(e)
        return None, msg


def insights(media_id):
    dados, erro = chamar(f"{media_id}/insights", metric=",".join(INSIGHTS))
    if erro:
        return {}, erro
    res = {}
    for item in dados.get("data", []):
        vals = item.get("values") or []
        v = vals[0].get("value") if vals else item.get("total_value", {}).get("value")
        nome = {"saved": "saved", "ig_reels_avg_watch_time": "avg_watch_ms"}.get(item["name"], item["name"])
        res[nome] = v
    return res, None


def slot_da_hora(h):
    return 0 if h < 10 else (1 if h < 15 else 2)


def main():
    agora = dt.datetime.now(dt.timezone.utc)
    met = aprendizado.carregar_metricas()
    publicados = selecao.carregar_publicados()
    lista, erro = chamar(f"{IG}/media", fields="id,timestamp,permalink,media_product_type,like_count,comments_count", limit=40)
    if erro:
        raise SystemExit(f"Falha ao listar midias: {erro}")
    for m in lista.get("data", []):
        if m.get("media_product_type") != "REELS":
            continue
        ts = dt.datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        idade_h = (agora - ts).total_seconds() / 3600
        if idade_h > 96:
            continue
        local = ts.astimezone(BRT)
        reg = met.setdefault(m["id"], {"permalink": m.get("permalink"), "publicado_em": m["timestamp"]})
        if "produto" not in reg:
            slot = slot_da_hora(local.hour)
            pub = next((p for p in publicados if p["data"] == str(local.date()) and p["slot"] == slot), None)
            reg.update({"data": str(local.date()), "slot": slot, "hora_local": local.strftime("%H:%M"),
                        "produto": pub["id"] if pub else None, "categoria": pub["categoria"] if pub else None,
                        "variante": (pub or {}).get("variante") or {}})
            if reg["variante"]:
                reg["variante"] = {**reg["variante"], "horario": ["08h", "12h", "19h"][slot]}
        for cp in CHECKPOINTS:
            chave = f"{cp}h"
            if idade_h >= cp and chave not in reg:
                snap = {"coletado_em": agora.isoformat(timespec="minutes"), "idade_h": round(idade_h, 1),
                        "likes": m.get("like_count"), "comments": m.get("comments_count")}
                ins, err = insights(m["id"])
                snap.update(ins)
                if err:
                    snap["erro_insights"] = err
                reg[chave] = snap
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(met, f, ensure_ascii=False, indent=1)
    gerar_relatorio(met)
    print(f"{len(met)} Reels acompanhados")


def gerar_relatorio(met):
    medias, alvo = aprendizado.medias_por_dimensao(met)
    nome = "visualizações em 24 h" if alvo == "views" else "engajamento (curtidas + 3×comentários + 5×salvos + 5×compart.)"
    lin = ["# Relatório de desempenho dos Reels", "", f"Métrica usada para comparar: **{nome}**.", "",
           "| Reel | Data | Horário | Variação | 24 h | 48 h | 72 h |", "|---|---|---|---|---|---|---|"]

    def fmt(s):
        if not s:
            return "–"
        if s.get("views") is not None:
            return f"{s['views']} views · {s.get('likes', 0)}♥ · {s.get('saved', 0)} salvos · {s.get('shares', 0)} compart."
        return f"{s.get('likes', 0)}♥ · {s.get('comments', 0)} coment."

    for mid, r in sorted(met.items(), key=lambda kv: kv[1].get("publicado_em", ""), reverse=True):
        v = r.get("variante") or {}
        var = ", ".join(f"{k}={v[k]}" for k in ("gancho", "voz", "formato") if k in v) or "–"
        lin.append(f"| [{r.get('produto') or mid}]({r.get('permalink')}) | {r.get('data', '')} | {r.get('hora_local', '')} | {var} | "
                   f"{fmt(r.get('24h'))} | {fmt(r.get('48h'))} | {fmt(r.get('72h'))} |")
    lin += ["", "## Média por variação", ""]
    for dim, vals in medias.items():
        lin.append(f"**{dim}**: " + " · ".join(f"{k}: {sum(v) / len(v):.0f} (n={len(v)})" for k, v in
                                            sorted(vals.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))))
        lin.append("")
    with open(RELATORIO, "w", encoding="utf-8") as f:
        f.write("\n".join(lin) + "\n")


if __name__ == "__main__":
    main()
