"""Dashboard de nível das caixas d'água (Streamlit + Firebase Realtime Database).

Arquitetura de dados:
- O histórico de cada sensor fica em memória no servidor (st.cache_resource),
  compartilhado entre todas as sessões e logins.
- A primeira consulta baixa tudo desde DATA_INICIO_HISTORICO; as seguintes
  buscam só o que é mais novo que o último timestamp já guardado.
- Uma trava de intervalo garante no máximo 1 consulta por sensor a cada
  MIN_INTERVALO_FETCH_S segundos, não importa quantas sessões estejam abertas.
- A parte de dados da tela é um fragmento que se atualiza sozinho, sem
  recarregar a página, o login nem perder os filtros.

Para adicionar um sensor (ex.: caixa d'água superior), basta preencher o
"path" da entrada correspondente em SENSORS.
"""

import os
import threading
from datetime import datetime, timedelta
from time import time
from typing import Any
from zoneinfo import ZoneInfo

import firebase_admin
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from firebase_admin import credentials, db
from google.auth.exceptions import TransportError
from plotly.subplots import make_subplots

# ============================================================
# CONFIGURAÇÃO
# ============================================================

TZ_BR = ZoneInfo("America/Sao_Paulo")
FIREBASE_APP_NAME = "app_water"
FORMATO_TS = "%Y-%m-%d %H:%M:%S"

# Histórico baixado na primeira carga
DATA_INICIO_HISTORICO = datetime(2026, 10, 4)

# Frequência de atualização automática da tela
# INTERVALO_ATUALIZACAO = "5min" # 300
INTERVALO_ATUALIZACAO = "3min"

# No máximo 1 consulta ao Firebase por sensor neste intervalo (segundos).
# Tem que ser um pouco menor que INTERVALO_ATUALIZACAO.
# MIN_INTERVALO_FETCH_S = 240
MIN_INTERVALO_FETCH_S = 140

# Filtros rápidos: nome -> dias (None = todo o período)
PILLS = {
    "Full Data": None,
    "90 dias": 90,
    "60 dias": 60,
    "30 dias": 30,
    "15 dias": 15,
    "7 dias": 7,
    "3 dias": 3,
    "1 dia": 1,
}

# Cada sensor: onde ler, como mostrar e quais linhas de referência desenhar.
# path=None => sensor ainda não conectado (aparece como "em breve").
SENSORES: dict[str, dict[str, Any]] = {
    "esp32": {
        "nome": "Água da chuva",
        "titulo": "Água da chuva :cloud_with_rain:",
        "aba": "Esp32",
        "tag": ":fire:",
        "path": "water_level/esp32_rain_water/log_data",
        # Descarta leituras com dist_mm >= este valor
        "dist_mm_max": 1000,
        "tem_media": True,
        "cor_dist": "green",
        "cor_temp": "blue",
        "cor_humi": "purple",
        "refs": [
            {"y": 360, "cor": "green", "largura": 1.5, "opacidade": 0.75},
            {"y": 650, "cor": "green", "largura": 1, "opacidade": 0.75},
            {"y": 780, "cor": "orange", "largura": 1.5, "opacidade": 0.75},
            {"y": 850, "cor": "salmon", "largura": 1.5, "opacidade": 0.75},
            {"y": 1000, "cor": "red", "largura": 1.5, "opacidade": 0.75},
        ],
        # (texto, posição "first"/"last", y)
        "anotacoes": [
            ("Max", "first", 400),
            ("Max", "last", 400),
            ("Perigo!", "last", 875),
            ("Vazia", "last", 975),
        ],
    },
    "esp8266": {
        "nome": "Cisterna",
        "titulo": "Cisterna :droplet:",
        "aba": "Esp8266",
        "tag": ":arrow_heading_down:",
        "path": "water_level/ESP8266_data/data_log",
        "dist_mm_max": None,
        "tem_media": False,
        "cor_dist": "red",
        "cor_temp": "steelblue",
        "cor_humi": "salmon",
        "refs": [
            {"y": 380, "cor": "green", "largura": 1.5, "opacidade": 1},
            {"y": 580, "cor": "orange", "largura": 1.5, "opacidade": 1},
        ],
        # Áreas sombreadas entre dois níveis (y0 e y1, em mm)
        "faixas": [
            {"y0": 600, "y1": 680, "cor": "orange", "opacidade": 0.05},
        ],
        "anotacoes": [],
    },
    "esp32_s3": {
        "nome": "Caixa D'água",
        "titulo": "Caixa D'água :shower:",
        "aba": "Esp32-S3",
        "tag": ":shower:",
        "path": None,  # <- preencher quando o sensor começar a enviar dados
        "dist_mm_max": None,
        "tem_media": False,
        "cor_dist": "teal",
        "cor_temp": "darkorange",
        "cor_humi": "goldenrod",
        "refs": [],
        "anotacoes": [],
    },
}

