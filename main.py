"""
Bot de monitoramento "Under Gols".

Fluxo a cada ciclo:
  1. Busca jogos de futebol ao vivo na Betsapi (pacote Bet365) -- essa
     chamada já traz placar e um minuto ESTIMADO (de graça, sem custo
     extra de API), calculado a partir do horário de início do jogo.
  2. Ignora categorias de base, Esoccer e países bloqueados.
  3. Pra jogos 0x0 dentro da janela, confirma o minuto EXATO e as odds
     com uma chamada extra (/bet365/event). Depois da 1ª chamada o bot
     agenda a próxima checagem só pra perto do próximo minuto-alvo.
  4. TESTE EM PARALELO: o mesmo jogo 0x0 gera uma entrada simulada em
     cada minuto de config.MINUTOS_ENTRADA (18, 20, 22, ...), com a odd
     daquele momento. Só o minuto config.MINUTO_GATILHO manda alerta no
     Telegram e mexe na banca; os outros só vão pra planilha.
  5. Resolve apostas simuladas cujo jogo já não está mais ao vivo
  6. Uma vez por dia, manda o resumo consolidado no chat de simulação

Rodar com: python main.py
"""

import html
import re
import time
from datetime import datetime

import config
import estado
import betsapi_client
import telegram_client
import sheets_client


def liga_excluida(nome_liga: str) -> bool:
    nome = (nome_liga or "").lower()
    termos = list(config.LIGAS_EXCLUIDAS_TERMOS) + list(config.PAISES_EXCLUIDOS_TERMOS)
    return any(termo in nome for termo in termos)


def faixa_de_odd(odd: float) -> str:
    """Rótulo da faixa de odd (vai pra planilha, pra comparar ROI por faixa)."""
    if odd < 1.80:
        return "1.72-1.80"
    if odd < 1.85:
        return "1.80-1.85"
    if odd < 1.95:
        return "1.85-1.95"
    return "1.95-2.00"


def genero_do_jogo(liga: str, casa: str, fora: str) -> str:
    """Estimativa: 'Feminino' se a liga/times indicam jogo de mulheres."""
    l = (liga or "").lower()
    if re.search(r"\b(women|womens|woman|feminin\w*|femenin\w*|femminile|feminine|fem)\b", l):
        return "Feminino"
    for t in (casa or "", fora or ""):
        if re.search(r"\(w\)|\bwomen\b|\bw$", t.strip().lower()):
            return "Feminino"
    return "Masculino"


def dentro_da_janela(minuto_estimado) -> bool:
    """
    Janela em minutos ESTIMADOS (que são inflados quando o jogo atrasa),
    só vale pra jogos que o bot ainda não viu: depois da 1ª chamada
    /event passamos a usar o minuto exato.
    """
    if minuto_estimado is None:
        return False
    alvos = config.MINUTOS_ENTRADA
    inicio = min(alvos) - config.JANELA_CONFIRMACAO_MINUTOS
    fim = max(alvos) + config.TOLERANCIA_MINUTOS + config.JANELA_CONFIRMACAO_MINUTOS
    return inicio <= minuto_estimado <= fim


def escolher_linha(odds: dict):
    """
    Entre as linhas entre LINHA_MINIMA e LINHA_MAXIMA com odd dentro da
    faixa, escolhe a de odd mais próxima de 1.90. Retorna (linha, odd)
    ou (None, None).
    """
    candidatas = {
        linha: odd for linha, odd in odds.items()
        if odd is not None
        and config.ODD_MINIMA <= odd <= config.ODD_MAXIMA
        and config.LINHA_MINIMA - 1e-6 <= linha <= config.LINHA_MAXIMA + 1e-6
    }
    if not candidatas:
        return None, None
    melhor = min(candidatas, key=lambda l: abs(candidatas[l] - 1.90))
    return melhor, candidatas[melhor]


def registrar_entrada(jogo: dict, est: dict, alvo: int, minuto_real, linha, odd: float) -> None:
    principal = (alvo == config.MINUTO_GATILHO)
    descricao = f"{jogo['time_casa']} x {jogo['time_fora']} ({jogo['liga']})"

    texto_alerta = None
    msg_canal_id = None
    if principal:
        texto_alerta = (
            f"{html.escape(jogo['time_casa'], quote=False)} x {html.escape(jogo['time_fora'], quote=False)}\n"
            f"{html.escape(jogo['liga'], quote=False)}\n"
            f"Under {linha} @{odd:.2f}"
        )
        # privado: alerta em tempo real
        telegram_client.enviar_alerta(texto_alerta)
        # canal de avisos: mesma mensagem; depois é editada com ✅/❌
        msg_canal_id = telegram_client.enviar_relatorio_simulacao(texto_alerta)

    estado.registrar_aposta_simulada(
        est, jogo["fi"], linha, odd, descricao, liga=jogo["liga"],
        minuto_alvo=alvo, minuto_real=minuto_real, notificar=principal,
    )
    aposta = est["apostas_abertas"][-1]
    if principal:
        aposta["msg_canal_id"] = msg_canal_id
        aposta["msg_canal_texto"] = texto_alerta

    sheets_client.registrar_entrada(
        id_aposta=aposta["id_aposta"],
        data_hora=aposta["data_entrada"],
        campeonato=jogo["liga"],
        partida=descricao,
        linha=linha,
        odd=odd,
        minuto=alvo,
        faixa_odd=faixa_de_odd(odd),
        genero=genero_do_jogo(jogo["liga"], jogo["time_casa"], jogo["time_fora"]),
    )


