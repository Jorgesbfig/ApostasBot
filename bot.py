import os
import json
import statistics
import requests
from datetime import datetime, timezone

# ============================================================
# CONFIGURAÇÃO
# ============================================================

API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SPORT = "soccer_portugal_primeira_liga"
REGION = "eu"

ESTIMADOR_URL = (
    "https://estimador.pt/data/football/"
    "liga-2026-27/"
)

BANCA_INICIAL = 20.00

STAKE_MIN = 0.50
STAKE_MAX = 2.00

MIN_BOOKMAKERS = 4
MIN_VALUE = 0.05
MIN_SCORE = 75

HISTORICO_FILE = "historico.json"


# ============================================================
# HISTÓRICO
# ============================================================

def historico_vazio():
    return {
        "banca_inicial": BANCA_INICIAL,
        "banca_atual": BANCA_INICIAL,
        "apostas": [],
        "snapshots": []
    }


def carregar_historico():

    if not os.path.exists(HISTORICO_FILE):
        return historico_vazio()

    try:

        with open(
            HISTORICO_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            dados = json.load(f)

        dados.setdefault(
            "banca_inicial",
            BANCA_INICIAL
        )

        dados.setdefault(
            "banca_atual",
            BANCA_INICIAL
        )

        dados.setdefault(
            "apostas",
            []
        )

        dados.setdefault(
            "snapshots",
            []
        )

        return dados

    except Exception as e:

        print(
            "Erro ao carregar histórico:",
            e
        )

        return historico_vazio()


def guardar_historico(dados):

    with open(
        HISTORICO_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            dados,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# CORRIGIR BANCA DE APOSTAS PENDENTES ANTIGAS
# ============================================================

def corrigir_banca_pendentes(historico):

    banca = float(
        historico.get(
            "banca_atual",
            BANCA_INICIAL
        )
    )

    alterou = False

    for aposta in historico["apostas"]:

        if aposta.get("estado") != "PENDENTE":
            continue

        if aposta.get("stake_reservada"):
            continue

        stake = float(
            aposta.get(
                "stake",
                0
            )
        )

        if stake <= 0:
            continue

        banca -= stake

        aposta["stake_reservada"] = True

        alterou = True

    historico["banca_atual"] = round(
        max(0, banca),
        2
    )

    return alterou


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(texto):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:

        print(
            "ERRO: Telegram não configurado."
        )

        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:

        resposta = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": texto
            },
            timeout=30
        )

        print(
            "Telegram:",
            resposta.status_code
        )

        return resposta.status_code == 200

    except Exception as e:

        print(
            "Erro Telegram:",
            e
        )

        return False


# ============================================================
# THE ODDS API
# ============================================================

def obter_jogos():

    url = (
        "https://api.the-odds-api.com/v4/sports/"
        f"{SPORT}/odds"
    )

    params = {
        "apiKey": API_KEY,
        "regions": REGION,
        "markets": "h2h",
        "oddsFormat": "decimal"
    }

    try:

        resposta = requests.get(
            url,
            params=params,
            timeout=30
        )

        print(
            "Estado API:",
            resposta.status_code
        )

        if resposta.status_code != 200:

            print(
                resposta.text
            )

            return []

        return resposta.json()

    except Exception as e:

        print(
            "Erro API:",
            e
        )

        return []


# ============================================================
# RESULTADOS
# ============================================================

def obter_resultados():

    url = (
        "https://api.the-odds-api.com/v4/sports/"
        f"{SPORT}/scores"
    )

    params = {
        "apiKey": API_KEY,
        "daysFrom": 3
    }

    try:

        resposta = requests.get(
            url,
            params=params,
            timeout=30
        )

        print(
            "Scores API:",
            resposta.status_code
        )

        if resposta.status_code != 200:

            print(
                resposta.text
            )

            return []

        return resposta.json()

    except Exception as e:

        print(
            "Erro Scores:",
            e
        )

        return []


# ============================================================
# ESTIMADOR.PT
# ============================================================

def obter_modelo_estimador():

    try:

        # Procuramos a jornada mais recente.
        for jornada in range(20, -1, -1):

            url = (
                ESTIMADOR_URL
                + f"md{jornada:02d}.json"
            )

            resposta = requests.get(
                url,
                timeout=20
            )

            if resposta.status_code == 200:

                dados = resposta.json()

                print(
                    "Estimador:",
                    url
                )

                return dados

        print(
            "Não foi possível obter dados do Estimador."
        )

        return None

    except Exception as e:

        print(
            "Erro Estimador:",
            e
        )

        return None


