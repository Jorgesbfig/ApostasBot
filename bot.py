import os
import requests
import sqlite3
from datetime import datetime, timezone

# =========================================================
# CONFIGURAÇÃO
# =========================================================

API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = "1139116211"

SPORT_KEY = "soccer_portugal_primeira_liga"

ODDS_URL = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
SCORES_URL = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/scores"

PARAMS_ODDS = {
    "apiKey": API_KEY,
    "regions": "eu",
    "markets": "h2h",
    "oddsFormat": "decimal"
}

PARAMS_SCORES = {
    "apiKey": API_KEY,
    "daysFrom": 3,
    "dateFormat": "iso"
}

STAKE_VIRTUAL = 1.00


# =========================================================
# BASE DE DADOS
# =========================================================

conn = sqlite3.connect("historico.db")
cursor = conn.cursor()


cursor.execute("""
CREATE TABLE IF NOT EXISTS analises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT,
    jogo TEXT,
    aposta TEXT,
    odd REAL,
    value REAL,
    score INTEGER
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS apostas_virtuais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT,
    jogo TEXT,
    aposta TEXT,
    odd REAL,
    value REAL,
    score INTEGER,
    estado TEXT
)
""")


conn.commit()


# =========================================================
# GARANTIR COLUNAS NOVAS
# =========================================================

def garantir_coluna(tabela, coluna, tipo):

    colunas = [
        x[1]
        for x in cursor.execute(
            f"PRAGMA table_info({tabela})"
        ).fetchall()
    ]

    if coluna not in colunas:

        cursor.execute(
            f"ALTER TABLE {tabela} "
            f"ADD COLUMN {coluna} {tipo}"
        )

        conn.commit()


garantir_coluna(
    "apostas_virtuais",
    "event_id",
    "TEXT"
)

garantir_coluna(
    "apostas_virtuais",
    "data_jogo",
    "TEXT"
)

garantir_coluna(
    "apostas_virtuais",
    "lucro",
    "REAL"
)


# =========================================================
# MARCAR REGISTOS ANTIGOS
# =========================================================

cursor.execute("""
UPDATE apostas_virtuais
SET estado = 'HISTORICA'
WHERE estado = 'PENDENTE'
AND data_jogo IS NULL
""")

conn.commit()


# =========================================================
# TELEGRAM
# =========================================================

def enviar_telegram(mensagem):

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": mensagem
            },
            timeout=20
        )

        return response

    except Exception as erro:

        print(
            "⚠️ Erro no Telegram:",
            erro
        )

        return None


# =========================================================
# 1. ATUALIZAR RESULTADOS
# =========================================================

print("")
print("==============================================")
print("⚽ VALUE FOOTBALL BOT")
print("==============================================")
print("")
print("🔎 A procurar resultados anteriores...")


scores_response = requests.get(
    SCORES_URL,
    params=PARAMS_SCORES,
    timeout=30
)


print(
    "Estado resultados:",
    scores_response.status_code
)


