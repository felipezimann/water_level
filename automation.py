import os.path
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from time import time
from typing import Any, cast
from plotly.subplots import make_subplots
from datetime import datetime
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, db

from google.auth.exceptions import TransportError

# Gerar o conteúdo do JSON para o Firebase
firebase_config = {
    "type": st.secrets["FIREBASE_TYPE"],
    "project_id": st.secrets["FIREBASE_PROJECT_ID"],
    "private_key_id": st.secrets["FIREBASE_PRIVATE_KEY_ID"],
    # Corrigir quebras de linha
    "private_key": st.secrets["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": st.secrets["FIREBASE_CLIENT_EMAIL"],
    "client_id": st.secrets["FIREBASE_CLIENT_ID"],
    "auth_uri": st.secrets["FIREBASE_AUTH_URI"],
    "token_uri": st.secrets["FIREBASE_TOKEN_URI"],
    "auth_provider_x509_cert_url": st.secrets["FIREBASE_AUTH_PROVIDER_CERT_URL"],
    "client_x509_cert_url": st.secrets["FIREBASE_CLIENT_CERT_URL"]
}

TZ_BR = ZoneInfo("America/Sao_Paulo")

# Escrever o JSON em um arquivo temporário
with open("firebase_credentials_temp.json", "w") as f:
    json.dump(firebase_config, f)


@st.cache_data(ttl=300)  # 5min
def ReadDataFirebase(sensor_path):

    print(firebase_admin._apps.keys())  # Deve mostrar os aplicativos restantes
    # # st.markdown(firebase_admin._apps.keys())

    # # Fechar todos os aplicativos
    # for app in list(firebase_admin._apps.values()):
    #     firebase_admin.delete_app(app)

    # # Verificar se todos os aplicativos foram fechados
    # print(firebase_admin._apps.keys())  # Deve estar vazio
    # # st.markdown(firebase_admin._apps.keys())

    # # Carregar credenciais do Firebase
    # cred = credentials.Certificate("firebase_credentials_temp.json")
    # databaseURL_firebase = st.secrets["FIREBASE_DATABASE_URL"]

    # app = firebase_admin.initialize_app(
    #     cred, {"databaseURL": databaseURL_firebase}, name='app_water')

    if "app_water" in firebase_admin._apps:
        app = firebase_admin.get_app("app_water")
    else:
        cred = credentials.Certificate("firebase_credentials_temp.json")
        databaseURL_firebase = st.secrets["FIREBASE_DATABASE_URL"]

        app = firebase_admin.initialize_app(
            cred,
            {"databaseURL": databaseURL_firebase},
            name="app_water"
        )

    # received_data = db.reference(path="/", app=app).get()
    # received_data = db.reference(path=sensor_path, app=app).get() # obter todos os dados

    ref = db.reference(sensor_path, app=app)
    # num_records = 1000
    # received_data = ref.order_by_key().limit_to_last(num_records).get()

    timestamp_inicio = datetime(2026, 10, 4)
    timestamp_fim = datetime.now(TZ_BR).replace(tzinfo=None)

    timestamp_inicio = timestamp_inicio.strftime("%Y-%m-%d %H:%M:%S")
    timestamp_fim = timestamp_fim.strftime("%Y-%m-%d %H:%M:%S")

    received_data = (
        ref
        .order_by_child("timestamp")
        .start_at(timestamp_inicio)
        .end_at(timestamp_fim)
        .get()
    )

    if received_data is None:
        return pd.DataFrame()

    # print(received_data)

    received_data = cast(dict[str, Any], received_data)

    records = list(received_data.values())

    # Convertendo para DataFrame
    df = pd.DataFrame(records)

    # Exibindo o DataFrame resultante
    # print(df)

    return df


def CreateFigDataFiltered(df_firebase, df_firebase_esp8266):

    # Checkbox para habilitar/desabilitar a curva "Média"
    show_mean = st.checkbox(
        "Mostrar Média",
        value=False,
        key="show_mean"
    )

    # ============================================================
    # CRIAR FIGURA 3 x 1
    # ============================================================

    fig_filtered = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        # subplot_titles=(
        #     "Distância",
        #     "Temperatura",
        #     "Umidade",
        # ),
    )

    # ============================================================
    # 1 - DISTÂNCIA + MÉDIA
    # ============================================================

    # Distância Firebase
    fig_filtered.add_trace(
        go.Scatter(
            x=df_firebase["timestamp"],
            y=df_firebase["dist"],
            mode="lines",
            line=dict(
                shape="hv",
                width=2,
                color="green",
            ),
            opacity=0.65,
            name="Distância Firebase",
        ),
        row=1,
        col=1,
    )

    # Linha vertical indicando o horário atual

    agora = datetime.now(TZ_BR).replace(tzinfo=None)

    fig_filtered.add_vline(
        x=agora,
        line_color="gray",
        line_width=1.5,
        line_dash="dash",
    )

    # Média Firebase
    if show_mean:
        fig_filtered.add_trace(
            go.Scatter(
                x=df_firebase["timestamp"],
                y=df_firebase["dist_mm"],
                mode="lines",
                line=dict(
                    width=1.5,
                    color="red",
                ),
                opacity=1,
                name="Média Firebase",
            ),
            row=1,
            col=1,
        )

    # =====================================================

    # Linhas de referência
    fig_filtered.add_hline(
        y=360,
        line_color="green",
        line_width=1.5,
        line_dash="dash",
    )

    fig_filtered.add_hline(
        y=650,
        line_color="green",
        line_width=1,
        opacity=0.75,
        line_dash="dash",
    )

    fig_filtered.add_hline(
        y=780,
        line_color="orange",
        line_width=1.5,
        opacity=0.75,
        line_dash="dash",
    )

    fig_filtered.add_hline(
        y=850,
        line_color="salmon",
        line_width=1.5,
        line_dash="dash",
    )

    fig_filtered.add_hline(
        y=1000,
        line_color="red",
        line_width=1.5,
        line_dash="dash",
    )

    # Anotações
    fig_filtered.add_annotation(
        text="Max",
        x=df_firebase["timestamp"].iloc[1],
        y=400,
        showarrow=False,
        row=1,
        col=1,
    )

    fig_filtered.add_annotation(
        text="Max",
        x=df_firebase["timestamp"].iloc[-1],
        y=400,
        showarrow=False,
        row=1,
        col=1,
    )

    fig_filtered.add_annotation(
        text="Perigo!",
        x=df_firebase["timestamp"].iloc[-1],
        y=875,
        showarrow=False,
        row=1,
        col=1,
    )

    fig_filtered.add_annotation(
        text="Vazia",
        x=df_firebase["timestamp"].iloc[-1],
        y=975,
        showarrow=False,
        row=1,
        col=1,
    )

    # Eixo Y invertido
    fig_filtered.update_yaxes(
        title_text="Distância (mm)",
        autorange="reversed",
        row=1,
        col=1,
    )

    # =====================================================
    # Plot 2 - esp8266 Firebase
    # =====================================================
    # fig_filtered.add_trace(
    #     go.Scatter(
    #         x=df_firebase_esp8266["timestamp"],
    #         y=df_firebase_esp8266["dist"],
    #         mode="lines",
    #         line=dict(
    #             width=1.5,
    #             color="red",
    #         ),
    #         opacity=1,
    #         name="TESTE esp8266 Firebase",
    #     ),
    #     row=1,
    #     col=1,
    # )
    fig_filtered.add_trace(
        go.Scatter(
            x=df_firebase_esp8266["timestamp"],
            y=df_firebase_esp8266["dist"],
            mode="lines",
            name="Distância ESP8266",
            line=dict(
                shape="hv",
                color="red",
                width=2,
            ),
        ),
        row=2,
        col=1,
    )
    # Linha vertical indicando o horário atual

    agora2 = datetime.now(TZ_BR).replace(tzinfo=None)

    fig_filtered.add_vline(
        x=agora2,
        line_color="gray",
        line_width=1.0,
        line_dash="dash",
    )

    # Linhas de referência
    fig_filtered.add_hline(
        y=380,
        line_color="green",
        line_width=1.5,
        line_dash="dash",
        row=2,  # pyright: ignore[reportArgumentType]
        col=1,  # pyright: ignore[reportArgumentType]
    )
    # Linhas de referência
    fig_filtered.add_hline(
        y=620,
        line_color="orange",
        line_width=1.5,
        line_dash="dash",
        row=2,  # pyright: ignore[reportArgumentType]
        col=1,  # pyright: ignore[reportArgumentType]
    )

    # Eixo Y invertido
    fig_filtered.update_yaxes(
        title_text="Distância (mm)",
        autorange="reversed",
        row=2,
        col=1,
    )
    # =====================================================
    # teste
    # =====================================================

    # ============================================================
    # 3 - TEMPERATURA
    # ============================================================

    fig_filtered.add_trace(
        go.Scatter(
            x=df_firebase["timestamp"],
            y=df_firebase["tempC"],
            mode="lines",
            name="Temperatura",
            line=dict(
                color="blue",
                width=1,
            ),
        ),
        row=3,
        col=1,
    )
    # df_firebase_esp8266: tempC
    fig_filtered.add_trace(
        go.Scatter(
            x=df_firebase_esp8266["timestamp"],
            y=df_firebase_esp8266["tempC"],
            mode="lines",
            line=dict(
                # shape="hv",
                width=2,
                color="steelblue",
            ),
            opacity=0.65,
            name="Temp. ESP8266",
        ),
        row=3,
        col=1,
    )
    fig_filtered.add_vline(
        x=agora2,
        line_color="gray",
        line_width=1.0,
        line_dash="dash",
    )

    fig_filtered.update_yaxes(
        title_text="Temperatura (°C)",
        row=3,
        col=1,
    )

    # ============================================================
    # 4 - UMIDADE
    # ============================================================

    fig_filtered.add_trace(
        go.Scatter(
            x=df_firebase["timestamp"],
            y=df_firebase["humi"],
            mode="lines",
            name="Umidade",
            line=dict(
                color="purple",
                width=1,
            ),
        ),
        row=4,
        col=1,
    )

    fig_filtered.add_trace(
        go.Scatter(
            x=df_firebase_esp8266["timestamp"],
            y=df_firebase_esp8266["humi"],
            mode="lines",
            name="Umidade ESP8266",
            line=dict(
                color="salmon",
                width=1,
            ),
        ),
        row=4,
        col=1,
    )

    fig_filtered.add_vline(
        x=agora2,
        line_color="gray",
        line_width=1.0,
        line_dash="dash",
    )

    fig_filtered.update_yaxes(
        title_text="Umidade (%)",
        row=4,
        col=1,
    )

    # ============================================================
    # EIXOS X
    # ============================================================

    fig_filtered.update_xaxes(
        title_text=None,
        row=1,
        col=1,
    )

    fig_filtered.update_xaxes(
        title_text=None,
        row=2,
        col=1,
    )

    fig_filtered.update_xaxes(
        title_text=None,
        row=3,
        col=1,
    )

    fig_filtered.update_xaxes(
        title_text=None,
        row=4,
        col=1,
    )

    # Mostrar ticklabels do eixo X em todos os subplots
    fig_filtered.update_xaxes(
        showticklabels=True,
    )

    # ============================================================
    # LAYOUT GERAL
    # ============================================================

    fig_filtered.update_layout(
        height=1250,
        hovermode="x",
        margin=dict(
            l=70,
            r=30,
            t=120,
            b=50,
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            y=1.02,
            xanchor="center",
            yanchor="bottom",
            font=dict(size=12),
            bordercolor="gray",
            borderwidth=1,
        )
    )

    return fig_filtered


