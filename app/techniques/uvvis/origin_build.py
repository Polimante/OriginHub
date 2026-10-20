"""UV-Vis inside Origin (embedded Python 3.11, no numpy): sheets, graphs, Tauc/Urbach Linear Fits."""
import math

import originpro as op
from origin_common import (
    LEGEND_BOTTOM_RIGHT,
    LEGEND_TOP_RIGHT,
    PALETTE,
    fill_xy_sheet,
    fitlr,
    is_num,
    line_graph,
    live_label,
    log,
    native_linear_fit,
    new_graph,
    rc,
    style_fit_curve,
)


def build(cfg):
    groups = cfg["groups"]
    book = op.new_book("w", lname="ABS")
    raw = book[0]
    raw.name = "Raw"
    base = book.add_sheet("Baseline")
    trans = book.add_sheet("Transmittance")

    ref = cfg.get("ref_nm", 850)
    p_raw = fill_xy_sheet(raw, groups, "y", "a.u.")
    p_base = fill_xy_sheet(base, groups, "y_corr", "a.u.")
    p_tr = fill_xy_sheet(trans, groups, "T", "%")

    # subtracted values: separate columns at the end of the sheet (not plotted;
    # Comments would become the legend text)
    allser = [s for g in groups for s in g["series"]]
    c0 = len(p_base) + len(groups)
    base.from_list(c0, [s["name"] for s in allser], lname="Sample", axis="N")
    base.from_list(c0 + 1, [s["base_value"] for s in allser],
                   lname="A(%g nm) subtracted" % ref, units="a.u.", axis="N")

    line_graph(raw, p_raw, "ABS_raw", "Wavelength (nm)", "Absorbance (a.u.)", cfg)
    line_graph(base, p_base, "ABS_baseline", "Wavelength (nm)", "Absorbance (a.u.)", cfg)
    line_graph(trans, p_tr, "ABS_T", "Wavelength (nm)", "Transmittance (%)", cfg)
    log("ABS: %d spectra, baseline at %g nm" % (len(p_raw), ref))

    if cfg.get("tauc"):
        build_tauc(cfg)
    return book


