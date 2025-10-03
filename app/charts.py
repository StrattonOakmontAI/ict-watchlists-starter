import plotly.graph_objects as go


def render_chart(df, zones: list[dict], entry=None, stop=None, targets=None) -> bytes:
fig = go.Figure()
fig.add_trace(go.Candlestick(x=df.index, open=df.open, high=df.high, low=df.low, close=df.close))
for z in zones:
fig.add_shape(type='rect', x0=z.get('x0', df.index[0]), x1=z.get('x1', df.index[-1]),
y0=z['low'], y1=z['high'], opacity=0.2)
if entry is not None and stop is not None:
fig.add_hline(y=entry)
fig.add_hline(y=stop)
if targets:
for t in targets:
fig.add_hline(y=t)
fig.update_layout(xaxis_rangeslider_visible=False, height=600, width=1000)
return fig.to_image(format='png')