if scores_response.status_code == 200:

    jogos_resultados = scores_response.json()

    apostas_pendentes = cursor.execute("""
        SELECT
            id,
            jogo,
            aposta,
            odd,
            event_id
        FROM apostas_virtuais
        WHERE estado = 'PENDENTE'
    """).fetchall()

    atualizadas = 0

    for aposta in apostas_pendentes:

        aposta_id = aposta[0]
        nome_jogo_aposta = aposta[1]
        aposta_escolhida = aposta[2]
        odd = float(aposta[3])
        event_id = aposta[4]

        jogo_encontrado = None


        # -------------------------------------------------
        # PRIMEIRO: procurar pelo EVENT ID
        # -------------------------------------------------

        if event_id:

            for jogo in jogos_resultados:

                if str(jogo.get("id")) == str(event_id):

                    jogo_encontrado = jogo
                    break


        # -------------------------------------------------
        # SEGUNDO: procurar pelo nome
        # -------------------------------------------------

        if jogo_encontrado is None:

            for jogo in jogos_resultados:

                nome_jogo = (
                    f"{jogo.get('home_team')} vs "
                    f"{jogo.get('away_team')}"
                )

                if nome_jogo == nome_jogo_aposta:

                    jogo_encontrado = jogo
                    break


        if jogo_encontrado is None:
            continue


        # -------------------------------------------------
        # JOGO AINDA NÃO TERMINOU
        # -------------------------------------------------

        if not jogo_encontrado.get("completed"):

            continue


        scores = jogo_encontrado.get("scores")

        if not scores:

            continue


        home_team = jogo_encontrado.get(
            "home_team"
        )

        away_team = jogo_encontrado.get(
            "away_team"
        )


        home_score = None
        away_score = None


        for equipa in scores:

            if equipa.get("name") == home_team:

                home_score = int(
                    equipa.get("score")
                )

            elif equipa.get("name") == away_team:

                away_score = int(
                    equipa.get("score")
                )


        if home_score is None or away_score is None:

            continue


        # -------------------------------------------------
        # RESULTADO REAL
        # -------------------------------------------------

        if home_score > away_score:

            resultado_real = home_team

        elif away_score > home_score:

            resultado_real = away_team

        else:

            resultado_real = "Draw"


        # -------------------------------------------------
        # RESULTADO DA APOSTA
        # -------------------------------------------------

        if aposta_escolhida == resultado_real:

            estado = "GANHA"

            lucro = odd - 1.0

        else:

            estado = "PERDIDA"

            lucro = -1.0


        cursor.execute("""
            UPDATE apostas_virtuais
            SET
                estado = ?,
                lucro = ?
            WHERE id = ?
        """, (
            estado,
            lucro,
            aposta_id
        ))


        conn.commit()


        atualizadas += 1


        print("")
        print("⚽", nome_jogo_aposta)
        print(
            f"🎯 Aposta: {aposta_escolhida}"
        )
        print(
            f"📊 Resultado: "
            f"{home_score}-{away_score}"
        )
        print(
            f"➡️ {estado}"
        )
        print(
            f"💰 Lucro virtual: "
            f"€{lucro:+.2f}"
        )


    print("")
    print(
        f"✅ Apostas atualizadas: {atualizadas}"
    )


else:

    print(
        "⚠️ Não foi possível consultar resultados."
    )


# =========================================================
# 2. OBTER NOVAS ODDS
# =========================================================

print("")
print("📊 A procurar novos jogos e sinais...")


response = requests.get(
    ODDS_URL,
    params=PARAMS_ODDS,
    timeout=30
)


print(
    "Estado API odds:",
    response.status_code
)


novos_sinais = []


