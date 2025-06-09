import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from datetime import datetime, timedelta
from sqlalchemy import create_engine
import re
from app import server  # obrigatório para Render reconhecer o WSGI server


#_____________________________________________________________________________________________SQL CREDENTIALS___________________________________________________________
import os
from sqlalchemy import create_engine

# Use environment variable from Render
DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback for local testing (optional)
if not DATABASE_URL:
    DATABASE_URL = "postgresql://root:AsAeIRM76j8npdz1hc20s2eoncZZH9Fy@dpg-d10spdi4d50c73b54dsg-a.oregon-postgres.render.com/hospital_data"

# Connect to PostgreSQL
engine = create_engine(DATABASE_URL)

# ----------------------------------------
# LOAD DATA FROM DATABASE
# ----------------------------------------

# Load all necessary tables
df_utente = pd.read_sql("SELECT * FROM universo_de_doentes", con=engine)
df_consultas = pd.read_sql("SELECT * FROM consultas_realizadas_marcadas", con=engine)
df_med = pd.read_sql("SELECT * FROM medicacao", con=engine)

df_utente.columns = df_utente.columns.str.upper()
df_consultas.columns = df_consultas.columns.str.upper()
df_med.columns = df_med.columns.str.upper()

# Ensure correct types
df_utente["PROCESSO"] = df_utente["PROCESSO"].astype(str)
df_consultas["PROCESSO"] = df_consultas["PROCESSO"].astype(str)
df_med["PROCESSO"] = df_med["PROCESSO"].astype(str)
df_consultas["DATACONSULTA"] = pd.to_datetime(df_consultas["DATACONSULTA"], errors="coerce")

#______________________________________________________________________________________________TRATAMENTO DE DADOS__________________________________________________
# TRATAMENTO DE MEDICAÇÃO________________________________________________________________________________________________________________________________
df = df_med.drop(columns=['TRATAMENTO'])
df = df.loc[df["QUANT"] > 0]
df["DATA_DISPENSA"] = pd.to_datetime(df["DATA_DISPENSA"], dayfirst=True)
df.sort_values(by=["PROCESSO", "DESIGN_ARTIGO", "DATA_DISPENSA"], inplace=True)

# Define max interval for continuous treatment
intervalo_maximo = 40  # days

# Create an identifier for continuous periods
df["Grupo"] = (
    df.groupby(["PROCESSO", "DESIGN_ARTIGO"])["DATA_DISPENSA"]
    .diff()
    .gt(pd.Timedelta(days=intervalo_maximo))
    .cumsum()
)

# Determine start and end of each continuous period
df_grouped = df.groupby(["PROCESSO", "DESIGN_ARTIGO", "Grupo"]).agg(
    Start=("DATA_DISPENSA", "min"),
    Finish=("DATA_DISPENSA", "max"),
    Cost=("VALOR", "sum")  # Summing cost for each period
).reset_index()

df_grouped["Finish"] += pd.Timedelta(days=30)



# Aggregate cost per year
df["Year"] = df["DATA_DISPENSA"].dt.year
df_yearly_cost = df.groupby("Year")["VALOR"].sum().reset_index()

# TRATAMENTO DE CONSULTAS____________________________________________________________________________________________________________________________________
# Remove duplicates
df_consultas = df_consultas.drop_duplicates()
df_consultas = df_consultas.dropna(subset=["PROCESSO", "DATACONSULTA"])
df_consultas["CODTIPOACTIVIDADE"] = df_consultas["CODTIPOACTIVIDADE"].fillna("DESCONHECIDO")
df_consultas["PROCESSO"] = df_consultas["PROCESSO"].astype(int)
df_consultas["DATACONSULTA"] = pd.to_datetime(df_consultas["DATACONSULTA"], errors='coerce')
data_atual = datetime.today()
df_consultas = df_consultas[df_consultas["DATACONSULTA"] <= data_atual]

if "DESCTIPOACTIVIDADE" in df_consultas.columns:
    df_consultas["DESCTIPOACTIVIDADE"] = df_consultas["DESCTIPOACTIVIDADE"].str.upper().str.strip()

df_consultas.drop(columns=['TIPO', 'ACTIVIDADE', 'MEDICO', 'DESCTIPOACTIVIDADE', 'NCITA', 'CODGRUPOAGENDA', 'SERVICOAGENDA'], inplace=True)