def CreateFigDataFiltered_backup(df_firebase):

    # Checkbox para habilitar/desabilitar a curva "Distance"
    show_mean = st.checkbox("Mostrar Média", value=False, key="show_mean")
    # show_Gsheets = st.checkbox(
    #     "Mostrar Gsheets", value=False, key="show_Gsheets")

    # Criar o gráfico de degraus usando plotly.graph_objects
    fig_filtered = go.Figure()

    # if show_Gsheets:
    #     fig_filtered.add_trace(
    #         go.Scatter(
    #             x=df_filtered["Date"],
    #             y=df_filtered["Distance"],
    #             mode="lines+markers",  # Modo linhas
    #             # line=dict(shape="hv"),  # 'hv' cria o efeito de degraus
    #             line=dict(
    #                 shape="hv",  # Estilo de degraus
    #                 # Espessura da linha (ajuste conforme necessário)
    #                 width=1,
    #                 color="blue",  # Cor da linha (opcional)
    #             ),
    #             marker=dict(
    #                 # Tamanho dos marcadores (ajuste conforme necessário)
    #                 size=4,
    #                 # Cor dos marcadores (opcional, pode ser diferente da linha)
    #                 color="blue"
    #             ),
    #             name="Distance",
    #             opacity=0.65
    #         )
    #     )

    # fig_filtered = px.line(
    #     data_frame=df_filtered,
    #     x="Date",
    #     y=["Distance"],
    #     markers=False,
    #     height=500,
    # )

    # Adicionar mais séries, se necessário
    fig_filtered.add_trace(
        go.Scatter(
            x=df_firebase["timestamp"],
            y=df_firebase["dist"],
            # mode="lines",
            # line=dict(color="orange", dash="solid"),
            mode="lines",  # Modo linhas ou "lines+markers"
            # line=dict(shape="hv"),  # 'hv' cria o efeito de degraus
            line=dict(
                shape="hv",  # Estilo de degraus
                width=2,     # Espessura da linha (ajuste conforme necessário)
                color="green",  # Cor da linha (opcional)
            ),
            marker=dict(
                # Tamanho dos marcadores (ajuste conforme necessário)
                size=4,
                # Cor dos marcadores (opcional, pode ser diferente da linha)
                color="green"
            ),
            opacity=0.65,
            name="Distância Firebase",
        )
    )

    # Adicionar mais séries, se necessário
    if show_mean:
        fig_filtered.add_trace(
            go.Scatter(
                x=df_firebase["timestamp"],
                y=df_firebase["dist_mm"],
                mode="lines",
                # line=dict(color="red", dash="solid"),
                # mode="lines+markers",  # Modo linhas
                # line=dict(shape="hv"),  # 'hv' cria o efeito de degraus
                line=dict(
                    # shape="hv",  # Estilo de degraus
                    # Espessura da linha (ajuste conforme necessário)
                    width=1.5,
                    color="red",  # Cor da linha (opcional)
                ),
                marker=dict(
                    # Tamanho dos marcadores (ajuste conforme necessário)
                    size=4,
                    # Cor dos marcadores (opcional, pode ser diferente da linha)
                    color="red"
                ),
                opacity=1,
                name="Média Firebase",
            )
        )

    fig_filtered.update_layout(  # customize font and legend orientation & position
        xaxis_title=None,
        yaxis_title="Distância (mm)",
        legend=dict(
            title=None,
            orientation="h",
            y=1.00, yanchor="bottom",
            x=0.98, xanchor="right",
        )
    )
    fig_filtered.update_yaxes(autorange='reversed')

    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="green",  # "salmon",
        line_width=1.5, opacity=1, line_dash="dash",
        x0=df_firebase["timestamp"].iloc[0],
        x1=df_firebase["timestamp"].iloc[-1],
        y0=360,
        y1=360,
        yref="y"
    )
    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="green",  # "salmon",
        line_width=1, opacity=0.75, line_dash="dash",
        x0=df_firebase["timestamp"].iloc[0],
        x1=df_firebase["timestamp"].iloc[-1],
        y0=650,
        y1=650,
        yref="y"
    )
    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="orange",  # "salmon",
        line_width=1.5, opacity=0.75, line_dash="dash",
        x0=df_firebase["timestamp"].iloc[0],
        x1=df_firebase["timestamp"].iloc[-1],
        y0=780,
        y1=780,
        yref="y"
    )
    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="salmon",  # "salmon",
        line_width=1.5, opacity=0.75, line_dash="dash",
        x0=df_firebase["timestamp"].iloc[0],
        x1=df_firebase["timestamp"].iloc[-1],
        y0=850,
        y1=850,
        yref="y"
    )
    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="red",  # "salmon",
        line_width=1.5, opacity=0.75, line_dash="dash",
        x0=df_firebase["timestamp"].iloc[0],
        x1=df_firebase["timestamp"].iloc[-1],
        y0=1000,
        y1=1000,
        yref="y"
    )

    fig_filtered.add_annotation(  # add a text callout with arrow
        text="Max", x=df_firebase["timestamp"].iloc[1],
        y=500,
        arrowhead=2,
        showarrow=False
    )
    fig_filtered.add_annotation(  # add a text callout with arrow
        text="Max", x=df_firebase["timestamp"].iloc[-1],
        y=500,
        arrowhead=2,
        showarrow=False
    )

    fig_filtered.add_annotation(  # add a text callout with arrow
        text="Perigo!", x=df_firebase["timestamp"].iloc[-1],
        y=925,
        arrowhead=2,
        showarrow=False
    )
    fig_filtered.add_annotation(  # add a text callout with arrow
        text="Vazia", x=df_firebase["timestamp"].iloc[-1],
        y=1025,
        arrowhead=2,
        showarrow=False
    )

    # Create figure temperature and humidity

    # fig_temp = px.line(
    #    df_filtered,
    #    x="Date",
    #    y=["Temperature" , "Humidity"],
    #    markers=True,
    #    title='Temperatura',
    #    height=600,
    #    color_discrete_sequence=["red", "green"] # This parameter do the trick.
    # )

    # fig_temp = px.line(
    #     df_filtered,
    #     x="Date",
    #     y=["Temperature"],
    #     markers=False,
    #     height=400,
    #     color_discrete_sequence=["red"]  # This parameter do the trick.
    # )
    # fig_temp.update_layout(  # customize font and legend orientation & position
    #     xaxis_title=None,
    #     yaxis_title="Temperatura (°C)",
    #     legend=dict(
    #         title=None,
    #         orientation="h",
    #         y=1.00, yanchor="bottom",
    #         x=0.98, xanchor="right"
    #     )
    # )

    # fig_humd = px.line(
    #     df_filtered,
    #     x="Date",
    #     y=["Humidity"],
    #     markers=False,
    #     height=400,
    #     color_discrete_sequence=["green"],  # This parameter do the trick.
    # )
    # fig_humd.update_layout(  # customize font and legend orientation & position
    #     xaxis_title=None,
    #     yaxis_title="Umidade (%)",
    #     legend=dict(
    #         title=None,
    #         orientation="h",
    #         y=1.00, yanchor="bottom",
    #         x=0.98, xanchor="right"
    #     )
    # )

    # Criar o gráfico inicial com a primeira série (eixo y principal)
    fig_temp_humd = go.Figure()

    fig_temp_humd.add_trace(
        go.Scatter(
            x=df_firebase["timestamp"],
            y=df_firebase["tempC"],
            mode="lines",
            name="Temperatura",
            line=dict(color="blue"),
            line_width=1.0,
        )
    )

    # Adicionar outra série ao eixo y secundário
    fig_temp_humd.add_trace(
        go.Scatter(
            x=df_firebase["timestamp"],
            y=df_firebase["humi"],
            mode="lines",
            name="Umidade",
            line=dict(color="red"),  # , dict(color="red", dash="dot")
            line_width=1.0,
            yaxis="y2",  # Associar ao eixo y secundário
        )
    )

    # Configurar o layout para o eixo y secundário
    fig_temp_humd.update_layout(
        xaxis=dict(
            title=None,              # Título do eixo X
            showgrid=True,             # Habilita as grades verticais
            gridcolor="LightGray",     # Cor das linhas da grade
            gridwidth=1,               # Espessura das linhas da grade
        ),
        yaxis=dict(
            title=dict(
                text="Temperatura (°C)",
                font=dict(
                    size=14
                ),
                # titlefont=dict(color="black"),
                # tickfont=dict(color="black"),
            ),
        ),
        yaxis2=dict(
            title=dict(
                text="Umidade (%)",
                font=dict(
                    size=14
                )
            ),
            # titlefont=dict(color="black"),
            # tickfont=dict(color="black"),
            overlaying="y",  # Sobrepõe o eixo y principal
            side="right",  # Eixo secundário no lado direito
        ),
        legend=dict(
            orientation="h",
            y=1.1,
            x=0.5,
            xanchor="center",
        ),
    )

    return fig_filtered, fig_temp_humd

    # dados sem filtro: fig_dist_raw, fig_temp_raw, fig_humd_raw
    fig_dist_raw = px.line(
        df_filtered_raw,
        x="timestamp",
        y="dist",
        markers=False,
        height=400,
        range_y=(200, 1000)
    )

    fig_temp_raw = px.line(
        df_filtered_raw,
        x="timestamp",
        y="tempC",
        markers=False,
        height=400,
        color_discrete_sequence=["red"]  # This parameter do the trick.
    )

    fig_humd_raw = px.line(
        df_filtered_raw,
        x="timestamp",
        y="humi",
        markers=False,
        height=400,
        color_discrete_sequence=["green"]  # This parameter do the trick.
    )
    return fig_dist_raw, fig_temp_raw, fig_humd_raw


