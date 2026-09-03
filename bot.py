import os
import sqlite3
import requests
from datetime import datetime, timezone

# =========================
# CONFIGURAÇÃO
# =========================

API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

SPORT = "soccer_portugal_primeira_liga"
REGION = "eu"

BANCA_INICIAL = 20.00
STAKE_MAX = 2.00
MAX_SINAIS_POR_JOGO = 1

DB = "historico.db"

# =========================
# BASE DE DADOS
# =========================

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS apostas_virtuais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    data_hora TEXT,
    jogo TEXT,
    aposta TEXT,
    odd REAL,
    probabilidade REAL,
    value REAL,
    score INTEGER,
    stake REAL,
    data_jogo TEXT,
    estado TEXT DEFAULT 'PENDENTE',
    lucro REAL DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    data_hora TEXT,
    jogo TEXT,
    bookmaker TEXT,
    aposta TEXT,
    odd REAL
)
""")

conn.commit()

# =========================
# TELEGRAM
# =========================

def enviar_telegram(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": "1139116211",
            "text": texto
        },
        timeout=30
    )

    return response.status_code == 200


# =========================
# ODDS API
# =========================

def obter_jogos():
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds"

    params = {
        "apiKey": API_KEY,
        "regions": REGION,
        "markets": "h2h",
        "oddsFormat": "decimal"
    }

    response = requests.get(url, params=params, timeout=30)

    print("Estado API:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        return []

    return response.json()


# =========================
# PROBABILIDADE JUSTA
# =========================

def probabilidade_justa(odds):
    """
    Converte odds de 1X2 em probabilidades implícitas
    e remove a margem do mercado.
    """

    if not odds:
        return None

    inversos = []

    for odd in odds:
        if odd and odd > 1:
            inversos.append(1 / odd)

    if len(inversos) < 3:
        return None

    total = sum(inversos)

    probabilidades = [
        x / total for x in inversos
    ]

    return probabilidades


# =========================
# SCORE
# =========================

def calcular_score(value, numero_casas):

    score = 50

    if value >= 0.03:
        score += 5

    if value >= 0.05:
        score += 10

    if value >= 0.08:
        score += 10

    if value >= 0.12:
        score += 10

    if numero_casas >= 5:
        score += 5

    if numero_casas >= 8:
        score += 5

    return min(score, 100)


# =========================
# STAKE
# =========================

def calcular_stake(score):

    if score < 75:
        return 0.50

    if score < 80:
        return 0.75

    if score < 85:
        return 1.00

    if score < 90:
        return 1.50

    return STAKE_MAX


# =========================
# ANÁLISE
# =========================

def analisar():

    jogos = obter_jogos()

    agora = datetime.now(timezone.utc)

    sinais = []

    for jogo in jogos:

        event_id = jogo.get("id")
        inicio = jogo.get("commence_time")

        if not inicio:
            continue

        try:
            data_jogo = datetime.fromisoformat(
                inicio.replace("Z", "+00:00")
            )
        except:
            continue

        # Ignorar jogos que já começaram
        if data_jogo <= agora:
            continue

        home = jogo.get("home_team", "")
        away = jogo.get("away_team", "")
        nome_jogo = f"{home} vs {away}"

        betclic = None
        outros = []

        # -------------------------
        # Encontrar bookmakers
        # -------------------------

        for bookmaker in jogo.get("bookmakers", []):

            nome_bookmaker = bookmaker.get("title", "")

            mercados = bookmaker.get("markets", [])

            for mercado in mercados:

                if mercado.get("key") != "h2h":
                    continue

                outcomes = mercado.get("outcomes", [])

                mapa = {}

                for outcome in outcomes:
                    nome = outcome.get("name")
                    odd = outcome.get("price")

                    if nome and odd:
                        mapa[nome] = odd

                if "betclic" in nome_bookmaker.lower():
                    betclic = mapa

                else:
                    outros.append(mapa)

        if not betclic:
            continue

        # Precisamos de pelo menos algumas casas para comparar
        if len(outros) < 3:
            continue

        # -------------------------
        # Guardar snapshot
        # -------------------------

        for nome_aposta, odd in betclic.items():

            cur.execute("""
                INSERT INTO snapshots
                (event_id, data_hora, jogo, bookmaker, aposta, odd)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                agora.isoformat(),
                nome_jogo,
                "Betclic",
                nome_aposta,
                odd
            ))

        # -------------------------
        # Avaliar cada seleção
        # -------------------------

        candidatos = []

        for selecao, odd_betclic in betclic.items():

            odds_mercado = []

            for mapa in outros:

                if selecao in mapa:

                    odd = mapa[selecao]

                    if odd and odd > 1:

                        odds_mercado.append(odd)

            if len(odds_mercado) < 3:
                continue

            # Mediana das outras casas
            odds_ordenadas = sorted(odds_mercado)

            meio = len(odds_ordenadas) // 2

            if len(odds_ordenadas) % 2 == 0:
                odd_consenso = (
                    odds_ordenadas[meio - 1]
                    + odds_ordenadas[meio]
                ) / 2
            else:
                odd_consenso = odds_ordenadas[meio]

            # Probabilidade implícita do consenso
            prob_implicita = 1 / odd_consenso

            # Value estimado
            value = (
                odd_betclic * prob_implicita
            ) - 1

            # Aceitar apenas value positivo
            if value <= 0:
                continue

            score = calcular_score(
                value,
                len(odds_mercado)
            )

            # Só queremos sinais fortes
            if score < 70:
                continue

            stake = calcular_stake(score)

            candidatos.append({
                "event_id": event_id,
                "jogo": nome_jogo,
                "aposta": selecao,
                "odd": odd_betclic,
                "probabilidade": prob_implicita,
                "value": value,
                "score": score,
                "stake": stake,
                "data_jogo": inicio
            })

        # -------------------------
        # Escolher apenas o melhor
        # -------------------------

        if candidatos:

            candidatos.sort(
                key=lambda x: (
                    x["score"],
                    x["value"]
                ),
                reverse=True
            )

            melhor = candidatos[0]

            sinais.append(melhor)

    conn.commit()

    return sinais


