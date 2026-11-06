"""Builds a 3D layout model of the CAB1 VFD conveyor control cabinet (=CONV+CAB1).

Every device from the EPLAN schematic (pages 3-10) becomes its own component, named by its
device tag and sized from a typical catalogue part. Devices are detailed enough to recognise
(DIN-rail profiles, toggles, screw terminals, LEDs, displays, raised device tags), but they are
still stand-ins: swap them for manufacturer STEP models once the real parts are chosen.

Axes: X = width (left to right), Y = height (up), Z = depth (back wall at Z = 0, door at the front).
All dimensions below are in mm; Fusion's API works in cm, so they are converted on the way in.
Run it in an empty Hybrid or Assembly design (a Part design allows only one component).
"""
import math
import traceback

import adsk.core
import adsk.fusion

MM = 0.1  # Fusion API length unit is cm

# Enclosure: wall-mounted steel enclosure 600 x 800 x 300 mm.
ENC_W, ENC_H, ENC_D, WALL = 600.0, 800.0, 300.0, 2.0
DOOR_T = 2.0

# Mounting plate 560 x 760 x 3 mm, 10 mm in front of the back wall.
PLATE_X, PLATE_Y, PLATE_W, PLATE_H, PLATE_T = 20.0, 20.0, 560.0, 760.0, 3.0
PLATE_Z = WALL + 10.0
PLATE_FRONT = PLATE_Z + PLATE_T

# DIN rail centre lines on the plate (mm from the plate's bottom edge).
RAIL_Y = {'A': 605.0, 'B': 340.0, 'C': 115.0}

LABELS = True  # raised device tags; set False for a faster build

COLORS = {
    'steel': (200, 200, 195),
    'plate': (215, 185, 120),
    'rail': (170, 170, 175),
    'duct': (120, 120, 120),
    'ductcover': (150, 150, 150),
    'grey': (215, 215, 210),
    'midgrey': (150, 150, 155),
    'dark': (70, 70, 70),
    'black': (25, 25, 25),
    'white': (245, 245, 245),
    'yellow': (240, 190, 20),
    'teal': (0, 130, 130),
    'silver': (165, 170, 175),
    'blue': (40, 90, 200),
    'green': (40, 170, 60),
    'red': (210, 30, 30),
    'orange': (235, 120, 20),
    'pe': (60, 170, 60),
    'lcd': (150, 190, 160),
    'led_green': (60, 230, 60),
    'led_red': (240, 40, 40),
    'led_yellow': (250, 210, 40),
}


