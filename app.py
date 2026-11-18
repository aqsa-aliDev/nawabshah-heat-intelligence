"""Nawabshah Heat Intelligence - Flask web application.
Run:  pip install -r requirements.txt   then   python app.py   ->  http://127.0.0.1:5000
"""
import datetime as dt, os, secrets, sqlite3, time
from functools import wraps
import numpy as np, pandas as pd, requests
from flask import Flask, abort, g, jsonify, redirect, render_template, request, session
from sklearn.ensemble import RandomForestRegressor
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
LAT, LON = 26.2483, 68.4097
app = Flask(__name__)
_key = os.path.join(BASE, ".secret_key")
if not os.path.exists(_key):
    open(_key, "w").write(secrets.token_hex(32))
app.secret_key = open(_key).read()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
DB = os.path.join(BASE, "users.db")

# ---------------- accounts ----------------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, name TEXT, pw TEXT)")
    return g.db


@app.teardown_appcontext
def close_db(_):
    if "db" in g:
        g.db.close()


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "user" not in session:
            return (jsonify(error="login"), 401) if request.path.startswith("/api") else redirect("/login")
        return f(*a, **k)
    return w


FAILS = {}  # ip -> (count, locked_until)


@app.route("/login", methods=["GET", "POST"])
def login():
    session.setdefault("csrf", secrets.token_hex(16))
    err, tab = None, "in"
    if request.method == "POST":
        if request.form.get("csrf") != session["csrf"]:
            abort(400)
        act, ip = request.form.get("action"), request.remote_addr
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if act == "guest":
            session["user"] = "Guest"
            return redirect("/")
        if act == "signup":
            tab, name = "up", request.form.get("name", "").strip()
            if not name or "@" not in email or "." not in email.split("@")[-1]:
                err = "Enter your name and a valid email."
            elif len(pw) < 8:
                err = "Password must be at least 8 characters."
            elif pw != request.form.get("password2"):
                err = "Passwords do not match."
            elif db().execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                err = "An account with this email already exists."
            else:
                db().execute("INSERT INTO users VALUES(?,?,?)", (email, name, generate_password_hash(pw)))
                db().commit()
                session["user"] = name
                return redirect("/")
        else:
            n, until = FAILS.get(ip, (0, 0))
            row = db().execute("SELECT name,pw FROM users WHERE email=?", (email,)).fetchone()
            if time.time() < until:
                err = "Too many attempts. Wait a minute and try again."
            elif row and check_password_hash(row[1], pw):
                FAILS.pop(ip, None)
                session["user"] = row[0]
                return redirect("/")
            else:
                n += 1
                FAILS[ip] = (0, time.time() + 60) if n >= 5 else (n, 0)
                err = "Wrong email or password."
    return render_template("login.html", err=err, tab=tab, csrf=session["csrf"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
@login_required
def home():
    return render_template("dashboard.html", user=session["user"])

# ---------------- data + models ----------------
DEFAULT_ZONES = pd.DataFrame([
    ("Old Bazaar", 26.2530, 68.4010, .92, .06, .14, 2.8, 24, .34),
    ("Station Road", 26.2475, 68.4075, .88, .08, .15, 2.2, 19, .30),
    ("Civil Lines", 26.2600, 68.4150, .45, .28, .24, 1.6, 8, .12),
    ("Sakrand Road", 26.2390, 68.4200, .70, .14, .19, 1.1, 17, .28),
    ("Housing Society", 26.2650, 68.4000, .55, .22, .22, 2.4, 11, .10),
    ("Industrial Area", 26.2350, 68.3950, .85, .05, .12, 3.0, 9, .22),
    ("Medical College", 26.2560, 68.4260, .50, .30, .23, 0.9, 6, .09),
    ("Katchi Abadi East", 26.2440, 68.4320, .90, .04, .13, 0.6, 26, .45),
    ("Canal Colony", 26.2700, 68.4180, .40, .38, .25, 0.3, 7, .15),
    ("Bus Terminal", 26.2420, 68.4110, .94, .03, .12, 1.8, 14, .27),
    ("Agri Edge North", 26.2780, 68.4080, .18, .55, .27, 0.4, 3, .18),
    ("Railway Quarters", 26.2500, 68.3900, .72, .12, .18, 2.9, 12, .25),
], columns=["zone", "lat", "lon", "built", "ndvi", "albedo", "water_km", "pop_k", "vulnerable"])


def load_zones():
    """Uses nawabshah_neighborhoods_demo.csv if it has the same column names, else built-in zones."""
    try:
        d = pd.read_csv(os.path.join(BASE, "nawabshah_neighborhoods_demo.csv"))
        if set(DEFAULT_ZONES.columns) <= set(d.columns):
            return d[list(DEFAULT_ZONES.columns)]
    except Exception:
        pass
    return DEFAULT_ZONES


ZONES = load_zones()
FEATS = ["built", "ndvi", "albedo", "water_km", "air_t", "rh", "wind"]
LABELS = ["Built-up share", "Vegetation (NDVI)", "Surface reflectivity", "Distance to water",
          "Air temperature", "Humidity", "Wind"]


def uhi_physics(built, ndvi, albedo, water_km, air_t, rh, wind):
    return (4.2 * built - 3.5 * ndvi - 5.0 * (albedo - .15) + 0.45 * water_km
            + 0.06 * (air_t - 30) * built - 0.35 * np.log1p(wind) - 0.01 * (rh - 40))


def train_zone_model():
    r = np.random.default_rng(7)
    n = 4000
    X = pd.DataFrame({"built": r.uniform(.1, 1, n), "ndvi": r.uniform(0, .6, n), "albedo": r.uniform(.1, .3, n),
                      "water_km": r.uniform(0, 3.5, n), "air_t": r.uniform(25, 50, n),
                      "rh": r.uniform(15, 85, n), "wind": r.uniform(.3, 7, n)})
    y = uhi_physics(**X.to_dict("series")) + r.normal(0, .25, n)
    return RandomForestRegressor(200, min_samples_leaf=3, random_state=1, n_jobs=-1).fit(X[FEATS], y)


ZONE_MODEL = train_zone_model()


def felt_temp(t, rh):
    t = np.asarray(t, dtype=float)
    return t + 0.33 * (rh / 100 * 6.105 * np.exp(17.27 * t / (237.7 + t))) - 4.0


def level(ft):
    return "Low" if ft < 35 else "Moderate" if ft < 43 else "High" if ft < 51 else "Extreme"


def predict(df, t, rh, wind):
    X = df[["built", "ndvi", "albedo", "water_km"]].assign(air_t=t, rh=rh, wind=wind)[FEATS]
    o = df.copy()
    o["uhi"] = ZONE_MODEL.predict(X)
    o["felt"] = felt_temp(t + o["uhi"], rh)
    o["level"] = o["felt"].map(level)
    o["score"] = (np.clip((o["felt"] - 30) / 30, 0, 1) * 80 + o["vulnerable"] * 20).round(0)
    return o

# ---- NASA POWER: download, cache, train, forecast ----
CACHE = os.path.join(BASE, "nasa_power_nawabshah.csv")
COLS = ["t", "rh", "ws", "sw"]


def nasa_history():
    fresh = os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < 86400
    if not fresh:
        end = dt.date.today() - dt.timedelta(days=3)
        for community in ("AG", "RE"):
            try:
                u = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MAX,RH2M,WS2M,"
                     f"ALLSKY_SFC_SW_DWN&community={community}&longitude={LON}&latitude={LAT}"
                     f"&start=20150101&end={end:%Y%m%d}&format=JSON")
                p = requests.get(u, timeout=60).json()["properties"]["parameter"]
                df = pd.DataFrame(p)
                df.index = pd.to_datetime(df.index, format="%Y%m%d")
                df = df.where(df > -900).dropna()
                if len(df) > 500:
                    df.to_csv(CACHE)
                    break
            except Exception:
                pass
    if os.path.exists(CACHE):
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)
    return None