df_utente_filtered = df_utente[df_utente["DATA_OBITO"].isna()]

processos_validos = df_utente_filtered["PROCESSO"].dropna().astype(int).unique()

df_consultas["DATACONSULTA"] = pd.to_datetime(df_consultas["DATACONSULTA"], errors='coerce')
df_ultima_consulta = df_consultas.groupby("PROCESSO")["DATACONSULTA"].max().reset_index()
data_limite = datetime.today() - timedelta(days=365)
df_alerta = df_ultima_consulta[df_ultima_consulta["DATACONSULTA"] < data_limite]
df_alerta = df_alerta[df_alerta["PROCESSO"].isin(processos_validos)]
df_alerta = df_alerta.sort_values(by="DATACONSULTA", ascending=True)
df_alerta["DATACONSULTA"] = df_alerta["DATACONSULTA"].dt.strftime("%d/%m/%Y")

num_processos_alerta = df_alerta.shape[0]

# Clean agenda descriptions
def remover_nomes(texto):
    return re.sub(r'\b(DR(?:A)?\.?\s*[A-ZÁÉÍÓÚÃÕÇ]+(?:\s+[A-ZÁÉÍÓÚÃÕÇ\.]+)*)', '', texto, flags=re.IGNORECASE).strip()

df_consultas['AGENDA_PROTECTED'] = df_consultas['AGENDA_DESC'].apply(remover_nomes)

def normalizar_descricoes(texto):
    texto = texto.upper()
    texto = re.sub(r'\bGERAL ONC\.?\b', 'GERAL ONCOLOGIA', texto)
    texto = re.sub(r'\bCONS\. ENF\.?\b', 'CONSULTA ENFERMAGEM', texto)
    texto = re.sub(r'\bONC\.?\b', 'ONCOLOGIA', texto)
    texto = re.sub(r'\s{2,}', ' ', texto)  # Remove multiple spaces
    return texto.strip(' -')

df_consultas['AGENDA_PROTECTED'] = df_consultas['AGENDA_PROTECTED'].apply(normalizar_descricoes)

#____________________________________________________________________________________________________REFRESH FUNCTIONS________________________________

def get_utente_data():
    query = "SELECT * FROM universo_de_doentes"
    df = pd.read_sql(query, con=engine)

    if "DATA_NASCIMENTO" in df.columns:
        df["DATA_NASCIMENTO"] = pd.to_datetime(df["DATA_NASCIMENTO"], dayfirst=True)
    if "DATA_OBITO" in df.columns:
        df["DATA_OBITO"] = pd.to_datetime(df["DATA_OBITO"], dayfirst=True)

    return df