# ============================================================
# NORMALIZAÇÃO DE NOMES
# ============================================================

def normalizar_nome(nome):

    if not nome:
        return ""

    nome = nome.lower().strip()

    substituicoes = {
        "sporting lisbon": "sporting cp",
        "sporting": "sporting cp",
        "porto": "porto",
        "fc porto": "porto",
        "benfica": "benfica",
        "sl benfica": "benfica",
        "moreirense fc": "moreirense",
        "moreirense": "moreirense",
        "vitoria sc": "vitoria sc",
        "vitória sc": "vitoria sc",
        "guimaraes": "vitoria sc",
        "vitoria guimaraes": "vitoria sc",
        "sc braga": "sc braga",
        "braga": "sc braga",
        "maritimo": "maritimo",
        "cs maritimo": "maritimo",
        "nacional": "nacional",
        "casa pia": "casa pia",
        "gil vicente": "gil vicente",
        "santa clara": "santa clara",
        "rio ave": "rio ave",
        "arouca": "arouca",
        "estoril": "estoril",
        "famalicao": "famalicao",
        "estrela amadora": "estrela amadora",
        "alverca": "alverca",
        "academico viseu": "academico viseu"
    }

    return substituicoes.get(
        nome,
        nome
    )


# ============================================================
# PROBABILIDADES DO ESTIMADOR
# ============================================================

def obter_probabilidades_estimador(dados):

    mapa = {}

    if not dados:
        return mapa

    jogos = dados.get(
        "next_matchday",
        {}
    ).get(
        "matches",
        []
    )

    for jogo in jogos:

        home = normalizar_nome(
            jogo.get("home")
        )

        away = normalizar_nome(
            jogo.get("away")
        )

        if not home or not away:
            continue

        chave = (
            home,
            away
        )

        mapa[chave] = {
            "Home": float(
                jogo.get(
                    "p_home",
                    0
                )
            ),
            "Draw": float(
                jogo.get(
                    "p_draw",
                    0
                )
            ),
            "Away": float(
                jogo.get(
                    "p_away",
                    0
                )
            )
        }

    return mapa


# ============================================================
# FORÇA DAS EQUIPAS
# ============================================================

def obter_forcas_equipa(dados):

    resultado = {}

    if not dados:
        return resultado

    for equipa, valores in dados.get(
        "team_strengths",
        {}
    ).items():

        nome = normalizar_nome(
            equipa
        )

        resultado[nome] = {
            "attack": float(
                valores.get(
                    "attack",
                    0
                )
            ),
            "defense": float(
                valores.get(
                    "defense",
                    0
                )
            )
        }

    return resultado


# ============================================================
# MODELO COMBINADO
# ============================================================

def calcular_probabilidade_modelo(
    home,
    away,
    selecao,
    probabilidades_estimador,
    forcas
):

    chave = (
        normalizar_nome(home),
        normalizar_nome(away)
    )

    probs = probabilidades_estimador.get(
        chave
    )

    if not probs:
        return None

    prob_estimador = probs.get(
        selecao,
        0
    )

    if prob_estimador <= 0:
        return None

    h = forcas.get(
        normalizar_nome(home),
        {}
    )

    a = forcas.get(
        normalizar_nome(away),
        {}
    )

    ataque_home = h.get(
        "attack",
        0
    )

    defesa_home = h.get(
        "defense",
        0
    )

    ataque_away = a.get(
        "attack",
        0
    )

    defesa_away = a.get(
        "defense",
        0
    )

    diferenca = (
        ataque_home
        - ataque_away
        - defesa_home
        + defesa_away
    )

    ajuste = max(
        -0.08,
        min(
            0.08,
            diferenca * 0.04
        )
    )

    if selecao == "Home":

        prob = (
            prob_estimador
            + ajuste
        )

    elif selecao == "Away":

        prob = (
            prob_estimador
            - ajuste
        )

    else:

        prob = (
            prob_estimador
            - abs(ajuste) * 0.25
        )

    return max(
        0.01,
        min(
            0.95,
            prob
        )
    )


# ============================================================
# SCORE
# ============================================================

