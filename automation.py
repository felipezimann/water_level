import os.path
from dotenv import load_dotenv
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from time import time

import firebase_admin
from firebase_admin import credentials, db

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Carregar variáveis do .env
load_dotenv()

# Gerar o conteúdo do JSON a partir das variáveis de ambiente para o Google Sheets
gs_credentials_data = {
    "installed": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uris": [
            os.getenv("GOOGLE_REDIRECT_URI")
        ]
    }
}

# Gerar o conteúdo do JSON para o Firebase
firebase_config = {
    "type": os.getenv("FIREBASE_TYPE"),
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
    # Corrigir quebras de linha
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
    "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
    "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
}

# Escrever o JSON em um arquivo temporário
with open("firebase_credentials_temp.json", "w") as f:
    json.dump(firebase_config, f)

# If modifying these scopes, delete the file token.json.
SCOPES = [os.getenv("GOOGLE_SCOPES")]

# The ID and range of a sample spreadsheet.
SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
RANGE_NAME = os.getenv("GOOGLE_RANGE_NAME")
RANGE_NAME2 = os.getenv("GOOGLE_RANGE_NAME2")


@st.cache_data(ttl=300)  # 5min
def ReadDataGoogleSheets():
    # start_time = time()
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            flow = InstalledAppFlow.from_client_config(
                gs_credentials_data, SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("sheets", "v4", credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = (
            sheet.values()
            .get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME)
            .execute()
        )
        values = result.get("values", [], )

        # result2 = (
        #     sheet.values()
        #     .get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME2)
        #     .execute()
        # )
        # values2 = result2.get("values", [])

        if not values:
            print("\nNo data found.\n")
            return

        # st.info(f"Data loaded in {time() - start_time:.2f} seconds")
        # st.success("Fetched data from API!")  # 👈 Show a success message
        return values

    except HttpError as err:
        print(err)


def ClearDataGoogleSheets(last_row_to_delete):
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            flow = InstalledAppFlow.from_client_config(
                gs_credentials_data, SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("sheets", "v4", credentials=creds)
        ultima_linha = 7 + last_row_to_delete
        request_body = {
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": "0",
                            "dimension": "ROWS",
                            "startIndex": 3,
                            "endIndex": ultima_linha
                        }
                    }
                }
            ]
        }

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = (
            sheet
            .batchUpdate(spreadsheetId=SPREADSHEET_ID, body=request_body)
            .execute()
        )
        return

    except HttpError as err:
        print(err)


@st.cache_data(ttl=300)  # 5min
def ReadDataFirebase():

    print(firebase_admin._apps.keys())  # Deve mostrar os aplicativos restantes
    # st.markdown(firebase_admin._apps.keys())

    # Fechar todos os aplicativos
    for app in list(firebase_admin._apps.values()):
        firebase_admin.delete_app(app)

    # Verificar se todos os aplicativos foram fechados
    print(firebase_admin._apps.keys())  # Deve estar vazio
    # st.markdown(firebase_admin._apps.keys())

    # Carregar credenciais do Firebase
    cred = credentials.Certificate("firebase_credentials_temp.json")
    databaseURL_firebase = os.getenv("FIREBASE_DATABASE_URL")

    app = firebase_admin.initialize_app(
        cred, {"databaseURL": databaseURL_firebase}, name='app_water')

    # received_data = db.reference(path="/", app=app).get()
    received_data = db.reference(path="water_level/log_data", app=app).get()

    # print(received_data)

    records = list(received_data.values())

    # Convertendo para DataFrame
    df = pd.DataFrame(records)

    # Exibindo o DataFrame resultante
    # print(df)

    return df


