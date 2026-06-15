"""Stock universe for the investment-ideas scanner: S&P 500 + Nasdaq-100.

Tickers are normalized to Yahoo Finance format (e.g. BRK.B -> BRK-B).
Sourced from Wikipedia constituent lists (S&P 500, Nasdaq-100). Kept as a
static list so a single scan is reproducible; refresh periodically.
"""

# --- Nasdaq-100 ---
_NASDAQ100 = [
    "ADBE","AMD","ABNB","ALNY","GOOGL","GOOG","AMZN","AEP","AMGN","ADI","AAPL",
    "AMAT","APP","ARM","ASML","ADSK","ADP","AXON","BKR","BKNG","AVGO","CDNS",
    "CHTR","CTAS","CSCO","CCEP","CTSH","CMCSA","CEG","CPRT","COST","CRWD","CSX",
    "DDOG","DXCM","FANG","DASH","EA","EXC","FAST","FER","FTNT","GEHC","GILD",
    "HON","IDXX","INSM","INTC","INTU","ISRG","KDP","KLAC","KHC","LRCX","LIN",
    "LITE","MAR","MRVL","MELI","META","MCHP","MU","MSFT","MSTR","MDLZ","MPWR",
    "MNST","NFLX","NVDA","NXPI","ORLY","ODFL","PCAR","PLTR","PANW","PAYX","PYPL",
    "PDD","PEP","QCOM","REGN","ROP","ROST","SNDK","STX","SHOP","SBUX","SNPS",
    "TMUS","TTWO","TSLA","TXN","TRI","VRSK","VRTX","WMT","WBD","WDC","WDAY",
    "XEL","ZS",
]

