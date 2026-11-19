"""
Diagnóstico ÚNICO (roda 1x na inicialização) pro futuro bot de ML
(favorito top 4 x time da parte de baixo, pré-jogo). Só imprime no log
do Render o formato real de alguns endpoints -- poucas chamadas, não aposta nada.
"""
import json
from datetime import datetime, timedelta, timezone

import requests

import config

BASE = "https://api.b365api.com"


def _chamar(rotulo: str, path: str, params: dict, tamanho: int = 1500):
    try:
        r = requests.get(f"{BASE}{path}", params={**params, "token": config.BETSAPI_TOKEN}, timeout=20)
        txt = r.text
        print(f"[ML-DIAG] {rotulo} -> HTTP {r.status_code}, {len(txt)} bytes")
        print(f"[ML-DIAG] {rotulo} amostra: {txt[:tamanho]}")
        try:
            return r.json()
        except Exception:
            return None
    except Exception as e:
        print(f"[ML-DIAG] {rotulo} erro: {e}")
        return None


def _canais_telegram() -> None:
    """Imprime id e nome dos chats/canais que falaram com o bot (sem o token)."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates",
                         params={"limit": 100}, timeout=20)
        vistos = {}
        for u in (r.json().get("result") or []):
            for chave in ("channel_post", "message", "my_chat_member"):
                m = u.get(chave)
                if m and m.get("chat"):
                    c = m["chat"]
                    vistos[c.get("id")] = (c.get("type"), c.get("title") or c.get("username") or c.get("first_name"))
        for cid, (tipo, nome) in vistos.items():
            print(f"[ML-DIAG] telegram chat id={cid} tipo={tipo} nome={nome}")
        if not vistos:
            print("[ML-DIAG] telegram: nenhuma atualização encontrada")
    except Exception as e:
        print(f"[ML-DIAG] telegram erro: {e}")


def rodar() -> None:
    _canais_telegram()
    amanha = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y%m%d")
    up = _chamar("upcoming", "/v1/bet365/upcoming", {"sport_id": 1, "day": amanha}, 300)
    itens = (up or {}).get("results") or []
    if not itens:
        return
    jogo = next((i for i in itens if (i.get("league") or {}).get("name") == "Brazil Serie A"), itens[0])
    fi, nosso = jogo.get("id"), jogo.get("our_event_id")
    print(f"[ML-DIAG] jogo de teste: {jogo.get('home')} x {jogo.get('away')} | liga {jogo.get('league')} | fi {fi} | our_event_id {nosso}")

    # odds 1x2 (ML) no pré-jogo
    pm = _chamar("prematch v3", "/v3/bet365/prematch", {"FI": fi}, 0)
    try:
        res = pm["results"][0]
        print(f"[ML-DIAG] prematch chaves: {list(res.keys())}")
        main = res.get("main") or {}
        print(f"[ML-DIAG] prematch main: {json.dumps(main)[:1800]}")
    except Exception as e:
        print(f"[ML-DIAG] prematch parse erro: {e}")

    # evento no ID nativo da BetsAPI -> traz o id de liga que a tabela aceita
    ev = _chamar("event_view nativo", "/v1/event/view", {"event_id": nosso}, 1200)
    liga_nativa = None
    try:
        liga_nativa = ev["results"][0]["league"]["id"]
    except Exception:
        pass
    print(f"[ML-DIAG] liga nativa: {liga_nativa}")
    if liga_nativa:
        _chamar("league_table", "/v1/league/table", {"league_id": liga_nativa}, 2500)
        # jogos encerrados da liga (base do backtest)
        _chamar("events ended", "/v1/events/ended", {"sport_id": 1, "league_id": liga_nativa}, 1200)
    # odds de abertura/fechamento
    _chamar("odds summary", "/v2/event/odds/summary", {"event_id": nosso}, 1200)
