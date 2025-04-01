import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, dash_table
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

# Create pivot table for SUM(QUANT) and SUM(VALOR) grouped by Year and TIPO_DOCUMENTO
df_pivot = df.pivot_table(
    index="Year", 
    columns="TIPO_DOCUMENTO", 
    values=["QUANT", "VALOR"], 
    aggfunc="sum"
).reset_index()

# Rename columns for better readability
df_pivot.columns = ["Year"] + [f"{col[0]} - {col[1]}" for col in df_pivot.columns[1:]]

# Dash App
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = dbc.Container([
    html.H1("Breast Cancer Medication Data", className="bg-secondary text-white p-2 mb-4"),

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

    # Gantt Chart
    dcc.Graph(id="gantt-chart"),

    # Bar plot
    dcc.Graph(id="cost-barplot"),

    # Data Table
    html.H4("Summary Table: Sum of QUANT & VALOR by Year and Document Type", className="mt-4"),
    dash_table.DataTable(
        id="summary-table",
        columns=[{"name": col, "id": col} for col in df_pivot.columns],
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'center'},
        page_size=10
    )
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

@app.callback(
    Output("summary-table", "data"),
    Input("processo-dropdown", "value")
)
def update_table(selected_processes):
    return df_pivot.to_dict("records")

if __name__ == "__main__":
    app.run_server(debug=True)