def CreateFigDataRaw(df_raw):

    # ============================================================
    # CRIAR FIGURA 3 x 1
    # ============================================================

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        # subplot_titles=(
        #     "Distância",
        #     "Temperatura",
        #     "Umidade",
        # ),
    )

    # ============================================================
    # 1 - DISTÂNCIA + MÉDIA
    # ============================================================

    # Distância Firebase
    fig.add_trace(
        go.Scatter(
            x=df_raw["timestamp"],
            y=df_raw["dist"],
            mode="lines",
            line=dict(
                # shape="hv",
                width=2,
                # color="green",
            ),
            opacity=0.65,
            name="Distância",
        ),
        row=1,
        col=1,
    )

    # Linha vertical indicando o horário atual

    agora = datetime.now(TZ_BR).replace(tzinfo=None)

    fig.add_vline(
        x=agora,
        line_color="gray",
        line_width=1.5,
        line_dash="dash",
    )

    # =====================================================
    # =====================================================
    # =====================================================

    # Eixo Y invertido
    fig.update_yaxes(
        title_text="Distância",
        autorange="reversed",
        row=1,
        col=1,
    )

    # ============================================================
    # 2 - TEMPERATURA
    # ============================================================

    fig.add_trace(
        go.Scatter(
            x=df_raw["timestamp"],
            y=df_raw["tempC"],
            mode="lines",
            name="Temperatura",
            line=dict(
                # color="blue",
                width=1,
            ),
        ),
        row=3,
        col=1,
    )

    fig.update_yaxes(
        title_text="Temperatura (°C)",
        row=3,
        col=1,
    )

    # ============================================================
    # 3 - mmCounter
    # ============================================================

    fig.add_trace(
        go.Scatter(
            x=df_raw["timestamp"],
            y=df_raw["mmCounter"],
            mode="lines",
            name="mmCounter",
            line=dict(
                color="red",
                width=1,
            ),
        ),
        row=2,
        col=1,
    )

    fig.update_yaxes(
        title_text="mmCounter",
        row=2,
        col=1,
    )

    # ============================================================
    # EIXOS X
    # ============================================================

    fig.update_xaxes(
        title_text=None,
        row=1,
        col=1,
    )

    fig.update_xaxes(
        title_text=None,
        row=2,
        col=1,
    )

    fig.update_xaxes(
        title_text=None,
        row=3,
        col=1,
    )

    # Mostrar ticklabels do eixo X em todos os subplots
    fig.update_xaxes(
        showticklabels=True,
    )

    # ============================================================
    # LAYOUT GERAL
    # ============================================================

    fig.update_layout(
        height=700,
        hovermode="x",
        margin=dict(
            l=70,
            r=30,
            t=120,
            b=50,
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            y=1.02,
            xanchor="center",
            yanchor="bottom",
            font=dict(size=12),
            bordercolor="gray",
            borderwidth=1,
        )
    )

    return fig


