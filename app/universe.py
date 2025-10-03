from pathlib import Path


def load_universe() -> list[str]:
custom = Path("app/data/universe/Heatseeker_WL.txt")
if custom.exists():
syms = [s.strip().upper() for s in custom.read_text().splitlines() if s.strip()]
return sorted(list(dict.fromkeys(syms)))
# fallback core list (liquid, optionable)
return ["SPY","QQQ","IWM","AAPL","MSFT","NVDA","AMZN","META","TSLA","GOOGL","AMD","NFLX","BA","JPM","INTC"]