def get_consulta_data(df_utente, data_limite_custom=None):
    df_consultas = pd.read_sql("SELECT * FROM consultas_realizadas_marcadas", con=engine)
    df_consultas.columns = df_consultas.columns.str.upper()
    df_consultas["PROCESSO"] = df_consultas["PROCESSO"].astype(str)
    df_consultas["DATACONSULTA"] = pd.to_datetime(df_consultas["DATACONSULTA"], errors="coerce")

    # Remove duplicates
    df_consultas = df_consultas.drop_duplicates()
    df_consultas = df_consultas.dropna(subset=["PROCESSO", "DATACONSULTA"])
    df_consultas["CODTIPOACTIVIDADE"] = df_consultas["CODTIPOACTIVIDADE"].fillna("DESCONHECIDO")
    df_consultas["PROCESSO"] = df_consultas["PROCESSO"].astype(int)
    df_consultas["DATACONSULTA"] = pd.to_datetime(df_consultas["DATACONSULTA"], errors='coerce')
    data_atual = datetime.today()
    df_consultas = df_consultas[df_consultas["DATACONSULTA"] <= data_atual]

    if "DESCTIPOACTIVIDADE" in df_consultas.columns:
        df_consultas["DESCTIPOACTIVIDADE"] = df_consultas["DESCTIPOACTIVIDADE"].str.upper().str.strip()

    df_consultas.drop(columns=['TIPO', 'ACTIVIDADE', 'MEDICO', 'DESCTIPOACTIVIDADE', 'NCITA', 'CODGRUPOAGENDA', 'SERVICOAGENDA'], inplace=True)

    df_utente_filtered = df_utente[df_utente["DATA_OBITO"].isna()]

    processos_validos = df_utente_filtered["PROCESSO"].dropna().astype(int).unique()

    df_consultas["DATACONSULTA"] = pd.to_datetime(df_consultas["DATACONSULTA"], errors='coerce')
    df_ultima_consulta = df_consultas.groupby("PROCESSO")["DATACONSULTA"].max().reset_index()
    data_limite = datetime.today() - timedelta(days=365)
    df_alerta = df_ultima_consulta[df_ultima_consulta["DATACONSULTA"] < data_limite]
    df_alerta = df_alerta[df_alerta["PROCESSO"].isin(processos_validos)]
    df_alerta = df_alerta.sort_values(by="DATACONSULTA", ascending=True)
    df_alerta["DATACONSULTA"] = df_alerta["DATACONSULTA"].dt.strftime("%d/%m/%Y")

    num_processos_alerta = df_alerta.shape[0]

    # Clean agenda descriptions
    def remover_nomes(texto):
        return re.sub(r'\b(DR(?:A)?\.?\s*[A-ZÁÉÍÓÚÃÕÇ]+(?:\s+[A-ZÁÉÍÓÚÃÕÇ\.]+)*)', '', texto, flags=re.IGNORECASE).strip()

    df_consultas['AGENDA_PROTECTED'] = df_consultas['AGENDA_DESC'].apply(remover_nomes)

    def normalizar_descricoes(texto):
        texto = texto.upper()
        texto = re.sub(r'\bGERAL ONC\.?\b', 'GERAL ONCOLOGIA', texto)
        texto = re.sub(r'\bCONS\. ENF\.?\b', 'CONSULTA ENFERMAGEM', texto)
        texto = re.sub(r'\bONC\.?\b', 'ONCOLOGIA', texto)
        texto = re.sub(r'\s{2,}', ' ', texto)  # Remove multiple spaces
        return texto.strip(' -')

    df_consultas['AGENDA_PROTECTED'] = df_consultas['AGENDA_PROTECTED'].apply(normalizar_descricoes)

    return df_consultas, df_alerta, num_processos_alerta


def get_medicacao_data():

    df_med = pd.read_sql("SELECT * FROM medicacao", con=engine)

    df_med.columns = df_med.columns.str.upper()

    df_med["PROCESSO"] = df_med["PROCESSO"].astype(str)

    df = df_med.drop(columns=['TRATAMENTO'])
    df = df.loc[df["QUANT"] > 0]
    df["DATA_DISPENSA"] = pd.to_datetime(df["DATA_DISPENSA"], dayfirst=True)
    df.sort_values(by=["PROCESSO", "DESIGN_ARTIGO", "DATA_DISPENSA"], inplace=True)

    # Define max interval for continuous treatment
    intervalo_maximo = 40  # days

    # Create an identifier for continuous periods
    df["Grupo"] = (
        df.groupby(["PROCESSO", "DESIGN_ARTIGO"])["DATA_DISPENSA"]
        .diff()
        .gt(pd.Timedelta(days=intervalo_maximo))
        .cumsum()
    )

    # Determine start and end of each continuous period
    df_grouped = df.groupby(["PROCESSO", "DESIGN_ARTIGO", "Grupo"]).agg(
        Start=("DATA_DISPENSA", "min"),
        Finish=("DATA_DISPENSA", "max"),
        Cost=("VALOR", "sum")  # Summing cost for each period
    ).reset_index()

    df_grouped["Finish"] += pd.Timedelta(days=30)


    # Aggregate cost per year
    df["Year"] = df["DATA_DISPENSA"].dt.year
    df_yearly_cost = df.groupby("Year")["VALOR"].sum().reset_index()

    return df, df_grouped, df_yearly_cost


# Create a Dash App__________________________________________________________________________________________________________________________________________
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)