class Builder:
    def __init__(self, app, design):
        self.app = app
        self.design = design
        self.root = design.rootComponent
        self.tbm = adsk.fusion.TemporaryBRepManager.get()
        self.appearances = {}
        self.base_appearance = self._find_base_appearance()
        try:
            orient = app.preferences.generalPreferences.defaultModelingOrientation
            self.z_up = orient == adsk.core.DefaultModelingOrientations.ZUpModelingOrientation
        except Exception:
            self.z_up = True
        self.label_errors = 0
        self.first_label_error = None

    # ---- appearances -------------------------------------------------------------------------
    def _find_base_appearance(self):
        for lib in self.app.materialLibraries:
            if 'appearance' not in lib.name.lower():
                continue
            for name in ('Paint - Enamel Glossy (Grey)', 'Plastic - Glossy (Grey)', 'Plastic - Matte (Grey)'):
                try:
                    a = lib.appearances.itemByName(name)
                except Exception:
                    a = None
                if a:
                    return a
            for i in range(lib.appearances.count):
                a = lib.appearances.item(i)
                if 'paint' in a.name.lower() or 'plastic' in a.name.lower():
                    return a
        return None

    def appearance(self, key):
        if key in self.appearances:
            return self.appearances[key]
        a = self.design.appearances.itemByName('CAB1 ' + key)
        if not a and self.base_appearance:
            try:
                a = self.design.appearances.addByCopy(self.base_appearance, 'CAB1 ' + key)
                r, g, b = COLORS[key]
                for i in range(a.appearanceProperties.count):
                    prop = a.appearanceProperties.item(i)
                    cp = adsk.core.ColorProperty.cast(prop)
                    if cp and cp.id in ('opaque_albedo', 'generic_diffuse', 'metal_f0', 'transparent_color'):
                        cp.value = adsk.core.Color.create(r, g, b, 255)
            except Exception:
                a = None
        self.appearances[key] = a
        return a

    # ---- geometry ----------------------------------------------------------------------------
    def point(self, x, y, z):
        """Model coordinates (Y up, Z towards the door) to Fusion's, honouring a Z-up preference."""
        if self.z_up:
            return adsk.core.Point3D.create(x * MM, -z * MM, y * MM)
        return adsk.core.Point3D.create(x * MM, y * MM, z * MM)

    def front_dir(self):
        return adsk.core.Vector3D.create(0, -1, 0) if self.z_up else adsk.core.Vector3D.create(0, 0, 1)

    def box_body(self, x0, y0, z0, x1, y1, z1):
        p0, p1 = self.point(x0, y0, z0), self.point(x1, y1, z1)
        obb = adsk.core.OrientedBoundingBox3D.create(
            adsk.core.Point3D.create((p0.x + p1.x) / 2, (p0.y + p1.y) / 2, (p0.z + p1.z) / 2),
            adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0),
            abs(p1.x - p0.x), abs(p1.y - p0.y), abs(p1.z - p0.z))
        return self.tbm.createBox(obb)

    def cyl_body(self, x, y, z0, z1, r):
        return self.tbm.createCylinderOrCone(self.point(x, y, z0), r * MM, self.point(x, y, z1), r * MM)

    def component(self, name, parent=None):
        parent = parent or self.root
        occ = parent.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occ.component.name = name
        return occ.component

    def add(self, comp, body, color, name=None):
        b = comp.bRepBodies.add(body)
        if name:
            b.name = name
        a = self.appearance(color)
        if a:
            b.appearance = a
        return b

    def box(self, comp, x0, y0, z0, x1, y1, z1, color, name=None):
        return self.add(comp, self.box_body(x0, y0, z0, x1, y1, z1), color, name)

    def cyl(self, comp, x, y, z0, z1, r, color, name=None):
        return self.add(comp, self.cyl_body(x, y, z0, z1, r), color, name)

    def block(self, name, x0, y0, z0, w, h, d, color, parent=None):
        comp = self.component(name, parent)
        self.box(comp, x0, y0, z0, x0 + w, y0 + h, z0 + d, color)
        return comp

    # ---- raised text -------------------------------------------------------------------------
    def label(self, comp, body, text, x0, y0, x1, y1, height=3.5, color='white'):
        """Raised text on the front face of body, centred in the box x0..x1 / y0..y1 (model mm)."""
        if not LABELS:
            return
        try:
            front = self.front_dir()
            face, best = None, None
            for f in body.faces:
                plane = adsk.core.Plane.cast(f.geometry)
                if not plane:
                    continue
                n = plane.normal
                if f.isParamReversed:
                    n.scaleBy(-1)
                if n.dotProduct(front) < 0.99:
                    continue
                c = f.centroid
                depth = c.x * front.x + c.y * front.y + c.z * front.z
                if best is None or depth > best:
                    face, best = f, depth
            if not face:
                return
            sk = comp.sketches.add(face)
            zf = 0.0  # depth is irrelevant: points are projected onto the sketch plane
            pa = sk.modelToSketchSpace(self.point(x0, y0, zf))
            right = sk.modelToSketchSpace(self.point(x0 + 10, y0, zf))
            # A face sketch's axes can be rotated against the model, so place the text by its
            # baseline start point and turn it to run along the model's right direction.
            angle = math.atan2(right.y - pa.y, right.x - pa.x)
            tw = 0.62 * height * len(text)  # approximate text width for centring
            start = sk.modelToSketchSpace(self.point((x0 + x1) / 2 - tw / 2, (y0 + y1) / 2 - height / 2, zf))
            inp = sk.sketchTexts.createInput(text, height * MM, start)
            inp.angle = angle
            txt = sk.sketchTexts.add(inp)
            ext = comp.features.extrudeFeatures.addSimple(
                txt, adsk.core.ValueInput.createByReal(0.4 * MM),
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            a = self.appearance(color)
            for i in range(ext.bodies.count):
                bd = ext.bodies.item(i)
                bd.name = 'Tag ' + text
                if a:
                    bd.appearance = a
            sk.isVisible = False
        except Exception as e:
            self.label_errors += 1
            if not self.first_label_error:
                self.first_label_error = '%s: %s' % (text, e)


# ---- device builders (model coordinates, mm) --------------------------------------------------

def px(x):
    return PLATE_X + x


def py(y):
    return PLATE_Y + y


def din_module(b, parent, row, x, name, tag, w, h, d, color, kind, poles=1, note=None):
    """DIN-rail modular device: full-height base, raised front window, screws, actuator, tag."""
    comp = b.component(name, parent)
    yc = py(RAIL_Y[row])
    z0 = PLATE_FRONT
    x0, x1 = px(x), px(x + w)
    base_d = d - 18
    b.box(comp, x0, yc - h / 2, z0, x1, yc + h / 2, z0 + base_d, color, 'Base')
    win = b.box(comp, x0, yc - 22.5, z0 + base_d, x1, yc + 22.5, z0 + d, color, 'Front')
    pw = w / poles
    for i in range(poles):
        cx = x0 + pw * (i + 0.5)
        for sy in (yc + h / 2 - 9, yc - h / 2 + 9):
            b.cyl(comp, cx, sy, z0 + base_d, z0 + base_d + 1.2, min(2.4, pw / 2 - 1.5), 'black', 'Screw')
        if kind == 'mcb':
            b.box(comp, cx - pw / 2 + 2.5, yc - 12, z0 + d, cx + pw / 2 - 2.5, yc + 2, z0 + d + 9, 'dark', 'Toggle')
    if kind == 'mcb' and poles > 1:
        b.box(comp, x0 + 2.5, yc - 3, z0 + d + 9, x1 - 2.5, yc + 1, z0 + d + 11, 'dark', 'Handle tie')
    if kind == 'switch':
        b.cyl(comp, (x0 + x1) / 2, yc - 4, z0 + d, z0 + d + 6, 13, 'black', 'Rotary base')
        b.box(comp, (x0 + x1) / 2 - 4, yc - 4 - 4, z0 + d + 6, (x0 + x1) / 2 + 4, yc - 4 + 4, z0 + d + 40,
              'midgrey', 'Door coupling shaft')
    if kind == 'contactor':
        b.box(comp, (x0 + x1) / 2 - 7, yc - 14, z0 + d, (x0 + x1) / 2 + 7, yc, z0 + d + 2, 'dark', 'Indicator window')
        for cx in (x0 + 5, x1 - 5):
            b.cyl(comp, cx, yc + 17, z0 + d, z0 + d + 1.2, 2.2, 'black', 'Coil terminal')
    if kind == 'relay':
        for i, c in enumerate(('led_green', 'led_green', 'led_yellow')):
            b.cyl(comp, (x0 + x1) / 2, yc + 14 - i * 6, z0 + d, z0 + d + 1, 1.6, c, 'LED')
    if kind == 'thermostat':
        b.cyl(comp, (x0 + x1) / 2, yc - 6, z0 + d, z0 + d + 7, 6.5, 'red', 'Setting dial')
    ty0, ty1 = (yc + 6, yc + 20) if kind in ('mcb', 'switch') else (yc - 21, yc - 9)
    b.label(comp, win, tag, x0, ty0, x1, ty1, 3.2 if w < 25 else 4.0)
    if note:
        b.label(comp, win, note, x0, ty0 - 8, x1, ty0 - 1, 2.5)
    return comp


def power_supply(b, parent, row, x, name, tag, w=40, h=125, d=115):
    comp = b.component(name, parent)
    yc, z0 = py(RAIL_Y[row]), PLATE_FRONT
    x0, x1 = px(x), px(x + w)
    body = b.box(comp, x0, yc - h / 2, z0, x1, yc + h / 2, z0 + d, 'silver', 'Housing')
    b.box(comp, x0 + 2, yc + h / 2 - 22, z0 + d, x1 - 2, yc + h / 2 - 6, z0 + d + 3, 'dark', 'Input terminals L N PE')
    b.box(comp, x0 + 2, yc - h / 2 + 6, z0 + d, x1 - 2, yc - h / 2 + 22, z0 + d + 3, 'dark', 'Output terminals + + - -')
    for i in range(3):
        b.cyl(comp, x0 + 8 + i * 12, yc + h / 2 - 14, z0 + d + 3, z0 + d + 4, 2.4, 'black', 'Screw')
    for i in range(4):
        b.cyl(comp, x0 + 6 + i * 9.3, yc - h / 2 + 14, z0 + d + 3, z0 + d + 4, 2.2, 'black', 'Screw')
    b.cyl(comp, x1 - 8, yc - h / 2 + 30, z0 + d, z0 + d + 1, 1.6, 'led_green', 'DC OK LED')
    b.cyl(comp, x0 + 8, yc - h / 2 + 30, z0 + d, z0 + d + 2, 2.5, 'orange', 'Voltage adjust')
    b.label(comp, body, tag, x0, yc + 6, x1, yc + 18, 4.0)
    b.label(comp, body, '24V DC 5A', x0, yc - 6, x1, yc + 4, 2.6, 'black')
    return comp


def plc_cpu(b, parent, row, x, name, tag, w=130, h=100, d=75):
    comp = b.component(name, parent)
    yc, z0 = py(RAIL_Y[row]), PLATE_FRONT
    x0, x1 = px(x), px(x + w)
    b.box(comp, x0, yc - h / 2, z0, x1, yc + h / 2, z0 + d - 4, 'dark', 'Housing')
    front = b.box(comp, x0 + 3, yc - h / 2 + 3, z0 + d - 4, x1 - 3, yc + h / 2 - 3, z0 + d, 'teal', 'Front cover')
    # Removable terminal blocks top (supply + DI) and bottom (DQ + AI).
    for (a, c) in ((x0 + 6, x0 + 60), (x0 + 64, x1 - 6)):
        b.box(comp, a, yc + h / 2 - 16, z0 + d, c, yc + h / 2 - 5, z0 + d + 4, 'midgrey', 'Top terminal block')
        b.box(comp, a, yc - h / 2 + 5, z0 + d, c, yc - h / 2 + 16, z0 + d + 4, 'midgrey', 'Bottom terminal block')
    # Status LEDs RUN/STOP, ERROR, MAINT.
    for i, c in enumerate(('led_green', 'led_red', 'led_yellow')):
        b.box(comp, x0 + 8, yc + 18 - i * 7, z0 + d, x0 + 14, yc + 22 - i * 7, z0 + d + 1, c, 'Status LED')
    # I/O status LEDs.
    for i in range(14):
        b.box(comp, x0 + 30 + i * 6, yc + 26, z0 + d, x0 + 33 + i * 6, yc + 29, z0 + d + 1, 'led_green', 'DI LED')
    for i in range(10):
        b.box(comp, x0 + 30 + i * 6, yc - 29, z0 + d, x0 + 33 + i * 6, yc - 26, z0 + d + 1, 'led_green', 'DQ LED')
    # Two PROFINET ports X1 P1/P2 on the underside front.
    for i in range(2):
        b.box(comp, x1 - 36 + i * 16, yc - h / 2 - 1, z0 + 20, x1 - 24 + i * 16, yc - h / 2 + 10, z0 + 40, 'black', 'RJ45 X1 P%d' % (i + 1))
    b.box(comp, x0 + 8, yc - 8, z0 + d, x0 + 22, yc - 4, z0 + d + 1, 'black', 'Memory card slot')
    b.label(comp, front, tag, x0 + 30, yc + 2, x1 - 10, yc + 18, 6.0)
    b.label(comp, front, 'CPU 1215C DC/DC/DC', x0 + 30, yc - 14, x1 - 10, yc - 2, 3.5)
    return comp


def drive(b, parent, row, x, name, tag, w=90, h=166, d=146):
    comp = b.component(name, parent)
    yc, z0 = py(RAIL_Y[row]), PLATE_FRONT
    x0, x1 = px(x), px(x + w)
    # Heat sink at the back with fins, power section in front.
    b.box(comp, x0, yc - h / 2, z0, x1, yc + h / 2, z0 + 30, 'silver', 'Heat sink')
    for i in range(9):
        fx = x0 + 4 + i * 10
        b.box(comp, fx, yc - h / 2, z0 + 30, fx + 2, yc + h / 2, z0 + 34, 'silver', 'Fin')
    body = b.box(comp, x0 + 3, yc - h / 2, z0 + 34, x1 - 3, yc + h / 2, z0 + d, 'dark', 'Housing')
    # Operator panel: display and keypad.
    b.box(comp, x0 + 15, yc + 30, z0 + d, x1 - 15, yc + 62, z0 + d + 2, 'black', 'Operator panel')
    b.box(comp, x0 + 20, yc + 44, z0 + d + 2, x1 - 20, yc + 58, z0 + d + 3, 'lcd', 'Display')
    for i in range(5):
        b.cyl(comp, x0 + 21 + i * 12, yc + 37, z0 + d + 2, z0 + d + 4, 3.0, 'midgrey', 'Key')
    # Ventilation slots and terminal covers.
    for i in range(6):
        b.box(comp, x0 + 15, yc - 45 - i * 6, z0 + d, x1 - 15, yc - 43 - i * 6, z0 + d + 0.5, 'black', 'Vent slot')
    b.box(comp, x0 + 8, yc + h / 2 - 14, z0 + d, x1 - 8, yc + h / 2 - 4, z0 + d + 1, 'midgrey', 'Mains terminal cover')
    b.box(comp, x0 + 8, yc - h / 2 + 4, z0 + d, x1 - 8, yc - h / 2 + 14, z0 + d + 1, 'midgrey', 'Motor terminal cover')
    b.label(comp, body, tag, x0, yc + 6, x1, yc + 22, 6.0)
    b.label(comp, body, 'VFD 1.5 kW', x0, yc - 10, x1, yc + 2, 4.0)
    return comp


def terminal_strip(b, parent, row, x, tag, terms):
    """Feed-through terminals 6.2 mm wide with screws and markers; PE terminals green/yellow."""
    comp = b.component('%s Terminal strip' % tag, parent)
    yc, z0 = py(RAIL_Y[row]), PLATE_FRONT
    cx = px(x)
    b.box(comp, cx - 1.5, yc - 22, z0, cx, yc + 22, z0 + 36, 'dark', 'End clamp')
    for t in terms:
        pe = t == 'PE'
        col = 'pe' if pe else 'grey'
        b.box(comp, cx, yc - 25, z0, cx + 6.2, yc + 25, z0 + 30, col, '%s:%s base' % (tag, t))
        b.box(comp, cx, yc - 16, z0 + 30, cx + 6.2, yc + 16, z0 + 45, col, '%s:%s body' % (tag, t))
        if pe:
            b.box(comp, cx, yc - 16, z0 + 45, cx + 6.2, yc - 10, z0 + 45.6, 'yellow', 'PE stripe')
        for sy in (yc + 21, yc - 21):
            b.cyl(comp, cx + 3.1, sy, z0 + 30, z0 + 31.2, 2.2, 'black', 'Screw')
        b.box(comp, cx + 0.6, yc - 3, z0 + 45, cx + 5.6, yc + 3, z0 + 45.8, 'white', 'Marker %s' % t)
        cx += 6.2
    b.box(comp, cx, yc - 22, z0, cx + 1.5, yc + 22, z0 + 36, 'dark', 'End plate')
    # Strip marker carrier above the terminals.
    carrier = b.box(comp, px(x), yc + 28, z0, max(cx, px(x) + 24), yc + 36, z0 + 2, 'white', 'Strip marker')
    b.label(comp, carrier, tag, px(x), yc + 28, max(cx, px(x) + 24), yc + 36, 4.0, 'black')
    return comp


def door_device(b, door, name, x, y, color, legend, front, dz, kind='button'):
    comp = b.component(name, door)
    b.cyl(comp, x, y, front, front + 8, 15, 'midgrey', 'Bezel')
    if kind == 'lamp':
        b.cyl(comp, x, y, front + 8, front + 14, 11, color, 'Lens')
    elif kind == 'selector':
        b.cyl(comp, x, y, front + 8, front + 12, 12, 'black', 'Selector body')
        b.box(comp, x - 3.5, y - 11, front + 12, x + 3.5, y + 11, front + 24, 'black', 'Selector lever')
    else:
        b.cyl(comp, x, y, front + 8, front + 12, 11.5, color, 'Push button')
    b.box(comp, x - 15, y - 20, dz - 55, x + 15, y + 20, dz, 'black', 'Contact block')
    plate = b.box(comp, x - 18, y - 33, front, x + 18, y - 21, front + 1, 'white', 'Legend plate')
    b.label(comp, plate, legend, x - 18, y - 33, x + 18, y - 21, 3.5, 'black')
    return comp


def build(builder):
    b = builder

    # ---- enclosure: five walls, open at the front ----------------------------------------------
    enc = b.component('+CAB1 Enclosure 600x800x300')
    shell = b.box_body(0, 0, 0, ENC_W, ENC_H, ENC_D)
    cavity = b.box_body(WALL, WALL, WALL, ENC_W - WALL, ENC_H - WALL, ENC_D + 10)
    b.tbm.booleanOperation(shell, cavity, adsk.fusion.BooleanTypes.DifferenceBooleanType)
    b.add(enc, shell, 'steel', 'Enclosure body')

    # Cable glands in the bottom wall (M25 for power, M20 for signals), pointing down.
    for i, (x, r) in enumerate(((120, 12.5), (200, 12.5), (300, 10), (380, 10), (460, 10))):
        b.add(enc, b.tbm.createCylinderOrCone(b.point(x, -12, 140), r * MM, b.point(x, 0, 140), r * MM),
              'black', 'Gland %d nut' % (i + 1))
        b.add(enc, b.tbm.createCylinderOrCone(b.point(x, -24, 140), (r - 3) * MM, b.point(x, -12, 140), (r - 5) * MM),
              'black', 'Gland %d seal' % (i + 1))

    # Filter fan -E1 on the right wall (low), outlet filter on the left wall (high), with louvres.
    fan = b.component('-E1 Filter fan 120x120', enc)
    fan_body = b.box(fan, ENC_W, 140, 90, ENC_W + 28, 260, 210, 'midgrey', 'Frame')
    for i in range(8):
        b.box(fan, ENC_W + 28, 150 + i * 13, 100, ENC_W + 30, 156 + i * 13, 200, 'dark', 'Louvre')
    outlet = b.component('Outlet filter 120x120', enc)
    b.box(outlet, -15, 600, 90, 0, 720, 210, 'midgrey', 'Frame')
    for i in range(8):
        b.box(outlet, -17, 610 + i * 13, 100, -15, 616 + i * 13, 200, 'dark', 'Louvre')

    # ---- door with its devices (+DOOR) ---------------------------------------------------------
    door = b.component('+DOOR Door')
    dz = ENC_D
    b.box(door, 0, 0, dz, ENC_W, ENC_H, dz + DOOR_T, 'steel', 'Door leaf')
    front = dz + DOOR_T
    b.box(door, 575, 380, front, 590, 470, front + 8, 'black', 'Lock base')
    b.box(door, 578, 395, front + 8, 587, 455, front + 25, 'black', 'Door handle')
    for hy in (100, 700):
        b.cyl(door, -2, hy, dz - 10, dz + 10, 6, 'midgrey', 'Hinge')

    # HMI -A2 (KTP400 class): bezel 140 x 116, 4.3" display, body behind the door.
    hmi = b.component('-A2 HMI 4in', door)
    bezel = b.box(hmi, 230, 582, front, 370, 698, front + 6, 'dark', 'Bezel')
    b.box(hmi, 245, 600, front + 6, 355, 680, front + 6.5, 'black', 'Display')
    b.box(hmi, 252, 607, front + 6.5, 348, 673, front + 6.8, 'lcd', 'Screen content')
    for i in range(4):
        b.box(hmi, 252 + i * 26, 586, front + 6, 266 + i * 26, 595, front + 7.5, 'midgrey', 'Function key F%d' % (i + 1))
    b.box(hmi, 238.5, 590.5, dz - 33, 361.5, 689.5, dz, 'dark', 'Body')
    b.label(hmi, bezel, '-A2', 330, 684, 368, 696, 3.5, 'white')

    # E-stop -S0: yellow legend ring and red mushroom head.
    es = b.component('-S0 Emergency stop', door)
    b.cyl(es, 500, 640, front, front + 2, 30, 'yellow', 'Legend ring')
    b.cyl(es, 500, 640, front + 2, front + 12, 15, 'midgrey', 'Bezel')
    b.add(es, b.tbm.createCylinderOrCone(b.point(500, 640, front + 12), 14 * MM,
                                         b.point(500, 640, front + 30), 20 * MM), 'red', 'Mushroom')
    b.box(es, 485, 620, dz - 55, 515, 660, dz, 'black', 'Contact blocks')
    plate = b.box(es, 470, 596, front, 530, 606, front + 1, 'white', 'Legend plate')
    b.label(es, plate, 'EMERGENCY STOP', 470, 596, 530, 606, 3.0, 'black')

    # Main switch handle (door coupling for -Q0), top left: red handle on yellow plate.
    qh = b.component('-Q0 Door handle', door)
    b.box(qh, 70, 600, front, 150, 680, front + 2, 'yellow', 'Handle plate')
    b.cyl(qh, 110, 640, front + 2, front + 10, 26, 'black', 'Handle base')
    b.box(qh, 102, 605, front + 10, 118, 675, front + 30, 'red', 'Handle lever')
    plate = b.box(qh, 80, 585, front, 140, 596, front + 1, 'white', 'Legend plate')
    b.label(qh, plate, 'MAIN SWITCH', 80, 585, 140, 596, 3.0, 'black')

    door_device(b, door, '-H1 Lamp Running (green)', 200, 510, 'green', 'RUNNING', front, dz, 'lamp')
    door_device(b, door, '-H2 Lamp Fault (red)', 300, 510, 'red', 'FAULT', front, dz, 'lamp')
    door_device(b, door, '-H3 Lamp Reset required (blue)', 400, 510, 'blue', 'RESET REQ.', front, dz, 'lamp')
    door_device(b, door, '-S1 Start (green)', 200, 420, 'green', 'START', front, dz)
    door_device(b, door, '-S2 Stop (red)', 300, 420, 'red', 'STOP', front, dz)
    door_device(b, door, '-S4 Reset (blue)', 400, 420, 'blue', 'RESET', front, dz)
    door_device(b, door, '-S3 Manual-Auto selector', 500, 420, 'black', 'MAN / AUTO', front, dz, 'selector')

    # ---- mounting plate +CAB1 ------------------------------------------------------------------
    plate = b.component('+CAB1 Mounting plate')
    b.box(plate, PLATE_X, PLATE_Y, PLATE_Z, PLATE_X + PLATE_W, PLATE_Y + PLATE_H, PLATE_FRONT, 'plate', 'Plate')

    # Slotted cable ducts 40 x 60 with covers.
    ducts = b.component('Cable ducts 40x60', plate)
    for name, x0, y0, w, h in (
            ('Duct top', 0, 700, 560, 40), ('Duct row A-B', 40, 470, 480, 40),
            ('Duct row B-C', 40, 170, 480, 40), ('Duct bottom', 0, 20, 560, 40),
            ('Duct left', 0, 60, 40, 640), ('Duct right', 520, 60, 40, 640)):
        b.box(ducts, px(x0), py(y0), PLATE_FRONT, px(x0 + w), py(y0 + h), PLATE_FRONT + 58, 'duct', name)
        b.box(ducts, px(x0) - 1, py(y0) - 1, PLATE_FRONT + 58, px(x0 + w) + 1, py(y0 + h) + 1, PLATE_FRONT + 60,
              'ductcover', name + ' cover')

    # DIN rails TS35 x 7.5 (hat profile).
    rails = b.component('DIN rails TS35', plate)
    for row, y in RAIL_Y.items():
        ry = py(y)
        b.box(rails, px(45), ry - 13.5, PLATE_FRONT, px(515), ry + 13.5, PLATE_FRONT + 1, 'rail', 'Rail %s web' % row)
        for s in (-1, 1):
            b.box(rails, px(45), ry + s * 13.5 - (1 if s > 0 else 0), PLATE_FRONT,
                  px(515), ry + s * 13.5 + (0 if s > 0 else 1), PLATE_FRONT + 7.5, 'rail', 'Rail %s wall' % row)
            b.box(rails, px(45), ry + s * 17.5 - (4 if s > 0 else 0), PLATE_FRONT + 6.5,
                  px(515), ry + s * 17.5 + (0 if s > 0 else 4), PLATE_FRONT + 7.5, 'rail', 'Rail %s flange' % row)

    # Row A: switching and protection (pages 3, 5, 6, 7).
    x = 55.0
    for name, tag, w, h, d, color, kind, poles, note in (
            ('-Q0 Main switch 3P 25A', '-Q0', 54, 80, 70, 'dark', 'switch', 3, '25A'),
            ('-F1 Motor breaker 3P 10A', '-F1', 54, 90, 75, 'grey', 'mcb', 3, 'C10'),
            ('-F2 MCB 1P+N 6A', '-F2', 36, 90, 75, 'grey', 'mcb', 2, 'C6'),
            ('-F11 MCB 1P 2A (1L+ PLC)', '-F11', 18, 90, 75, 'grey', 'mcb', 1, 'C2'),
            ('-F12 MCB 1P 2A (2L+ inputs)', '-F12', 18, 90, 75, 'grey', 'mcb', 1, 'C2'),
            ('-F13 MCB 1P 4A (3L+ outputs)', '-F13', 18, 90, 75, 'grey', 'mcb', 1, 'C4'),
            ('-K10 Safety relay PNOZ s3', '-K10', 22.5, 98, 120, 'yellow', 'relay', 2, None),
            ('-B1 Thermostat 35C', '-B1', 17.5, 67, 46, 'grey', 'thermostat', 1, None)):
        din_module(b, plate, 'A', x, name, tag, w, h, d, color, kind, poles, note)
        x += w + 6

    # Row B: contactor, power supply, PLC, drive (pages 4, 5, 8-10).
    din_module(b, plate, 'B', 55, '-K1 Contactor AC-3 9A', '-K1', 45, 85, 80, 'grey', 'contactor', 3)
    power_supply(b, plate, 'B', 106, '-T1 Power supply 24V DC 5A', '-T1')
    plc_cpu(b, plate, 'B', 152, '-A1 PLC CPU 1215C DC/DC/DC', '-A1')
    drive(b, plate, 'B', 300, '-U1 VFD 1.5 kW', '-U1')

    # Row C: terminal strips -X0 (infeed), -X1 (motor), -X2 (door and field signals).
    terminal_strip(b, plate, 'C', 55, '-X0', ['1', '2', '3', '4', 'PE'])
    terminal_strip(b, plate, 'C', 105, '-X1', ['1', '2', '3', 'PE'])
    terminal_strip(b, plate, 'C', 150, '-X2', ['1', '2', '3', '4', '5', '10', '11', '12'])

    # The motor -M1 (+FIELD) sits outside the cabinet and is not modelled.


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        # Build into the open design when it is empty; otherwise start a new document.
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design or design.rootComponent.occurrences.count or design.rootComponent.bRepBodies.count:
            app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
            design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.DirectDesignType
        builder = Builder(app, design)
        build(builder)
        app.activeViewport.fit()
        msg = 'CAB1 cabinet built with detailed devices.'
        if builder.label_errors:
            msg += '\n\n%d text labels could not be placed. First error:\n%s' % (
                builder.label_errors, builder.first_label_error)
        ui.messageBox(msg + '\n\nSizes are typical catalogue placeholders.')
    except Exception:
        if ui:
            ui.messageBox('CAB1 cabinet script failed:\n{}'.format(traceback.format_exc()))