CONFIG_PLOTLY = {
    "responsive": True,
    "displayModeBar": True,
    "scrollZoom": False,
    "displaylogo": False,
    "toImageButtonOptions": {
        "format": "png",
        "filename": "grafico_nivel_agua",
        "height": 1200,
        "width": 1000,
        "scale": 3,
    },
}


def agora() -> datetime:
    """Horário atual de Brasília, sem fuso (os timestamps do Firebase não têm)."""
    return datetime.now(TZ_BR).replace(tzinfo=None)


# ============================================================
# FIREBASE + HISTÓRICO INCREMENTAL
# ============================================================


@st.cache_resource
def get_firebase_app():
    """Inicializa o app do Firebase uma única vez (sem arquivo em disco)."""
    if FIREBASE_APP_NAME in firebase_admin._apps:
        return firebase_admin.get_app(FIREBASE_APP_NAME)

    config = {
        "type": st.secrets["FIREBASE_TYPE"],
        "project_id": st.secrets["FIREBASE_PROJECT_ID"],
        "private_key_id": st.secrets["FIREBASE_PRIVATE_KEY_ID"],
        "private_key": st.secrets["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
        "client_email": st.secrets["FIREBASE_CLIENT_EMAIL"],
        "client_id": st.secrets["FIREBASE_CLIENT_ID"],
        "auth_uri": st.secrets["FIREBASE_AUTH_URI"],
        "token_uri": st.secrets["FIREBASE_TOKEN_URI"],
        "auth_provider_x509_cert_url": st.secrets["FIREBASE_AUTH_PROVIDER_CERT_URL"],
        "client_x509_cert_url": st.secrets["FIREBASE_CLIENT_CERT_URL"],
    }
    return firebase_admin.initialize_app(
        credentials.Certificate(config),
        {"databaseURL": st.secrets["FIREBASE_DATABASE_URL"]},
        name=FIREBASE_APP_NAME,
    )


@st.cache_resource
def get_store() -> dict[str, Any]:
    """Armazém compartilhado entre todas as sessões (vive até o app reiniciar)."""
    return {"lock": threading.Lock(), "sensores": {}}


def _estado_vazio() -> dict[str, Any]:
    return {
        "df": pd.DataFrame(),
        "ultima_consulta": 0.0,   # epoch da última consulta bem-sucedida
        "ultima_duracao": 0.0,    # segundos que a última consulta levou
        "ultimos_novos": 0,       # linhas novas na última consulta
        "baixados_total": 0,      # registros baixados desde o início do app
    }


def _registros_para_df(data: Any) -> pd.DataFrame:
    if not data:
        return pd.DataFrame()
    if isinstance(data, dict):
        registros = list(data.values())
    else:  # o Firebase devolve lista quando as chaves são inteiros sequenciais
        registros = [r for r in data if r]
    df = pd.DataFrame(registros)
    if df.empty or "timestamp" not in df.columns:
        return pd.DataFrame()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def atualizar_sensor(path: str, forcar: bool = False) -> pd.DataFrame:
    """Devolve o histórico do sensor, baixando só o que é novo.

    O DataFrame devolvido é compartilhado: não altere as colunas dele
    (filtros que criam um novo DataFrame são seguros).
    """
    store = get_store()
    with store["lock"]:
        s = store["sensores"].setdefault(path, _estado_vazio())
        df = s["df"]

        recente = (time() - s["ultima_consulta"]) < MIN_INTERVALO_FETCH_S
        if not df.empty and recente and not forcar:
            return df

        if df.empty:
            inicio = DATA_INICIO_HISTORICO
        else:
            inicio = df["timestamp"].max().to_pydatetime()

        t0 = time()
        data = (
            db.reference(path, app=get_firebase_app())
            .order_by_child("timestamp")
            .start_at(inicio.strftime(FORMATO_TS))
            .get()
        )
        s["ultima_duracao"] = time() - t0

        novos = _registros_para_df(data)
        linhas_antes = len(df)
        if not novos.empty:
            combinado = novos if df.empty else pd.concat([df, novos], ignore_index=True)
            # start_at é inclusivo: o último ponto já guardado volta repetido
            s["df"] = (
                combinado.drop_duplicates(subset="timestamp", keep="last")
                .sort_values("timestamp")
                .reset_index(drop=True)
            )
            s["baixados_total"] += len(novos)

        s["ultimos_novos"] = len(s["df"]) - linhas_antes
        s["ultima_consulta"] = time()
        return s["df"]


def obter_df(path: str, forcar: bool = False) -> tuple[pd.DataFrame, str | None]:
    """Como atualizar_sensor, mas se a conexão cair devolve o que já está em memória."""
    try:
        return atualizar_sensor(path, forcar), None
    except TransportError:
        guardado = get_store()["sensores"].get(path, {}).get("df")
        if guardado is None or guardado.empty:
            raise
        return guardado, "Conexão com o Firebase interrompida: exibindo dados já carregados."


def limpar(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Mantém só leituras válidas (status Success e dist_mm abaixo do limite)."""
    if df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    for col in ("statusDist", "statusTempHumd"):
        if col in df.columns:
            mask &= df[col] == "Success"
    limite = cfg.get("dist_mm_max")
    if limite is not None and "dist_mm" in df.columns:
        mask &= df["dist_mm"] < limite
    return df[mask]


# ============================================================
# FIGURAS
# ============================================================


def criar_fig_dados(
    dfs: dict[str, pd.DataFrame], mostrar_media: bool
) -> go.Figure:
    """Uma linha de distância por sensor ativo + temperatura + umidade."""
    ativos = [(k, SENSORES[k]) for k in dfs]
    n_dist = len(ativos)
    linha_temp = n_dist + 1
    linha_humi = n_dist + 2

    fig = make_subplots(
        rows=n_dist + 2, cols=1, shared_xaxes=True, vertical_spacing=0.06
    )

    for i, (key, cfg) in enumerate(ativos, start=1):
        df = dfs[key]

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["dist"],
                mode="lines",
                line=dict(shape="hv", width=2, color=cfg["cor_dist"]),
                opacity=0.65,
                name=f"Distância {cfg['nome']}",
            ),
            row=i,
            col=1,
        )

        if mostrar_media and cfg["tem_media"] and "dist_mm" in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"],
                    y=df["dist_mm"],
                    mode="lines",
                    line=dict(width=1.5, color="red"),
                    name=f"Média {cfg['nome']}",
                ),
                row=i,
                col=1,
            )

        for ref in cfg["refs"]:
            fig.add_hline(
                y=ref["y"],
                line_color=ref["cor"],
                line_width=ref["largura"],
                opacity=ref["opacidade"],
                line_dash="dash",
                row=i,  # pyright: ignore[reportArgumentType]
                col=1,  # pyright: ignore[reportArgumentType]
            )

        for faixa in cfg.get("faixas", []):
            fig.add_hrect(
                y0=faixa["y0"],
                y1=faixa["y1"],
                fillcolor=faixa["cor"],
                opacity=faixa["opacidade"],
                line_width=0,
                layer="below",
                row=i,  # pyright: ignore[reportArgumentType]
                col=1,  # pyright: ignore[reportArgumentType]
            )

        if not df.empty:
            for texto, posicao, y in cfg["anotacoes"]:
                x = df["timestamp"].iloc[0 if posicao == "first" else -1]
                fig.add_annotation(
                    text=texto, x=x, y=y, showarrow=False, row=i, col=1
                )

        fig.update_yaxes(
            title_text="Distância (mm)", autorange="reversed", row=i, col=1
        )

    for key, cfg in ativos:
        df = dfs[key]
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["tempC"],
                mode="lines",
                line=dict(width=1.0, color=cfg["cor_temp"]),
                name=f"Temp. {cfg['nome']}",
            ),
            row=linha_temp,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["humi"],
                mode="lines",
                line=dict(width=1, color=cfg["cor_humi"]),
                name=f"Umidade {cfg['nome']}",
            ),
            row=linha_humi,
            col=1,
        )

    fig.update_yaxes(title_text="Temperatura (°C)", row=linha_temp, col=1)
    fig.update_yaxes(title_text="Umidade (%)", row=linha_humi, col=1)

    # Linha vertical do horário atual, uma vez só, em todos os subplots
    fig.add_vline(
        x=agora(),
        line_color="gray",
        line_width=1.0,
        line_dash="dash",
        row="all",  # pyright: ignore[reportArgumentType]
        col="all",  # pyright: ignore[reportArgumentType]
    )

    fig.update_xaxes(title_text=None, showticklabels=True)
    fig.update_layout(
        height=312 * (n_dist + 2),
        hovermode="x",
        margin=dict(l=70, r=30, t=120, b=50),
        legend=dict(
            orientation="h",
            x=0.5,
            y=1.02,
            xanchor="center",
            yanchor="bottom",
            font=dict(size=12),
            bordercolor="gray",
            borderwidth=1,
        ),
    )
    return fig


def criar_fig_raw(df: pd.DataFrame) -> go.Figure:
    """Gráfico dos dados brutos (sem filtro): distância, mmCounter e temperatura."""
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06)

    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["dist"],
            mode="lines",
            line=dict(width=2),
            opacity=0.65,
            name="Distância",
        ),
        row=1,
        col=1,
    )
    fig.update_yaxes(title_text="Distância", autorange="reversed", row=1, col=1)

    if "mmCounter" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["mmCounter"],
                mode="lines",
                line=dict(color="red", width=1),
                name="mmCounter",
            ),
            row=2,
            col=1,
        )
    fig.update_yaxes(title_text="mmCounter", row=2, col=1)

    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["tempC"],
            mode="lines",
            line=dict(width=1),
            name="Temperatura",
        ),
        row=3,
        col=1,
    )
    fig.update_yaxes(title_text="Temperatura (°C)", row=3, col=1)

    fig.add_vline(
        x=agora(),
        line_color="gray",
        line_width=1.5,
        line_dash="dash",
        row="all",  # pyright: ignore[reportArgumentType]
        col="all",  # pyright: ignore[reportArgumentType]
    )

    fig.update_xaxes(title_text=None, showticklabels=True)
    fig.update_layout(
        height=700,
        hovermode="x",
        margin=dict(l=70, r=30, t=120, b=50),
        legend=dict(
            orientation="h",
            x=0.5,
            y=1.02,
            xanchor="center",
            yanchor="bottom",
            font=dict(size=12),
            bordercolor="gray",
            borderwidth=1,
        ),
    )
    return fig


# ============================================================
# COMPONENTES DE INTERFACE
# ============================================================

CSS_METRICAS = """
<style>
    [data-testid="stMetricValue"] { font-size: 20px !important; }
</style>
"""


def _fmt(valor: float, unidade: str) -> str:
    return f"{valor:.1f}{unidade}".replace(".", ",")


def mostrar_metricas(cfg: dict[str, Any], df: pd.DataFrame) -> None:
    st.markdown(cfg["titulo"])

    if cfg["path"] is None:
        st.caption("Em breve")
        return
    if df.empty:
        st.warning("Sem leituras válidas.")
        return

    ultimo = df.iloc[-1]
    tag = cfg["tag"]

    st.metric(
        label=f"Distância {tag} :straight_ruler:",
        value=_fmt(float(ultimo["dist"]) * 0.1, " cm"),
        border=True,
    )
    st.metric(
        label=f"Temperatura {tag} :thermometer:",
        value=_fmt(float(ultimo["tempC"]), "°C"),
        border=True,
    )
    st.metric(
        label=f"Umidade {tag} :sweat_drops:",
        value=_fmt(float(ultimo["humi"]), "%"),
        border=True,
    )

    ts = ultimo["timestamp"]
    atraso = agora() - ts
    cor = "green" if atraso <= timedelta(minutes=10) else "red"
    st.metric(
        label=f"Última atualização {tag} :calendar:",
        value=ts.strftime("%d/%m/%Y\n\n%H:%M:%S"),
        delta=f"{int(atraso.total_seconds() // 60)} min "
        f"{int(atraso.total_seconds() % 60)} s",
        delta_color=cor,
        border=True,
    )


def mostrar_resumo_consultas() -> None:
    """Quanto o último ciclo de consulta ao Firebase custou (útil no plano free)."""
    store = get_store()
    linhas = []
    for cfg in SENSORES.values():
        s = store["sensores"].get(cfg["path"]) if cfg["path"] else None
        if s and s["ultima_consulta"]:
            hora = datetime.fromtimestamp(s["ultima_consulta"], TZ_BR)
            linhas.append(
                f"**{cfg['nome']}**: consulta às {hora:%H:%M:%S}, "
                f"{s['ultimos_novos']} novos, {s['ultima_duracao']:.2f} s"
            )
    if linhas:
        st.info("Firebase\n\n" + "\n\n".join(linhas))


def mostrar_contagem(nome: str, df: pd.DataFrame) -> None:
    if not df.empty and "timestamp" in df.columns:
        st.warning(
            f"**{nome}**: {len(df)} pontos \n\n"
            f"{df['timestamp'].min():%d/%m/%Y %H:%M} até "
            f"{df['timestamp'].max():%d/%m/%Y %H:%M}"
        )
    else:
        st.warning(f"{nome}: database sem dados")


# ============================================================
# PAINEL (fragmento que se atualiza sozinho)
# ============================================================


@st.fragment(run_every=INTERVALO_ATUALIZACAO)
def painel() -> None:
    st.markdown(CSS_METRICAS, unsafe_allow_html=True)

    forcar = st.button("Atualizar agora", icon="🔄")

    # ---- Carga incremental ----
    ativos = {k: c for k, c in SENSORES.items() if c["path"]}
    brutos: dict[str, pd.DataFrame] = {}
    avisos: list[str] = []
    try:
        for key, cfg in ativos.items():
            brutos[key], aviso = obter_df(cfg["path"], forcar)
            if aviso and aviso not in avisos:
                avisos.append(aviso)
    except TransportError:
        st.warning("Conexão com Firebase interrompida.")
        if st.button("Reconectar Firebase", type="primary"):
            st.rerun()
        return

    for aviso in avisos:
        st.warning(aviso)

    validos = {k: limpar(brutos[k], ativos[k]) for k in ativos}
    com_dados = [df for df in validos.values() if not df.empty]
    if not com_dados:
        st.warning("Nenhuma leitura válida encontrada.")
        return

    # ---- Filtros (pills + slider) ----
    # Limites do slider alinhados em dias: ficam estáveis entre as atualizações
    # automáticas, então o intervalo escolhido pelo usuário não é resetado.
    min_dt = (
        min(df["timestamp"].min() for df in com_dados)
        .to_pydatetime()
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    max_dt = (agora() + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    def aplicar_pill() -> None:
        dias = PILLS.get(st.session_state.get("filtro_pill") or "Full Data")
        ini = min_dt if dias is None else max(min_dt, agora() - timedelta(days=dias))
        st.session_state["slider_datas"] = (ini, max_dt)

    if "slider_datas" not in st.session_state:
        st.session_state["slider_datas"] = (min_dt, max_dt)
    ini, fim = st.session_state["slider_datas"]
    st.session_state["slider_datas"] = (
        min(max(ini, min_dt), max_dt),
        min(max(fim, min_dt), max_dt),
    )

    selecao = st.pills(
        "Filtro:",
        list(PILLS),
        selection_mode="single",
        key="filtro_pill",
        on_change=aplicar_pill,
    )
    if selecao is None:
        st.markdown("Nenhum filtro selecionado, mostrando todos os dados.")
    else:
        st.markdown(f"Você selecionou os últimos: {selecao}.")

    start_date, end_date = st.slider(
        "Filtro de datas:",
        min_value=min_dt,
        max_value=max_dt,
        format="DD/MM/YY",
        step=timedelta(days=1),
        key="slider_datas",
    )

    mostrar_media = st.checkbox("Mostrar Média", value=False, key="show_mean")

    filtrados = {
        k: df[(df["timestamp"] >= start_date) & (df["timestamp"] <= end_date)]
        for k, df in validos.items()
    }
    fig_dados = criar_fig_dados(filtrados, mostrar_media)

    # ---- Abas ----
    abas = st.tabs(
        [":chart_with_upwards_trend: Dados", ":gear: Configurações"]
        + [c["aba"] for c in SENSORES.values()]
    )

    with abas[0]:
        col_info, col_graf = st.columns([0.35, 0.65])

        with col_info:
            st.markdown("### Firebase")
            colunas = st.columns(len(SENSORES))
            for coluna, (key, cfg) in zip(colunas, SENSORES.items()):
                with coluna:
                    mostrar_metricas(cfg, validos.get(key, pd.DataFrame()))

            mostrar_resumo_consultas()

            for key, cfg in ativos.items():
                mostrar_contagem(cfg["nome"], filtrados[key])

        with col_graf:
            st.plotly_chart(
                fig_dados, theme=None, width="stretch", config=CONFIG_PLOTLY
            )

    with abas[1]:
        with st.expander("Uso do Firebase"):
            store = get_store()
            for cfg in ativos.values():
                s = store["sensores"].get(cfg["path"])
                if s:
                    st.text(
                        f"{cfg['nome']}: {len(s['df'])} registros em memória, "
                        f"{s['baixados_total']} baixados desde que o app iniciou"
                    )
            st.text(f"Atualização automática: a cada {INTERVALO_ATUALIZACAO}")

    for aba, (key, cfg) in zip(abas[2:], SENSORES.items()):
        with aba:
            st.markdown(f"#### Firebase {cfg['aba']}")
            if cfg["path"] is None:
                st.info("Sensor ainda não conectado.")
                continue
            bruto = brutos[key]
            if bruto.empty:
                st.info("Sem dados.")
                continue
            c1, c2 = st.columns(2)
            with c1:
                st.dataframe(
                    bruto.sort_values(by="timestamp", ascending=False),
                    hide_index=True,
                    width=1500,
                    height=500,
                )
            with c2:
                st.plotly_chart(criar_fig_raw(bruto), theme=None, width="stretch")


# ============================================================
# LOGIN E MAIN
# ============================================================


def check_login() -> bool:
    """Tela simples de autenticação."""

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    _, col_login, _ = st.columns([1, 1, 1])

    with col_login:
        st.subheader("🔐 Acesso ao Sistema")

        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")

            if st.form_submit_button("Entrar"):
                if (
                    username == st.secrets["LOGIN_USER"]
                    and password == st.secrets["LOGIN_PASSWORD"]
                ):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

    return False


def main() -> None:
    st.set_page_config(
        page_title="Automação Caixas D'água",
        page_icon="💧",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Autenticar antes de carregar qualquer dado
    if not check_login():
        st.stop()

    if st.sidebar.button("Sair"):
        st.session_state.authenticated = False
        st.rerun()

    painel()


if __name__ == "__main__":
    if os.name == "nt":
        os.system("cls")
    main()
