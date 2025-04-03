import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# Load data

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

# Create a Dash App
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Layout definition with Tabs
app.layout = dbc.Container([
    # Row for Logo and Tabs
    dbc.Row([
        # Logo Column (Left)
        dbc.Col([html.Img(src="/assets/LOGOTIPO.jpg", height="100px")], width="auto", className="p-0 m-0 d-flex align-items-center"),
        
        # Tabs Column (Right, Centered)
        dbc.Col([
            dbc.Tabs([
                dbc.Tab(label="Utentes", tab_id="utentes"),
                dbc.Tab(label="Consultas", tab_id="consultas"),
                dbc.Tab(label="Medicação", tab_id="medicacao")
            ], id="tabs", active_tab="medicacao")
        ], width="auto", className="p-0 m-0 d-flex align-items-center ms-auto")
    ], style={"backgroundColor": "#FFFFFF", "width": "100%", "height": "100px", "padding": "0px", "margin": "0px"}, align="center"),


    # Title Placeholder (Will be Updated Dynamically)
    dbc.Row([dbc.Col(id="medicacao-title", width=12)], className="w-100", style={"height": "50px"}),

    # Placeholder for Tab Content
    dbc.Row([dbc.Col(id="tab-content", width=12)]),

    # This Div holds the filters and graphs, and will be shown only when the "Medicação" tab is selected
    html.Div(
        dbc.Row([

            # Filters Row: Dropdowns for filtering
            dbc.Row([
                dbc.Col([html.Label("Select Processos:"),
                         dcc.Dropdown(id="processo-dropdown",
                                      options=[{"label": processo, "value": processo} for processo in df["PROCESSO"].unique()],
                                      multi=True, placeholder="Select Processos")], width=4),
                dbc.Col([html.Label("Select Medicamentos:"),
                         dcc.Dropdown(id="medicamento-dropdown",
                                      options=[{"label": medicamento, "value": medicamento} for medicamento in df["DESIGN_ARTIGO"].unique()],
                                      multi=True, placeholder="Select Medicamentos")], width=4),
                dbc.Col([html.Label("Select Year:"),
                         dcc.Dropdown(id="year-dropdown",
                                      options=[{"label": str(year), "value": year} for year in df["Year"].unique()],
                                      multi=True, placeholder="Select Year")], width=4)
            ], className="w-100"),

            # Graphs (Empty initially)
            dbc.Row([dbc.Col(dcc.Graph(id="barplot-cost-year"), width=6),
                     dbc.Col(dcc.Graph(id="piechart-cost-distribution"), width=6)]),

            # Gantt chart (Empty initially)
            dbc.Row([dbc.Col(dcc.Graph(id="gantt-chart"), width=12)]),

        ], id="medicacao-filters"),  # This div will be shown/hidden based on the active tab
        id="medicacao-filters-container"  # The container div for the filters
    )

])

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

    fig = px.bar(df_yearly_cost, x="Year", y="VALOR", title="Total Medication Cost Per Year")
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
    fig.update_yaxes(autorange="reversed", title="PROCESSO - DESIGN_ARTIGO")
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
    df_cost_distribution = filtered_df.groupby("DESIGNACAO_FAMILIA")["VALOR"].sum().reset_index()

    fig = px.pie(df_cost_distribution, names="DESIGNACAO_FAMILIA", values="VALOR", title="Cost Distribution by Medication Family")
    return fig


if __name__ == "__main__":
    app.run_server(debug=True)
