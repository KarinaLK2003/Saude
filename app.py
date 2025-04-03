import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc

#______________________________________________________________DATA TRANSFORMATION
# Load data
ficheiro_excel = 'Cancro_da_Mama_dados_03-01-2025.xlsx'
df = pd.read_excel(ficheiro_excel, sheet_name='medicação')
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

#_________________________________________________________________DASH APP
# Dash App
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)

app.layout = dbc.Container([
    # Row for Logo and Tabs
    dbc.Row([
        # Logo Column (Left)
        dbc.Col([
            html.Img(src="/assets/LOGOTIPO.jpg", height="100px")
        ], width="auto", className="p-0 m-0 d-flex align-items-center"),

        # Tabs Column (Right, Centered)
        dbc.Col([
            dbc.Tabs(
                [
                    dbc.Tab(label="Utentes", tab_id="utentes"),
                    dbc.Tab(label="Consultas", tab_id="consultas"),
                    dbc.Tab(label="Medicação", tab_id="medicacao")
                ],
                id="tabs",
                active_tab="medicacao"
            )
        ], width="auto", className="p-0 m-0 d-flex align-items-center ms-auto")
    ], 
    style={"backgroundColor": "#FFFFFF", "width": "100%", "height": "100px", "padding": "0px", "margin": "0px"},
    align="center"),

    # Title Placeholder (Will be Updated Dynamically)
    dbc.Row([
        dbc.Col(id="medicacao-title", width=12)
    ], className="w-100", style={"height": "50px"}),  

    # Placeholder for Tab Content
    dbc.Row([
        dbc.Col(id="tab-content", width=12)
    ]),

], fluid=True)  # Full-width container


# Callback to Show/Hide Title Based on Selected Tab
@app.callback(
    Output("medicacao-title", "children"),
    Input("tabs", "active_tab")
)
def update_title(active_tab):
    if active_tab == "medicacao":
        return html.Div(
            html.H1("Medicação", 
                    style={"color": "white", "margin": "0 auto", "padding": "10px", "textAlign": "left"}),
            style={"backgroundColor": "#8D0E19", "width": "100%", "padding": "0px", "margin": "0px"}
        )
            
    else:
        return "" 

# Callback to render content based on selected tab
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab")
)
def render_tab_content(active_tab):
    if active_tab == "utentes":
        return html.P("Content for Utentes")  
    elif active_tab == "consultas":
        return html.P("Content for Consultas")  
    elif active_tab == "medicacao":
        return dbc.Container([
            # Sidebar with dropdown for filtering Gantt Chart
            dbc.Row([
                dbc.Col([
                    html.Label("Selecione o número do processo:", style={"paddingTop": "40px"}),
                    dcc.Dropdown(
                        id="processo-dropdown",
                        options=[{"label": str(p), "value": p} for p in df_grouped["PROCESSO"].unique()],
                        multi=True,
                        placeholder="Filtrar por processo"
                    )
                ], width=3),
            ], className="mb-4"),

            # Graphs
            dcc.Graph(id="gantt-chart"),
            dcc.Graph(id="cost-barplot"),
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H4("Total Dispensações"), html.H3(len(df))
                ])), width=2),

                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H4("Valor Total (€)"), html.H3(f"{df['VALOR'].sum():,.2f}")
                ])), width=2),

                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H4("Média por Dispensação"), html.H3(f"{df['QUANT'].mean():.1f}")
                ])), width=2),
            ]),
            

        ], fluid=True)  
    
    return html.P("Select a tab")  


# Callbacks for graphs
@app.callback(
    Output("gantt-chart", "figure"),
    Input("tabs", "active_tab"), 
    Input("processo-dropdown", "value")
)
def update_gantt_chart(active_tab, selected_processes):
    if active_tab != "medicacao":  
        return go.Figure()

    if not selected_processes:  
        selected_processes = df_grouped["PROCESSO"].unique().tolist()  

    filtered_df = df_grouped[df_grouped["PROCESSO"].isin(selected_processes)]

    # Generate task names
    filtered_df["Task"] = filtered_df["PROCESSO"].astype(str) + " - " + filtered_df["DESIGN_ARTIGO"]

    # Define distinct colors for each process
    color_palette = px.colors.qualitative.Set1  
    unique_processes = filtered_df["PROCESSO"].unique()
    color_map = {process: color_palette[i % len(color_palette)] for i, process in enumerate(unique_processes)}

    # Create the timeline chart
    fig = px.timeline(
        filtered_df, 
        x_start="Start", 
        x_end="Finish", 
        y="Task", 
        color="PROCESSO", 
        color_discrete_map=color_map
    )

    fig.update_yaxes(autorange="reversed", title="PROCESSO - DESIGN_ARTIGO")
    fig.update_layout(coloraxis_showscale=False)

    return fig


@app.callback(
    Output("cost-barplot", "figure"),
    Input("tabs", "active_tab"),  
    Input("gantt-chart", "figure")
)
def update_barplot(active_tab, _):
    if active_tab != "medicacao":  # Prevent updates for other tabs
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_yearly_cost["Year"], y=df_yearly_cost["VALOR"], marker_color='royalblue'))
    fig.update_layout(title="Total Medication Cost Per Year", xaxis_title="Year", yaxis_title="Total Cost")
    return fig


# Expose the server object for Gunicorn
server = app.server

if __name__ == "__main__":
    app.run_server(debug=True)
