"""
Configuração central do bot de monitoramento Under Gols.

As credenciais reais (tokens) NUNCA devem ficar escritas neste arquivo.
Elas são lidas de variáveis de ambiente (definidas no Render, ou num
arquivo .env local que não vai pro Git).
"""

import os

# ---------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

# Chat onde os alertas em tempo real são enviados (seu chat privado)
CHAT_ID_ALERTAS = os.environ.get("CHAT_ID_ALERTAS", "5511216910")

# Chat onde o relatório diário da simulação é enviado (grupo "Alerta Under")
CHAT_ID_SIMULACAO = os.environ.get("CHAT_ID_SIMULACAO", "-1004404899807")

# ---------------------------------------------------------------------
# Betsapi
# ---------------------------------------------------------------------
BETSAPI_TOKEN = os.environ.get("BETSAPI_TOKEN", "")
BETSAPI_BASE_URL = "https://api.b365api.com/v1"

# ---------------------------------------------------------------------
# Regra do padrão (gatilho do alerta)
# ---------------------------------------------------------------------
MINUTO_GATILHO = 22          # minuto do ALERTA principal (Telegram + banca simulada)
PLACAR_GATILHO = (0, 0)      # (gols_casa, gols_fora) que dispara o alerta

# TESTE EM PARALELO: o mesmo jogo 0x0 gera uma entrada simulada em CADA
# um desses minutos (com a odd daquela hora). Só o MINUTO_GATILHO manda
# mensagem no Telegram; os outros só entram na planilha (coluna "Minuto"),
# pra comparar depois qual minuto rende mais. Precisa incluir o
# MINUTO_GATILHO.
MINUTOS_ENTRADA = [18, 20, 22, 24, 26, 28]
# Se a odd não estiver na faixa exatamente no minuto-alvo, tenta de novo
# nos ciclos seguintes até este tanto de minutos depois, e desiste.
TOLERANCIA_MINUTOS = 2

# Faixa de linhas de Under aceitas (Under 2.75 a Under 4.5, passo 0.25)
LINHA_MINIMA = 2.75
LINHA_MAXIMA = 4.5

# Linhas simuladas em paralelo (usadas só na simulação, não no alerta)
LINHAS_SIMULADAS = [
    "Under 4.5", "Under 4.25", "Under 4", "Under 3.75",
    "Under 3.5", "Under 3.25", "Under 3", "Under 2.75",
]

# Só considera (alerta + simulação) uma linha cuja odd no momento do
# gatilho esteja dentro dessa faixa -- fora da faixa, a linha é
# ignorada mesmo que o placar bata o padrão.
ODD_MINIMA = 1.72
ODD_MAXIMA = 2.00

# ---------------------------------------------------------------------
# Filtro de competições a ignorar (categorias de base)
# Qualquer liga cujo nome contenha um destes termos (case-insensitive)
# é ignorada tanto pro alerta quanto pra simulação.
# ---------------------------------------------------------------------
LIGAS_EXCLUIDAS_TERMOS = [
    # categorias de base (u17..u23, sub-xx, youth, junior, juvenil) LIBERADAS em 2026-11-27
    "reserve", "reservas",
    "esoccer", "e-soccer", "efootball", "e-football", "cyber", "fifa",
]

# Países bloqueados (ROI ruim no histórico do VBB: Noruega -19,6% em 70 tips;
# Áustria e Alemanha pediu o usuário). Compara com o nome da liga na BetsAPI.
PAISES_EXCLUIDOS_TERMOS = ["norway", "norwegian", "austria", "germany"]

# ---------------------------------------------------------------------
# Estratégia de checagem (economiza chamadas de API):
# 1. /inplay_filter dá o horário de início -> estimamos o minuto de graça
# 2. só chamamos /bet365/event (que tem o relógio exato + odds) pros
#    jogos cujo minuto ESTIMADO já passou perto do gatilho
# 3. IMPORTANTE: as odds mudam a cada instante -- um jogo 0x0 pode não
#    ter nenhuma linha na faixa de odd exatamente no minuto 21, mas
#    ter alguns minutos depois (ou vice-versa). Por isso, em vez de
#    checar só uma vez e desistir, RECHECAMOS a cada ciclo enquanto o
#    jogo continuar 0x0, do minuto MINUTO_GATILHO até MINUTO_LIMITE.
# 4. A estimativa de minuto é calculada a partir do horário PROGRAMADO
#    do jogo -- se o jogo começou atrasado (comum, principalmente em
#    ligas menores), a estimativa fica inflada e o jogo pode nunca
#    entrar na janela de confirmação, sendo pulado silenciosamente
#    desde o início (confirmado em 2026-08-19 com um caso real).
#    JANELA_CONFIRMACAO_MINUTOS alargada bem generosa pra tolerar isso.
# ---------------------------------------------------------------------
JANELA_CONFIRMACAO_MINUTOS = 8   # margem (em min estimados) antes do 1º minuto-alvo e depois do último
# (a janela vai de min(MINUTOS_ENTRADA)-8 até max(MINUTOS_ENTRADA)+TOLERANCIA+8, em minutos
# ESTIMADOS; depois da 1ª chamada /event o bot passa a usar o minuto exato e agenda
# a próxima checagem só pra perto do próximo minuto-alvo)

# Teto de chamadas /event por ciclo (protege a cota compartilhada da
# BetsAPI com o Planilheiro). Jogos mais perto do gatilho têm prioridade.
MAX_EVENT_POR_CICLO = 8


