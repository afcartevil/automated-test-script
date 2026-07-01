import sys
import os
from datetime import timedelta
import numpy as np
import dash
from dash import dcc, html, Input, Output
import plotly.graph_objs as go
from pypowertool.pt5reader import PT5Reader

# Usage: python compare_pt5.py <file1.pt5> <file2.pt5> [timezone_offset_hours]
if len(sys.argv) < 3:
    print("Usage: python compare_pt5.py <pt5_file1> <pt5_file2> [timezone_offset_hours]")
    sys.exit(1)
file1, file2 = sys.argv[1], sys.argv[2]
try:
    tz = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
except ValueError:
    tz = 0.0

# Preload and downsample data
delta = timedelta(hours=tz)
r1 = PT5Reader(file1, delta)
r2 = PT5Reader(file2, delta)


def extract(reader):
    data = reader.get_interval_averages_fast(0, reader.header.duration, 1.0)
    times = np.array([(t0 - reader.header.captureDate).total_seconds() for t0, _, _, _ in data])
    curr = np.array([d[2] for d in data])
    volt = np.array([d[3] for d in data])
    power = curr * volt
    return {'time': times, 'current_mA': curr, 'voltage_V': volt, 'power_mW': power}


buf1 = extract(r1)
buf2 = extract(r2)

# Compute overall averages
avg1_i, avg1_v, _ = r1.get_overall_average()
avg2_i, avg2_v, _ = r2.get_overall_average()
avg_map1 = {
    'current_mA': avg1_i,
    'voltage_V': avg1_v,
    'power_mW': (avg1_i * avg1_v) if avg1_i and avg1_v else None
}
avg_map2 = {
    'current_mA': avg2_i,
    'voltage_V': avg2_v,
    'power_mW': (avg2_i * avg2_v) if avg2_i and avg2_v else None
}

# Dash app setup
app = dash.Dash(__name__)
server = app.server
app.layout = html.Div(style={'fontFamily': 'Arial', 'margin': '20px'}, children=[
    html.H1('PT5 文件对比分析', style={'textAlign': 'center', 'marginBottom': '20px'}),
    html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '10px', 'alignItems': 'center'}, children=[
        html.Label('波形:'),
        dcc.Dropdown(id='param', options=[
            {'label': '电流 (mA)', 'value': 'current_mA'},
            {'label': '电压 (V)', 'value': 'voltage_V'},
            {'label': '功率 (mW)', 'value': 'power_mW'}
        ], value='current_mA', clearable=False, style={'width': '200px'}),
        html.Label('偏移 (hh:mm:ss)：'),
        dcc.Input(id='base', type='text', value='00:00:00', debounce=True, style={'width': '120px'}),
        html.Label('微调 (秒)：'),
        html.Div([
            dcc.Slider(id='slider', min=-120, max=120, step=0.1, value=0, updatemode='mouseup'),
        ], style={'width': '400px'}),
        html.Label('交互模式：'),
        dcc.RadioItems(id='mode', options=[
            {'label': '选择', 'value': 'select'},
            {'label': '缩放', 'value': 'zoom'}
        ], value='select', inline=True),
        html.Button('清除区间', id='clear-btn', n_clicks=0)
    ]),
    dcc.Graph(id='graph', config={'displayModeBar': True}, style={'height': '600px'}),
    html.Div(id='selection-info', style={'marginTop': '10px', 'fontSize': '16px'})
])


# Callback: update graph
@app.callback(
    Output('graph', 'figure'),
    [Input('param', 'value'), Input('base', 'value'), Input('slider', 'value'), Input('mode', 'value'),
     Input('clear-btn', 'n_clicks')]
)
def update_graph(param, base, slider, mode, clear_clicks):
    # compute offset
    try:
        h, m, s = map(int, base.split(':'))
        base_sec = h * 3600 + m * 60 + s
    except:
        base_sec = 0
    offset = base_sec + slider
    # data arrays
    t1, y1 = buf1['time'], buf1[param]
    t2, y2 = buf2['time'], buf2[param]
    y2i = np.interp(t1, t2 + offset, y2, left=np.nan, right=np.nan)
    diff = y1 - y2i
    # customdata for hover
    file1_times = [(r1.header.captureDate + timedelta(seconds=tt)).strftime('%Y-%m-%d %H:%M:%S') for tt in t1]
    file2_times = [(r2.header.captureDate + timedelta(seconds=(tt - offset))).strftime('%Y-%m-%d %H:%M:%S') for tt in
                   t1]
    custom = list(zip(file1_times, file2_times, y1, y2i, diff))
    name1, name2 = os.path.basename(file1), os.path.basename(file2)
    hovertemplate = (
        'Rel Time: %{x:.3f}s<br>'
        'File1: %{customdata[0]} %{customdata[2]:.3f}<br>'
        'File2: %{customdata[1]} %{customdata[3]:.3f}<br>'
        'Diff: %{customdata[4]:.3f}<extra></extra>'
    )
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=t1, y=y1, mode='lines', name=name1, customdata=custom, hovertemplate=hovertemplate))
    fig.add_trace(go.Scattergl(x=t1, y=y2i, mode='lines', name=name2))
    fig.update_layout(
        xaxis_title='Time (s)', yaxis_title=param,
        hovermode='x unified', dragmode=mode,
        margin={'l': 50, 'r': 20, 't': 20, 'b': 50}
    )
    return fig


# Callback: selection info
@app.callback(
    Output('selection-info', 'children'),
    [Input('graph', 'selectedData'), Input('param', 'value'), Input('base', 'value'),
     Input('slider', 'value'), Input('mode', 'value'), Input('clear-btn', 'n_clicks')]
)
def update_selection(selectedData, param, base, slider, mode, clear_clicks):
    ctx = dash.callback_context
    # clear action
    if ctx.triggered and 'clear-btn' in ctx.triggered[0]['prop_id']:
        return '未选择区间'
    # only when in select mode
    if mode != 'select':
        return '未选择区间'
    # no selection
    if not selectedData or 'range' not in selectedData:
        return '未选择区间'
    # parse interval
    try:
        x0, x1 = selectedData['range']['x']
        h, m, s = map(int, base.split(':'))
        base_sec = h * 3600 + m * 60 + s
    except:
        return '无法解析区间或偏移'
    offset = base_sec + slider
    t1, y1 = buf1['time'], buf1[param]
    t2, y2 = buf2['time'], buf2[param]
    y2i = np.interp(t1, t2 + offset, y2, left=np.nan, right=np.nan)
    mask = (t1 >= x0) & (t1 <= x1)
    if not mask.any():
        return '区间超出数据范围'
    if np.isnan(y2i[mask]).any():
        return '区间包含未对齐数据，无法展示汇总'
    avg1 = np.nanmean(y1[mask])
    avg2 = np.nanmean(y2i[mask])
    duration = x1 - x0
    return (
        f"区间: {x0:.3f}s - {x1:.3f}s | 时长: {duration:.3f}s | 平均: {avg1:.3f} vs {avg2:.3f}, 差值: {avg1 - avg2:.3f}")


if __name__ == '__main__':
    app.run(
        debug=False,
        use_reloader=False,
        dev_tools_ui=False,
        dev_tools_props_check=False
    )
