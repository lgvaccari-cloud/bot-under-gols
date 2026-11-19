"""
Diagnóstico ÚNICO (roda 1x na inicialização) pro futuro bot de ML
(favorito top 4 x time da parte de baixo, pré-jogo). Só imprime no log
do Render o formato real de 4 endpoints -- poucas chamadas, não aposta nada.
"""
import json
from datetime import datetime, timedelta, timezone

import requests

import config

BASE = "https://api.b365api.com"


def _chamar(rotulo: str, path: str, params: dict):
    try:
        r = requests.get(f"{BASE}{path}", params={**params, "token": config.BETSAPI_TOKEN}, timeout=20)
        txt = r.text
        print(f"[ML-DIAG] {rotulo} -> HTTP {r.status_code}, {len(txt)} bytes")
        print(f"[ML-DIAG] {rotulo} amostra: {txt[:1500]}")
        try:
            return r.json()
        except Exception:
            return None
    except Exception as e:
        print(f"[ML-DIAG] {rotulo} erro: {e}")
        return None


def rodar() -> None:
    amanha = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y%m%d")
    up = _chamar("upcoming", "/v1/bet365/upcoming", {"sport_id": 1, "day": amanha})
    itens = (up or {}).get("results") or []
    print(f"[ML-DIAG] upcoming: {len(itens)} jogos, paginação: {(up or {}).get('pager')}")
    if not itens:
        return
    jogo = next((i for i in itens if "women" not in str((i.get("league") or {}).get("name", "")).lower()), itens[0])
    fi = jogo.get("id")
    liga = (jogo.get("league") or {}).get("id")
    print(f"[ML-DIAG] jogo de teste: {jogo.get('home')} x {jogo.get('away')} | liga {jogo.get('league')} | fi {fi}")
    _chamar("prematch v3", "/v3/bet365/prematch", {"FI": fi})
    _chamar("prematch v4", "/v4/bet365/prematch", {"FI": fi})
    _chamar("league_table", "/v1/league/table", {"league_id": liga})
    _chamar("event_view", "/v1/event/view", {"event_id": fi})