def calcular_score(
    value,
    prob_modelo,
    prob_mercado,
    casas
):

    score = 50

    if value >= 0.05:
        score += 10

    if value >= 0.08:
        score += 5

    if value >= 0.12:
        score += 5

    if value >= 0.18:
        score += 5

    if prob_modelo >= 0.50:
        score += 10

    elif prob_modelo >= 0.35:
        score += 5

    diferenca = (
        prob_modelo
        - prob_mercado
    )

    if diferenca >= 0.05:
        score += 5

    if diferenca >= 0.10:
        score += 5

    if casas >= 5:
        score += 5

    if casas >= 8:
        score += 5

    return min(
        score,
        100
    )


# ============================================================
# STAKE
# ============================================================

def calcular_stake(
    score,
    banca
):

    if banca <= 0:
        return 0

    if score >= 90:

        percentagem = 0.08

    elif score >= 85:

        percentagem = 0.065

    elif score >= 80:

        percentagem = 0.05

    elif score >= 75:

        percentagem = 0.035

    else:

        percentagem = 0.025

    stake = (
        banca
        * percentagem
    )

    stake = max(
        STAKE_MIN,
        stake
    )

    stake = min(
        STAKE_MAX,
        stake
    )

    if stake > banca:
        stake = banca

    return round(
        stake,
        2
    )


# ============================================================
# ANÁLISE
# ============================================================

def analisar_jogos(
    dados,
    probabilidades_estimador,
    forcas
):

    agora = datetime.now(
        timezone.utc
    )

    candidatos = []
    diagnosticos = []

    for jogo in dados:

        event_id = jogo.get(
            "id"
        )

        home = jogo.get(
            "home_team"
        )

        away = jogo.get(
            "away_team"
        )

        commence_time = jogo.get(
            "commence_time"
        )

        if not event_id or not home or not away:
            continue

        if not commence_time:
            continue

        try:

            data_jogo = datetime.fromisoformat(
                commence_time.replace(
                    "Z",
                    "+00:00"
                )
            )

        except Exception:

            continue

        if data_jogo <= agora:
            continue

        betclic = None
        outros = []

        for bookmaker in jogo.get(
            "bookmakers",
            []
        ):

            nome_bookmaker = bookmaker.get(
                "title",
                ""
            )

            for mercado in bookmaker.get(
                "markets",
                []
            ):

                if mercado.get(
                    "key"
                ) != "h2h":

                    continue

                mapa = {}

                for outcome in mercado.get(
                    "outcomes",
                    []
                ):

                    nome = outcome.get(
                        "name"
                    )

                    odd = outcome.get(
                        "price"
                    )

                    if (
                        nome
                        and odd
                        and odd > 1
                    ):

                        mapa[nome] = odd

                if (
                    "betclic"
                    in nome_bookmaker.lower()
                ):

                    betclic = mapa

                elif mapa:

                    outros.append(
                        mapa
                    )

        if not betclic:
            diagnosticos.append(
                f"{home} vs {away}: sem Betclic"
            )
            continue

        if len(outros) < MIN_BOOKMAKERS:
            diagnosticos.append(
                f"{home} vs {away}: poucas casas ({len(outros)})"
            )
            continue

        selecoes = {
            "Home": home,
            "Draw": "Draw",
            "Away": away
        }

        opcoes = []

        for tipo, nome_selecao in selecoes.items():

            if nome_selecao not in betclic:
                continue

            odd_betclic = betclic[
                nome_selecao
            ]

            odds_outros = []

            for mapa in outros:

                if nome_selecao in mapa:

                    odd = mapa[
                        nome_selecao
                    ]

                    if odd and odd > 1:

                        odds_outros.append(
                            odd
                        )

            if len(
                odds_outros
            ) < MIN_BOOKMAKERS:

                continue

            consenso_odd = statistics.median(
                odds_outros
            )

            prob_mercado = (
                1
                / consenso_odd
            )

            prob_modelo = (
                calcular_probabilidade_modelo(
                    home,
                    away,
                    tipo,
                    probabilidades_estimador,
                    forcas
                )
            )

            if prob_modelo is None:
                continue

            value = (
                odd_betclic
                * prob_modelo
            ) - 1

            if value < MIN_VALUE:
                continue

            score = calcular_score(
                value,
                prob_modelo,
                prob_mercado,
                len(odds_outros)
            )

            if score < MIN_SCORE:
                continue

            opcoes.append({

                "event_id": event_id,

                "jogo": (
                    f"{home} vs {away}"
                ),

                "home": home,

                "away": away,

                "aposta": nome_selecao,

                "tipo": tipo,

                "odd": round(
                    odd_betclic,
                    2
                ),

                "prob_modelo": round(
                    prob_modelo,
                    4
                ),

                "prob_mercado": round(
                    prob_mercado,
                    4
                ),

                "value": round(
                    value,
                    4
                ),

                "score": score,

                "data_jogo": commence_time
            })

        if opcoes:

            opcoes.sort(
                key=lambda x: (
                    x["score"],
                    x["value"]
                ),
                reverse=True
            )

            candidatos.append(
                opcoes[0]
            )

        else:

            diagnosticos.append(
                f"{home} vs {away}: sem value suficiente"
            )

    return candidatos, diagnosticos