def processar_jogo(jogo: dict, est: dict, orcamento: dict = None) -> None:
    fi = jogo["fi"]
    if estado.jogo_ja_verificado(est, fi):
        return
    if not jogo["jogo_comecou"]:
        return

    # checagem BARATA (sem API): se o placar já não é 0x0, o jogo nunca
    # mais bate o padrão -- encerra o acompanhamento dele.
    if (jogo["gols_casa"], jogo["gols_fora"]) != config.PLACAR_GATILHO:
        estado.marcar_jogo_verificado(est, fi)
        return

    ja_visto = fi in est["entradas_por_jogo"]
    if not ja_visto and not dentro_da_janela(jogo["minuto_estimado"]):
        return

    feitos = est["entradas_por_jogo"].setdefault(fi, [])
    pendentes = [t for t in config.MINUTOS_ENTRADA if t not in feitos]
    if not pendentes:
        estado.marcar_jogo_verificado(est, fi)
        return

    agora = time.time()
    if est["proxima_checagem"].get(fi, 0) > agora:
        return  # ainda longe do próximo minuto-alvo

    # teto de chamadas /event por ciclo (cota compartilhada da API)
    if orcamento is not None:
        if orcamento["restante"] <= 0:
            return  # tenta no próximo ciclo
        orcamento["restante"] -= 1

    try:
        detalhe = betsapi_client.obter_detalhe_evento(fi)
    except Exception as e:
        print(f"[erro] Falha ao buscar detalhe do jogo {fi}: {e}")
        return

    minuto = detalhe["minuto_exato"]
    if minuto is None:
        print(f"[debug] Não consegui calcular minuto exato do jogo {fi} "
              f"({jogo['time_casa']} x {jogo['time_fora']}). "
              f"Resposta bruta (primeiros 3 itens): {detalhe.get('_bruto_debug', [])[:3]}")
        return

    tol = config.TOLERANCIA_MINUTOS

    # alvos que já passaram além da tolerância: desiste deles
    for t in pendentes:
        if minuto > t + tol:
            feitos.append(t)

    # alvos "devidos" agora (minuto-alvo atingido, ainda dentro da tolerância)
    devidos = [t for t in pendentes if t not in feitos and t <= minuto <= t + tol]
    if devidos:
        alvo = max(devidos)
        # alvos devidos mais antigos que este (mesma chamada) são descartados,
        # senão duas entradas idênticas entrariam com rótulos de minutos diferentes
        for t in devidos:
            if t != alvo:
                feitos.append(t)

        odds = detalhe["odds_under"]
        print(f"[debug] {jogo['time_casa']} x {jogo['time_fora']} (jogo {fi}) "
              f"minuto {minuto}, alvo {alvo}: odds {odds}")
        linha, odd = escolher_linha(odds)
        if linha is not None:
            feitos.append(alvo)
            registrar_entrada(jogo, est, alvo, minuto, linha, odd)
        else:
            print(f"[debug] Nenhuma linha na faixa de odd pro jogo {fi} no alvo {alvo} "
                  f"-- tenta de novo no próximo ciclo (tolerância {tol} min).")

    restantes = [t for t in config.MINUTOS_ENTRADA if t not in feitos]
    if not restantes:
        estado.marcar_jogo_verificado(est, fi)
        return

    # agenda a próxima checagem: só volta a chamar a API perto do próximo alvo
    proximo = min(restantes)
    if minuto < proximo - 1:
        est["proxima_checagem"][fi] = agora + (proximo - 1 - minuto) * 60


