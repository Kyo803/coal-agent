from sandbox import sb

NOISE = '''import math

def noise2(x, y):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)

    def h(i, j):
        n = (i * 127 + j * 311) % 65536
        n = ((n ^ (n >> 4)) * 39221) & 0xFFFF
        return (n & 0xFFFF) / 65535.0

    a = h(ix, iy); b = h(ix + 1, iy)
    c = h(ix, iy + 1); d = h(ix + 1, iy + 1)
    return (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy)
            + c * (1 - fx) * fy + d * fx * fy)
'''

MESH = '''from noise import noise2

def build_terrain(size=32, scale=10.0, height=2.0):
    verts, faces = [], []
    h = [[noise2(x / 6.0, y / 6.0) * height for x in range(size + 1)]
         for y in range(size + 1)]
    for y in range(size + 1):
        for x in range(size + 1):
            verts.append((round(x * scale / size, 4), round(h[y][x], 4),
                          round(y * scale / size, 4)))
    for y in range(size):
        for x in range(size):
            a = y * (size + 1) + x
            b, c, d = a + 1, a + (size + 1), a + (size + 1) + 1
            faces.append((a, b, d))
            faces.append((a, d, c))
    return verts, faces

def write_obj(verts, faces, path):
    with open(path, "w") as f:
        for v in verts:
            f.write("v %.4f %.4f %.4f\\n" % v)
        for (a, b, c) in faces:
            f.write("f %d %d %d\\n" % (a + 1, b + 1, c + 1))

def write_stl(verts, faces, path):
    import math
    import struct

    def normal(a, b, c):
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        w = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u[1] * w[2] - u[2] * w[1],
             u[2] * w[0] - u[0] * w[2],
             u[0] * w[1] - u[1] * w[0])
        L = math.sqrt(sum(x * x for x in n)) or 1.0
        return tuple(x / L for x in n)

    with open(path, "wb") as f:
        f.write(b"0" * 80)
        f.write(struct.pack("<I", len(faces)))
        for (a, b, c) in faces:
            n = normal(verts[a], verts[b], verts[c])
            f.write(struct.pack("<12fH", *(n + verts[a] + verts[b] + verts[c]),
                                0))
'''

RASTER = '''def render(verts, faces, out, size=(320, 200)):
    import math
    w, h = size
    cam = (0.0, 3.0, 6.0)
    light = (0.4, 1.0, 0.3)
    frame = [[(18, 26, 40) for x in range(w)] for y in range(h)]

    tris = []
    for f in faces:
        vs = [verts[i] for i in f]
        u = (vs[1][0] - vs[0][0], vs[1][1] - vs[0][1], vs[1][2] - vs[0][2])
        v = (vs[2][0] - vs[0][0], vs[2][1] - vs[0][1], vs[2][2] - vs[0][2])
        n = (u[1] * v[2] - u[2] * v[1],
             u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])
        L = math.sqrt(sum(x * x for x in n)) or 1.0
        n = tuple(x / L for x in n)
        lam = n[0] * light[0] + n[1] * light[1] + n[2] * light[2]
        shade = 0.25 + 0.75 * max(0.0, lam)
        pts = []
        ok = True
        for (x, y, z) in vs:
            dz = z - cam[2]
            if dz <= 0:
                ok = False
                break
            px = int(w / 2 + ((x - cam[0]) / dz) * w)
            py = int(h / 2 - ((y - cam[1]) / dz) * h)
            pts.append((px, py))
        if not ok:
            continue
        depth = sum(vs[i][2] for i in range(3)) / 3.0
        tris.append((depth, pts, shade))

    tris.sort(key=lambda t: t[0])  # far -> near

    def inside(px, py, t):
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        d1 = cross(t[0], t[1], (px, py))
        d2 = cross(t[1], t[2], (px, py))
        d3 = cross(t[2], t[0], (px, py))
        neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (neg and pos)

    for depth, pts, shade in tris:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, x1 = max(0, min(xs)), min(w - 1, max(xs))
        y0, y1 = max(0, min(ys)), min(h - 1, max(ys))
        for yy in range(y0, y1 + 1):
            for xx in range(x0, x1 + 1):
                if inside(xx, yy, pts):
                    frame[yy][xx] = (int(50 * shade + 15),
                                     int(120 * shade + 20),
                                     int(210 * shade + 20))

    with open(out, "w") as f:
        f.write("P3\\n%d %d\\n255\\n" % (w, h))
        for row in frame:
            for p in row:
                f.write("%d %d %d\\n" % p)
'''

MAIN = '''from mesh import build_terrain, write_obj, write_stl
from raster import render

def main():
    verts, faces = build_terrain(32)
    write_obj(verts, faces, "mesh.obj")
    write_stl(verts, faces, "mesh.stl")
    render(verts, faces, "preview.ppm")
    print("FORGE:PASS")

if __name__ == "__main__":
    main()
'''

for rel, content in [("noise.py", NOISE), ("mesh.py", MESH),
                     ("raster.py", RASTER), ("main.py", MAIN)]:
    sb.write("/home/coal/work/forge-mesh/" + rel, content)

print(sb.shell("ls -la /home/coal/work/forge-mesh")["out"])