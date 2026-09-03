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

BANCA_INICIAL = 20.00
STAKE_MIN = 0.50
STAKE_MAX = 2.00

MIN_BOOKMAKERS = 4
MIN_VALUE = 0.03
MIN_SCORE = 75

HISTORICO_FILE = "historico.json"


# ============================================================
# HISTÓRICO
# ============================================================

def carregar_historico():

    if not os.path.exists(HISTORICO_FILE):
        return {
            "banca_inicial": BANCA_INICIAL,
            "banca_atual": BANCA_INICIAL,
            "apostas": [],
            "snapshots": []
        }

    try:
        with open(HISTORICO_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)

        dados.setdefault("banca_inicial", BANCA_INICIAL)
        dados.setdefault("banca_atual", BANCA_INICIAL)
        dados.setdefault("apostas", [])
        dados.setdefault("snapshots", [])

        return dados

    except Exception:
        return {
            "banca_inicial": BANCA_INICIAL,
            "banca_atual": BANCA_INICIAL,
            "apostas": [],
            "snapshots": []
        }


def guardar_historico(dados):

    with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(
            dados,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(texto):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: Telegram não configurado.")
        return False

    url = (
        f"https://api.telegram.org/"
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

        print("Telegram:", resposta.status_code)

        return resposta.status_code == 200

    except Exception as e:

        print("Erro Telegram:", e)

        return False


# ============================================================
# THE ODDS API
# ============================================================

def obter_jogos():

    url = (
        f"https://api.the-odds-api.com/v4/sports/"
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

        print("Estado API:", resposta.status_code)

        if resposta.status_code != 200:
            print(resposta.text)
            return []

        return resposta.json()

    except Exception as e:

        print("Erro API:", e)

        return []


# ============================================================
# RESULTADOS
# ============================================================

def obter_resultados():

    url = (
        f"https://api.the-odds-api.com/v4/sports/"
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

        print("Scores API:", resposta.status_code)

        if resposta.status_code != 200:
            print(resposta.text)
            return []

        return resposta.json()

    except Exception as e:

        print("Erro Scores:", e)

        return []


# ============================================================
# PROBABILIDADE JUSTA
# ============================================================

def probabilidades_justas(outcomes):

    odds = []

    for outcome in outcomes:

        odd = outcome.get("price")

        if odd and odd > 1:
            odds.append(odd)

    if len(odds) < 3:
        return {}

    probabilidades_brutas = [
        1 / odd for odd in odds
    ]

    margem = sum(probabilidades_brutas)

    resultado = {}

    for outcome in outcomes:

        nome = outcome.get("name")
        odd = outcome.get("price")

        if not nome or not odd or odd <= 1:
            continue

        prob = (1 / odd) / margem

        resultado[nome] = prob

    return resultado


# ============================================================
# SCORE
# ============================================================

def calcular_score(value, casas):

    score = 50

    if value >= 0.03:
        score += 10

    if value >= 0.05:
        score += 5

    if value >= 0.08:
        score += 5

    if value >= 0.10:
        score += 5

    if casas >= 5:
        score += 5

    if casas >= 8:
        score += 5

    return min(score, 100)


# ============================================================
# STAKE
# ============================================================

def calcular_stake(score, banca):

    if banca <= 0:
        return 0

    if score < 75:
        percentagem = 0.025

    elif score < 80:
        percentagem = 0.035

    elif score < 85:
        percentagem = 0.05

    elif score < 90:
        percentagem = 0.065

    else:
        percentagem = 0.08

    stake = banca * percentagem

    stake = max(STAKE_MIN, stake)
    stake = min(STAKE_MAX, stake)

    if stake > banca:
        stake = banca

    return round(stake, 2)


# ============================================================
# NORMALIZAR NOME DO JOGO
# ============================================================

def chave_jogo(home, away):

    return (
        home.strip().lower()
        + " vs "
        + away.strip().lower()
    )


# ============================================================
# ANALISAR JOGOS
# ============================================================

def analisar_jogos(dados):

    agora = datetime.now(timezone.utc)

    candidatos = []

    for jogo in dados:

        event_id = jogo.get("id")
        home = jogo.get("home_team")
        away = jogo.get("away_team")
        commence_time = jogo.get("commence_time")

        if not event_id or not home or not away:
            continue

        if not commence_time:
            continue

        try:

            data_jogo = datetime.fromisoformat(
                commence_time.replace("Z", "+00:00")
            )

        except Exception:
            continue

        if data_jogo <= agora:
            continue

        nome_jogo = f"{home} vs {away}"

        betclic = None
        outros = []

        # ----------------------------------------------------
        # BOOKMAKERS
        # ----------------------------------------------------

        for bookmaker in jogo.get("bookmakers", []):

            nome_bookmaker = bookmaker.get("title", "")

            for mercado in bookmaker.get("markets", []):

                if mercado.get("key") != "h2h":
                    continue

                outcomes = mercado.get("outcomes", [])

                mapa = {}

                for outcome in outcomes:

                    nome = outcome.get("name")
                    odd = outcome.get("price")

                    if nome and odd and odd > 1:
                        mapa[nome] = odd

                if "betclic" in nome_bookmaker.lower():

                    betclic = mapa

                else:

                    if mapa:
                        outros.append(mapa)

        if not betclic:
            continue

        if len(outros) < MIN_BOOKMAKERS:
            continue

        # ----------------------------------------------------
        # AVALIAR CADA RESULTADO
        # ----------------------------------------------------

        opcoes = []

        for selecao, odd_betclic in betclic.items():

            odds_outros = []

            for mapa in outros:

                if selecao in mapa:

                    odd = mapa[selecao]

                    if odd and odd > 1:
                        odds_outros.append(odd)

            if len(odds_outros) < MIN_BOOKMAKERS:
                continue

            # Mediana do mercado
            consenso_odd = statistics.median(odds_outros)

            # Probabilidade de mercado
            probabilidade = 1 / consenso_odd

            # Value contra Betclic
            value = (
                odd_betclic * probabilidade
            ) - 1

            if value < MIN_VALUE:
                continue

            score = calcular_score(
                value,
                len(odds_outros)
            )

            if score < MIN_SCORE:
                continue

            opcoes.append({
                "event_id": event_id,
                "jogo": nome_jogo,
                "home": home,
                "away": away,
                "aposta": selecao,
                "odd": round(odd_betclic, 2),
                "probabilidade": round(probabilidade, 4),
                "value": round(value, 4),
                "score": score,
                "data_jogo": commence_time
            })

        # ----------------------------------------------------
        # APENAS A MELHOR DO JOGO
        # ----------------------------------------------------

        if opcoes:

            opcoes.sort(
                key=lambda x: (
                    x["score"],
                    x["value"]
                ),
                reverse=True
            )

            candidatos.append(opcoes[0])

    return candidatos


# ============================================================
# GUARDAR SNAPSHOTS
# ============================================================

def guardar_snapshots(dados, historico):

    agora = datetime.now(timezone.utc).isoformat()

    for jogo in dados:

        event_id = jogo.get("id")
        home = jogo.get("home_team")
        away = jogo.get("away_team")

        if not event_id or not home or not away:
            continue

        for bookmaker in jogo.get("bookmakers", []):

            nome = bookmaker.get("title", "")

            for mercado in bookmaker.get("markets", []):

                if mercado.get("key") != "h2h":
                    continue

                for outcome in mercado.get("outcomes", []):

                    historico["snapshots"].append({
                        "event_id": event_id,
                        "data_hora": agora,
                        "jogo": f"{home} vs {away}",
                        "bookmaker": nome,
                        "aposta": outcome.get("name"),
                        "odd": outcome.get("price")
                    })

    # Não deixar o ficheiro crescer infinitamente
    if len(historico["snapshots"]) > 10000:
        historico["snapshots"] = historico["snapshots"][-10000:]


# ============================================================
# GUARDAR NOVAS APOSTAS
# ============================================================

def guardar_apostas(candidatos, historico):

    novas = []

    banca = historico["banca_atual"]

    for candidato in candidatos:

        event_id = candidato["event_id"]

        # Nunca mais de uma aposta pendente por jogo
        existe = False

        for aposta in historico["apostas"]:

            if (
                aposta.get("event_id") == event_id
                and aposta.get("estado") == "PENDENTE"
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
            "event_id": event_id,
            "data_criacao": datetime.now(
                timezone.utc
            ).isoformat(),
            "jogo": candidato["jogo"],
            "home": candidato["home"],
            "away": candidato["away"],
            "aposta": candidato["aposta"],
            "odd": candidato["odd"],
            "probabilidade": candidato["probabilidade"],
            "value": candidato["value"],
            "score": candidato["score"],
            "stake": stake,
            "data_jogo": candidato["data_jogo"],
            "estado": "PENDENTE",
            "lucro": 0
        }

        historico["apostas"].append(aposta)

        novas.append(aposta)

        # Não comprometer mais do que a banca disponível
        banca -= stake

    return novas


# ============================================================
# LIQUIDAR APOSTAS
# ============================================================

def liquidar_apostas(resultados, historico):

    alteradas = []

    for resultado in resultados:

        if not resultado.get("completed"):
            continue

        scores = resultado.get("scores")

        if not scores:
            continue

        home = resultado.get("home_team")
        away = resultado.get("away_team")
        event_id = resultado.get("id")

        if not event_id:
            continue

        # Determinar resultado
        home_score = None
        away_score = None

        for score in scores:

            nome = score.get("name")
            valores = score.get("score")

            if valores is None:
                continue

            try:
                valor = int(valores)
            except Exception:
                continue

            if nome == home:
                home_score = valor

            elif nome == away:
                away_score = valor

        if home_score is None or away_score is None:
            continue

        if home_score > away_score:
            vencedor = home

        elif away_score > home_score:
            vencedor = away

        else:
            vencedor = "Draw"

        for aposta in historico["apostas"]:

            if aposta.get("estado") != "PENDENTE":
                continue

            if aposta.get("event_id") != event_id:
                continue

            stake = float(aposta["stake"])
            odd = float(aposta["odd"])

            if aposta["aposta"] == vencedor:

                lucro = round(
                    stake * (odd - 1),
                    2
                )

                aposta["estado"] = "GANHA"
                aposta["lucro"] = lucro

                historico["banca_atual"] = round(
                    historico["banca_atual"]
                    + stake
                    + lucro,
                    2
                )

            else:

                lucro = -stake

                aposta["estado"] = "PERDIDA"
                aposta["lucro"] = lucro

                historico["banca_atual"] = round(
                    historico["banca_atual"]
                    + lucro,
                    2
                )

            aposta["resultado"] = (
                f"{home} {home_score}-{away_score} {away}"
            )

            alteradas.append(aposta)

    return alteradas


# ============================================================
# ESTATÍSTICAS
# ============================================================

def estatisticas(historico):

    ganhas = 0
    perdidas = 0
    pendentes = 0
    lucro = 0
    total_stakes = 0

    for aposta in historico["apostas"]:

        estado = aposta.get("estado")

        if estado == "GANHA":

            ganhas += 1
            lucro += float(aposta.get("lucro", 0))
            total_stakes += float(aposta.get("stake", 0))

        elif estado == "PERDIDA":

            perdidas += 1
            lucro += float(aposta.get("lucro", 0))
            total_stakes += float(aposta.get("stake", 0))

        elif estado == "PENDENTE":

            pendentes += 1

    total = ganhas + perdidas

    if total:
        acerto = ganhas / total * 100
    else:
        acerto = 0

    if total_stakes:
        roi = lucro / total_stakes * 100
    else:
        roi = 0

    return {
        "ganhas": ganhas,
        "perdidas": perdidas,
        "pendentes": pendentes,
        "lucro": round(lucro, 2),
        "acerto": round(acerto, 1),
        "roi": round(roi, 1),
        "banca": round(
            historico["banca_atual"],
            2
        )
    }


# ============================================================
# MENSAGEM TELEGRAM
# ============================================================

def criar_mensagem(novas, liquidadas, stats):

    texto = "🧠 VALUE FOOTBALL BOT\n\n"
    texto += "🇵🇹 LIGA PORTUGAL\n"
    texto += "🏦 BETCLIC\n\n"

    if novas:

        texto += (
            f"🔥 {len(novas)} NOVA(S) "
            f"OPORTUNIDADE(S)\n\n"
        )

        for aposta in novas:

            try:

                data = datetime.fromisoformat(
                    aposta["data_jogo"]
                    .replace("Z", "+00:00")
                ).strftime("%d/%m %H:%M")

            except Exception:

                data = aposta["data_jogo"]

            texto += f"⚽ {aposta['jogo']}\n"
            texto += f"🎯 {aposta['aposta']}\n"
            texto += f"🏦 Betclic @ {aposta['odd']:.2f}\n"
            texto += (
                f"📊 Prob. mercado: "
                f"{aposta['probabilidade'] * 100:.1f}%\n"
            )
            texto += (
                f"💎 Value estimado: "
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
            texto += f"🗓️ {data}\n\n"

    if liquidadas:

        texto += "📋 RESULTADOS ATUALIZADOS\n\n"

        for aposta in liquidadas:

            if aposta["estado"] == "GANHA":
                emoji = "🟢"
            else:
                emoji = "🔴"

            texto += (
                f"{emoji} {aposta['jogo']} — "
                f"{aposta['aposta']}\n"
            )

            texto += (
                f"💰 Resultado: "
                f"€{aposta['lucro']:+.2f}\n\n"
            )

    if not novas and not liquidadas:

        texto += (
            "🔎 Nenhuma nova oportunidade "
            "nesta análise.\n\n"
        )

    texto += "📊 BALANÇO VIRTUAL\n\n"
    texto += f"🟢 Ganhas: {stats['ganhas']}\n"
    texto += f"🔴 Perdidas: {stats['perdidas']}\n"
    texto += f"⚪ Pendentes: {stats['pendentes']}\n"
    texto += f"🎯 Acerto: {stats['acerto']:.1f}%\n"
    texto += f"💰 Lucro: €{stats['lucro']:.2f}\n"
    texto += f"📈 ROI: {stats['roi']:.1f}%\n"
    texto += f"💼 Banca virtual: €{stats['banca']:.2f}\n\n"

    texto += "⚠️ MODO TESTE\n"
    texto += "Nenhuma aposta real foi efetuada."

    return texto


# ============================================================
# MAIN
# ============================================================

def main():

    print("===================================")
    print("VALUE FOOTBALL BOT")
    print("===================================")

    if not API_KEY:
        print("ERRO: ODDS_API_KEY não encontrada.")
        return

    if not TELEGRAM_TOKEN:
        print("ERRO: TELEGRAM_BOT_TOKEN não encontrada.")
        return

    if not TELEGRAM_CHAT_ID:
        print("ERRO: TELEGRAM_CHAT_ID não encontrada.")
        return

    historico = carregar_historico()

    # --------------------------------------------------------
    # RESULTADOS
    # --------------------------------------------------------

    resultados = obter_resultados()

    liquidadas = liquidar_apostas(
        resultados,
        historico
    )

    # --------------------------------------------------------
    # ODDS ATUAIS
    # --------------------------------------------------------

    jogos = obter_jogos()

    guardar_snapshots(
        jogos,
        historico
    )

    candidatos = analisar_jogos(
        jogos
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
        stats
    )

    enviar_telegram(
        mensagem
    )

    print("Novas apostas:", len(novas))
    print("Apostas liquidadas:", len(liquidadas))
    print("Banca:", stats["banca"])
    print("Execução concluída.")


if __name__ == "__main__":
    main()