# ------------------------------------------------------------ Tauc / Urbach
def build_tauc(cfg):
    t = cfg["tauc"]
    n_exp = t["exponent"]                         # "2", "2/3", "1/2", "1/3"
    has_d = t["has_thickness"]
    if has_d and n_exp == "2":
        base_units = "cm\\+(-2) eV\\+(2)"
    elif has_d:
        base_units = "(cm\\+(-1) eV)\\+(%s)" % n_exp
    else:
        base_units = "a.u."
    # Unicode column name: renders correctly in the Linear Fit results table
    ty_name = "(αhν)²" if n_exp == "2" else "(αhν)^(%s)" % n_exp

    rows_out = []
    for k, s in enumerate(ss for g in cfg["groups"] for ss in g["series"]):
        ta = s.get("tauc")
        if not ta:
            continue
        book = op.new_book("w", lname="Tauc data - " + s["name"])
        wks = book[0]
        wks.name = "Data"

        # 10^p scaling on the Tauc axis (readable numbers, as in papers); Eg does not change
        p = 0
        if ta.get("rows"):
            win = [ta["ty"][i - 1] for i in range(ta["rows"][0], ta["rows"][1] + 1)]
            top = max(v for v in win if is_num(v))
            p = int(math.floor(math.log10(top))) if top > 0 else 0
        ty = [v / 10 ** p if is_num(v) else v for v in ta["ty"]]
        yunits = ("10\\+(%d) %s" % (p, base_units)) if p else base_units
        ytitle = "(\\g(a)h\\g(n))\\+(%s) (%s)" % (n_exp, yunits)

        cols = [(s["lam"], "Wavelength", "nm", "N"),
                (ta["e"], "Photon energy", "eV", "X"),
                (s["y_corr"], "Absorbance (baseline)", "a.u.", "Y"),
                (ta["alpha"], "α", "cm\\+(-1)" if has_d else "a.u.", "Y"),
                (ty, ty_name, yunits, "Y"),
                (ta["ln_alpha"], "ln α", "", "Y")]
        for j, (data, ln, un, ax) in enumerate(cols):
            wks.from_list(j, data, lname=ln, units=un, axis=ax)
        row = {"Sample": s["name"], "Book": book.name, "d (nm)": s.get("d_nm") or "",
               "Transition": t["label"], "Tauc range (nm)": "%g-%g" % tuple(s["tauc_range"])}

        if not ta.get("rows"):
            rows_out.append(row)
            continue

        # ---- Tauc: preview of Eg (for the axes) and uncertainty of the initial window
        f = fitlr(wks, 2, 5, ta["rows"])
        eg = -f["a"] / f["b"]
        r1, r2_ = ta["rows"]
        q = max(1, (r2_ - r1) // 4)
        egs = [eg]
        for a1, a2 in ((r1 + q, r2_ + q), (r1 - q, r2_ - q), (r1 + q, r2_), (r1, r2_ - q)):
            if 1 <= a1 < a2 <= len(ta["e"]) and a2 - a1 >= 3:
                fa = fitlr(wks, 2, 5, (a1, a2))
                if fa["b"] > 0:
                    egs.append(-fa["a"] / fa["b"])
        row["Eg window uncertainty (eV)"] = (max(egs) - min(egs)) / 2

        gp = new_graph(cfg.get("template", "PadraoLinha"))
        gp.name = "Tauc%d" % (k + 1)
        gp.lname = "Tauc - " + s["name"]
        gl = gp[0]
        gl.add_plot(wks, coly=4, colx=1, type="l")
        p0 = gl.plot_list()[0]
        p0.color = PALETTE[k % len(PALETTE)]
        p0.set_cmd("-w 1000")
        x0, x1 = eg - 0.25, eg + 0.45
        ymax = max([v for e, v in zip(ta["e"], ty) if is_num(v) and x0 <= e <= x1] or [1])
        gl.set_xlim(x0, x1)
        gl.set_ylim(0, 1.1 * ymax)
        gl.axis("x").title = "Photon energy (eV)"
        gl.axis("y").title = ytitle

        rep, vals = native_linear_fit(wks, 2, 5, ta["rows"], "TaucFit")
        style_fit_curve(gl)
        gl.lt_exec(LEGEND_TOP_RIGHT)
        live_label(gl, "E\\-(g) = $(%s,.4) ± $(%s,.4) eV"
                   % (rc(rep, "Parameters", "XIntercept", "Value"),
                      rc(rep, "Parameters", "XIntercept", "Error")))
        pv = vals.get("Parameters", {})
        row.update({"Initial fit rows": "%d-%d" % tuple(ta["rows"]),
                    "Eg (eV)": pv.get("XIntercept", {}).get("Value"),
                    "Eg fit error (eV)": pv.get("XIntercept", {}).get("Error"),
                    "R2 Tauc": vals.get("RegStats", {}).get("C1", {}).get("RSqCOD")})

        # ---- Urbach: ln(alpha) vs E at the absorption edge
        if ta.get("urows"):
            gp = new_graph(cfg.get("template", "PadraoLinha"))
            gp.name = "Urbach%d" % (k + 1)
            gp.lname = "Urbach - " + s["name"]
            gl = gp[0]
            gl.add_plot(wks, coly=5, colx=1, type="l")
            p0 = gl.plot_list()[0]
            p0.color = PALETTE[k % len(PALETTE)]
            p0.set_cmd("-w 1000")
            x0, x1 = eg - 0.2, eg + 0.1
            ys = [v for e, v in zip(ta["e"], ta["ln_alpha"]) if is_num(v) and x0 <= e <= x1]
            gl.set_xlim(x0, x1)
            if ys:
                gl.set_ylim(min(ys) - 0.3, max(ys) + 0.3)
            gl.axis("x").title = "Photon energy (eV)"
            gl.axis("y").title = "ln \\g(a)"

            urep, uvals = native_linear_fit(wks, 2, 6, ta["urows"], "UrbachFit")
            style_fit_curve(gl)
            gl.lt_exec(LEGEND_BOTTOM_RIGHT)
            slope, serr = rc(urep, "Parameters", "Slope", "Value"), rc(urep, "Parameters", "Slope", "Error")
            live_label(gl, "E\\-(U) = $(1000/%s,.1) ± $(1000*%s/%s^2,.2) meV" % (slope, serr, slope))
            b = uvals.get("Parameters", {}).get("Slope", {})
            if b.get("Value"):
                eu = 1000.0 / b["Value"]
                row.update({"Initial Urbach rows": "%d-%d" % tuple(ta["urows"]),
                            "EU (meV)": eu, "EU error (meV)": 1000.0 * b["Error"] / b["Value"] ** 2,
                            "R2 Urbach": uvals.get("RegStats", {}).get("C1", {}).get("RSqCOD"),
                            "Urbach reliable": "yes" if eu <= t["urbach_max"] else
                                               "no (E_U > %g meV: not an exponential tail)" % t["urbach_max"]})
        rows_out.append(row)

    build_results(rows_out)
    log("Tauc: %d sample(s)" % len(rows_out))


def build_results(rows_out):
    """Summary with the values of the INITIAL fit of each sample.

    The live values (which change if the range is edited in Origin) are in the
    TaucFit/UrbachFit reports of each book and in the graph labels.
    """
    book = op.new_book("w", lname="Tauc Results")
    res = book[0]
    res.name = "Results"
    keys = ["Sample", "Book", "d (nm)", "Transition", "Tauc range (nm)", "Initial fit rows",
            "Eg (eV)", "Eg fit error (eV)", "Eg window uncertainty (eV)", "R2 Tauc",
            "Initial Urbach rows", "EU (meV)", "EU error (meV)", "R2 Urbach", "Urbach reliable"]
    note = "initial fit; live values in the TaucFit/UrbachFit reports"
    for j, key in enumerate(keys):
        vals = [r.get(key) for r in rows_out]
        vals = [("" if v is None else v) for v in vals]
        res.from_list(j, vals, lname=key, comments=note if j >= 6 else "")


# ------------------------------------------------------------ test hook
def selftest(cfg):
    """Changes the data of the 1st sample and checks that the Linear Fit recalculates."""
    books = {b.lname: b for b in op.pages("w")}
    db = books["Tauc data - " + cfg["groups"][0]["series"][0]["name"]]
    log("selftest sheets: %s" % [w.name for w in db])
    eg_expr = 'ReportCell("%s","TaucFit","Parameters","XIntercept","Value")' % db.name
    log("selftest Eg before: %r" % op.lt_float(eg_expr))
    d = db["Data"]
    tyc = d.to_list(4)
    d.from_list(4, [v + 0.5 if is_num(v) else v for v in tyc])
    op.lt_exec("run -p au; doc -uw;")
    log("selftest Eg after (Y + 0.5): %r" % op.lt_float(eg_expr))