# Layout definition with Tabs
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([html.Img(src="/assets/LOGOTIPO.jpg", height="100px")], width="auto", className="p-0 m-0 d-flex align-items-center"),
        dbc.Col([
            dbc.Tabs([
                dbc.Tab(label="Utentes", tab_id="utentes"),
                dbc.Tab(label="Consultas", tab_id="consultas"),
                dbc.Tab(label="Medicação", tab_id="medicacao")
            ], id="tabs", active_tab="medicacao")
        ], width="auto", className="p-0 m-0 d-flex align-items-center ms-auto")
    ], style={"backgroundColor": "#FFFFFF", "width": "100%", "height": "100px", "padding": "0px", "margin": "0px"}, align="center"),

    dbc.Row([dbc.Col(id="medicacao-title", width=12)], className="w-100", style={"height": "50px", "marginBottom": "20px"}),

    # Main tab content placeholder (for df_alert table)
    dbc.Row([dbc.Col(id="tab-content", width=12)]),

    # Medicação filters & graphs (only shown when tab is 'medicacao')
    html.Div(
        dbc.Row([
            dbc.Row([
                dbc.Col([html.Label("Selecione o/s processo/s:"),
                         dcc.Dropdown(id="processo-dropdown",
                                      options=[{"label": processo, "value": processo} for processo in df["PROCESSO"].unique()],
                                      multi=True, placeholder="Select Processos")], width=4),
                dbc.Col([html.Label("Selecione o/s medicamento/s:"),
                         dcc.Dropdown(id="medicamento-dropdown",
                                      options=[{"label": medicamento, "value": medicamento} for medicamento in df["DESIGN_ARTIGO"].unique()],
                                      multi=True, placeholder="Select Medicamentos")], width=4),
                dbc.Col([html.Label("Selecione o/s ano/s:"),
                         dcc.Dropdown(id="year-dropdown",
                                      options=[{"label": str(year), "value": year} for year in df["Year"].unique()],
                                      multi=True, placeholder="Select Year")], width=4)
            ], className="w-100"),

            dbc.Row([dbc.Col(dcc.Graph(id="barplot-cost-year"), width=6),
                     dbc.Col(dcc.Graph(id="piechart-cost-distribution"), width=6)]),

            dbc.Row([dbc.Col(dcc.Graph(id="gantt-chart"), width=12)]),
        ], id="medicacao-filters"),
        id="medicacao-filters-container"
    ),
    dcc.Interval(id='interval-component', interval=60000*5, n_intervals=0)
])

# CALLBACKS MEDICAÇÃO________________________________________________________________________________________________________________________________

from flask_caching import Cache

# Initialize cache for the app
cache = Cache(app.server, config={'CACHE_TYPE': 'SimpleCache'})

# Cache data loading functions for 5 minutes (adjust timeout as needed)
@cache.memoize(timeout=300)
def cached_get_medicacao_data():
    return get_medicacao_data()

@cache.memoize(timeout=300)
def cached_get_consulta_data(df_utente, data_limite_custom=None):
    return get_consulta_data(df_utente, data_limite_custom)

# Increase interval to 60 seconds (adjust in your layout component too)
# Example for interval-component: dcc.Interval(id='interval-component', interval=60*1000, n_intervals=0)

# Callback to Show/Hide Title and Filters Based on Selected Tab
@app.callback(
    [Output("medicacao-title", "children"),
     Output("medicacao-filters-container", "style")],
    Input("tabs", "active_tab"),
    Input("interval-component", "n_intervals")
)
def update_content(active_tab, n_intervals):
    if active_tab == "medicacao":
        return (
            html.Div(
                html.H1("Medicação",
                        style={"color": "white", "margin": "0 auto", "padding": "10px", "textAlign": "left"}),
                style={"backgroundColor": "#8D0E19", "width": "100%", "padding": "0px", "margin": "0px"}
            ),
            {"display": "block"}  # Show filters and graphs
        )
    else:
        return "", {"display": "none"}  # Hide filters and graphs

# Update Barplot of Cost per Year
@app.callback(
    Output("barplot-cost-year", "figure"),
    Input("processo-dropdown", "value"),
    Input("medicamento-dropdown", "value"),
    Input("year-dropdown", "value"),
    Input("interval-component", "n_intervals")
)
def update_cost_barplot(selected_processes, selected_medications, selected_years, n_intervals):
    df, _, df_yearly_cost = cached_get_medicacao_data()
    filtered_df = df.copy()


    # Filter based on selections
    if selected_processes:
        filtered_df = filtered_df[filtered_df["PROCESSO"].isin(selected_processes)]
    if selected_medications:
        filtered_df = filtered_df[filtered_df["DESIGN_ARTIGO"].isin(selected_medications)]
    if selected_years:
        filtered_df = filtered_df[filtered_df["Year"].isin(selected_years)]

    # Group by year and sum the cost
    df_yearly_cost = filtered_df.groupby("Year")["VALOR"].sum().reset_index()

    fig = px.bar(df_yearly_cost, x="Year", y="VALOR", title="Total de medicamentos por ano")
    return fig

