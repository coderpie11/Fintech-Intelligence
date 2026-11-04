import yfinance as yf

tk = yf.Ticker("RELIANCE.NS")
df = tk.history(period="1mo", interval="1d", auto_adjust=False)
print(df[["Open", "High", "Low", "Close", "Volume"]].tail(10))
print("--- actions ---")
try:
    print(tk.actions.tail(6))
except Exception as e:
    print("actions err", e)
print("--- splits ---")
try:
    print(tk.splits.tail(6))
except Exception as e:
    print("splits err", e)

for sym in ("TCS.NS", "HDFCBANK.NS", "NIFTYBEES.NS", "GOLDBEES.NS", "BANKBEES.NS",
            "SILVERBEES.NS", "ITBEES.NS", "JUNIORBEES.NS", "LIQUIDBEES.NS",
            "CPSEETF.NS", "MON100.NS", "SETFNIF50.NS"):
    try:
        h = yf.Ticker(sym).history(period="5y", interval="1d", auto_adjust=False)
        last = h["Close"].iloc[-1] if len(h) else None
        print(sym, len(h), round(float(last), 2) if last is not None else None,
              str(h.index[-1].date()) if len(h) else "")
    except Exception as e:
        print(sym, "ERR", type(e).__name__, str(e)[:80])