# ---------------------------------------------------------------------
# Marcação de resultado no canal de avisos: a mensagem do alerta é
# editada e recebe estas marcas embaixo quando o jogo termina.
# ---------------------------------------------------------------------
MARCAS_RESULTADO = {
    "green": "✅✅✅✅✅✅",
    "meio green": "🔄✅",
    "void": "🔄",
    "meio red": "🔄❌",
    "red": "❌",
}

# Canal extra de avisos do minuto 20 (mesmo formato do canal principal).
# Defina CHAT_ID_MIN20 no Render; sem ele, o minuto 20 segue só na planilha.
CHAT_ID_MIN20 = os.environ.get("CHAT_ID_MIN20", "")
CHAT_ID_MIN18 = os.environ.get("CHAT_ID_MIN18", "")

# minuto de entrada -> chat que recebe o aviso (o 22 também manda no privado)
CANAIS_POR_MINUTO = {MINUTO_GATILHO: CHAT_ID_SIMULACAO}
if CHAT_ID_MIN20:
    CANAIS_POR_MINUTO[20] = CHAT_ID_MIN20
if CHAT_ID_MIN18:
    CANAIS_POR_MINUTO[18] = CHAT_ID_MIN18

# ---------------------------------------------------------------------
# RAMIFICAÇÃO: entradas dos minutos RAMO_MINUTOS, sem as ligas excluídas
# aqui, vão TAMBÉM pra um canal e uma planilha próprios. O bot principal
# continua igual. Tudo por variável de ambiente (sem redeploy pra mudar):
#   CHAT_ID_RAMO_18         canal do Telegram da ramificação, entradas do min 18
#   CHAT_ID_RAMO_22         canal do Telegram da ramificação, entradas do min 22
#   GOOGLE_SHEET_ID_RAMO    planilha própria da ramificação
#   RAMO_LIGAS_EXCLUIDAS    termos do nome da liga/país, separados por ";"
#                           (ex: "Czechia;MLS;Women")  -- compara sem maiúsc.
# A ramificação só liga se algum CHAT_ID_RAMO_xx ou GOOGLE_SHEET_ID_RAMO existir.
# ---------------------------------------------------------------------
RAMO_MINUTOS = [18, 22]
RAMO_CANAIS = {m: os.environ.get(f"CHAT_ID_RAMO_{m}", "") for m in RAMO_MINUTOS}
RAMO_CANAIS = {m: c for m, c in RAMO_CANAIS.items() if c}   # só os configurados
GOOGLE_SHEET_ID_RAMO = os.environ.get("GOOGLE_SHEET_ID_RAMO", "")
RAMO_LIGAS_EXCLUIDAS = [t.strip().lower() for t in
                        os.environ.get("RAMO_LIGAS_EXCLUIDAS", "").split(";") if t.strip()]


def _norm_liga(nome: str) -> str:
    return (nome or "").replace("\u2019", "'").strip().lower()


# Lista de ligas excluídas da ramificação: nomes EXATOS (um por linha) em
# ramo_ligas_excluidas.txt. Comparação pelo nome inteiro, sem maiúsculas.
RAMO_LIGAS_EXCLUIDAS_EXATAS = set()
try:
    _arq = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ramo_ligas_excluidas.txt")
    with open(_arq, "r", encoding="utf-8") as _f:
        RAMO_LIGAS_EXCLUIDAS_EXATAS = {_norm_liga(l) for l in _f if l.strip()}
except Exception as _e:
    print(f"[aviso] lista de ligas excluídas da ramificação não carregou: {_e}")

RAMO_ATIVO = bool(RAMO_CANAIS or GOOGLE_SHEET_ID_RAMO)

# ---------------------------------------------------------------------
# Simulação (banca fictícia)
# ---------------------------------------------------------------------
BANCA_INICIAL = 100_000.00   # R$100.000
STAKE_UNIDADE = 1_000.00     # R$1.000 = 1 unidade por entrada

# ---------------------------------------------------------------------
# Google Sheets (registro das apostas simuladas, com campeonato
# separado numa coluna, pra dar pra filtrar por liga depois de
# acumular volume)
# ---------------------------------------------------------------------
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")

# ---------------------------------------------------------------------
# Operação
# ---------------------------------------------------------------------
INTERVALO_POLLING_SEGUNDOS = 45  # frequência de checagem dos jogos ao vivo
HORARIO_RELATORIO_DIARIO = "23:59"  # horário (HH:MM, Brasília) do resumo

# Arquivo onde o estado persiste entre reinicializações do processo
# (jogos já notificados, apostas simuladas em aberto, histórico)
# Caminho do arquivo de estado -- em produção (Render com disco
# persistente), define DISCO_PERSISTENTE_PATH apontando pro diretório
# montado do disco (ex: /var/data), senão usa o diretório local (que
# se perde a cada redeploy, ok só pra teste).
_pasta_estado = os.environ.get("DISCO_PERSISTENTE_PATH", ".")
ARQUIVO_ESTADO = os.path.join(_pasta_estado, "estado.json")

# ---------------------------------------------------------------------
# Modo teste (temporário)
# ---------------------------------------------------------------------
# Se True, IGNORA o placar/minuto reais e força o alerta a disparar no
# primeiro jogo ao vivo elegível que encontrar -- só pra validar o fluxo
# completo (mensagem no Telegram + busca de odds + registro da simulação)
# sem precisar esperar um 0x0 de verdade no minuto 21.
# IMPORTANTE: desligar (False) antes de rodar valendo de verdade.
MODO_TESTE = False

