"""UV-Vis keys of the payload read by origin_build.py: baseline, %T, Tauc/Urbach columns and fit rows."""
from __future__ import annotations

from core.dataset import Dataset
from core.origin_bridge import ordered

from . import analysis as an

DEFAULTS = {"ref_nm": 850.0, "a_max": 3.0, "n": 0.5, "tauc": False,
            "edge_min_nm": 300.0, "edge_window_nm": 45.0}


def build_payload(payload: dict, datasets: list[Dataset], options: dict) -> None:
    o = {**DEFAULTS, **options}
    ref, a_max, n, do_tauc = o["ref_nm"], o["a_max"], o["n"], o["tauc"]
    # thickness is used only if every sample has one (otherwise alpha would mix units)
    use_d = do_tauc and all(d.meta.get("d_nm") for d in datasets)
    payload["ref_nm"] = ref
    series = [s for g in payload["groups"] for s in g["series"]]
    for ds, s in zip(ordered(payload, datasets), series):
        y_corr, v = an.baseline(ds.x, ds.y, ref)
        s["lam"] = ds.x.tolist()
        s["y_corr"] = y_corr.tolist()
        s["T"] = an.transmittance(ds.y).tolist()
        s["base_value"] = v
        if do_tauc:
            rng = ds.meta.get("tauc_range") or an.suggest_range(
                ds.x, y_corr, ds.y, a_max, width=o["edge_window_nm"], lam_min=o["edge_min_nm"])
            d_nm = ds.meta.get("d_nm") if use_d else None
            r = an.tauc_analysis(ds.x, ds.y, y_corr, n, d_nm, rng, a_max)
            s["d_nm"] = d_nm
            s["tauc_range"] = [float(rng[0]), float(rng[1])]
            s["tauc"] = {"e": r.e.tolist(), "alpha": r.alpha.tolist(), "ty": r.ty.tolist(),
                         "ln_alpha": r.ln_alpha.tolist(),
                         "rows": list(r.tauc.rows) if r.tauc else None,
                         "urows": list(r.urbach.rows) if r.urbach else None}
    if do_tauc:
        payload["tauc"] = {"exponent": an.EXPONENT_LABEL[n], "has_thickness": use_d,
                           "label": next(k for k, v in an.TRANSITIONS.items() if v == n),
                           "urbach_max": an.URBACH_MAX_MEV}