def make_xy(d):
    X = pd.DataFrame({f"{c}_{k}": d[c].shift(k) for k in range(3) for c in COLS})
    doy = d.index.dayofyear
    X["s"], X["c"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    return X, d["t"].shift(-1)


def nasa_model():
    raw = nasa_history()
    if raw is None:
        return None
    d = raw.rename(columns={"T2M_MAX": "t", "RH2M": "rh", "WS2M": "ws", "ALLSKY_SFC_SW_DWN": "sw"})[COLS]
    X, y = make_xy(d)
    ok = y.notna() & X.notna().all(axis=1)
    X, y = X[ok], y[ok]
    rf = lambda: RandomForestRegressor(300, min_samples_leaf=3, random_state=1, n_jobs=-1)
    m = rf().fit(X[:-365], y[:-365])
    mae = float(np.abs(m.predict(X[-365:]) - y[-365:]).mean())
    base = float(np.abs(X["t_0"][-365:] - y[-365:]).mean())
    model = rf().fit(X, y)
    today = pd.Timestamp(dt.date.today())
    hist = d.copy()
    for _ in range(max(1, (today - hist.index[-1]).days) + 2):
        xr, _y = make_xy(hist)
        nxt = hist.iloc[-1].copy()
        nxt["t"] = model.predict(xr.iloc[[-1]])[0]
        hist.loc[hist.index[-1] + pd.Timedelta(days=1)] = nxt
    fc = hist.iloc[len(d):]["t"]
    peak = float(fc[fc.index >= today].max())
    dist = np.abs(d.index.dayofyear - today.dayofyear)
    near = d[np.minimum(dist, 365 - dist) <= 10]["t"]
    h = d.iloc[-30:]
    return dict(peak=round(peak, 1), p95=round(float(near.quantile(.95)), 1), typical=round(float(near.median()), 1),
                mae=round(mae, 2), base=round(base, 2), days=len(d), source=os.path.basename(CACHE),
                hot=peak > float(near.quantile(.95)), rh=float(d["rh"].iloc[-3:].mean()), ws=float(d["ws"].iloc[-3:].mean()),
                hist_dates=[x.strftime("%d %b") for x in h.index], hist=[round(v, 1) for v in h["t"]],
                fc_dates=[x.strftime("%d %b") for x in fc.index], fc=[round(float(v), 1) for v in fc])


_FC = {"at": 0, "v": None}


def forecast():
    if time.time() - _FC["at"] > 6 * 3600:
        _FC["v"], _FC["at"] = nasa_model(), time.time()
    return _FC["v"]


def num(name, default, lo, hi):
    try:
        return float(np.clip(float(request.args.get(name, default)), lo, hi))
    except ValueError:
        return float(default)


def scenario():
    fc = forecast()
    d = (round(fc["peak"] * 2) / 2, round(fc["rh"]), round(fc["ws"], 1)) if fc else (42.0, 35, 2.0)
    return (num("t", d[0], 25, 50), num("rh", d[1], 10, 90), num("ws", d[2], .3, 8)), fc

# ---------------- API ----------------
@app.route("/api/state")
@login_required
def state():
    (t, rh, ws), fc = scenario()
    res = predict(ZONES, t, rh, ws).sort_values("score", ascending=False).round(3)
    imp = sorted(zip(LABELS, ZONE_MODEL.feature_importances_), key=lambda x: -x[1])
    pick = [res.zone.iloc[0], res.zone.iloc[len(res) // 2], res.zone.iloc[-1]]
    sweep = {z: [] for z in pick}
    temps = list(range(30, 51, 2))
    for tt in temps:
        p = predict(ZONES, tt, rh, ws).set_index("zone")
        for z in pick:
            sweep[z].append(round(float(felt_temp(tt + p.loc[z, "uhi"], rh)), 1))
    hi = res["level"].isin(["High", "Extreme"])
    return jsonify(params=dict(t=t, rh=rh, ws=ws), zones=res.to_dict("records"),
                   city_level=level(res.felt.max()), n_high=int(hi.sum()),
                   exposed=int(res.loc[hi, "pop_k"].sum() * 1000), uhi_avg=round(float(res.uhi.mean()), 1),
                   gap=round(float(res.uhi.max() - res.uhi.min()), 1), forecast=fc,
                   importance=[[a, round(float(b), 3)] for a, b in imp], sweep=dict(temps=temps, series=sweep))


@app.route("/api/whatif")
@login_required
def whatif():
    (t, rh, ws), _ = scenario()
    z0 = ZONES[ZONES.zone == request.args.get("zone", "")]
    if z0.empty:
        abort(404)
    tree, roof = num("tree", .15, 0, .4), num("roof", .08, 0, .15)
    z1 = z0.assign(ndvi=(z0.ndvi + tree).clip(upper=.7), albedo=(z0.albedo + roof).clip(upper=.4))
    a, b = predict(z0, t, rh, ws).iloc[0], predict(z1, t, rh, ws).iloc[0]
    return jsonify(before=dict(felt=round(float(a.felt), 1), level=a.level),
                   after=dict(felt=round(float(b.felt), 1), level=b.level), people=int(z0.pop_k.iloc[0] * 1000))


if __name__ == "__main__":
    forecast()  # download + train once at start-up
    app.run(debug=False, host="127.0.0.1", port=5000)
