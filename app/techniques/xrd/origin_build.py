"""XRD inside Origin (embedded Python 3.11, no numpy): raw and normalized stacked graphs."""
import originpro as op
from origin_common import log, style_plots

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


def build(cfg):
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