# ============================================================
# SNAPSHOTS
# ============================================================

def guardar_snapshots(
    dados,
    historico
):

    agora = datetime.now(
        timezone.utc
    ).isoformat()

    for jogo in dados:

        event_id = jogo.get(
            "id"
        )

        home = jogo.get(
            "home_team"
        )

        away = jogo.get(
            "away_team"
        )

        if not event_id or not home or not away:
            continue

        for bookmaker in jogo.get(
            "bookmakers",
            []
        ):

            nome = bookmaker.get(
                "title",
                ""
            )

            for mercado in bookmaker.get(
                "markets",
                []
            ):

                if mercado.get(
                    "key"
                ) != "h2h":

                    continue

                for outcome in mercado.get(
                    "outcomes",
                    []
                ):

                    historico[
                        "snapshots"
                    ].append({

                        "event_id": event_id,

                        "data_hora": agora,

                        "jogo": (
                            f"{home} vs {away}"
                        ),

                        "bookmaker": nome,

                        "aposta": outcome.get(
                            "name"
                        ),

                        "odd": outcome.get(
                            "price"
                        )
                    })

    if len(
        historico["snapshots"]
    ) > 10000:

        historico[
            "snapshots"
        ] = historico[
            "snapshots"
        ][-10000:]


# ============================================================
# GUARDAR APOSTAS
# ============================================================

def guardar_apostas(
    candidatos,
    historico
):

    novas = []

    banca = float(
        historico["banca_atual"]
    )

    for candidato in candidatos:

        event_id = candidato[
            "event_id"
        ]

        existe = False

        for aposta in historico[
            "apostas"
        ]:

            if (
                aposta.get(
                    "event_id"
                ) == event_id
                and aposta.get(
                    "estado"
                ) == "PENDENTE"
            ):

                existe = True
                break

        if existe:
            continue

        stake = calcular_stake(
            candidato["score"],
            banca
        )

        if stake <= 0:
            continue

        aposta = {

            "event_id":
                event_id,

            "data_criacao":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "jogo":
                candidato["jogo"],

            "home":
                candidato["home"],

            "away":
                candidato["away"],

            "aposta":
                candidato["aposta"],

            "tipo":
                candidato["tipo"],

            "odd":
                candidato["odd"],

            "prob_modelo":
                candidato["prob_modelo"],

            "prob_mercado":
                candidato["prob_mercado"],

            "value":
                candidato["value"],

            "score":
                candidato["score"],

            "stake":
                stake,

            "data_jogo":
                candidato["data_jogo"],

            "estado":
                "PENDENTE",

            "stake_reservada":
                True,

            "lucro":
                0
        }

        historico[
            "apostas"
        ].append(
            aposta
        )

        novas.append(
            aposta
        )

        banca -= stake

    historico[
        "banca_atual"
    ] = round(
        max(0, banca),
        2
    )

    return novas


# ============================================================
# LIQUIDAR APOSTAS
# ============================================================