# Update Gantt Chart
@app.callback(
    Output("gantt-chart", "figure"),
    Input("tabs", "active_tab"),
    Input("processo-dropdown", "value"),
    Input("medicamento-dropdown", "value"),
    Input("interval-component", "n_intervals")
)
def update_gantt_chart(active_tab, selected_processes, selected_medications, n_intervals):
    if active_tab != "medicacao":
        return go.Figure()

    _, df_grouped, _ = cached_get_medicacao_data()

    # If no process selected, show all
    if not selected_processes:
        selected_processes = df_grouped["PROCESSO"].unique().tolist()

    filtered_df = df_grouped[df_grouped["PROCESSO"].isin(selected_processes)]

    if selected_medications:
        filtered_df = filtered_df[filtered_df["DESIGN_ARTIGO"].isin(selected_medications)]

    filtered_df = filtered_df.copy()
    filtered_df["Task"] = filtered_df["PROCESSO"].astype(str) + " - " + filtered_df["DESIGN_ARTIGO"]

    color_palette = px.colors.qualitative.Set1
    unique_processes = filtered_df["PROCESSO"].unique()
    color_map = {process: color_palette[i % len(color_palette)] for i, process in enumerate(unique_processes)}

    fig = px.timeline(
        filtered_df,
        x_start="Start",
        x_end="Finish",
        y="Task",
        color="PROCESSO",
        color_discrete_map=color_map
    )
    fig.update_yaxes(autorange="reversed", title="Processo - Medicamento")
    fig.update_layout(coloraxis_showscale=False)

    return fig

# Update Pie Chart Cost Distribution
@app.callback(
    Output("piechart-cost-distribution", "figure"),
    Input("processo-dropdown", "value"),
    Input("medicamento-dropdown", "value"),
    Input("year-dropdown", "value"),
    Input("interval-component", "n_intervals")
)
def update_piechart(selected_processes, selected_medications, selected_years, n_intervals):
    df, _, _ = cached_get_medicacao_data()

    filtered_df = df
    if selected_processes:
        filtered_df = filtered_df[filtered_df["PROCESSO"].isin(selected_processes)]
    if selected_medications:
        filtered_df = filtered_df[filtered_df["DESIGN_ARTIGO"].isin(selected_medications)]
    if selected_years:
        filtered_df = filtered_df[filtered_df["Year"].isin(selected_years)]

    df_cost_distribution = filtered_df.groupby("TIPO_DOCUMENTO")["VALOR"].sum().reset_index()

    fig = px.pie(df_cost_distribution, names="TIPO_DOCUMENTO", values="VALOR", title="Distribuição do custo por tipo de documento")
    return fig

# Render Tab Content
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
)
def render_tab_content(active_tab):
    if active_tab == "consultas":
        return html.Div([
            html.Div(
                html.H1("Consultas",
                        style={"color": "white", "margin": "0 auto", "padding": "10px", "textAlign": "left"}),
                style={"backgroundColor": "#8D0E19", "width": "100%", "padding": "0px", "margin": "0px"}
            ),

            dbc.Row([
                dbc.Col([
                    html.Label("Selecione a data limite para última consulta:"),
                    dcc.DatePickerSingle(
                        id="consulta-date-picker",
                        date=pd.Timestamp.today().date(),
                        display_format='YYYY-MM-DD',
                        placeholder="Escolha a data"
                    ),
                    dcc.Checklist(
                        id="include-deceased-checklist",
                        options=[{"label": " Incluir pacientes falecidos", "value": "include"}],
                        value=[],
                        style={"marginTop": "10px"}
                    )
                ], width=4)
            ], className="mb-3"),

            dash_table.DataTable(
                id="alerta-table",
                columns=[],
                data=[],
                style_table={"overflowX": "auto"},
                style_cell={"textAlign": "left", "padding": "5px"},
                style_header={"backgroundColor": "#f5f5f5", "fontWeight": "bold"},
                page_size=10
            ),

            dbc.Row([
                dbc.Col([
                    html.Label("Selecione o Processo (sem consulta após a data escolhida):"),
                    dcc.Dropdown(
                        id="processo-dropdown-consultas",
                        options=[],
                        multi=False,
                        placeholder="Select Processo"
                    )
                ], width=4)
            ], className="mb-4"),

            dcc.Graph(id="consultas-plot")
        ])