if response.status_code == 200:

    jogos = response.json()

    print(
        f"Jogos recebidos: {len(jogos)}"
    )


    agora = datetime.now(timezone.utc)


    # =====================================================
    # ANALISAR CADA JOGO
    # =====================================================

    for jogo in jogos:

        event_id = str(
            jogo.get("id")
        )

        home_team = jogo.get(
            "home_team"
        )

        away_team = jogo.get(
            "away_team"
        )

        commence_time = jogo.get(
            "commence_time"
        )


        if not home_team or not away_team:

            continue


        if not commence_time:

            continue


        # -------------------------------------------------
        # DATA DO JOGO
        # -------------------------------------------------

        try:

            data_jogo = datetime.fromisoformat(
                commence_time.replace(
                    "Z",
                    "+00:00"
                )
            )

        except Exception:

            continue


        # -------------------------------------------------
        # SÓ JOGOS FUTUROS
        # -------------------------------------------------

        if data_jogo <= agora:

            continue


        nome_jogo = (
            f"{home_team} vs {away_team}"
        )


        # =================================================
        # PROCURAR BETCLIC
        # =================================================

        betclic = None


        for bookmaker in jogo.get(
            "bookmakers",
            []
        ):

            titulo = bookmaker.get(
                "title",
                ""
            ).lower()


            if "betclic" in titulo:

                betclic = bookmaker
                break


        if betclic is None:

            continue


        # =================================================
        # ODDS BETCLIC
        # =================================================

        odds_betclic = {}


        for mercado in betclic.get(
            "markets",
            []
        ):

            if mercado.get("key") != "h2h":

                continue


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


                if nome and odd:

                    odds_betclic[
                        nome
                    ] = float(odd)


        # =================================================
        # ENCONTRAR MELHOR SINAL DO JOGO
        # =================================================

        candidatos = []


        for resultado, odd_betclic in odds_betclic.items():

            outras_odds = []


            for bookmaker in jogo.get(
                "bookmakers",
                []
            ):

                titulo = bookmaker.get(
                    "title",
                    ""
                ).lower()


                if "betclic" in titulo:

                    continue


                for mercado in bookmaker.get(
                    "markets",
                    []
                ):

                    if mercado.get("key") != "h2h":

                        continue


                    for outcome in mercado.get(
                        "outcomes",
                        []
                    ):

                        if outcome.get(
                            "name"
                        ) == resultado:

                            try:

                                outras_odds.append(
                                    float(
                                        outcome.get(
                                            "price"
                                        )
                                    )
                                )

                            except:

                                pass


            # ------------------------------------------------
            # PRECISAMOS DE PELO MENOS 3 CASAS
            # ------------------------------------------------

            if len(outras_odds) < 3:

                continue


            outras_odds.sort()


            # ------------------------------------------------
            # MEDIANA
            # ------------------------------------------------

            meio = len(outras_odds) // 2


            if len(outras_odds) % 2 == 0:

                consenso = (
                    outras_odds[meio - 1]
                    +
                    outras_odds[meio]
                ) / 2

            else:

                consenso = outras_odds[meio]


            if consenso <= 0:

                continue


            # ------------------------------------------------
            # VALUE
            # ------------------------------------------------

            probabilidade = 1 / consenso


            value = (
                odd_betclic
                *
                probabilidade
            ) - 1


            value_percent = value * 100


            # ------------------------------------------------
            # SCORE
            # ------------------------------------------------

            score = 50


            if value_percent >= 5:

                score += 10


            if value_percent >= 8:

                score += 10


            if value_percent >= 12:

                score += 10


            if len(outras_odds) >= 5:

                score += 10


            if len(outras_odds) >= 8:

                score += 10


            score = min(
                score,
                100
            )


            # ------------------------------------------------
            # FILTRO
            # ------------------------------------------------

            if 3 <= value_percent <= 25:

                candidatos.append({

                    "jogo": nome_jogo,

                    "aposta": resultado,

                    "odd": odd_betclic,

                    "value": value_percent,

                    "score": score,

                    "event_id": event_id,

                    "data_jogo": commence_time

                })


        # =================================================
        # ESCOLHER APENAS 1 SINAL
        # =================================================

        if candidatos:

            candidatos.sort(
                key=lambda x: (
                    x["score"],
                    x["value"]
                ),
                reverse=True
            )


            melhor = candidatos[0]


            # ------------------------------------------------
            # VERIFICAR SE JÁ EXISTE
            # ------------------------------------------------

            existe = cursor.execute("""
                SELECT COUNT(*)
                FROM apostas_virtuais
                WHERE event_id = ?
                AND aposta = ?
            """, (
                melhor["event_id"],
                melhor["aposta"]
            )).fetchone()[0]


            if existe == 0:

                # =========================================
                # GUARDAR ANÁLISE
                # =========================================

                cursor.execute("""
                    INSERT INTO analises (
                        data_hora,
                        jogo,
                        aposta,
                        odd,
                        value,
                        score
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    melhor["jogo"],
                    melhor["aposta"],
                    melhor["odd"],
                    melhor["value"],
                    melhor["score"]
                ))


                # =========================================
                # GUARDAR APOSTA VIRTUAL
                # =========================================

                cursor.execute("""
                    INSERT INTO apostas_virtuais (
                        data_hora,
                        jogo,
                        aposta,
                        odd,
                        value,
                        score,
                        estado,
                        event_id,
                        data_jogo,
                        lucro
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    melhor["jogo"],
                    melhor["aposta"],
                    melhor["odd"],
                    melhor["value"],
                    melhor["score"],
                    "PENDENTE",
                    melhor["event_id"],
                    melhor["data_jogo"],
                    None
                ))


                conn.commit()


                novos_sinais.append(
                    melhor
                )


# =========================================================
# 3. ESTATÍSTICAS
# =========================================================

ganhas = cursor.execute("""
    SELECT COUNT(*)
    FROM apostas_virtuais
    WHERE estado = 'GANHA'
""").fetchone()[0]


