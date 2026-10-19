"""Runs INSIDE Origin (embedded Python, no numpy).

The app writes a JSON file with the already-processed data and calls Origin with
    Origin64.exe -rs run -pyf "<copy of this file>"
The first line of the copy defines PAYLOAD (path to the JSON file).
"""
import json
import math
import traceback

import originpro as op
from originpro.utils import lt_tree_to_dict

PALETTE = ["#332288", "#CC6677", "#44AA99", "#DDCC77", "#882255",
           "#88CCEE", "#117733", "#999933", "#AA4499"]


def log(msg):
    with open(PAYLOAD + ".log", "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def new_graph(template):
    try:
        return op.new_graph(template=template)
    except Exception:
        log("template %s not found, using 'line'" % template)
        return op.new_graph(template="line")


def style_plots(gl, width):
    for i, p in enumerate(gl.plot_list()):
        p.color = PALETTE[i % len(PALETTE)]
        p.set_cmd("-w %d" % int(width * 500))


LEGEND_TOP_RIGHT = ("legend -r; legend.background=0; doc -uw;"
                    "legend.x = layer.x.to - legend.dx/2 - 0.02*(layer.x.to - layer.x.from);"
                    "legend.y = layer.y.to - legend.dy/2 - 0.02*(layer.y.to - layer.y.from);")
LEGEND_BOTTOM_RIGHT = ("legend -r; legend.background=0; doc -uw;"
                       "legend.x = layer.x.to - legend.dx/2 - 0.02*(layer.x.to - layer.x.from);"
                       "legend.y = layer.y.from + legend.dy/2 + 0.04*(layer.y.to - layer.y.from);")


def is_num(v):
    return v is not None and v == v               # drops None and NaN


# ------------------------------------------------------------------ UV-Vis
def fill_xy_sheet(wks, groups, key, units, comment_key=None):
    """X1, Y..., X2, Y... (one X per range/step). Returns [(Y column, X column)]."""
    col, pairs = 0, []
    for gi, g in enumerate(groups):
        xcol = col
        wks.from_list(col, g["x"], lname="Wavelength", units="nm",
                      comments="X%d" % (gi + 1), axis="X")
        col += 1
        for s in g["series"]:
            wks.from_list(col, s[key], lname=s["name"], units=units,
                          comments=s.get(comment_key, "") if comment_key else "", axis="Y")
            pairs.append((col, xcol))
            col += 1
    return pairs


def line_graph(wks, pairs, gname, xtitle, ytitle, cfg):
    gp = new_graph(cfg.get("template", "PadraoLinha"))
    gp.name = gname
    gl = gp[0]
    for ycol, xcol in pairs:
        gl.add_plot(wks, coly=ycol, colx=xcol, type="l")
    style_plots(gl, cfg.get("line_width", 2))
    gl.rescale()
    gl.axis("x").title = xtitle
    gl.axis("y").title = ytitle
    gl.lt_exec(LEGEND_TOP_RIGHT)
    return gp


def build_abs(cfg):
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
def fitlr(wks, xcol, ycol, rows):
    """Origin's quick linear fit (fitlr), used only for the window uncertainty."""
    op.lt_exec("fitlr iy:=[%s]%s!(%d,%d)[%d:%d];"
               % (wks.get_book().name, wks.name, xcol, ycol, rows[0], rows[1]))
    r = op.lt_float("fitlr.r")
    return {k: op.lt_float("fitlr." + k) for k in ("a", "b", "aerr", "berr")} | {"r2": r * r}


def native_linear_fit(wks, xcol, ycol, rows, sheet_name):
    """Origin's Linear Fit (the same as Analysis > Fitting > Linear Fit).

    Creates the full report (parameters, X-intercept, R2, ANOVA, residuals), draws
    the line on the active graph and keeps auto recalculation: changing the range in
    "Change Parameters" (green lock) redoes everything.
    Returns ((book, report sheet), results of the initial fit).
    """
    bk, sh = wks.get_book().name, wks.name
    op.lt_exec("tree _lr; xop execute:=init classname:=FitLinear iotrgui:=_lr;")
    op.lt_exec("_lr.GUI.AutoUpdate = 1;"                    # auto recalculation
               "_lr.GUI.Quantities.XIntercept = 1;"         # X-axis intercept (Eg)
               "_lr.GUI.Graph1.XDataType.Range = 1;"        # line spans the whole X scale
               "_lr.GUI.Graph1.XDataType.N = 200;")
    op.lt_exec('_lr.GUI.InputData.Range1.X$ = "[%s]%s!%d[%d:%d]";'
               '_lr.GUI.InputData.Range1.Y$ = "[%s]%s!%d[%d:%d]";'
               % (bk, sh, xcol, rows[0], rows[1], bk, sh, ycol, rows[0], rows[1]))
    op.lt_exec("@NLFS = 0; xop execute:=report iotrgui:=_lr; xop execute:=cleanup; del -vt _lr;")
    rep, cur = op.get_lt_str("__REPORT"), op.get_lt_str("__FITCURVE")   # "[Book]Sheet!"
    book = wks.get_book()
    # readable names; the operation stays linked (tested: renaming does not break recalculation)
    book[rep[rep.index("]") + 1:-1]].name = sheet_name
    book[cur[cur.index("]") + 1:-1]].name = sheet_name + "Curve"
    op.lt_exec("tree _res; getresults tr:=_res iw:=[%s]%s!;" % (bk, sheet_name))
    values = lt_tree_to_dict("_res")
    op.lt_exec("del -vt _res;")
    return (bk, sheet_name), values


def rc(rep, table, row, col):
    """ReportCell expression (reads a report cell; follows the recalculation)."""
    return 'ReportCell("%s","%s","%s","%s","%s")' % (rep[0], rep[1], table, row, col)


def live_label(gl, text, xfrac=0.04, yfrac=0.05):
    """Label with substitution on: $(...) is re-evaluated when the fit changes."""
    x0, x1 = gl.get_float("x.from"), gl.get_float("x.to")
    y0, y1 = gl.get_float("y.from"), gl.get_float("y.to")
    lab = gl.add_label(text, x0 + xfrac * (x1 - x0), y1 - yfrac * (y1 - y0))
    lab.set_int("link", 1)
    lab.set_int("fsize", 18)
    lab.set_int("background", 0)
    return lab


def style_fit_curve(gl):
    fit = gl.plot_list()[-1]                                 # the line added by Linear Fit
    fit.color = "#000000"
    fit.set_cmd("-w 1000")
    fit.set_cmd("-d 1")


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


# -------------------------------------------------------------------- XRD
# Same frame as PadraoLinha (ABS): 3 pt frame on all 4 sides, outward ticks
# (major and minor) on the bottom only, 18 pt numbers, 22 pt titles, 14 pt legend without frame.
# Difference: the intensity axis shows only its title (no numbers, no ticks).
XRD_FRAME = """
layer.x.showAxes = 3; layer.y.showAxes = 3;
layer.x.thickness = 3; layer.x2.thickness = 3;
layer.y.thickness = 3; layer.y2.thickness = 3;
layer.x.ticks = 10; layer.x2.ticks = 0;
layer.y.ticks = 0;  layer.y2.ticks = 0;
layer.y.showLabels = 0;
layer.x.label.pt = 18;
xb.fsize = 22; yl.fsize = 22;
legend.fsize = 14; legend.background = 0;
"""


def build_xrd(cfg):
    g = cfg["groups"][0]
    book = op.new_book("w", lname="XRD")
    raw = book[0]
    raw.name = "Raw"
    norm = book.add_sheet("normalized")

    for wks, key, units in ((raw, "y", "counts"), (norm, "y_norm", "a.u.")):
        wks.from_list(0, g["x"], lname="Diffraction Angle", units="2θ", axis="X")
        for j, s in enumerate(g["series"], start=1):
            wks.from_list(j, s[key], lname=s["name"], units=units, axis="Y")

    n = len(g["series"])
    for wks, ytitle, gname in ((raw, "Intensity (a.u.)", "XRD_raw"),
                               (norm, "Normalized Intensity (a.u.)", "XRD_norm")):
        # Plot > Basic 2D > Stacked Lines by Y Offsets (template OffsetStackY)
        rng = "[%s]%s!(1,2:%d)" % (book.name, wks.name, n + 1)
        op.lt_exec("plotxy iy:=%s plot:=200 ogl:=[<new template:=OffsetStackY>];" % rng)
        gp = op.find_graph()                     # the graph just created
        gp.name = gname
        gl = gp[0]
        style_plots(gl, cfg.get("line_width", 2))
        gl.rescale()
        gl.axis("x").title = "Diffraction Angle (2θ)"
        gl.axis("y").title = ytitle
        gl.lt_exec(XRD_FRAME)
        log("%s: %d curves" % (gname, len(gl.plot_list())))
    return book


# ------------------------------------------------------------------- main
try:
    open(PAYLOAD + ".log", "w").close()
    with open(PAYLOAD, encoding="utf-8") as f:
        cfg = json.load(f)
    op.set_show(True)
    for b in list(op.pages("w")):                 # the empty Book1 that Origin opens on its own
        if all(not w.to_list(c) for w in b for c in range(w.cols)):
            b.destroy()
    if cfg["kind"] == "ABS":
        build_abs(cfg)
    elif cfg["kind"] == "XRD":
        build_xrd(cfg)
    if cfg.get("save_path"):
        op.save(cfg["save_path"])
        log("saved to " + cfg["save_path"])
    if cfg.get("export_png"):
        import os
        os.makedirs(cfg["export_png"], exist_ok=True)
        for gp in op.graph_list():
            gp.save_fig(os.path.join(cfg["export_png"], gp.name + ".png"), width=1000)
    if cfg.get("selftest"):
        # test only: changes the data of the 1st sample and checks that everything recalculates
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
    log("OK")
except Exception:
    log(traceback.format_exc())
    op.lt_exec('type -b "Error while building the project. See the log: %s.log";' % PAYLOAD.replace("\\", "/"))