def CreateFigDataFiltered(df_filtered, df2):

    fig_filtered = px.line(
        data_frame=df_filtered,
        x="Date",
        y=["Distance"],
        markers=False,
        height=500,
    )

    # Adicionar mais séries, se necessário
    fig_filtered.add_trace(
        go.Scatter(
            x=df2["timestamp"],
            y=df2["dist"],
            mode="lines",
            name="Distância Firebase",
            line=dict(color="orange", dash="solid"),
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
        line_width=2.5, opacity=1, line_dash="dash",
        x0=df_filtered["Date"].iloc[0],
        x1=df_filtered["Date"].iloc[-1],
        y0=350,
        y1=350,
        yref="y"
    )
    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="green",  # "salmon",
        line_width=2, opacity=0.75, line_dash="dash",
        x0=df_filtered["Date"].iloc[0],
        x1=df_filtered["Date"].iloc[-1],
        y0=675,
        y1=675,
        yref="y"
    )
    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="orange",  # "salmon",
        line_width=2, opacity=0.75, line_dash="dash",
        x0=df_filtered["Date"].iloc[0],
        x1=df_filtered["Date"].iloc[-1],
        y0=800,
        y1=800,
        yref="y"
    )
    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="salmon",  # "salmon",
        line_width=2, opacity=1, line_dash="dash",
        x0=df_filtered["Date"].iloc[0],
        x1=df_filtered["Date"].iloc[-1],
        y0=900,
        y1=900,
        yref="y"
    )
    fig_filtered.add_shape(  # add a horizontal "target" line
        type="line",
        line_color="red",  # "salmon",
        line_width=2, opacity=1, line_dash="dash",
        x0=df_filtered["Date"].iloc[0],
        x1=df_filtered["Date"].iloc[-1],
        y0=1000,
        y1=1000,
        yref="y"
    )

    fig_filtered.add_annotation(  # add a text callout with arrow
        text="Max", x=df_filtered["Date"].iloc[1],
        y=375,
        arrowhead=2,
        showarrow=False
    )
    fig_filtered.add_annotation(  # add a text callout with arrow
        text="Max", x=df_filtered["Date"].iloc[-1],
        y=325,
        arrowhead=2,
        showarrow=False
    )

    fig_filtered.add_annotation(  # add a text callout with arrow
        text="Perigo!", x=df_filtered["Date"].iloc[-1],
        y=925,
        arrowhead=2,
        showarrow=False
    )
    fig_filtered.add_annotation(  # add a text callout with arrow
        text="Vazia", x=df_filtered["Date"].iloc[-1],
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

    fig_temp = px.line(
        df_filtered,
        x="Date",
        y=["Temperature"],
        markers=False,
        height=400,
        color_discrete_sequence=["red"]  # This parameter do the trick.
    )
    fig_temp.update_layout(  # customize font and legend orientation & position
        xaxis_title=None,
        yaxis_title="Temperatura (°C)",
        legend=dict(
            title=None,
            orientation="h",
            y=1.00, yanchor="bottom",
            x=0.98, xanchor="right"
        )
    )

    fig_humd = px.line(
        df_filtered,
        x="Date",
        y=["Humidity"],
        markers=False,
        height=400,
        color_discrete_sequence=["green"],  # This parameter do the trick.
    )
    fig_humd.update_layout(  # customize font and legend orientation & position
        xaxis_title=None,
        yaxis_title="Umidade (%)",
        legend=dict(
            title=None,
            orientation="h",
            y=1.00, yanchor="bottom",
            x=0.98, xanchor="right"
        )
    )

    #
    #
    #
    #

    # Criar o gráfico inicial com a primeira série (eixo y principal)
    fig_temp_humd = go.Figure()

    fig_temp_humd.add_trace(
        go.Scatter(
            x=df2["timestamp"],
            y=df2["tempC"],
            mode="lines",
            name="Temperatura",
            line=dict(color="blue"),
        )
    )

    # Adicionar outra série ao eixo y secundário
    fig_temp_humd.add_trace(
        go.Scatter(
            x=df2["timestamp"],
            y=df2["humi"],
            mode="lines",
            name="Umidade",
            line=dict(color="red", dash="dot"),
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
            title="Temperatura (°C)",
            titlefont=dict(color="black"),
            tickfont=dict(color="black"),
        ),
        yaxis2=dict(
            title="Umidade (%)",
            titlefont=dict(color="black"),
            tickfont=dict(color="black"),
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

    return fig_filtered, fig_temp, fig_humd, fig_temp_humd


def CreateFigDataRaw(df_filtered_raw):
    # dados sem filtro: fig_dist_raw, fig_temp_raw, fig_humd_raw
    fig_dist_raw = px.line(
        df_filtered_raw,
        x="Date",
        y="Distance",
        markers=False,
        height=400,
        range_y=(200, 1000)
    )

    fig_temp_raw = px.line(
        df_filtered_raw,
        x="Date",
        y="Temperature",
        markers=False,
        height=400,
        color_discrete_sequence=["red"]  # This parameter do the trick.
    )

    fig_humd_raw = px.line(
        df_filtered_raw,
        x="Date",
        y="Humidity",
        markers=False,
        height=400,
        color_discrete_sequence=["green"]  # This parameter do the trick.
    )
    return fig_dist_raw, fig_temp_raw, fig_humd_raw


def main():

    print("")
    print('*****************************************************')
    print('  ----->>>>> Starting code here! <<<<<-----')
    print('*****************************************************')
    print("")

    st.set_page_config(
        page_title="Automação Caixa D'água",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Inicializar estado
    if "data_loaded" not in st.session_state:
        st.session_state.data_loaded = False

    if st.button("Force Update", icon="🔄", type="primary"):
        # ReadDataGoogleSheets().clear() # clear func cache only
        # ReadDataFirebase.clear() # clear func cache only
        st.cache_data.clear()  # clear cache
        st.session_state.data_loaded = False
        # You can clear a function's cache with func.clear() or
        # clear the entire cache with st.cache_data.clear().

    _ = """
    # Verificar se os dados estão carregados
    if st.session_state.data_loaded == False:
        # st.warning("Os dados não estão carregados. Carregue os dados primeiro!")
        print(
            f"[{datetime.now()}] - Os dados não estão carregados. Carregue os dados primeiro!")
        start_func = time()
        valuesRead = ReadDataGoogleSheets()
        loading_time = time() - start_func
        st.session_state.data_loaded = True
        print(f"[{datetime.now()}] - Dados carregados com sucesso!")
    else:
        # Prosseguir com o código se os dados estiverem carregados
        start_func = time()
        valuesRead = ReadDataGoogleSheets()
        loading_time = time() - start_func
        # st.success("Dados carregados com sucesso!")
        print(f"[{datetime.now()}] - Using Cache! Dados carregados com sucesso!")
    """

    # Carregar dados Google Sheets
    start_func = time()
    valuesRead = ReadDataGoogleSheets()
    loading_time = time() - start_func
    print(f"[{datetime.now()}] - Dados carregados com sucesso!")

    df = pd.DataFrame(data=valuesRead[7:], columns=valuesRead[1])

    # Carregar dados do Firebase
    start_func_fire = time()
    df_firebase = ReadDataFirebase()  # Read data from Firebase
    loading_time_fire = time() - start_func_fire
    print("")
    print("Firebase data loaded!")
    print("")
    df_firebase.info()

    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y %H:%M:%S')
    # Garantir que a coluna 'Date' esteja no formato datetime.datetime
    # df['Date'] = df['Date'].dt.to_pydatetime()

    df = df.iloc[::5, :]  # filtro de dados
    # df.info()
    # downsampled_df.info()

    first_date = df['Date'].iloc[0]
    last_date = df['Date'].iloc[-1]
    last_30days = df['Date'].iloc[-1] - timedelta(days=30)

    # print('first_date ->>>', first_date)
    # print('last_date ->>>', last_date)
    # print('last_30days ->>>', last_30days)

    df_filtered = df[(df["Dist Status"] == "Success") &
                     (df["TempHumd Status"] == "Success") &
                     (df['Date'] > first_date)]

    df_filtered_raw = df_filtered

    # média movel
    # df_filtered['Distance'] = pd.to_numeric(
    #     df_filtered['Distance']).rolling(5).mean()
    print("")
    print("Google Sheets data loaded!")
    print("")
    df_filtered.info()
    print("")

    data_inicial_max = first_date.to_pydatetime()
    data_final_max = last_date.to_pydatetime()

    data_inicial = data_inicial_max
    data_final = data_final_max

    options = ["Full Data", "60 dias", "30 dias", "7 dias", "3 dias"]
    selection = st.pills("Filtro:", options, selection_mode="single")

    # Mapeamento das opções para os filtros
    filter_mapping = {
        None: (data_inicial_max, data_final_max),  # Intervalo completo
        "Full Data": (data_inicial_max, data_final_max),  # Intervalo completo
        "60 dias": (data_final_max - timedelta(days=60), data_final_max),
        "30 dias": (data_final_max - timedelta(days=30), data_final_max),
        "7 dias": (data_final_max - timedelta(days=7), data_final_max),
        "3 dias": (data_final_max - timedelta(days=3), data_final_max),
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
    df_filtered = df_filtered[(df_filtered['Date'] >= start_date) & (
        df_filtered['Date'] <= end_date)]

    # Create data figures from filtered and raw data
    fig_filtered, fig_temp, fig_humd, fig_temp_humd = CreateFigDataFiltered(
        df_filtered, df_firebase)
    fig_dist_raw, fig_temp_raw, fig_humd_raw = CreateFigDataRaw(
        df_filtered_raw)

    # =================================================================
    # =================================================================
    # =================================================================
    # =================================================================
    # =================================================================

    tab1, tab2, tab3, tab4 = st.tabs(
        [":chart_with_upwards_trend: Dados", ":gear: Configurações", "Dados em Tabela", "firebase"])

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

            GS_col, fire_col = st.columns([0.5, 0.5])

            with GS_col:
                GS_col.markdown("### Google Sheets")
                last_dist = float(df_filtered["Distance"].iloc[-1])
                st.metric(label="Distância GS:straight_ruler:",
                          value=f'{last_dist*0.1:.1f} cm'.replace(".", ","),
                          delta=None)

                last_temp = float(df_filtered["Temperature"].iloc[-1])
                st.metric(label="Temperatura :thermometer:",
                          value=f'{last_temp:.1f}°C'.replace(".", ","))

                last_humd = float(df_filtered["Humidity"].iloc[-1])
                st.metric(label="Umidade :sweat_drops:",
                          value=f'{last_humd:.1f}%'.replace(".", ","))

                last_date = df_filtered["Date"].iloc[-1]
                st.metric(label=":clock4: Última atualização :calendar:",
                          value=str(last_date))
            with fire_col:
                fire_col.markdown("### Firebase")
                last_dist = float(df_firebase["dist"].iloc[-1])
                st.metric(label="Distância :fire: :straight_ruler:",
                          value=f'{last_dist*0.1:.1f} cm'.replace(".", ","),
                          delta=None)

                last_temp = float(df_firebase["tempC"].iloc[-1])
                st.metric(label="Temperatura :fire: :thermometer:",
                          value=f'{last_temp:.1f}°C'.replace(".", ","))

                last_humd = float(df_firebase["humi"].iloc[-1])
                st.metric(label="Umidade :fire: :sweat_drops:",
                          value=f'{last_humd:.1f}%'.replace(".", ","))

                last_date = df_firebase["timestamp"].iloc[-1]
                st.metric(label=":clock4: :fire: Última atualização :fire: :calendar:",
                          value=str(last_date))

            st.info(f"Google Sheets Data loaded in {loading_time:.2f} seconds")
            st.info(f"Firebase Data loaded in {loading_time_fire:.2f} seconds")

        with col2:
            st.plotly_chart(fig_filtered, theme=None, use_container_width=True)

            # Criar colunas e adicionar o slider em uma coluna estreita
            _, col2_slider, _ = st.columns([1, 2, 1])

            with col2_slider:  # Adiciona o slider à coluna mais estreita
                pass

        # ============
        # gráfico novo
        # ============
        st.plotly_chart(fig_temp_humd, theme="streamlit",
                        use_container_width=True)
        # ============

        col1a, col2a = st.columns(2)
        col1a.plotly_chart(fig_temp, theme="streamlit",
                           use_container_width=True)
        col2a.plotly_chart(fig_humd, theme="streamlit",
                           use_container_width=True)

    with tab2:
        with st.expander("Raw Data"):
            st.text(f'Última atualização: {last_date}')

            _, col4, _ = st.columns([0.25, 0.50, 0.25])
            col4.plotly_chart(fig_dist_raw, theme=None,
                              use_container_width=True)
            col4.plotly_chart(fig_temp_raw, theme=None,
                              use_container_width=True)
            col4.plotly_chart(fig_humd_raw, theme=None,
                              use_container_width=True)

    with tab3:
        st.dataframe(df, width=1000, height=800)

    with tab4:

        fig_fire = px.line(
            data_frame=df_firebase,
            x="timestamp",
            y=["dist"],
            markers=False,
            height=500,
        )

        st.plotly_chart(fig_fire, theme=None, use_container_width=True)

        st.dataframe(df_firebase, width=1000, height=800)


if __name__ == "__main__":
    os.system('cls')
    main()