perdidas = cursor.execute("""
    SELECT COUNT(*)
    FROM apostas_virtuais
    WHERE estado = 'PERDIDA'
""").fetchone()[0]


pendentes = cursor.execute("""
    SELECT COUNT(*)
    FROM apostas_virtuais
    WHERE estado = 'PENDENTE'
""").fetchone()[0]


total_validas = (
    ganhas
    +
    perdidas
    +
    pendentes
)


lucro_total = cursor.execute("""
    SELECT COALESCE(
        SUM(lucro),
        0
    )
    FROM apostas_virtuais
    WHERE estado IN (
        'GANHA',
        'PERDIDA'
    )
""").fetchone()[0]


apostas_fechadas = (
    ganhas
    +
    perdidas
)


if apostas_fechadas > 0:

    taxa_acerto = (
        ganhas
        /
        apostas_fechadas
    ) * 100


    roi = (
        lucro_total
        /
        (apostas_fechadas * STAKE_VIRTUAL)
    ) * 100

else:

    taxa_acerto = 0

    roi = 0


# =========================================================
# 4. MOSTRAR ESTATÍSTICAS
# =========================================================

print("")
print("==============================================")
print("📊 BALANÇO VIRTUAL")
print("==============================================")

print(
    f"🎟️ Apostas válidas: {total_validas}"
)

print(
    f"🟢 Ganhas: {ganhas}"
)

print(
    f"🔴 Perdidas: {perdidas}"
)

print(
    f"⚪ Pendentes: {pendentes}"
)

print(
    f"🎯 Taxa de acerto: {taxa_acerto:.1f}%"
)

print(
    f"💰 Lucro virtual: €{lucro_total:.2f}"
)

print(
    f"📈 ROI: {roi:.1f}%"
)


# =========================================================
# 5. TELEGRAM
# =========================================================

mensagem = (
    "🧠 VALUE FOOTBALL BOT\n"
    "🇵🇹 LIGA PORTUGAL\n"
    "🏦 BETCLIC\n\n"
)


if novos_sinais:

    mensagem += (
        f"🔥 {len(novos_sinais)} "
        f"novo(s) sinal(is)\n\n"
    )


    for sinal in novos_sinais:

        try:

            data_formatada = datetime.fromisoformat(
                sinal["data_jogo"].replace(
                    "Z",
                    "+00:00"
                )
            ).astimezone().strftime(
                "%d/%m %H:%M"
            )

        except:

            data_formatada = "data desconhecida"


        mensagem += (
            f"⚽ {sinal['jogo']}\n"
            f"🎯 {sinal['aposta']}\n"
            f"💰 Odd: "
            f"{sinal['odd']:.2f}\n"
            f"💎 Value: "
            f"+{sinal['value']:.1f}%\n"
            f"⭐ Score: "
            f"{sinal['score']}/100\n"
            f"🗓️ {data_formatada}\n\n"
        )

else:

    mensagem += (
        "🔎 Nenhum novo sinal "
        "encontrado.\n\n"
    )


mensagem += (
    "📊 BALANÇO VIRTUAL\n"
    f"🟢 Ganhas: {ganhas}\n"
    f"🔴 Perdidas: {perdidas}\n"
    f"⚪ Pendentes: {pendentes}\n"
    f"🎯 Acerto: {taxa_acerto:.1f}%\n"
    f"💰 Lucro: €{lucro_total:.2f}\n"
    f"📈 ROI: {roi:.1f}%\n\n"
    "⚠️ MODO TESTE\n"
    "€1 virtual por sinal.\n"
    "Nenhum dinheiro real foi apostado."
)


telegram_response = enviar_telegram(
    mensagem
)


if telegram_response is not None:

    print("")
    print(
        "Telegram:",
        telegram_response.status_code
    )


    if telegram_response.status_code == 200:

        print(
            "✅ Informação enviada "
            "para o Telegram!"
        )

    else:

        print(
            "⚠️ Erro no Telegram:"
        )

        print(
            telegram_response.text
        )


# =========================================================
# FINAL
# =========================================================

conn.close()

print("")
print("==============================================")
print("🏁 BOT TERMINADO")
print("==============================================")