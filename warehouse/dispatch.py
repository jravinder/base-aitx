"""Perfect-foresight battery dispatch, as a linear program (scipy HiGHS). UPPER BOUND by construction:
the battery knows every price of the day in advance and pays no degradation cost.

One Base battery: 39.2 kWh, 10 kW (sim/fleet.py), 90% round trip (sqrt(0.9) each way, an assumption).
Each local day is its own block: the day starts and ends at the reserve floor, so no energy is
carried between days. Days with 23 or 25 hours (DST) are handled because blocks have any length.

Energy only:      max sum p_t (d_t - c_t) dt
Energy + AS:      adds hourly capacity offers a_k (k = RegUp, RegDn, RRS, ECRS, NonSpin), paid the
                  DAM AS clearing price ($/MW per hour). Deployment energy is ignored (capacity only).
  headroom        d - c + RegUp + RRS + ECRS + NonSpin <= P      c - d + RegDn <= P
  energy backing  SOC_start - floor >= dt * sum(a_k * duration_k) over the up services
                  cap - SOC_start   >= dt * RegDn * duration
  Assumed durations (hours of energy behind each MW offered): Reg 1, RRS 1, ECRS 1, NonSpin 4.
  The reserve floor shrinks the up-service energy backing; it does not limit RegDn.
"""
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

CAP_KWH, P_KW = 39.2, 10.0
ETA = 0.9 ** 0.5
AS_UP = {"regup": 1.0, "rrs": 1.0, "ecrs": 1.0, "nspin": 4.0}
AS_DN = {"regdn": 1.0}


def solve(price, day, dt=1.0, floor=0.3, as_prices=None, energy=True, cap=CAP_KWH, pkw=P_KW):
    """price: $/MWh per interval (n,), day: block id per interval (sorted, contiguous).
    as_prices: dict service -> $/MW-h per interval, or None. Returns dict of arrays (kW, kWh, $)."""
    n = len(price)
    services = list(AS_UP) + list(AS_DN) if as_prices is not None else []
    k = len(services)
    # variable layout: c (n), d (n), soc_end (n), a_s (n each)
    nv = 3 * n + k * n
    C, D, S = 0, n, 2 * n
    A = {s: 3 * n + i * n for i, s in enumerate(services)}
    fl, top = floor * cap, cap
    # objective (minimise negative $): $/MWh * kW * h / 1000 = $
    obj = np.zeros(nv)
    obj[C:C + n] = price * dt / 1000.0
    obj[D:D + n] = -price * dt / 1000.0
    for s in services:
        obj[A[s]:A[s] + n] = -np.asarray(as_prices[s]) * dt / 1000.0
    idx = np.arange(n)
    first = np.r_[True, day[1:] != day[:-1]]
    last = np.r_[day[1:] != day[:-1], True]
    # SOC balance: soc_t - soc_{t-1} - eta c dt + d dt / eta = 0   (soc_{-1} = floor at a day start)
    rows, cols, vals = [idx, idx, idx], [S + idx, C + idx, D + idx], [np.ones(n), -ETA * dt * np.ones(n), dt / ETA * np.ones(n)]
    nf = ~first
    rows.append(idx[nf]); cols.append(S + idx[nf] - 1); vals.append(-np.ones(nf.sum()))
    Aeq = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, nv))
    beq = np.where(first, fl, 0.0)
    # inequalities
    ub_r, ub_c, ub_v, ub_b = [], [], [], []
    r0 = 0

    def add(cl, vl, b):
        nonlocal r0
        m = len(b)
        for c_, v_ in zip(cl, vl):
            ub_r.append(r0 + np.arange(m)); ub_c.append(c_); ub_v.append(v_)
        ub_b.append(b)
        r0 += m

    if k:
        up = [A[s] + idx for s in AS_UP]
        add([D + idx, C + idx] + up, [np.ones(n), -np.ones(n)] + [np.ones(n)] * len(up), np.full(n, pkw))
        add([C + idx, D + idx, A["regdn"] + idx], [np.ones(n), -np.ones(n), np.ones(n)], np.full(n, pkw))
        # energy backing uses SOC at the start of the interval: soc_{t-1}, or the floor at a day start
        prev_c = [A[s] + idx for s in AS_UP]
        prev_v = [np.full(n, dt * AS_UP[s]) for s in AS_UP]
        # dt*sum(a*dur) - soc_{t-1} <= -floor  (for t not first);  dt*sum(a*dur) <= 0 at first (soc=floor)
        cl, vl = list(prev_c), list(prev_v)
        sel = np.where(nf)[0]
        cl.append(S + np.where(nf, idx - 1, 0)); vl.append(np.where(nf, -1.0, 0.0))
        add(cl, vl, np.where(nf, -fl, 0.0))
        # dt*regdn*dur + soc_{t-1} <= cap   (first: floor + ... <= cap)
        add([A["regdn"] + idx, S + np.where(nf, idx - 1, 0)], [np.full(n, dt * AS_DN["regdn"]), np.where(nf, 1.0, 0.0)],
            np.where(nf, top, top - fl))
        del sel
    Aub = sp.csr_matrix((np.concatenate(ub_v), (np.concatenate(ub_r), np.concatenate(ub_c))), shape=(r0, nv)) if r0 else None
    bub = np.concatenate(ub_b) if r0 else None
    bounds = np.zeros((nv, 2))
    bounds[C:D, 1] = bounds[D:S, 1] = pkw if energy else 0.0
    bounds[S:S + n, 0], bounds[S:S + n, 1] = fl, top
    bounds[S + idx[last], 1] = fl            # each day ends at the floor
    for s in services:
        bounds[A[s]:A[s] + n, 1] = pkw
    res = linprog(obj, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq, bounds=bounds, method="highs")
    assert res.status == 0, res.message
    x = res.x
    out = {"charge_kw": x[C:C + n], "discharge_kw": x[D:D + n], "soc_kwh": x[S:S + n],
           "energy_usd": price * (x[D:D + n] - x[C:C + n]) * dt / 1000.0}
    for s in services:
        out[f"{s}_kw"] = x[A[s]:A[s] + n]
        out[f"{s}_usd"] = np.asarray(as_prices[s]) * x[A[s]:A[s] + n] * dt / 1000.0
    return out