def liquidar_apostas(
    resultados,
    historico
):

    alteradas = []

    for resultado in resultados:

        if not resultado.get(
            "completed"
        ):
            continue

        scores = resultado.get(
            "scores"
        )

        if not scores:
            continue

        home = resultado.get(
            "home_team"
        )

        away = resultado.get(
            "away_team"
        )

        event_id = resultado.get(
            "id"
        )

        if not event_id:
            continue

        home_score = None
        away_score = None

        for score in scores:

            nome = score.get(
                "name"
            )

            valores = score.get(
                "score"
            )

            if valores is None:
                continue

            try:

                valor = int(
                    valores
                )

            except Exception:

                continue

            if nome == home:

                home_score = valor

            elif nome == away:

                away_score = valor

        if (
            home_score is None
            or away_score is None
        ):

            continue

        if home_score > away_score:

            vencedor = home

        elif away_score > home_score:

            vencedor = away

        else:

            vencedor = "Draw"

        for aposta in historico[
            "apostas"
        ]:

            if aposta.get(
                "estado"
            ) != "PENDENTE":

                continue

            if aposta.get(
                "event_id"
            ) != event_id:

                continue

            stake = float(
                aposta["stake"]
            )

            odd = float(
                aposta["odd"]
            )

            if aposta[
                "aposta"
            ] == vencedor:

                lucro = round(
                    stake
                    * (odd - 1),
                    2
                )

                aposta[
                    "estado"
                ] = "GANHA"

                aposta[
                    "lucro"
                ] = lucro

                historico[
                    "banca_atual"
                ] = round(
                    historico[
                        "banca_atual"
                    ]
                    + stake
                    + lucro,
                    2
                )

            else:

                lucro = -stake

                aposta[
                    "estado"
                ] = "PERDIDA"

                aposta[
                    "lucro"
                ] = lucro

                # A stake já foi retirada
                # da banca quando a aposta foi criada.
                # Por isso, numa perda não retiramos
                # novamente o valor.

            aposta[
                "resultado"
            ] = (
                f"{home} "
                f"{home_score}-"
                f"{away_score} "
                f"{away}"
            )

            aposta[
                "stake_reservada"
            ] = False

            alteradas.append(
                aposta
            )

    return alteradas


# ============================================================
# ESTATÍSTICAS
# ============================================================

def estatisticas(
    historico
):

    ganhas = 0
    perdidas = 0
    pendentes = 0
    lucro = 0
    total_stakes = 0

    for aposta in historico[
        "apostas"
    ]:

        estado = aposta.get(
            "estado"
        )

        if estado == "GANHA":

            ganhas += 1

            lucro += float(
                aposta.get(
                    "lucro",
                    0
                )
            )

            total_stakes += float(
                aposta.get(
                    "stake",
                    0
                )
            )

        elif estado == "PERDIDA":

            perdidas += 1

            lucro += float(
                aposta.get(
                    "lucro",
                    0
                )
            )

            total_stakes += float(
                aposta.get(
                    "stake",
                    0
                )
            )

        elif estado == "PENDENTE":

            pendentes += 1

    total = (
        ganhas
        + perdidas
    )

    acerto = (
        ganhas
        / total
        * 100
        if total
        else 0
    )

    roi = (
        lucro
        / total_stakes
        * 100
        if total_stakes
        else 0
    )

    return {

        "ganhas":
            ganhas,

        "perdidas":
            perdidas,

        "pendentes":
            pendentes,

        "lucro":
            round(
                lucro,
                2
            ),

        "acerto":
            round(
                acerto,
                1
            ),

        "roi":
            round(
                roi,
                1
            ),

        "banca":
            round(
                historico[
                    "banca_atual"
                ],
                2
            )
    }


# ============================================================
# TELEGRAM
# ============================================================

