from jugaad_data.nse import NSELive
import yfinance as yf

n = NSELive()
sym = "EMBASSY"
page = n.s.get("https://www.nseindia.com/get-quotes/equity?symbol=" + sym, timeout=15)
print("page:", page.status_code)
r = n.s.get(n.base_url + "/quote-equity?symbol=" + sym, timeout=15)
print("api:", r.status_code)

d = yf.download(["EMBASSY.NS", "INDIGRID.NS", "NXST.NS", "MINDSPACE.NS"],
                period="5d", progress=False)
print(d.tail(3))