# --- S&P 500 ---
_SP500 = [
    "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB",
    "AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN",
    "AMCR","AEE","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH","ADI",
    "AON","APA","APO","AAPL","AMAT","APP","APTV","ACGL","ADM","ARES","ANET",
    "AJG","AIZ","T","ATO","ADSK","ADP","AZO","AVB","AVY","AXON","BKR","BALL",
    "BAC","BAX","BDX","BRK-B","BBY","TECH","BIIB","BLK","BX","XYZ","BNY","BA",
    "BKNG","BSX","BMY","AVGO","BR","BRO","BF-B","BLDR","BG","BXP","CHRW","CDNS",
    "CPT","CPB","COF","CAH","CCL","CARR","CVNA","CASY","CAT","CBOE","CBRE","CDW",
    "COR","CNC","CNP","CF","CRL","SCHW","CHTR","CVX","CMG","CB","CHD","CIEN",
    "CI","CINF","CTAS","CSCO","C","CFG","CLX","CME","CMS","KO","CTSH","COHR",
    "COIN","CL","CMCSA","FIX","CAG","COP","ED","STZ","CEG","COO","CPRT","GLW",
    "CPAY","CTVA","CSGP","COST","CRH","CRWD","CCI","CSX","CMI","CVS","DHR","DRI",
    "DDOG","DVA","DECK","DE","DELL","DAL","DVN","DXCM","FANG","DLR","DG","DLTR",
    "D","DPZ","DASH","DOV","DOW","DHI","DTE","DUK","DD","ETN","EBAY","SATS",
    "ECL","EIX","EW","EA","ELV","EME","EMR","ETR","EOG","EQT","EFX","EQIX",
    "EQR","ERIE","ESS","EL","EG","EVRG","ES","EXC","EXE","EXPE","EXPD","EXR",
    "XOM","FFIV","FDS","FICO","FAST","FRT","FDX","FIS","FITB","FSLR","FE","FISV",
    "F","FTNT","FTV","FOXA","FOX","BEN","FCX","GRMN","IT","GE","GEHC","GEV",
    "GEN","GNRC","GD","GIS","GM","GPC","GILD","GPN","GL","GDDY","GS","HAL","HIG",
    "HAS","HCA","DOC","HSIC","HSY","HPE","HLT","HD","HON","HRL","HST","HWM","HPQ",
    "HUBB","HUM","HBAN","HII","IBM","IEX","IDXX","ITW","INCY","IR","PODD","INTC",
    "IBKR","ICE","IFF","IP","INTU","ISRG","IVZ","INVH","IQV","IRM","JBHT","JBL",
    "JKHY","J","JNJ","JCI","JPM","KVUE","KDP","KEY","KEYS","KMB","KIM","KMI",
    "KKR","KLAC","KHC","KR","LHX","LH","LRCX","LVS","LDOS","LEN","LII","LLY",
    "LIN","LYV","LMT","L","LOW","LULU","LITE","LYB","MTB","MPC","MAR","MRSH",
    "MLM","MAS","MA","MKC","MCD","MCK","MDT","MRK","META","MET","MTD","MGM",
    "MCHP","MU","MSFT","MAA","MRNA","TAP","MDLZ","MPWR","MNST","MCO","MS","MOS",
    "MSI","MSCI","NDAQ","NTAP","NFLX","NEM","NWSA","NWS","NEE","NKE","NI","NDSN",
    "NSC","NTRS","NOC","NCLH","NRG","NUE","NVDA","NVR","NXPI","ORLY","OXY","ODFL",
    "OMC","ON","OKE","ORCL","OTIS","PCAR","PKG","PLTR","PANW","PSKY","PH","PAYX",
    "PYPL","PNR","PEP","PFE","PCG","PM","PSX","PNW","PNC","POOL","PPG","PPL",
    "PFG","PG","PGR","PLD","PRU","PEG","PTC","PSA","PHM","PWR","QCOM","DGX","Q",
    "RL","RJF","RTX","O","REG","REGN","RF","RSG","RMD","RVTY","HOOD","ROK","ROL",
    "ROP","ROST","RCL","SPGI","CRM","SNDK","SBAC","SLB","STX","SRE","NOW","SHW",
    "SPG","SWKS","SJM","SW","SNA","SOLV","SO","LUV","SWK","SBUX","STT","STLD",
    "STE","SYK","SMCI","SYF","SNPS","SYY","TMUS","TROW","TTWO","TPR","TRGP","TGT",
    "TEL","TDY","TER","TSLA","TXN","TPL","TXT","TMO","TJX","TKO","TTD","TSCO",
    "TT","TDG","TRV","TRMB","TFC","TYL","TSN","USB","UBER","UDR","ULTA","UNP",
    "UAL","UPS","URI","UNH","UHS","VLO","VEEV","VTR","VLTO","VRSN","VRSK","VZ",
    "VRTX","VRT","VTRS","VICI","V","VST","VMC","WRB","GWW","WAB","WMT","DIS",
    "WBD","WM","WAT","WEC","WFC","WELL","WST","WDC","WY","WSM","WMB","WTW","WDAY",
    "WYNN","XEL","XYL","YUM","ZBRA","ZBH","ZTS",
]


def _normalize(t):
    """Yahoo uses '-' for share-class dots (BRK.B -> BRK-B)."""
    return t.strip().upper().replace(".", "-")


def universe(name="both"):
    """Return a deduplicated, Yahoo-normalized ticker list for the requested universe."""
    name = (name or "both").lower()
    if name == "sp500":
        src = _SP500
    elif name in ("nasdaq100", "ndx", "nasdaq"):
        src = _NASDAQ100
    else:  # both
        src = _SP500 + _NASDAQ100
    seen, out = set(), []
    for t in src:
        n = _normalize(t)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


# membership flags for display
_SP500_SET = {_normalize(t) for t in _SP500}
_NDX_SET = {_normalize(t) for t in _NASDAQ100}


def membership(ticker):
    t = _normalize(ticker)
    tags = []
    if t in _SP500_SET:
        tags.append("S&P 500")
    if t in _NDX_SET:
        tags.append("Nasdaq-100")
    return tags