def check_login():
    """Tela simples de autenticação."""

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    col_esquerda, col_login, col_direita = st.columns([1, 1, 1])

    with col_login:
        st.subheader("🔐 Acesso ao Sistema")

        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")

            submitted = st.form_submit_button("Entrar")

            if submitted:
                if (
                    username == st.secrets["LOGIN_USER"]
                    and password == st.secrets["LOGIN_PASSWORD"]
                ):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

    return False


def main():

    print("")
    print('*****************************************************')
    print('  ----->>>>> Starting code here! <<<<<-----')
    print('*****************************************************')
    print("")

    st.set_page_config(
        page_title="Automação Caixas D'água",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Verificar autenticação antes de carregar os dados
    if not check_login():
        st.stop()

    # A partir daqui, somente usuários autenticados têm acesso
    # ao restante da aplicação

    # Inicializar estado
    if "data_loaded" not in st.session_state:
        st.session_state.data_loaded = False

    if st.sidebar.button("Sair"):
        st.session_state.authenticated = False
        st.rerun()

    # if st.button("Force Update", icon="🔄", type="primary"):
    #     # ReadDataGoogleSheets().clear() # clear func cache only
    #     # ReadDataFirebase.clear() # clear func cache only
    #     st.cache_data.clear()  # clear cache
    #     st.session_state.data_loaded = False
    #     # You can clear a function's cache with func.clear() or
    #     # clear the entire cache with st.cache_data.clear().

    # Carregar dados do Firebase

    if "var" not in st.session_state:
        st.session_state.var = 0

    try:
        if st.session_state.var == 1:
            st.session_state.var = 0
            raise TransportError("Erro de conexão simulado")

        start_func_fire = time()

        df_firebase = ReadDataFirebase("water_level/esp32_rain_water/log_data")

        df_firebase_esp8266 = ReadDataFirebase(
            "water_level/ESP8266_data/data_log"
        )

        loading_time_fire = time() - start_func_fire

        print("\nFirebase data loaded!\n")
        df_firebase.info()
        df_firebase_esp8266.info()

    except TransportError:

        st.warning("Conexão com Firebase interrompida.")

        if st.button("Reconectar Firebase", type="primary"):
            st.cache_data.clear()
            st.rerun()

        st.stop()

    # Garantir que a coluna 'Date' esteja no formato datetime.datetime
    df_firebase['timestamp'] = pd.to_datetime(df_firebase['timestamp'])
    df_firebase['timestamp'] = df_firebase['timestamp'].dt.to_pydatetime()

    df_firebase_esp8266['timestamp'] = pd.to_datetime(df_firebase_esp8266['timestamp'])
    df_firebase_esp8266['timestamp'] = df_firebase_esp8266['timestamp'].dt.to_pydatetime()

    # DataFrame esteja ordenado cronologicamente
    df_firebase = df_firebase.sort_values("timestamp").reset_index(drop=True)

    df_firebase_esp8266 = df_firebase_esp8266.sort_values("timestamp").reset_index(drop=True)

    # df_firebase = df_firebase.iloc[::1, :]  # filtro de dados

    # Criando a data 01/08/2025 no formato datetime
    data = datetime(2026, 9, 1)

    df_firebase_raw = df_firebase
    df_firebase_esp8266_raw = df_firebase_esp8266

    df_firebase = df_firebase[(df_firebase["statusDist"] == "Success") &
                              (df_firebase["statusTempHumd"] == "Success") &
                              (df_firebase['timestamp'] > data) &
                              (df_firebase['dist_mm'] < 1000)]

    df_firebase_esp8266 = df_firebase_esp8266[(df_firebase_esp8266["statusDist"] == "Success") &
                                              (df_firebase_esp8266["statusTempHumd"] == "Success") &
                                              (df_firebase_esp8266['timestamp'] > data)]

    first_date = df_firebase['timestamp'].iloc[0]
    last_date = datetime.now(TZ_BR).replace(tzinfo=None)
    # last_date = df_firebase['timestamp'].iloc[-1]

    # first_date = df_filtered['Date'].iloc[0]
    # last_date = df_filtered['Date'].iloc[-1]

    # print('first_date ->>>', first_date)
    # print('last_date ->>>', last_date)
    # print('last_30days ->>>', last_30days)

    # média movel
    # df_filtered['Distance'] = pd.to_numeric(
    #     df_filtered['Distance']).rolling(5).mean()

    data_inicial_max = first_date
    data_final_max = last_date

    data_inicial = data_inicial_max
    data_final = data_final_max

    options = ["Full Data", "90 dias", "60 dias",
               "30 dias", "15 dias", "7 dias", "3 dias", "1 dia"]
    selection = st.pills("Filtro:", options, selection_mode="single")

    # Mapeamento das opções para os filtros
    filter_mapping = {
        None: (data_inicial_max, data_final_max),  # Intervalo completo
        "Full Data": (data_inicial_max, data_final_max),  # Intervalo completo
        "90 dias": (data_final_max - timedelta(days=90), data_final_max),
        "60 dias": (data_final_max - timedelta(days=60), data_final_max),
        "30 dias": (data_final_max - timedelta(days=30), data_final_max),
        "15 dias": (data_final_max - timedelta(days=15), data_final_max),
        "7 dias": (data_final_max - timedelta(days=7), data_final_max),
        "3 dias": (data_final_max - timedelta(days=3), data_final_max),
        "1 dia": (data_final_max - timedelta(days=1), data_final_max),
    }
    if selection == None:
        st.markdown(
            f"Nenhum filtro selecionado, mostrando todos os dados.")
    else:
        st.markdown(f"Você selecionou os últimos: {selection}.")

    # Obter o intervalo com base na seleção
    data_inicial, data_final = filter_mapping.get(
        selection, [])

    start_date, end_date = st.slider("Filtro de datas:",
                                     min_value=data_inicial_max,
                                     max_value=data_final_max,
                                     value=(data_inicial, data_final),
                                     format="DD/MM/YY",
                                     step=timedelta(days=1))
    # print(start_date)
    # print(end_date)

    # Filtrar os dados com base no slider
    df_firebase = df_firebase[(df_firebase['timestamp'] >= start_date) & (
        df_firebase['timestamp'] <= end_date)]

    df_firebase_esp8266 = df_firebase_esp8266[(df_firebase_esp8266['timestamp'] >= start_date) & (
        df_firebase_esp8266['timestamp'] <= end_date)]

    # Create data figures from filtered and raw data
    # fig_filtered, fig_temp_humd = CreateFigDataFiltered(df_firebase)
    fig_filtered = CreateFigDataFiltered(df_firebase, df_firebase_esp8266)

    fig_fire_raw = CreateFigDataRaw(df_firebase_raw)
    fig_8266_raw = CreateFigDataRaw(df_firebase_esp8266_raw)

    # =================================================================
    # =================================================================
    # =================================================================
    # =================================================================
    # =================================================================

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [":chart_with_upwards_trend: Dados", ":gear: Configurações", "Esp32", "Esp8266", "Esp32-S3"])

    with tab2:

        with st.expander("Ajustar linhas"):
            pass
            # last_row_to_delete = st.slider(
            #     'Quantas linhas gostaria de deletar?', 1, 100, 1)
            # st.write("Vamos deletar ", last_row_to_delete, 'linhas')

            # cmd_limpar = st.button(
            #     f"Deletar {last_row_to_delete} linhas do registro")
            # if cmd_limpar:
            #     ClearDataGoogleSheets(last_row_to_delete)
            #     print("linhas deletadas")

    with tab1:

        col1, col2 = st.columns([0.35, 0.65])

        with col1:

            col1.markdown("### Firebase")

            esp32_col, esp8266_col, esp32_s3 = st.columns([0.333, 0.333, 0.333])

            with esp32_col:

                st.markdown("""
                    <style>
                        [data-testid="stMetricValue"] {
                            font-size: 20px !important;
                        }
                    </style>
                    """, unsafe_allow_html=True)
                esp32_col.markdown("Água da chuva :cloud_with_rain:")

                last_dist = float(df_firebase["dist"].iloc[-1])
                st.metric(label="Distância :fire: :straight_ruler:",
                          value=f'{last_dist*0.1:.1f} cm'.replace(".", ","),
                          delta=None, border=True)

                last_temp = float(df_firebase["tempC"].iloc[-1])
                st.metric(label="Temperatura :fire: :thermometer:",
                          value=f'{last_temp:.1f}°C'.replace(".", ","), border=True)

                last_humd = float(df_firebase["humi"].iloc[-1])
                st.metric(label="Umidade :fire: :sweat_drops:",
                          value=f'{last_humd:.1f}%'.replace(".", ","), border=True)

                last_date = df_firebase["timestamp"].iloc[-1]
                delta = datetime.now(TZ_BR).replace(tzinfo=None) - last_date
                if delta <= timedelta(minutes=10):
                    delta_cor = "green"
                else:
                    delta_cor = "red"
                st.metric(label="Última atualização :fire: :calendar:",
                          #   value=str(last_date),
                          value=last_date.strftime("%d/%m/%Y\n\n%H:%M:%S"),
                          delta=f"{int(delta.total_seconds() // 60)} min "
                          f"{int(delta.total_seconds() % 60)} s",
                          border=True, delta_color=delta_cor)
            with esp8266_col:
                st.markdown("""
                    <style>
                        [data-testid="stMetricValue"] {
                            font-size: 20px !important;
                        }
                    </style>
                    """, unsafe_allow_html=True)
                esp8266_col.markdown("Cisterna :droplet:")
                last_dist = float(df_firebase_esp8266["dist"].iloc[-1])
                st.metric(label="Distância :arrow_heading_down: :straight_ruler:",
                          value=f'{last_dist*0.1:.1f} cm'.replace(".", ","),
                          delta=None, border=True)

                last_temp = float(df_firebase_esp8266["tempC"].iloc[-1])
                st.metric(label="Temperatura :arrow_heading_down: :thermometer:",
                          value=f'{last_temp:.1f}°C'.replace(".", ","), border=True)

                last_humd = float(df_firebase_esp8266["humi"].iloc[-1])
                st.metric(label="Umidade :arrow_heading_down: :sweat_drops:",
                          value=f'{last_humd:.1f}%'.replace(".", ","), border=True)

                last_date = df_firebase_esp8266["timestamp"].iloc[-1]
                delta = datetime.now(TZ_BR).replace(tzinfo=None) - last_date
                if delta <= timedelta(minutes=10):
                    delta_cor = "green"
                else:
                    delta_cor = "red"
                st.metric(label="Última atualização :arrow_heading_down: :calendar:",
                          #   value=str(last_date),
                          value=last_date.strftime("%d/%m/%Y\n\n%H:%M:%S"),
                          delta=f"{int(delta.total_seconds() // 60)} min "
                          f"{int(delta.total_seconds() % 60)} s",
                          border=True, delta_color=delta_cor)
            with esp32_s3:
                st.markdown("""
                    <style>
                        [data-testid="stMetricValue"] {
                            font-size: 20px !important;
                        }
                    </style>
                    """, unsafe_allow_html=True)
                esp32_s3.markdown("Caixa D'água :shower:")
                pass

            # st.info(f"Google Sheets Data loaded in {loading_time:.2f} seconds")
            st.info(f"Firebase Data loaded in {loading_time_fire:.2f} seconds")

            # função para contar pontos e mostrar datas de início e fim do banco de dados
            for nome, df in [
                ("ESP32", df_firebase),
                ("ESP8266", df_firebase_esp8266),
            ]:
                if not df.empty and "timestamp" in df.columns:
                    n = df["timestamp"].count()
                    inicio = df["timestamp"].min()
                    fim = df["timestamp"].max()

                    st.warning(
                        f"**{nome}**: {n:} pontos \n\n"
                        f"{inicio:%d/%m/%Y %H:%M} até "
                        f"{fim:%d/%m/%Y %H:%M}"
                    )
                else:
                    st.warning(f"{nome}: database sem dados")

        with col2:
            # ============
            # gráfico novo com subplots
            # ============
            st.plotly_chart(fig_filtered, theme=None, width='stretch', config={
                "responsive": True,
                "displayModeBar": True,
                "scrollZoom": False,
                "displaylogo": False,
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": "grafico_nivel_agua",
                    "height": 1200,
                    "width": 1000,
                    "scale": 3
                }}
            )

            # fig_filtered.write_image("fig1.png")

            # Gerar PNG em alta resolução
            # img_bytes = fig_filtered.to_image(
            #     format="png",
            #     scale=3  # aumenta a resolução em 3x
            # )

            # st.download_button(
            #     label="📥 Download gráfico em PNG",
            #     data=img_bytes,
            #     file_name="grafico_caixa_dagua.png",
            #     mime="image/png",
            # )

            # st.plotly_chart(fig_filtered, theme=None, width='stretch')

            # ============
            # gráfico novo
            # ============
            # st.plotly_chart(fig_temp_humd, theme=None,
            #                 width='stretch')
            # ============

    with tab2:
        with st.expander("Raw Data"):
            st.text(f'Última atualização: {last_date}')

    with tab3:
        st.markdown("#### Firebase Esp32")
        col1a, col2a = st.columns(2)

        with col1a:
            # Plota df esp32 raw
            st.dataframe(df_firebase_raw.sort_values(by="timestamp", ascending=False),
                         hide_index=True, width=1500, height=500)
        with col2a:
            # plota dados filtrados com mmCounter
            # fig_fire = px.line(
            #     data_frame=df_firebase,
            #     x="timestamp",
            #     y=["dist"],
            #     markers=False,
            #     height=300,
            # )
            # fig_fire.update_yaxes(autorange='reversed')
            # fig_fire_mmCounter = px.line(
            #     data_frame=df_firebase,
            #     x="timestamp",
            #     y=["mmCounter"],
            #     markers=False,
            #     height=300,
            #     color_discrete_sequence=["red"],
            # )

            # st.plotly_chart(fig_fire, theme=None, width='stretch')
            st.plotly_chart(fig_fire_raw, theme=None, width='stretch')

    with tab4:
        st.markdown("#### Firebase Esp8266")
        col1a, col2a = st.columns(2)

        with col1a:
            st.dataframe(df_firebase_esp8266_raw.sort_values(by="timestamp",
                         ascending=False), hide_index=True, width=1500, height=500)

        with col2a:
            st.plotly_chart(fig_8266_raw, theme=None, width='stretch')

    with tab5:
        st.markdown("#### Firebase Esp32-S3")


if __name__ == "__main__":
    os.system('cls')
    main()
