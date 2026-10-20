"""UV-Vis instrument formats. Recognition is by content, not by file name."""
from __future__ import annotations

import re
import struct
from pathlib import Path

import numpy as np

from core.dataset import Dataset, read_text

KEY = "ABS"


# ------------------------------------------------------------ JASCO V-780 TXT
def detect_jasco(path: Path) -> float:
    if path.suffix.lower() not in (".txt", ".csv", ".dat", ".jws"):
        return 0.0
    head = read_text(path, 4000)
    if "XYDATA" in head and ("ULTRAVIOLET" in head or "ABSORBANCE" in head or "JASCO" in head):
        return 1.0
    return 0.0


def read_jasco(path: Path) -> list[Dataset]:
    """JASCO V-780 TXT: only the (lambda, A) pairs below XYDATA."""
    lines = read_text(path).splitlines()
    header, xs, ys = {}, [], []
    i = 0
    while i < len(lines) and lines[i].strip() != "XYDATA":
        parts = lines[i].split("\t", 1)
        if len(parts) == 2:
            header[parts[0].strip()] = parts[1].strip()
        i += 1
    for line in lines[i + 1:]:
        parts = line.replace(",", ".").split()
        if len(parts) < 2:
            break                        # end of the numeric block
        try:
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
        except ValueError:
            break

    # the file name wins: users often rename the file after the measurement
    m = re.search(r"^Sample name\t(.*)$", "\n".join(lines), re.M)
    internal = (m.group(1).strip() if m else "") or header.get("TITLE", "")

    x, y = np.array(xs), np.array(ys)
    order = np.argsort(x)                # the instrument writes from 850 down to 400
    return [Dataset(KEY, path.stem, x[order], y[order], path,
                    {"sample_name": internal, "date": header.get("DATE", "")})]


# ------------------------------------------------------------ Agilent 8453/8454 .SD
def detect_agilent_sd(path: Path) -> float:
    if path.suffix.lower() != ".sd":
        return 0.0
    head = path.read_bytes()[:4096]
    return 1.0 if b"REGISTER FILE" in head and b"CHPUVObject" in head else 0.0


def read_agilent_sd(path: Path) -> list[Dataset]:
    """ChemStation UV-Vis .SD (Agilent 8453/8454): several spectra in one file.

    Binary format (MFC serialization) with no public documentation; decoded as:
      - each spectrum starts at "CHPUVObject";
      - metadata: UTF-16 key, 2-byte type, 4 bytes, uint16 length, UTF-16 value;
      - "Absorbance (AU)" + 00 00 FF FF + uint32 n + 1 byte + n doubles;
      - "Wavelength (nm)" + 00 00 FF FF + uint32 n + 01 + ... start and step (doubles).
    """
    d = path.read_bytes()
    u = lambda s: s.encode("utf-16le")

    def meta(key, start, stop):
        i = d.find(u(key), start, stop)
        if i < 0:
            return ""
        j = i + len(u(key)) + 6                      # type (2) + 4 bytes
        n = struct.unpack_from("<H", d, j)[0]
        return d[j + 2:j + 2 + 2 * n].decode("utf-16le", "replace").strip() if n < 500 else ""

    def block(label, start, stop):
        i = d.find(u(label), start, stop)
        if i < 0:
            raise ValueError(f"block '{label}' not found")
        e = i + len(u(label))
        if d[e:e + 4] != b"\x00\x00\xff\xff":
            raise ValueError(f"unexpected format after '{label}'")
        return e + 8, struct.unpack_from("<I", d, e + 4)[0]

    starts = [m.start() for m in re.finditer(b"CHPUVObject", d)]
    out, seen = [], {}
    for k, o in enumerate(starts):
        stop = starts[k + 1] if k + 1 < len(starts) else len(d)
        if d.find(u("Absorbance (AU)"), o, stop) < 0:
            continue
        a0, n = block("Absorbance (AU)", o, stop)
        y = np.array(struct.unpack_from("<%dd" % n, d, a0 + 1))
        w0, nw = block("Wavelength (nm)", a0, len(d))
        if d[w0] == 1:                                # implicit axis: start + step
            x = None
            for off in range(w0 + 1, w0 + 48):
                s0, st = struct.unpack_from("<2d", d, off)
                if 100 <= s0 <= 3500 and 0 < st <= 20:
                    x = s0 + st * np.arange(nw)
                    break
            if x is None:
                raise ValueError("wavelength axis not found")
        else:                                         # explicit axis
            x = np.array(struct.unpack_from("<%dd" % nw, d, w0 + 1))
        name = meta("SampleName", o, stop) or f"{path.stem}_{k + 1}"
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:                            # same name measured again
            name = f"{name}_{seen[name]}"
        order = np.argsort(x)
        out.append(Dataset(KEY, name, x[order], y[order], path,
                           {"time": meta("TimeOfDay", o, stop), "date": meta("Date", o, stop),
                            "instrument": meta("InstrId", o, stop)}))
    if not out:
        raise ValueError("no spectrum found in the .SD file")
    return out