# Update Alert Dropdown and Table
@app.callback(
    Output("processo-dropdown-consultas", "options"),
    Output("alerta-table", "columns"),
    Output("alerta-table", "data"),
    Input("consulta-date-picker", "date"),
    Input("include-deceased-checklist", "value"),
    Input("interval-component", "n_intervals")
)
def update_alerta_dropdown_and_table(selected_date, include_deceased_values, n_intervals):
    if not selected_date:
        return [], [], []

    df_consultas, df_alerta, _ = cached_get_consulta_data(df_utente, data_limite_custom=selected_date)
    df_utente_info = get_utente_data()

    df_alerta = df_alerta.copy()
    df_utente_info = df_utente_info.copy()
    df_utente_info.columns = df_utente_info.columns.str.strip().str.upper()
    print(df_utente_info)

    df_alerta["PROCESSO"] = pd.to_numeric(df_alerta["PROCESSO"], errors="coerce")
    df_utente_info["PROCESSO"] = pd.to_numeric(df_utente_info["PROCESSO"], errors="coerce")
    df_utente_info["DATA_OBITO"] = pd.to_datetime(df_utente_info["DATA_OBITO"], errors="coerce")

    df_alerta = df_alerta.merge(
        df_utente_info[["PROCESSO", "DATA_OBITO"]],
        on="PROCESSO",
        how="left"
    )

    include_deceased = "include" in include_deceased_values
    if not include_deceased:
        df_alerta = df_alerta[df_alerta["DATA_OBITO"].isna()]

    df_alerta["DATA_OBITO"] = df_alerta["DATA_OBITO"].dt.strftime("%Y-%m-%d")

    dropdown_options = [{"label": str(p), "value": p} for p in df_alerta["PROCESSO"].unique()]
    table_columns = [{"name": col, "id": col} for col in df_alerta.columns]
    table_data = df_alerta.to_dict("records")

    return dropdown_options, table_columns, table_data

# Update Consultas Plot
@app.callback(
    Output("consultas-plot", "figure"),
    Input("processo-dropdown-consultas", "value"),
    Input("consulta-date-picker", "date"),
    Input("interval-component", "n_intervals")
)
def update_consultas_plot(selected_process, selected_date, n_intervals):
    if not selected_process or not selected_date:
        return go.Figure()

    df_consultas, _, _ = cached_get_consulta_data(df_utente, data_limite_custom=selected_date)
    df_filtered = df_consultas[df_consultas["PROCESSO"] == selected_process]

    if df_filtered.empty:
        return go.Figure()

    # Convert once, safely
    df_filtered = df_filtered.copy()
    df_filtered["CODTIPOACTIVIDADE"] = pd.to_numeric(df_filtered["CODTIPOACTIVIDADE"], errors="coerce").astype("Int64")

    tipo_map = {
        1: "PRIMEIRA CONSULTA",
        2: "CONSULTA SUBSEQUENTE"
    }
    df_filtered["TIPO_ACTIVIDADE_DESC"] = df_filtered["CODTIPOACTIVIDADE"].map(tipo_map).fillna("OUTRO")

    fig = px.scatter(
        df_filtered.sort_values("DATACONSULTA"),
        x="DATACONSULTA",
        y="TIPO_ACTIVIDADE_DESC",
        color="AGENDA_PROTECTED",
        title=f"Consultas do Processo {selected_process}",
        labels={
            "DATACONSULTA": "Data da Consulta",
            "TIPO_ACTIVIDADE_DESC": "Tipo de Atividade",
            "AGENDA_PROTECTED": "Descrição da Agenda"
        }
    )

    fig.update_layout(
        xaxis_title="Data da Consulta",
        yaxis_title="Tipo de Atividade",
        showlegend=True
    )

    return fig

# Run the app
app = Dash(__name__)
server = app.server  # necessário para gunicorn/Render

if __name__ == "__main__":
    app.run_server(debug=True)




