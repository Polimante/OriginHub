"""Runs INSIDE Origin (embedded Python 3.11, no numpy): helpers shared by every technique.

The app writes a run folder in %LOCALAPPDATA%\\OriginHub with payload.json, this file,
the technique's script (copied as origin_build.py) and launch.py, and calls
    Origin64.exe -rs run -pyf "<run folder>\\launch.py"
launch.py calls run(PAYLOAD), which imports origin_build and calls its build(cfg).
Progress and errors go to payload.json.log; the last line is OK when everything worked.
"""
import json
import traceback

import originpro as op
from originpro.utils import lt_tree_to_dict

PAYLOAD = ""                                     # set by run()
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


# ------------------------------------------------------------ worksheets and graphs
def fill_xy_sheet(wks, groups, key, units, xname="Wavelength", xunits="nm", comment_key=None):
    """X1, Y..., X2, Y... (one X per range/step). Returns [(Y column, X column)]."""
    col, pairs = 0, []
    for gi, g in enumerate(groups):
        xcol = col
        wks.from_list(col, g["x"], lname=xname, units=xunits, comments="X%d" % (gi + 1), axis="X")
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


# ------------------------------------------------------------ fits
def fitlr(wks, xcol, ycol, rows):
    """Origin's quick linear fit (fitlr), used for quick values such as window uncertainties."""
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


# ------------------------------------------------------------------- main
def save_origin_paths():
    """Tells the app where Origin's User Files Folder is (used by its setup check)."""
    import os
    uff = ""
    try:
        uff = op.path("u")
    except Exception:
        try:
            op.lt_exec("string __ohuff$ = %Y;")
            uff = op.get_lt_str("__ohuff")
        except Exception:
            pass
    if uff:
        work = os.path.dirname(os.path.dirname(PAYLOAD))          # %LOCALAPPDATA%\OriginHub
        with open(os.path.join(work, "origin_paths.json"), "w", encoding="utf-8") as f:
            json.dump({"user_files": uff}, f)
        log("User Files Folder: " + uff)


def run(payload_path):
    """Entry point called by launch.py."""
    global PAYLOAD
    PAYLOAD = payload_path
    try:
        open(PAYLOAD + ".log", "w").close()
        with open(PAYLOAD, encoding="utf-8") as f:
            cfg = json.load(f)
        op.set_show(True)
        try:
            save_origin_paths()
        except Exception:
            log("could not read the User Files Folder")
        for b in list(op.pages("w")):                 # the empty Book1 that Origin opens on its own
            if all(not w.to_list(c) for w in b for c in range(w.cols)):
                b.destroy()
        import origin_build                           # the technique's script, copied next to this file
        origin_build.build(cfg)
        if cfg.get("save_path"):
            op.save(cfg["save_path"])
            log("saved to " + cfg["save_path"])
        if cfg.get("export_png"):
            import os
            os.makedirs(cfg["export_png"], exist_ok=True)
            for gp in op.graph_list():
                gp.save_fig(os.path.join(cfg["export_png"], gp.name + ".png"), width=1000)
        if cfg.get("selftest") and hasattr(origin_build, "selftest"):
            origin_build.selftest(cfg)               # test only (tools/e2e_test.py --selftest)
        log("OK")
    except Exception:
        log(traceback.format_exc())
        op.lt_exec('type -b "Error while building the project. See the log: %s.log";'
                   % PAYLOAD.replace("\\", "/"))
