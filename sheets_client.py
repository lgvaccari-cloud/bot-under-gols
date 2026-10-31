"""
Registro das apostas simuladas numa planilha do Google Sheets.

Escreve na primeira aba (o "Log" bruto) em DOIS momentos:
1. Na hora que a aposta é aberta -- linha nova com status "Aguardando"
2. Quando a aposta resolve -- atualiza ESSA MESMA linha com o
   resultado final (Green/Red/Void/Meio Green/Meio Red) e o retorno

A segunda aba (métricas por país/campeonato/linha) é feita com
fórmula QUERY direto na planilha, não por código -- ver README.

Colunas do Log: Data | Jogo | País | Campeonato | Linha | Tip |
Stake | Odd | Resultado | Retorno Líquido | ID | Minuto | Faixa odd |
Gênero (tudo em unidades,
mesma convenção da outra planilha -- 1 stake = 1 unidade = R$1.000).
A coluna K (ID) é só técnica, pra achar a linha certa na hora de
atualizar -- pode ficar escondida/estreita na planilha.

Precisa de uma conta de serviço do Google (arquivo JSON de credencial)
com acesso de Editor na planilha -- ver README para o passo a passo
de criação.
"""

import json

import gspread
from google.oauth2.service_account import Credentials

import config

_ESCOPOS = ["https://www.googleapis.com/auth/spreadsheets"]

_cliente = None
_planilha = None

COLUNA_ID = 11  # K -- 1-indexado (A=1, B=2, ..., K=11)
COLUNA_RESULTADO = 9   # I
COLUNA_RETORNO = 10    # J
COLUNA_PLACAR = 15     # O -- placar final ("2 x 1")
_cabecalho_ok = False


def _conectar():
    """Conecta preguiçosamente (só na primeira vez que for usado)."""
    global _cliente, _planilha
    if _planilha is not None:
        return _planilha

    if not config.GOOGLE_SERVICE_ACCOUNT_JSON or not config.GOOGLE_SHEET_ID:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON ou GOOGLE_SHEET_ID não configurados -- "
            "registro na planilha desativado."
        )

    info_credencial = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
    credenciais = Credentials.from_service_account_info(info_credencial, scopes=_ESCOPOS)
    _cliente = gspread.authorize(credenciais)
    _planilha = _cliente.open_by_key(config.GOOGLE_SHEET_ID).sheet1
    return _planilha


def _estimar_pais(campeonato: str) -> str:
    """
    Estimativa simples: usa a primeira palavra do nome da liga como
    país (ex: "Poland III Liga" -> "Poland"). Não é perfeito -- ligas
    continentais/regionais (ex: "Europe Friendlies") vão aparecer com
    a região no lugar do país.
    """
    if not campeonato:
        return ""
    return campeonato.split()[0]


def registrar_entrada(id_aposta: str, data_hora: str, campeonato: str,
                       partida: str, linha, odd: float, minuto=None,
                       faixa_odd: str = "", genero: str = "") -> None:
    """
    Adiciona uma linha no Log assim que a aposta é aberta, com status
    "Aguardando" -- id_aposta precisa ser único (ex: "{fi}_{linha}"),
    usado depois pra achar e atualizar essa mesma linha.
    """
    try:
        aba = _conectar()
        pais = _estimar_pais(campeonato)
        tip = f"Under {linha}"

        aba.append_row([
            data_hora, partida, pais, campeonato, linha, tip, 1,
            odd, "Aguardando", "", id_aposta,
            minuto if minuto is not None else "", faixa_odd, genero,
        ])
    except Exception as e:
        # Nunca deixa um erro na planilha derrubar o bot -- só loga.
        print(f"[erro] Falha ao registrar entrada na planilha: {e}")


def garantir_cabecalho_placar() -> None:
    """Escreve o título da coluna O (Placar final) uma vez por execução."""
    global _cabecalho_ok
    if _cabecalho_ok:
        return
    try:
        aba = _conectar()
        aba.batch_update([{"range": "O1", "values": [["Placar final"]]}],
                         value_input_option="RAW")
        _cabecalho_ok = True
    except Exception as e:
        print(f"[erro] Falha ao escrever cabeçalho do placar: {e}")


def atualizar_resultado(id_aposta: str, resultado: str, lucro_reais: float,
                        placar: str = "") -> None:
    """
    Acha a linha com esse id_aposta (coluna K) e atualiza Resultado,
    Retorno Líquido e Placar final. Se não achar a linha, não faz nada.
    """
    try:
        aba = _conectar()
        celula = aba.find(id_aposta, in_column=COLUNA_ID)
        if celula is None:
            print(f"[aviso] Não achei a linha da aposta {id_aposta} na planilha "
                  f"pra atualizar o resultado -- talvez tenha sido registrada antes "
                  f"dessa função existir.")
            return

        retorno_liquido_unidades = round(lucro_reais / config.STAKE_UNIDADE, 4)
        dados = [{
            "range": f"I{celula.row}:J{celula.row}",
            "values": [[resultado.title(), retorno_liquido_unidades]],
        }]
        if placar:
            dados.append({"range": f"O{celula.row}", "values": [[placar]]})
        # uma única chamada -- poupa a cota de escritas do Sheets
        aba.batch_update(dados, value_input_option="RAW")
    except Exception as e:
        print(f"[erro] Falha ao atualizar resultado na planilha: {e}")


def ler_linhas() -> list:
    """Todas as linhas do Log (lista de listas de texto), ou [] se falhar."""
    try:
        return _conectar().get_all_values()
    except Exception as e:
        print(f"[erro] Falha ao ler a planilha: {e}")
        return []


def escrever_correcoes(correcoes: list) -> bool:
    """
    correcoes: lista de {"row": n, "resultado": "Green", "retorno": 0.85, "placar": "2 x 1"}
    Atualiza I:J e O dessas linhas numa chamada só.
    """
    if not correcoes:
        return True
    try:
        aba = _conectar()
        dados = []
        for c in correcoes:
            dados.append({"range": f"I{c['row']}:J{c['row']}",
                          "values": [[c["resultado"], c["retorno"]]]})
            dados.append({"range": f"O{c['row']}", "values": [[c["placar"]]]})
        aba.batch_update(dados, value_input_option="RAW")
        return True
    except Exception as e:
        print(f"[erro] Falha ao gravar correções na planilha: {e}")
        return False


def escrever_placares(itens: list) -> bool:
    """Só a coluna O (placar final), sem mexer em resultado/retorno."""
    try:
        aba = _conectar()
        aba.batch_update([{"range": f"O{c['row']}", "values": [[c["placar"]]]} for c in itens],
                         value_input_option="RAW")
        return True
    except Exception as e:
        print(f"[erro] Falha ao gravar placares: {e}")
        return False