def resolver_apostas_pendentes(est: dict, lista_ao_vivo: list) -> None:
    """
    Verifica apostas simuladas em aberto: se o jogo já não está
    na lista de jogos ao vivo, consideramos que terminou e checamos
    o placar final pra apurar o resultado.
    Reaproveita a lista de jogos ao vivo já buscada no ciclo (economiza
    uma chamada de API por ciclo).
    """
    if not est["apostas_abertas"]:
        return

    jogos_ao_vivo = {j["fi"] for j in lista_ao_vivo}
    ainda_abertas = []
    placares_cache = {}  # várias entradas do mesmo jogo -> 1 chamada /result só

    for aposta in est["apostas_abertas"]:
        fi = aposta["fi"]
        if fi in jogos_ao_vivo:
            ainda_abertas.append(aposta)
            continue

        # jogo não está mais na lista de ao vivo -- assumimos encerrado
        # e buscamos o placar final oficial via /bet365/result.
        if fi not in placares_cache:
            placares_cache[fi] = _placar_final_estimado(fi)
        gols_totais_final = placares_cache[fi]
        if gols_totais_final is None:
            ainda_abertas.append(aposta)
            continue

        resolvida = estado.resolver_aposta(est, aposta, gols_totais_final)
        emojis_resultado = {
            "green": "✅", "red": "❌", "void": "⚪",
            "meio green": "🟢", "meio red": "🔴",
        }
        emoji = emojis_resultado.get(resolvida["resultado"], "❔")
        print(f"{emoji} {aposta['linha']} (min {aposta.get('minuto_alvo', '?')}) | "
              f"{aposta['jogo']} | lucro: R${resolvida['lucro']}")

        if aposta.get("notificar", True):
            marca = config.MARCAS_RESULTADO.get(resolvida["resultado"], "❔")
            base = aposta.get("msg_canal_texto") or (
                f"{html.escape(aposta['jogo'], quote=False)}\n"
                f"Under {aposta['linha']} @{aposta['odd']:.2f}"
            )
            novo_texto = f"{base}\n{marca}"
            editou = False
            if aposta.get("msg_canal_id"):
                editou = telegram_client.editar_mensagem(
                    config.CHAT_ID_SIMULACAO, aposta["msg_canal_id"], novo_texto)
            if not editou:
                # sem mensagem original (ex: aposta antiga) ou edição falhou
                telegram_client.enviar_relatorio_simulacao(novo_texto)

        sheets_client.atualizar_resultado(
            id_aposta=aposta.get("id_aposta", ""),
            resultado=resolvida["resultado"],
            lucro_reais=resolvida["lucro"],
        )

    est["apostas_abertas"] = ainda_abertas


def _placar_final_estimado(fi: str):
    resultado = betsapi_client.obter_placar_final(fi)
    if resultado is None:
        return None
    gols_casa, gols_fora = resultado
    return gols_casa + gols_fora


def enviar_relatorio_diario_se_necessario(est: dict) -> None:
    hoje = datetime.now().strftime("%Y-%m-%d")
    if est.get("ultimo_relatorio_enviado") == hoje:
        return

    agora = datetime.now().strftime("%H:%M")
    if agora < config.HORARIO_RELATORIO_DIARIO:
        return

    banca_atual = est["banca"]
    lucro_total_acumulado = banca_atual - config.BANCA_INICIAL

    # só as entradas do minuto principal (as outras são só teste, na planilha)
    apostas_hoje = [
        a for a in est["apostas_resolvidas"]
        if a["data_resolucao"].startswith(hoje) and a.get("notificar", True)
    ]
    greens = sum(1 for a in apostas_hoje if a["resultado"] == "green")
    reds = sum(1 for a in apostas_hoje if a["resultado"] == "red")
    lucro_hoje = sum(a["lucro"] for a in apostas_hoje)

    texto_relatorio = (
        f"📊 Relatório diário — {hoje}\n\n"
        f"Entradas hoje: {len(apostas_hoje)} ({greens}✅ / {reds}❌)\n"
        f"Lucro hoje: R${lucro_hoje:+.2f}\n\n"
        f"Banca atual: R${banca_atual:,.2f}\n"
        f"Lucro acumulado: R${lucro_total_acumulado:+,.2f}"
    )

    telegram_client.enviar_relatorio_simulacao(texto_relatorio)
    est["ultimo_relatorio_enviado"] = hoje


def ciclo() -> None:
    est = estado.carregar()

    lista_ao_vivo = betsapi_client.listar_jogos_ao_vivo()
    jogos = [j for j in lista_ao_vivo if not liga_excluida(j["liga"])]

    na_janela = [j for j in jogos if dentro_da_janela(j["minuto_estimado"])]
    print(f"[ciclo {datetime.now().strftime('%H:%M:%S')}] {len(jogos)} jogos ao vivo (após filtro) | "
          f"{len(na_janela)} na janela | {len(est['entradas_por_jogo'])} em acompanhamento")

    # jogos mais perto do gatilho primeiro, pra o teto de /event por
    # ciclo nunca atrasar quem está prestes a bater o minuto
    orcamento = {"restante": config.MAX_EVENT_POR_CICLO}
    jogos_ordenados = sorted(
        jogos, key=lambda j: j["minuto_estimado"] if j["minuto_estimado"] is not None else -1,
        reverse=True,
    )
    for jogo in jogos_ordenados:
        processar_jogo(jogo, est, orcamento=orcamento)

    resolver_apostas_pendentes(est, lista_ao_vivo)
    enviar_relatorio_diario_se_necessario(est)

    estado.salvar(est)


def main() -> None:
    print("Bot Under Gols iniciado.")
    while True:
        try:
            ciclo()
        except Exception as e:
            print(f"[erro] {e}")
        time.sleep(config.INTERVALO_POLLING_SEGUNDOS)


if __name__ == "__main__":
    main()