# =========================
# GUARDAR SINAIS
# =========================

def guardar_sinais(sinais):

    novos = []

    for sinal in sinais:

        # Não repetir o mesmo jogo
        cur.execute("""
            SELECT COUNT(*)
            FROM apostas_virtuais
            WHERE event_id = ?
            AND estado = 'PENDENTE'
        """, (sinal["event_id"],))

        existe = cur.fetchone()[0]

        if existe > 0:
            continue

        cur.execute("""
            INSERT INTO apostas_virtuais
            (
                event_id,
                data_hora,
                jogo,
                aposta,
                odd,
                probabilidade,
                value,
                score,
                stake,
                data_jogo,
                estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDENTE')
        """, (
            sinal["event_id"],
            datetime.now(timezone.utc).isoformat(),
            sinal["jogo"],
            sinal["aposta"],
            sinal["odd"],
            sinal["probabilidade"],
            sinal["value"],
            sinal["score"],
            sinal["stake"],
            sinal["data_jogo"]
        ))

        novos.append(sinal)

    conn.commit()

    return novos


# =========================
# BALANÇO
# =========================

def obter_balanco():

    cur.execute("""
        SELECT COUNT(*)
        FROM apostas_virtuais
        WHERE estado = 'GANHA'
    """)

    ganhas = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM apostas_virtuais
        WHERE estado = 'PERDIDA'
    """)

    perdidas = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM apostas_virtuais
        WHERE estado = 'PENDENTE'
    """)

    pendentes = cur.fetchone()[0]

    cur.execute("""
        SELECT COALESCE(SUM(lucro), 0)
        FROM apostas_virtuais
        WHERE estado IN ('GANHA', 'PERDIDA')
    """)

    lucro = cur.fetchone()[0]

    total = ganhas + perdidas

    if total > 0:
        acerto = (ganhas / total) * 100
    else:
        acerto = 0

    if total > 0:
        roi = (lucro / total) * 100
    else:
        roi = 0

    return (
        ganhas,
        perdidas,
        pendentes,
        acerto,
        lucro,
        roi
    )


# =========================
# MENSAGEM
# =========================

def criar_mensagem(novos):

    texto = "🧠 VALUE FOOTBALL BOT\n\n"
    texto += "🇵🇹 LIGA PORTUGAL\n\n"
    texto += "🏦 BETCLIC\n\n"

    if novos:

        texto += f"🔥 {len(novos)} novo(s) sinal(is)\n\n"

        for sinal in novos:

            data = sinal["data_jogo"]

            try:
                data_formatada = datetime.fromisoformat(
                    data.replace("Z", "+00:00")
                ).strftime("%d/%m %H:%M")
            except:
                data_formatada = data

            texto += f"⚽ {sinal['jogo']}\n\n"
            texto += f"🎯 {sinal['aposta']}\n"
            texto += f"💰 Odd: {sinal['odd']:.2f}\n"
            texto += (
                f"📊 Probabilidade: "
                f"{sinal['probabilidade'] * 100:.1f}%\n"
            )
            texto += (
                f"💎 Value: "
                f"{sinal['value'] * 100:+.1f}%\n"
            )
            texto += f"⭐ Score: {sinal['score']}/100\n"
            texto += f"💶 Stake virtual: €{sinal['stake']:.2f}\n"
            texto += f"🗓️ {data_formatada}\n\n"

    else:

        texto += "🔎 Nenhum novo sinal encontrado.\n\n"

    (
        ganhas,
        perdidas,
        pendentes,
        acerto,
        lucro,
        roi
    ) = obter_balanco()

    texto += "📊 BALANÇO VIRTUAL\n\n"
    texto += f"🟢 Ganhas: {ganhas}\n"
    texto += f"🔴 Perdidas: {perdidas}\n"
    texto += f"⚪ Pendentes: {pendentes}\n"
    texto += f"🎯 Acerto: {acerto:.1f}%\n"
    texto += f"💰 Lucro: €{lucro:.2f}\n"
    texto += f"📈 ROI: {roi:.1f}%\n\n"

    texto += "⚠️ MODO TESTE\n"
    texto += "€1 virtual por sinal.\n"
    texto += "Nenhum dinheiro real foi apostado."

    return texto


# =========================
# EXECUÇÃO
# =========================

if __name__ == "__main__":

    if not API_KEY:
        print("ERRO: ODDS_API_KEY não encontrada.")
        raise SystemExit

    if not TELEGRAM_TOKEN:
        print("ERRO: TELEGRAM_BOT_TOKEN não encontrado.")
        raise SystemExit

    sinais = analisar()

    novos = guardar_sinais(sinais)

    mensagem = criar_mensagem(novos)

    enviado = enviar_telegram(mensagem)

    print("Novos sinais:", len(novos))
    print("Telegram:", enviado)
    print("Execução concluída.")
