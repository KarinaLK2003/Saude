import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Load data
ficheiro_excel = 'Cancro_da_Mama_dados_03-01-2025.xlsx'
df = pd.read_excel(ficheiro_excel, sheet_name='medicação')
df_consultas = pd.read_excel(ficheiro_excel, sheet_name='consultas realizadas marcadas')
df_utente = pd.read_excel(ficheiro_excel, sheet_name='universo de doentes')

# TRATAMENTO DE MEDICAÇÃO________________________________________________________________________________________________________________________________
df = df.drop(columns=['TRATAMENTO'])
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
# Remover duplicados
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
    )
])

# CALLBACKS MEDICAÇÃO________________________________________________________________________________________________________________________________



# Callback to Show/Hide Title and Filters Based on Selected Tab
@app.callback(
    [Output("medicacao-title", "children"),
     Output("medicacao-filters-container", "style")],
    Input("tabs", "active_tab")
)
def update_content(active_tab):
    if active_tab == "medicacao":
        return (
            html.Div(
                html.H1("Medicação", 
                        style={"color": "white", "margin": "0 auto", "padding": "10px", "textAlign": "left"}),
                style={"backgroundColor": "#8D0E19", "width": "100%", "padding": "0px", "margin": "0px"}
            ),
            {"display": "block"}  # Show the filters and graphs
        )
    else:
        return "", {"display": "none"}  # Hide the filters and graphs when another tab is selected

# Callbacks for updating the graphs
@app.callback(
    Output("barplot-cost-year", "figure"),
    Input("processo-dropdown", "value"),
    Input("medicamento-dropdown", "value"),
    Input("year-dropdown", "value")
)
def update_cost_barplot(selected_processes, selected_medications, selected_years):
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


@app.callback(
    Output("gantt-chart", "figure"),
    Input("tabs", "active_tab"),  # Trigger the callback when the active tab changes
    Input("processo-dropdown", "value"),  # Input for filtering by selected processes

    Input("medicamento-dropdown", "value")  # Input for filtering by selected medicamentos
)
def update_gantt_chart(active_tab, selected_processes, selected_medications):
    # Check if the active tab is 'medicacao', if not, return an empty figure
    if active_tab != "medicacao":  
        return go.Figure()

    # If no specific process is selected, show all processes
    if not selected_processes:  
        selected_processes = df_grouped["PROCESSO"].unique().tolist()  

    # Filter the data based on the selected processes
    filtered_df = df_grouped[df_grouped["PROCESSO"].isin(selected_processes)]

    # Filter by selected medication(s) if provided
    if selected_medications:
        filtered_df = filtered_df[filtered_df["DESIGN_ARTIGO"].isin(selected_medications)]

    # Create task names for the Gantt chart (combining process and medication design)
    filtered_df["Task"] = filtered_df["PROCESSO"].astype(str) + " - " + filtered_df["DESIGN_ARTIGO"]

    # Define distinct colors for each process
    color_palette = px.colors.qualitative.Set1  # A set of qualitative colors
    unique_processes = filtered_df["PROCESSO"].unique()
    color_map = {process: color_palette[i % len(color_palette)] for i, process in enumerate(unique_processes)}

    # Create the Gantt chart using plotly express
    fig = px.timeline(
        filtered_df, 
        x_start="Start", 
        x_end="Finish", 
        y="Task", 
        color="PROCESSO", 
        color_discrete_map=color_map  # Color mapping by process
    )

    # Reverse the y-axis for proper Gantt chart layout (top-to-bottom task order)
    fig.update_yaxes(autorange="reversed", title="Processo - Medicamento")
    fig.update_layout(coloraxis_showscale=False)  # Remove color scale legend

    return fig


@app.callback(
    Output("piechart-cost-distribution", "figure"),
    Input("processo-dropdown", "value"),
    Input("medicamento-dropdown", "value"),
    Input("year-dropdown", "value")
)
def update_piechart(selected_processes, selected_medications, selected_years):
    filtered_df = df.copy()

    # Filter based on selections
    if selected_processes:
        filtered_df = filtered_df[filtered_df["PROCESSO"].isin(selected_processes)]
    if selected_medications:
        filtered_df = filtered_df[filtered_df["DESIGN_ARTIGO"].isin(selected_medications)]
    if selected_years:
        filtered_df = filtered_df[filtered_df["Year"].isin(selected_years)]

    # Group by family or medication type for the pie chart
    df_cost_distribution = filtered_df.groupby("TIPO_DOCUMENTO")["VALOR"].sum().reset_index()

    fig = px.pie(df_cost_distribution, names="TIPO_DOCUMENTO", values="VALOR", title="Distribuição do custo por tipo de documento")
    return fig

# Callback for rendering content in the consultas tab
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab")
)
def render_tab_content(active_tab):
    if active_tab == "consultas":
        return html.Div([
            html.Div(
                html.H1("Consultas", 
                        style={"color": "white", "margin": "0 auto", "padding": "10px", "textAlign": "left"}),
                style={"backgroundColor": "#8D0E19", "width": "100%", "padding": "0px", "margin": "0px"}
            ),
            html.H2("Processos sem consulta há mais de 12 meses", className="mb-4 mt-3"),

            # DataTable for consultas without a consultation in the last 12 months
            dash_table.DataTable(
                columns=[{"name": col, "id": col} for col in df_alerta.columns],
                data=df_alerta.to_dict("records"),
                style_table={"overflowX": "auto"},
                style_cell={"textAlign": "left", "padding": "5px"},
                style_header={"backgroundColor": "#f5f5f5", "fontWeight": "bold"},
                page_size=10
            ),

            # Dropdown to filter by PROCESSO
            dbc.Row([
                dbc.Col([  # Ensure this dropdown is part of the consultas tab
                    html.Label("Selecione o Processo:"),
                    dcc.Dropdown(
                        id="processo-dropdown-consultas",  # Correct ID
                        options=[{"label": str(p), "value": p} for p in df_consultas["PROCESSO"].unique()],
                        multi=False,
                        placeholder="Select Processo"
                    )
                ], width=4)
            ], className="mb-4"),

            # Add a plot for consultations of the selected process
            dcc.Graph(id="consultas-plot")  # Correct ID
        ])
    return None

# Callback for consultas plot
@app.callback(
    Output("consultas-plot", "figure"),
    Input("processo-dropdown-consultas", "value")  # Ensure the dropdown ID matches
)
def update_consultas_plot(selected_process):
    if not selected_process:
        return go.Figure()

    filtered_df = df_consultas[df_consultas["PROCESSO"] == selected_process]

    # Create scatter plot with AGENDA_DESC as the color
    fig = px.scatter(filtered_df, 
                     x="DATACONSULTA", 
                     y="CODTIPOACTIVIDADE", 
                     color="AGENDA_DESC",  # Set color by AGENDA_DESC
                     title=f"Consultas do Processo {selected_process}",
                     labels={"DATACONSULTA": "Data da Consulta", 
                             "CODTIPOACTIVIDADE": "Tipo de Atividade",
                             "AGENDA_DESC": "Agenda Descrição"})

    fig.update_layout(
        xaxis_title="Data da Consulta",
        yaxis_title="Tipo de Atividade",
        showlegend=True  # Show the legend for different AGENDA_DESC values
    )

    return fig



# RUN APP_____________________________________________________________________________________________________________________________________________________________
server = app.server
if __name__ == "__main__":
    app.run_server(debug=True)