def criar_mensagem(
    novas,
    liquidadas,
    stats,
    diagnosticos,
    numero_jogos
):

    texto = (
        "🧠 VALUE FOOTBALL BOT\n\n"
    )

    texto += (
        "🇵🇹 LIGA PORTUGAL\n"
    )

    texto += (
        "🏦 BETCLIC\n\n"
    )

    if novas:

        texto += (
            f"🔥 {len(novas)} "
            "NOVA(S) OPORTUNIDADE(S)\n\n"
        )

        for aposta in novas:

            try:

                data = datetime.fromisoformat(
                    aposta[
                        "data_jogo"
                    ].replace(
                        "Z",
                        "+00:00"
                    )
                ).strftime(
                    "%d/%m %H:%M"
                )

            except Exception:

                data = aposta[
                    "data_jogo"
                ]

            texto += (
                f"⚽ {aposta['jogo']}\n"
            )

            texto += (
                f"🎯 {aposta['aposta']}\n"
            )

            texto += (
                f"🏦 Betclic @ "
                f"{aposta['odd']:.2f}\n"
            )

            texto += (
                f"🧠 Prob. modelo: "
                f"{aposta['prob_modelo'] * 100:.1f}%\n"
            )

            texto += (
                f"📊 Prob. mercado: "
                f"{aposta['prob_mercado'] * 100:.1f}%\n"
            )

            texto += (
                f"💎 Value modelo: "
                f"{aposta['value'] * 100:+.1f}%\n"
            )

            texto += (
                f"⭐ Score: "
                f"{aposta['score']}/100\n"
            )

            texto += (
                f"💶 Stake virtual: "
                f"€{aposta['stake']:.2f}\n"
            )

            texto += (
                f"🗓️ {data}\n\n"
            )

    if liquidadas:

        texto += (
            "📋 RESULTADOS ATUALIZADOS\n\n"
        )

        for aposta in liquidadas:

            if aposta[
                "estado"
            ] == "GANHA":

                emoji = "🟢"

            else:

                emoji = "🔴"

            texto += (
                f"{emoji} "
                f"{aposta['jogo']} — "
                f"{aposta['aposta']}\n"
            )

            texto += (
                f"💰 Resultado: "
                f"€{aposta['lucro']:+.2f}\n\n"
            )

    texto += (
        "🔎 ANÁLISE DESTA EXECUÇÃO\n\n"
    )

    texto += (
        f"⚽ Jogos encontrados: "
        f"{numero_jogos}\n"
    )

    texto += (
        f"🎯 Oportunidades: "
        f"{len(novas)}\n\n"
    )

    if diagnosticos:

        texto += (
            "ℹ️ Alguns filtros:\n"
        )

        for motivo in diagnosticos[:6]:

            texto += (
                f"• {motivo}\n"
            )

        texto += "\n"

    texto += (
        "📊 BALANÇO VIRTUAL\n\n"
    )

    texto += (
        f"🟢 Ganhas: "
        f"{stats['ganhas']}\n"
    )

    texto += (
        f"🔴 Perdidas: "
        f"{stats['perdidas']}\n"
    )

    texto += (
        f"⚪ Pendentes: "
        f"{stats['pendentes']}\n"
    )

    texto += (
        f"🎯 Acerto: "
        f"{stats['acerto']:.1f}%\n"
    )

    texto += (
        f"💰 Lucro: "
        f"€{stats['lucro']:.2f}\n"
    )

    texto += (
        f"📈 ROI: "
        f"{stats['roi']:.1f}%\n"
    )

    texto += (
        f"💼 Banca virtual: "
        f"€{stats['banca']:.2f}\n\n"
    )

    texto += (
        "⚠️ MODO TESTE\n"
    )

    texto += (
        "Nenhuma aposta real foi efetuada."
    )

    return texto


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "==================================="
    )

    print(
        "VALUE FOOTBALL BOT"
    )

    print(
        "==================================="
    )

    if not API_KEY:

        print(
            "ERRO: ODDS_API_KEY não encontrada."
        )

        return

    if not TELEGRAM_TOKEN:

        print(
            "ERRO: TELEGRAM_BOT_TOKEN não encontrada."
        )

        return

    if not TELEGRAM_CHAT_ID:

        print(
            "ERRO: TELEGRAM_CHAT_ID não encontrada."
        )

        return

    historico = carregar_historico()

    # --------------------------------------------------------
    # CORRIGIR BANCA DE APOSTAS PENDENTES
    # --------------------------------------------------------

    historico_corrigido = (
        corrigir_banca_pendentes(
            historico
        )
    )

    if historico_corrigido:

        guardar_historico(
            historico
        )

    # --------------------------------------------------------
    # RESULTADOS
    # --------------------------------------------------------

    resultados = obter_resultados()

    liquidadas = liquidar_apostas(
        resultados,
        historico
    )

    # --------------------------------------------------------
    # MODELO ESTIMADOR
    # --------------------------------------------------------

    dados_estimador = (
        obter_modelo_estimador()
    )

    probabilidades_estimador = (
        obter_probabilidades_estimador(
            dados_estimador
        )
    )

    forcas = (
        obter_forcas_equipa(
            dados_estimador
        )
    )

    print(
        "Jogos com probabilidades do modelo:",
        len(
            probabilidades_estimador
        )
    )

    # --------------------------------------------------------
    # ODDS
    # --------------------------------------------------------

    jogos = obter_jogos()

    guardar_snapshots(
        jogos,
        historico
    )

    candidatos, diagnosticos = analisar_jogos(
        jogos,
        probabilidades_estimador,
        forcas
    )

    novas = guardar_apostas(
        candidatos,
        historico
    )

    guardar_historico(
        historico
    )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    stats = estatisticas(
        historico
    )

    mensagem = criar_mensagem(
        novas,
        liquidadas,
        stats,
        diagnosticos,
        len(jogos)
    )

    enviar_telegram(
        mensagem
    )

    print(
        "Novas apostas:",
        len(novas)
    )

    print(
        "Apostas liquidadas:",
        len(liquidadas)
    )

    print(
        "Banca:",
        stats["banca"]
    )

    print(
        "Execução concluída."
    )


if __name__ == "__main__":
    main()
