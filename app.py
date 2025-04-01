import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc

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

# Dash App
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = dbc.Container([
    # Header with Logo
    dbc.Row([
        dbc.Col(html.Img(src="/assets/LOGOTIPO.jpg", height="60px"), width="auto"),
        dbc.Col(html.H1("Breast Cancer Medication Data", className="bg-secondary text-white p-2 mb-4"), width=True)
    ], align="center", className="mb-4"),  # Aligns logo and title

    # Sidebar with dropdown for filtering Gantt Chart
    dbc.Row([
        dbc.Col([
            html.Label("Select PROCESSO:"),
            dcc.Dropdown(
                id="processo-dropdown",
                options=[{"label": str(p), "value": p} for p in df_grouped["PROCESSO"].unique()],
                multi=True,
                placeholder="Filter by PROCESSO"
            )
        ], width=3),
    ], className="mb-4"),

    # Graphs
    dcc.Graph(id="gantt-chart"),
    dcc.Graph(id="cost-barplot")
])

@app.callback(
    Output("gantt-chart", "figure"),
    Input("processo-dropdown", "value")
)
def update_gantt_chart(selected_processes):
    if not selected_processes:  # Handles None and empty list cases
        selected_processes = df_grouped["PROCESSO"].unique().tolist()  # Show all processes if none selected

    filtered_df = df_grouped[df_grouped["PROCESSO"].isin(selected_processes)]

    # Generate task names
    filtered_df["Task"] = filtered_df["PROCESSO"].astype(str) + " - " + filtered_df["DESIGN_ARTIGO"]

    # Define distinct colors for each process
    color_palette = px.colors.qualitative.Set1  # Use Set1 for different colors
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

    # **Remove the color scale legend (if needed)**
    fig.update_layout(coloraxis_showscale=False)

    return fig

@app.callback(
    Output("cost-barplot", "figure"),
    Input("gantt-chart", "figure")  # Dummy input to trigger callback
)
def update_barplot(_):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_yearly_cost["Year"], y=df_yearly_cost["VALOR"], marker_color='royalblue'))
    fig.update_layout(title="Total Medication Cost Per Year", xaxis_title="Year", yaxis_title="Total Cost")
    return fig

# Expose the server object for Gunicorn
server = app.server

if __name__ == "__main__":
    app.run_server(debug=True)
