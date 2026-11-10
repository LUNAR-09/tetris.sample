# -*- coding: utf-8 -*-
"""
폐허의 도시 : 리빌드 3D  (Ruined City : Rebuild 3D)
망가진 로봇이 적을 쓰러뜨릴수록 몸이 수리되어 세계 최강의 로봇이 되는 3D 로그라이크 액션
(pygame 만으로 직접 만든 소프트웨어 3D 렌더러 사용 - 3인칭 시점)

[조작]
  W A S D     : 이동 (카메라 기준)         Space / ↑ : 점프 (증강으로 공중 점프)
  Q E / ← →   : 카메라 회전               사격은 가장 가까운 적을 향해 자동 조준 + 자동 발사
  P / ESC     : 일시정지                  1 2 3 : 증강 선택 (마우스 클릭도 가능)
"""
import pygame
import random
import math
import sys
import os
import json
from operator import itemgetter

pygame.init()

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
WORLD_W, WORLD_H = 900, 540          # 3D 화면 크기
PANEL_W = 200                        # 왼쪽 리더보드 너비
WIN_W, WIN_H = WORLD_W + PANEL_W, WORLD_H
FPS = 60
STAGE_TIME = 120.0                   # 2분마다 보스 + 스테이지 상승
ARENA = 24.0                         # 경기장 반 크기 (미터)
GRAV = 24.0
JUMP_V = 9.0

screen = pygame.display.set_mode((WIN_W, WIN_H))
pygame.display.set_caption("Ruined City : Rebuild 3D")
clock = pygame.time.Clock()


# ------------------------------------------------------------
# 폰트 (한글 폰트가 있으면 한글, 없으면 영어)
# ------------------------------------------------------------
def find_korean_font():
    names = ("malgungothic", "malgun gothic", "applegothic", "applesdgothicneo",
             "nanumgothic", "nanumbarungothic", "notosanscjkkr", "notosanskr",
             "gulim", "dotum", "batang")
    for n in names:
        try:
            p = pygame.font.match_font(n)
        except Exception:
            p = None
        if p:
            return p
    return None


KFONT = find_korean_font()
KO = KFONT is not None


def make_font(size):
    if KFONT:
        return pygame.font.Font(KFONT, size)
    return pygame.font.SysFont(None, int(size * 1.15))


F_S = make_font(15)
F_M = make_font(20)
F_L = make_font(34)
F_XL = make_font(58)


def T(ko, en):
    return ko if KO else en


# ------------------------------------------------------------
# 난이도
# ------------------------------------------------------------
DIFFS = [
    dict(key="rookie", ko="초보", en="ROOKIE", sko="초보", sen="ROK",
         hp=0.75, dmg=0.7, spawn=1.35, php=140, mult=1.0, color=(110, 230, 130)),
    dict(key="veteran", ko="베테랑", en="VETERAN", sko="베테랑", sen="VET",
         hp=1.0, dmg=1.0, spawn=1.0, php=115, mult=1.5, color=(240, 220, 90)),
    dict(key="insane", ko="인세인", en="INSANE", sko="인세인", sen="INS",
         hp=1.45, dmg=1.4, spawn=0.72, php=100, mult=2.5, color=(255, 140, 50)),
    dict(key="nightmare", ko="나이트메어", en="NIGHTMARE", sko="나이트", sen="NTM",
         hp=2.0, dmg=2.0, spawn=0.5, php=90, mult=4.0, color=(255, 60, 80)),
]


def dname(d):
    return d["ko"] if KO else d["en"]


def dshort(d):
    return d["sko"] if KO else d["sen"]


def diff_by_key(k):
    for d in DIFFS:
        if d["key"] == k:
            return d
    return DIFFS[1]


# ------------------------------------------------------------
# 기록(리더보드) 저장
# ------------------------------------------------------------
try:
    _BASE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _BASE = os.getcwd()
SAVE_PATH = os.path.join(_BASE, "robot3d_records.json")


def load_records():
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        recs = [r for r in data if isinstance(r, dict) and "score" in r]
        recs.sort(key=lambda r: -r["score"])
        return recs[:10]
    except Exception:
        return []


def save_records(recs):
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False)
    except Exception:
        pass


def add_record(recs, game):
    rec = dict(score=int(game.score), stage=game.stage, kills=game.p.kills,
               diff=game.d["key"], level=game.p.level)
    recs.append(rec)
    recs.sort(key=lambda r: -r["score"])
    del recs[10:]
    save_records(recs)
    game.saved = True
    return recs.index(rec) + 1 if rec in recs else None


# ------------------------------------------------------------
# 유틸
# ------------------------------------------------------------
def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerpc(a, b, k):
    return (int(a[0] + (b[0] - a[0]) * k), int(a[1] + (b[1] - a[1]) * k),
            int(a[2] + (b[2] - a[2]) * k))


def mulc(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


def turn_toward(cur, target, step):
    diff = (target - cur + math.pi) % (2 * math.pi) - math.pi
    return cur + clamp(diff, -step, step)


def draw_text(surf, text, font, color, pos, anchor="topleft", shadow=True):
    img = font.render(str(text), True, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = font.render(str(text), True, (0, 0, 0))
        surf.blit(sh, (r.x + 1, r.y + 1))
    surf.blit(img, r)
    return r


# ------------------------------------------------------------
# 3D 렌더러 (원근 투영 + 면 정렬 + 안개 + 간단한 조명)
# ------------------------------------------------------------
FOCAL = 560.0
CX, CY = WORLD_W / 2, 300.0
NEAR = 0.5
FAR = 150.0
PITCH = 0.42
FOG_COLOR = (138, 92, 78)
FOG_START, FOG_RANGE, FOG_MAX = 16.0, 60.0, 0.86
_LL = math.sqrt(0.4 ** 2 + 0.78 ** 2 + 0.48 ** 2)
LX, LY, LZ = 0.4 / _LL, 0.78 / _LL, -0.48 / _LL
AMB, DIF = 0.42, 0.62
HORIZON_Y = CY - FOCAL * math.tan(PITCH)

# 상자의 면 (꼭짓점 번호), 꼭짓점 번호 = ix*4 + iy*2 + iz
FACE_PX = (4, 5, 7, 6)
FACE_NX = (0, 1, 3, 2)
FACE_PY = (2, 3, 7, 6)
FACE_NY = (0, 1, 5, 4)
FACE_PZ = (1, 3, 7, 5)
FACE_NZ = (0, 2, 6, 4)


def clip_near(pts):
    out = []
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        ain = a[2] >= NEAR
        bin_ = b[2] >= NEAR
        if ain:
            out.append(a)
        if ain != bin_:
            t = (NEAR - a[2]) / (b[2] - a[2])
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, NEAR))
    return out


def make_sky():
    s = pygame.Surface((WORLD_W, WORLD_H))
    hy = int(HORIZON_Y)
    top, hor = (30, 22, 48), (176, 108, 84)
    for y in range(WORLD_H):
        if y < hy:
            k = clamp(y / max(1, hy), 0, 1)
            col = lerpc(top, hor, k ** 1.5)
        else:
            k = clamp((y - hy) / 160.0, 0, 1)
            col = lerpc(FOG_COLOR, (62, 50, 54), k)
        pygame.draw.line(s, col, (0, y), (WORLD_W, y))
    return s


SKY = make_sky()

TILE = 4.0
TN = 8
TILES = []
for _i in range(-TN, TN):
    for _j in range(-TN, TN):
        x0, z0 = _i * TILE, _j * TILE
        mx, mz = x0 + TILE / 2, z0 + TILE / 2
        inside = abs(mx) < ARENA and abs(mz) < ARENA
        v = ((_i * 7 + _j * 13) % 5) * 3
        if inside:
            base = (74 + v, 68 + v, 72 + v) if (_i + _j) % 2 == 0 else (66 + v, 60 + v, 64 + v)
        else:
            base = (50 + v // 2, 44 + v // 2, 48 + v // 2)
        TILES.append((((x0, z0), (x0 + TILE, z0), (x0 + TILE, z0 + TILE), (x0, z0 + TILE)), base))


class View:
    def __init__(self):
        self.pitch = PITCH
        self.dist = 12.0
        self.items = []
        self.under = []
        self.set_camera(0, 1, 0, 0)

    def set_camera(self, tx, ty, tz, yaw):
        sp, cp = math.sin(self.pitch), math.cos(self.pitch)
        sy, cy = math.sin(yaw), math.cos(yaw)
        self.yaw = yaw
        self.f = (sy * cp, -sp, cy * cp)
        self.r = (cy, 0.0, -sy)
        self.u = (sy * sp, cp, cy * sp)
        self.cam = (tx - self.f[0] * self.dist, ty - self.f[1] * self.dist, tz - self.f[2] * self.dist)

    def proj(self, x, y, z):
        """월드 좌표 → (화면x, 화면y, 깊이). 카메라 뒤면 None"""
        camx, camy, camz = self.cam
        dx, dy, dz = x - camx, y - camy, z - camz
        zc = dx * self.f[0] + dy * self.f[1] + dz * self.f[2]
        if zc < NEAR:
            return None
        xc = dx * self.r[0] + dz * self.r[2]
        yc = dx * self.u[0] + dy * self.u[1] + dz * self.u[2]
        return (CX + FOCAL * xc / zc, CY - FOCAL * yc / zc, zc)

    # ----- 바닥 -----
    def draw_floor(self, surf):
        camx, camy, camz = self.cam
        fx, fy, fz = self.f
        rx, rz = self.r[0], self.r[2]
        ux, uy, uz = self.u
        poly = pygame.draw.polygon
        for corners, base in TILES:
            pts = []
            for wx, wz in corners:
                dx, dy, dz = wx - camx, -camy, wz - camz
                pts.append((dx * rx + dz * rz, dx * ux + dy * uy + dz * uz, dx * fx + dy * fy + dz * fz))
            zmin = min(p[2] for p in pts)
            zmax = max(p[2] for p in pts)
            if zmax < NEAR:
                continue
            if zmin < NEAR:
                pts = clip_near(pts)
                if len(pts) < 3:
                    continue
            zc = sum(p[2] for p in pts) / len(pts)
            if zc > FAR + 20:
                continue
            sp = [(CX + FOCAL * x / z, CY - FOCAL * y / z) for x, y, z in pts]
            xs = [q[0] for q in sp]
            if max(xs) < 0 or min(xs) > WORLD_W:
                continue
            fog = clamp((zc - FOG_START) / FOG_RANGE, 0, FOG_MAX)
            col = lerpc(base, FOG_COLOR, fog)
            poly(surf, col, sp)
            if zc < 50:
                poly(surf, mulc(col, 0.78), sp, 1)

    # ----- 3D 상자 추가 -----
    def add_box(self, x, y, z, hw, hh, hd, yaw, color, em=False, flash=0.0, edge=True):
        camx, camy, camz = self.cam
        fx, fy, fz = self.f
        rx, rz = self.r[0], self.r[2]
        ux, uy, uz = self.u
        dx, dy, dz = x - camx, y - camy, z - camz
        zc = dx * fx + dy * fy + dz * fz
        rad = hw + hh + hd
        if zc < -rad or zc > FAR:
            return
        if zc > NEAR:
            sxc = CX + FOCAL * (dx * rx + dz * rz) / zc
            m = rad * FOCAL / zc + 40
            if sxc < -m or sxc > WORLD_W + m:
                return
        c = math.cos(yaw)
        s = math.sin(yaw)
        # 보이는 면 판정 (카메라 쪽을 향한 면만)
        tx = -dx * c + dz * s
        ty = -dy
        tz = -(dx * s + dz * c)
        d_x = c * LX - s * LZ
        d_z = s * LX + c * LZ
        faces = []
        if tx > hw:
            faces.append((FACE_PX, AMB + DIF * max(0.0, d_x)))
        elif tx < -hw:
            faces.append((FACE_NX, AMB + DIF * max(0.0, -d_x)))
        if ty > hh:
            faces.append((FACE_PY, AMB + DIF * max(0.0, LY)))
        elif ty < -hh:
            faces.append((FACE_NY, AMB + DIF * max(0.0, -LY)))
        if tz > hd:
            faces.append((FACE_PZ, AMB + DIF * max(0.0, d_z)))
        elif tz < -hd:
            faces.append((FACE_NZ, AMB + DIF * max(0.0, -d_z)))
        if not faces:
            return
        ax, az = hw * c, -hw * s
        bx, bz = hd * s, hd * c
        V = []
        allin = True
        for ix in (-1, 1):
            for iy in (-1, 1):
                for iz in (-1, 1):
                    wx = dx + ix * ax + iz * bx
                    wy = dy + iy * hh
                    wz = dz + ix * az + iz * bz
                    vz = wx * fx + wy * fy + wz * fz
                    if vz < NEAR:
                        allin = False
                    V.append((wx * rx + wz * rz, wx * ux + wy * uy + wz * uz, vz))
        if allin:
            P = [(CX + FOCAL * a / c3, CY - FOCAL * b / c3) for a, b, c3 in V]
        base = color
        if flash > 0:
            base = lerpc(color, (255, 255, 255), min(0.75, flash * 9))
        fog = clamp((zc - FOG_START) / FOG_RANGE, 0, FOG_MAX)
        out = []
        for idxs, br in faces:
            if em:
                col = base
            else:
                br = min(1.15, br)
                col = (min(255, int(base[0] * br)), min(255, int(base[1] * br)), min(255, int(base[2] * br)))
            if fog > 0:
                col = lerpc(col, FOG_COLOR, fog)
            ed = mulc(col, 0.55) if (edge and fog < 0.5 and not em) else None
            if allin:
                pts = [P[i] for i in idxs]
            else:
                cp = clip_near([V[i] for i in idxs])
                if len(cp) < 3:
                    continue
                pts = [(CX + FOCAL * a / c3, CY - FOCAL * b / c3) for a, b, c3 in cp]
            out.append((col, pts, ed))
        if out:
            self.items.append((zc, 0, out))

    def add_dot(self, x, y, z, radius, color, halo=None):
        p = self.proj(x, y, z)
        if p is None or p[2] > FAR:
            return
        r = max(1, int(radius * FOCAL / p[2]))
        self.items.append((p[2], 1, (color, p[0], p[1], r, halo)))

    def add_line(self, a, b, color, width=2):
        pa = self.proj(*a)
        pb = self.proj(*b)
        if pa is None or pb is None:
            return
        self.items.append((min(pa[2], pb[2]), 2, (color, (pa[0], pa[1]), (pb[0], pb[1]), width)))

    def add_flash(self, x, y, z, radius, color, alpha):
        p = self.proj(x, y, z)
        if p is None:
            return
        r = min(240, max(2, int(radius * FOCAL / p[2])))
        self.items.append((p[2] - 0.5, 3, (color, p[0], p[1], r, alpha)))

    def add_shadow(self, x, z, r):
        self.under.append((0, x, z, r))

    def add_ring(self, x, z, r, color, width=2):
        self.under.append((1, x, z, r, color, width))

    def flush(self, surf):
        for u in self.under:
            if u[0] == 0:
                p = self.proj(u[1], 0.02, u[2])
                if p is None:
                    continue
                w = max(2, int(u[3] * FOCAL / p[2] * 2))
                h = max(1, int(w * 0.42))
                pygame.draw.ellipse(surf, lerpc((20, 17, 22), FOG_COLOR, clamp((p[2] - FOG_START) / FOG_RANGE, 0, 0.8)),
                                    (int(p[0] - w / 2), int(p[1] - h / 2), w, h))
            else:
                pts = []
                for k in range(20):
                    a = k * math.tau / 20
                    q = self.proj(u[1] + math.sin(a) * u[3], 0.05, u[2] + math.cos(a) * u[3])
                    if q is None:
                        pts = None
                        break
                    pts.append((q[0], q[1]))
                if pts:
                    pygame.draw.lines(surf, u[4], True, pts, u[5])
        self.items.sort(key=itemgetter(0), reverse=True)
        for z, k, d in self.items:
            if k == 0:
                for col, pts, ed in d:
                    pygame.draw.polygon(surf, col, pts)
                    if ed:
                        pygame.draw.polygon(surf, ed, pts, 1)
            elif k == 1:
                col, x, y, r, halo = d
                if halo:
                    pygame.draw.circle(surf, halo, (int(x), int(y)), r + 2)
                pygame.draw.circle(surf, col, (int(x), int(y)), r)
            elif k == 2:
                col, a, b, w = d
                pygame.draw.line(surf, col, a, b, w)
            else:
                col, x, y, r, alpha = d
                fs = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(fs, (col[0], col[1], col[2], alpha), (r, r), r)
                surf.blit(fs, (int(x) - r, int(y) - r))
        self.items = []
        self.under = []


VIEW = View()


# ------------------------------------------------------------
# 월드: 장애물(올라갈 수 있는 콘크리트 블록), 폐허 배경
# ------------------------------------------------------------
class Obstacle:
    def __init__(self, x, z, hw, hd, top, color):
        self.x, self.z, self.hw, self.hd, self.top, self.color = x, z, hw, hd, top, color


OBST = [
    Obstacle(-9, -7, 2.2, 2.2, 1.2, (122, 116, 110)),
    Obstacle(10, -9, 2.5, 2.0, 1.6, (112, 108, 112)),
    Obstacle(-13, 8, 2.0, 3.0, 1.2, (118, 112, 106)),
    Obstacle(11, 10, 3.0, 2.2, 1.0, (126, 118, 108)),
    Obstacle(0, -15, 3.5, 1.5, 2.0, (108, 104, 110)),
    Obstacle(-18, -2, 1.5, 3.0, 1.6, (116, 110, 106)),
    Obstacle(17, 0, 1.5, 2.0, 2.0, (110, 106, 112)),
    Obstacle(2, 14, 2.0, 2.0, 2.6, (120, 114, 108)),
    Obstacle(-4, 5, 1.2, 1.2, 0.8, (128, 120, 112)),
]


def push_out(x, z, r, y):
    """원-사각형 충돌: 장애물에 파고들면 밀어낸다"""
    pushed = False
    for ob in OBST:
        if y >= ob.top - 0.25:
            continue
        nx = clamp(x, ob.x - ob.hw, ob.x + ob.hw)
        nz = clamp(z, ob.z - ob.hd, ob.z + ob.hd)
        dx, dz = x - nx, z - nz
        d2 = dx * dx + dz * dz
        if d2 < r * r:
            if d2 > 1e-9:
                d = math.sqrt(d2)
                x = nx + dx / d * r
                z = nz + dz / d * r
            else:
                ox = ob.hw - abs(x - ob.x)
                oz = ob.hd - abs(z - ob.z)
                if ox < oz:
                    x = ob.x + (ob.hw + r) * (1 if x >= ob.x else -1)
                else:
                    z = ob.z + (ob.hd + r) * (1 if z >= ob.z else -1)
            pushed = True
    return x, z, pushed


def support_height(x, z, r, y):
    """발밑 지면 높이 (장애물 위에 서 있을 수 있음)"""
    h = 0.0
    for ob in OBST:
        if ob.top <= h or y < ob.top - 0.3:
            continue
        if abs(x - ob.x) < ob.hw + r * 0.7 and abs(z - ob.z) < ob.hd + r * 0.7:
            h = ob.top
    return h


_rnd = random.Random(5)
SCENERY = []
for _k in range(30):
    a = _k / 30 * math.tau + _rnd.uniform(-0.05, 0.05)
    d = _rnd.uniform(38, 64)
    bx, bz = math.cos(a) * d, math.sin(a) * d
    w, dd, h = _rnd.uniform(3.5, 8), _rnd.uniform(3.5, 8), _rnd.uniform(9, 38)
    col = (_rnd.randint(60, 86), _rnd.randint(48, 66), _rnd.randint(60, 80))
    yaw = _rnd.uniform(0, 1.5)
    SCENERY.append((bx, h / 2, bz, w, h / 2, dd, yaw, col))
    if _rnd.random() < 0.75:
        h2 = _rnd.uniform(3, 8)
        SCENERY.append((bx + _rnd.uniform(-1, 1) * w * 0.3, h + h2 / 2, bz + _rnd.uniform(-1, 1) * dd * 0.3,
                        w * 0.62, h2 / 2, dd * 0.62, yaw + 0.3, mulc(col, 0.8)))
RUBBLE = []
for _k in range(26):
    rx_, rz_ = _rnd.uniform(-ARENA + 2, ARENA - 2), _rnd.uniform(-ARENA + 2, ARENA - 2)
    if any(abs(rx_ - o.x) < o.hw + 1 and abs(rz_ - o.z) < o.hd + 1 for o in OBST) or math.hypot(rx_, rz_) < 3:
        continue
    s_ = _rnd.uniform(0.12, 0.35)
    RUBBLE.append((rx_, s_, rz_, s_ * 1.3, s_, s_ * 0.9, _rnd.uniform(0, 3),
                   (_rnd.randint(80, 120), _rnd.randint(70, 100), _rnd.randint(70, 96))))


def draw_scene(view):
    for (x, y, z, hw, hh, hd, yaw, col) in SCENERY:
        view.add_box(x, y, z, hw, hh, hd, yaw, col, edge=False)
    for (x, y, z, hw, hh, hd, yaw, col) in RUBBLE:
        view.add_box(x, y, z, hw, hh, hd, yaw, col)
    wall = (74, 68, 78)
    for (wx, wz, hx, hz) in ((0, ARENA + 0.5, ARENA + 1, 0.5), (0, -ARENA - 0.5, ARENA + 1, 0.5),
                             (ARENA + 0.5, 0, 0.5, ARENA + 1), (-ARENA - 0.5, 0, 0.5, ARENA + 1)):
        view.add_box(wx, 0.5, wz, hx, 0.5, hz, 0, wall, edge=False)
        view.add_box(wx, 1.04, wz, hx, 0.05, hz, 0, (255, 170, 50), em=True, edge=False)
    for ob in OBST:
        view.add_box(ob.x, ob.top / 2, ob.z, ob.hw, ob.top / 2, ob.hd, 0, ob.color)
        view.add_box(ob.x, ob.top + 0.04, ob.z, ob.hw + 0.06, 0.05, ob.hd + 0.06, 0, mulc(ob.color, 1.25))
        view.add_box(ob.x + ob.hw * 0.5, ob.top + 0.28, ob.z - ob.hd * 0.3, 0.03, 0.26, 0.03, 0, (140, 86, 54))


# ------------------------------------------------------------
# 증강 아이콘 (코드로 그리는 벡터 아이콘)
# ------------------------------------------------------------
_ICON_CACHE = {}


def draw_icon_shape(s, key, col):
    pg = pygame.draw
    W = (245, 248, 255)
    dk = lerpc(col, (0, 0, 0), 0.5)
    lt = lerpc(col, (255, 255, 255), 0.55)
    if key == "hp":
        pts = [(14, 10), (50, 10), (57, 28), (47, 52), (32, 61), (17, 52), (7, 28)]
        pg.polygon(s, col, pts)
        pg.polygon(s, dk, pts, 3)
        pg.rect(s, W, (28, 19, 8, 30))
        pg.rect(s, W, (17, 30, 30, 8))
    elif key == "dmg":
        pg.polygon(s, (255, 150, 50), [(22, 44), (42, 44), (32, 63)])
        pg.polygon(s, (255, 220, 100), [(27, 44), (37, 44), (32, 56)])
        pg.rect(s, col, (22, 16, 20, 30), border_radius=3)
        pg.polygon(s, col, [(22, 16), (42, 16), (32, 2)])
        pg.rect(s, lt, (26, 20, 5, 22))
        pg.rect(s, dk, (22, 40, 20, 5))
    elif key == "rate":
        for i in range(3):
            ox = 8 + i * 17
            pg.lines(s, col if i < 2 else lt, False, [(ox, 14), (ox + 15, 32), (ox, 50)], 7)
    elif key == "speed":
        pts = [(38, 3), (14, 35), (29, 35), (22, 61), (50, 26), (35, 26)]
        pg.polygon(s, col, pts)
        pg.polygon(s, lt, pts, 2)
    elif key == "jump":
        pts = [(32, 4), (50, 24), (39, 24), (39, 40), (25, 40), (25, 24), (14, 24)]
        pg.polygon(s, col, pts)
        pg.polygon(s, dk, pts, 2)
        pg.ellipse(s, lt, (12, 46, 40, 10), 3)
        pg.ellipse(s, col, (18, 54, 28, 7), 3)
    elif key == "multi":
        for ex in (10, 32, 54):
            pg.line(s, col, (32, 58), (ex, 14), 5)
            pg.circle(s, lt, (ex, 12), 6)
        pg.circle(s, W, (32, 58), 5)
    elif key == "pierce":
        pg.rect(s, dk, (16, 8, 9, 48), border_radius=2)
        pg.rect(s, dk, (39, 8, 9, 48), border_radius=2)
        pg.line(s, col, (3, 32), (50, 32), 6)
        pg.polygon(s, lt, [(61, 32), (46, 20), (46, 44)])
    elif key == "explosive":
        pts = []
        for i in range(16):
            a = i * math.tau / 16
            rr = 30 if i % 2 == 0 else 14
            pts.append((32 + math.cos(a) * rr, 32 + math.sin(a) * rr))
        pg.polygon(s, col, pts)
        pg.circle(s, lt, (32, 32), 12)
        pg.circle(s, W, (32, 32), 5)
    elif key == "lifesteal":
        pg.polygon(s, col, [(32, 3), (15, 34), (49, 34)])
        pg.circle(s, col, (32, 40), 18)
        pg.rect(s, W, (29, 30, 6, 20))
        pg.rect(s, W, (22, 37, 20, 6))
    elif key == "regen":
        pg.arc(s, col, (8, 8, 48, 48), 0.5, 3.4, 6)
        pg.arc(s, lt, (8, 8, 48, 48), 3.7, 6.6, 6)
        pg.polygon(s, col, [(52, 14), (60, 32), (42, 30)])
        pg.polygon(s, lt, [(12, 50), (4, 32), (22, 34)])
        pg.rect(s, W, (30, 22, 5, 20))
        pg.rect(s, W, (23, 29, 19, 5))
    elif key == "shield":
        pts = [(32, 3), (56, 12), (54, 38), (32, 61), (10, 38), (8, 12)]
        pg.polygon(s, col, pts)
        pg.polygon(s, lt, [(32, 12), (47, 18), (46, 36), (32, 51), (18, 36), (17, 18)])
        pg.polygon(s, dk, pts, 3)
    elif key == "missile":
        pg.polygon(s, (255, 150, 50), [(27, 46), (37, 46), (32, 63)])
        pg.rect(s, col, (24, 14, 16, 34), border_radius=3)
        pg.polygon(s, lt, [(24, 14), (40, 14), (32, 2)])
        pg.polygon(s, dk, [(24, 38), (12, 54), (24, 48)])
        pg.polygon(s, dk, [(40, 38), (52, 54), (40, 48)])
        pg.circle(s, W, (32, 28), 5)
    elif key == "saw":
        pts = []
        for i in range(20):
            a = i * math.tau / 20
            rr = 30 if i % 2 == 0 else 22
            pts.append((32 + math.cos(a) * rr, 32 + math.sin(a) * rr))
        pg.polygon(s, col, pts)
        pg.circle(s, lt, (32, 32), 16, 3)
        pg.circle(s, dk, (32, 32), 7)
    elif key == "crit":
        pg.circle(s, col, (32, 32), 21, 5)
        for a, b in (((32, 3), (32, 18)), ((32, 46), (32, 61)), ((3, 32), (18, 32)), ((46, 32), (61, 32))):
            pg.line(s, col, a, b, 5)
        pg.circle(s, lt, (32, 32), 7)
    else:  # heal
        pg.rect(s, col, (6, 18, 52, 38), border_radius=7)
        pg.rect(s, lt, (22, 8, 20, 12), 4, border_radius=3)
        pg.rect(s, W, (28, 26, 8, 22))
        pg.rect(s, W, (21, 33, 22, 8))


def make_icon(key, color, size=64):
    ck = (key, size)
    if ck in _ICON_CACHE:
        return _ICON_CACHE[ck]
    big = pygame.Surface((64, 64), pygame.SRCALPHA)
    draw_icon_shape(big, key, color)
    img = big if size == 64 else pygame.transform.smoothscale(big, (size, size))
    _ICON_CACHE[ck] = img
    return img


# ------------------------------------------------------------
# 증강 (로그라이크 요소)
# ------------------------------------------------------------
def a_hp(p):
    p.max_hp += 30
    p.hp = min(p.max_hp, p.hp + 30)


def a_dmg(p):
    p.dmg *= 1.25


def a_rate(p):
    p.fire_delay = max(0.08, p.fire_delay * 0.83)


def a_speed(p):
    p.speed *= 1.12


def a_jump(p):
    p.extra_jumps += 1


def a_multi(p):
    p.bullets += 1


def a_pierce(p):
    p.pierce += 1


def a_explosive(p):
    p.explosive += 1


def a_lifesteal(p):
    p.lifesteal += 2.0


def a_regen(p):
    p.regen += 1.0


def a_shield(p):
    p.shield_lvl += 1
    p.shield_ready = True


def a_missile(p):
    p.missile += 1


def a_saw(p):
    p.saw += 1


def a_crit(p):
    p.crit += 0.15


def a_heal(p):
    p.hp = min(p.max_hp, p.hp + p.max_hp * 0.5)


AUGS = [
    dict(key="hp", ko=("강화 장갑", "최대 HP +30, 즉시 30 회복"), en=("Reinforced Armor", "Max HP +30 and heal 30"), max=99, fn=a_hp, color=(110, 220, 120)),
    dict(key="dmg", ko=("고출력 탄", "공격력 +25%"), en=("Overcharged Rounds", "Damage +25%"), max=8, fn=a_dmg, color=(255, 110, 90)),
    dict(key="rate", ko=("고속 장전", "발사 속도 +20%"), en=("Rapid Loader", "Fire rate +20%"), max=6, fn=a_rate, color=(255, 200, 80)),
    dict(key="speed", ko=("추진 부스터", "이동 속도 +12%"), en=("Thruster Boost", "Move speed +12%"), max=4, fn=a_speed, color=(120, 200, 255)),
    dict(key="jump", ko=("공중 점프", "공중에서 점프 +1회"), en=("Air Jump", "+1 mid-air jump"), max=2, fn=a_jump, color=(170, 160, 255)),
    dict(key="multi", ko=("다중 발사", "한 번에 쏘는 탄 +1"), en=("Multi-Shot", "+1 projectile per shot"), max=4, fn=a_multi, color=(120, 230, 255)),
    dict(key="pierce", ko=("관통탄", "탄이 적을 +1 관통"), en=("Piercing Rounds", "Bullets pierce +1 enemy"), max=3, fn=a_pierce, color=(200, 200, 255)),
    dict(key="explosive", ko=("폭발탄", "착탄 시 주변 폭발"), en=("Explosive Rounds", "Bullets explode on hit"), max=3, fn=a_explosive, color=(255, 150, 60)),
    dict(key="lifesteal", ko=("나노 수리", "적 처치 시 HP +2"), en=("Nano Repair", "Heal 2 HP per kill"), max=5, fn=a_lifesteal, color=(110, 255, 160)),
    dict(key="regen", ko=("자가 수복", "초당 HP +1 회복"), en=("Auto-Repair", "Regenerate 1 HP/sec"), max=4, fn=a_regen, color=(90, 230, 190)),
    dict(key="shield", ko=("에너지 실드", "피해 1회 막기 (재충전)"), en=("Energy Shield", "Block 1 hit (recharges)"), max=3, fn=a_shield, color=(100, 200, 255)),
    dict(key="missile", ko=("추적 미사일", "주기적으로 유도 미사일 발사"), en=("Homing Missiles", "Auto-fires homing missiles"), max=4, fn=a_missile, color=(255, 120, 80)),
    dict(key="saw", ko=("회전 톱날", "몸 주위를 도는 톱날 +1"), en=("Orbital Saw", "+1 orbiting saw blade"), max=4, fn=a_saw, color=(210, 210, 220)),
    dict(key="crit", ko=("치명 코어", "치명타 확률 +15% (2배 피해)"), en=("Critical Core", "+15% crit chance (x2 dmg)"), max=4, fn=a_crit, color=(255, 230, 90)),
    dict(key="heal", ko=("긴급 수리 키트", "HP 50% 즉시 회복"), en=("Emergency Kit", "Heal 50% HP now"), max=999, fn=a_heal, color=(255, 120, 160)),
]


def aug_name(a):
    return a["ko"][0] if KO else a["en"][0]


def aug_desc(a):
    return a["ko"][1] if KO else a["en"][1]


# ------------------------------------------------------------
# 이펙트 (3D)
# ------------------------------------------------------------
class Spark:
    def __init__(self, x, y, z, vx, vy, vz, life, color, size=0.08, grav=9.0):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = vx, vy, vz
        self.life = self.max_life = life
        self.color, self.size, self.grav = color, size, grav

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z += self.vz * dt
        self.vy -= self.grav * dt
        if self.y < 0.03:
            self.y = 0.03
            self.vy = abs(self.vy) * 0.3
            self.vx *= 0.6
            self.vz *= 0.6
        self.life -= dt

    def draw(self, view):
        k = max(0.0, self.life / self.max_life)
        view.add_dot(self.x, self.y, self.z, self.size * (0.4 + 0.6 * k), lerpc((40, 20, 10), self.color, k))


class Ring:
    def __init__(self, x, z, r0, r1, life, color, width=3):
        self.x, self.z, self.r0, self.r1 = x, z, r0, r1
        self.life = self.max_life = life
        self.color, self.width = color, width

    def update(self, dt):
        self.life -= dt

    def draw(self, view):
        k = clamp(self.life / self.max_life, 0.0, 1.0)
        r = self.r1 + (self.r0 - self.r1) * k
        view.add_ring(self.x, self.z, max(0.05, r), lerpc((30, 24, 28), self.color, k), self.width)


class Flash:
    def __init__(self, x, y, z, r0, r1, life, color):
        self.x, self.y, self.z, self.r0, self.r1 = x, y, z, r0, r1
        self.life = self.max_life = life
        self.color = color

    def update(self, dt):
        self.life -= dt

    def draw(self, view):
        k = clamp(self.life / self.max_life, 0.0, 1.0)
        view.add_flash(self.x, self.y, self.z, self.r1 + (self.r0 - self.r1) * k, self.color, int(200 * k))


class FloatText:
    def __init__(self, x, y, z, text, color, big=False, life=1.0):
        self.x, self.y, self.z, self.text, self.color, self.big = x, y, z, text, color, big
        self.life = self.max_life = life

    def update(self, dt):
        self.y += 1.3 * dt
        self.life -= dt


# ------------------------------------------------------------
# 총알 (3D)
# ------------------------------------------------------------
class Bullet:
    def __init__(self, x, y, z, vx, vy, vz, dmg, friendly, r=0.14, color=(255, 255, 255),
                 pierce=0, explosive=0, homing=False, life=1.6, crit=False):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = vx, vy, vz
        self.dmg, self.friendly, self.r, self.color = dmg, friendly, r, color
        self.pierce, self.explosive, self.homing = pierce, explosive, homing
        self.life, self.crit = life, crit
        self.speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        self.hit = set()
        self.dead = False

    def update(self, g, dt):
        if self.homing:
            tg = g.nearest_enemy(self.x, self.y, self.z, 999)
            if tg:
                tx, ty, tz = tg.x - self.x, tg.y + tg.h * 0.5 - self.y, tg.z - self.z
                d = math.sqrt(tx * tx + ty * ty + tz * tz) + 1e-6
                k = min(1.0, 5.0 * dt)
                nx = self.vx / self.speed * (1 - k) + tx / d * k
                ny = self.vy / self.speed * (1 - k) + ty / d * k
                nz = self.vz / self.speed * (1 - k) + tz / d * k
                n = math.sqrt(nx * nx + ny * ny + nz * nz) + 1e-6
                self.vx, self.vy, self.vz = nx / n * self.speed, ny / n * self.speed, nz / n * self.speed
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z += self.vz * dt
        self.life -= dt
        if (self.life <= 0 or self.y < 0.02 or self.y > 40 or
                abs(self.x) > ARENA + 14 or abs(self.z) > ARENA + 14):
            self.dead = True

    def draw(self, view):
        c = self.color
        if self.friendly:
            view.add_line((self.x, self.y, self.z), (self.x - self.vx * 0.04, self.y - self.vy * 0.04, self.z - self.vz * 0.04),
                          lerpc((20, 20, 30), c, 0.7), 3)
        view.add_dot(self.x, self.y, self.z, self.r, c, lerpc((0, 0, 0), c, 0.45))
        if not self.friendly:
            view.add_dot(self.x, self.y, self.z, self.r * 0.45, (255, 245, 225))


# ------------------------------------------------------------
# 파츠(상자) 기반 모델링 헬퍼
# ------------------------------------------------------------
def B(P, lx, ly, lz, hw, hh, hd, col, em=False, yo=0.0):
    P.append((lx, ly, lz, hw, hh, hd, col, em, yo))


def draw_parts(view, e, parts, fall=0.0):
    c = math.cos(e.yaw)
    s = math.sin(e.yaw)
    fl = e.flash
    ca, sa = math.cos(fall), math.sin(fall)
    for (lx, ly, lz, hw, hh, hd, col, em, yo) in parts:
        if fall > 0:
            ly, lz = ly * ca - lz * sa, ly * sa + lz * ca
            if fall > 0.8:
                hh, hd = hd, hh
        wx = e.x + lx * c + lz * s
        wz = e.z - lx * s + lz * c
        view.add_box(wx, e.y + ly, wz, hw, hh, hd, e.yaw + yo, col, em, fl)


# ------------------------------------------------------------
# 플레이어 로봇 (수리 단계에 따라 모습이 변함)
# ------------------------------------------------------------
REPAIR_AT = [6, 20, 42, 75, 120]
REPAIR_NAMES = [("다리", "LEGS"), ("사격팔", "GUN ARM"), ("왼팔", "LEFT ARM"),
                ("머리", "HEAD"), ("코어", "CORE")]


def robot_parts(p, t, firing):
    r = p.repair
    legs_ok, gun_ok, arm_ok, head_ok, core_ok = r > 0, r > 1, r > 2, r > 3, r > 4
    if r >= 5:
        ARM, ACC, GLOW = (240, 228, 196), (255, 196, 60), (255, 236, 150)
    else:
        ARM, ACC, GLOW = (208, 216, 230), (70, 215, 255), (140, 240, 255)
    DULL, DARK, RUST, CABLE = (126, 128, 138), (42, 46, 58), (138, 86, 54), (240, 205, 60)
    c_leg = ARM if legs_ok else DULL
    c_gun = ARM if gun_ok else DULL
    c_arm = ARM if arm_ok else DULL
    c_head = ARM if head_ok else DULL
    c_body = ARM if core_ok else DULL
    moving = p.moving and p.on_ground
    air = not p.on_ground
    sw = math.sin(t * 11) * 0.28 if moving else 0.0
    bob = abs(math.sin(t * 11)) * 0.05 if moving else math.sin(t * 2.5) * 0.015
    P = []
    # 다리
    for side in (-1, 1):
        zo = (0.2 * side) if air else sw * side
        if side < 0 and not legs_ok:
            B(P, -0.22, 0.24, zo * 0.4, 0.09, 0.2, 0.1, RUST)
            B(P, -0.22, 0.05, zo * 0.4, 0.11, 0.05, 0.14, DARK)
            B(P, -0.18, 0.5, 0.05, 0.014, 0.1, 0.014, CABLE, True)
        else:
            B(P, side * 0.22, 0.64, zo * 0.5, 0.1, 0.2, 0.11, c_leg)
            B(P, side * 0.22, 0.3, zo, 0.085, 0.2, 0.095, mulc(c_leg, 0.82))
            B(P, side * 0.22, 0.07, zo + 0.06, 0.12, 0.07, 0.17, DARK)
            if legs_ok:
                B(P, side * 0.22, 0.48, zo * 0.8 + 0.1, 0.06, 0.04, 0.04, ACC, True)
    # 몸통
    B(P, 0, 0.95 + bob, 0, 0.24, 0.09, 0.15, DARK)
    B(P, 0, 1.09 + bob, 0, 0.2, 0.1, 0.14, mulc(c_body, 0.75))
    B(P, 0, 1.34 + bob, 0, 0.3, 0.2, 0.19, c_body)
    B(P, 0, 1.45 + bob, 0.1, 0.26, 0.09, 0.12, mulc(c_body, 1.06))
    if core_ok:
        B(P, 0, 1.33 + bob, 0.2, 0.08, 0.08, 0.02, GLOW, True)
        B(P, 0, 1.33 + bob, 0.2, 0.13, 0.13, 0.015, DARK)
    else:
        B(P, 0.13, 1.32 + bob, 0.2, 0.09, 0.09, 0.02, RUST)
        dim = (230, 70, 60) if int(t * 4) % 3 == 0 else (90, 40, 40)
        B(P, -0.07, 1.34 + bob, 0.2, 0.05, 0.05, 0.02, dim, True)
        B(P, 0.02, 1.2 + bob, 0.2, 0.2, 0.015, 0.02, DARK)
    # 백팩 + 부스터
    B(P, 0, 1.32 + bob, -0.26, 0.2, 0.2, 0.08, DARK)
    for sx in (-0.1, 0.1):
        B(P, sx, 1.15 + bob, -0.31, 0.05, 0.07, 0.05, (90, 96, 110))
        if air:
            B(P, sx, 0.98 + bob, -0.34, 0.035, 0.12, 0.035, (255, 160, 60), True)
    # 머리
    B(P, 0, 1.6 + bob, 0, 0.07, 0.05, 0.07, DARK)
    B(P, 0, 1.74 + bob, 0.02, 0.15, 0.13, 0.14, c_head)
    if head_ok:
        B(P, 0, 1.75 + bob, 0.165, 0.12, 0.045, 0.02, ACC, True)
        B(P, 0.1, 1.99 + bob, 0, 0.012, 0.1, 0.012, DARK)
        B(P, 0.1, 2.1 + bob, 0, 0.025, 0.025, 0.025, (255, 80, 80), True)
        for sx in (-0.17, 0.17):
            B(P, sx, 1.74 + bob, 0, 0.03, 0.06, 0.06, ACC)
    else:
        B(P, -0.05, 1.75 + bob, 0.165, 0.07, 0.04, 0.02, (60, 100, 112), True)
        B(P, 0.08, 1.75 + bob, 0.165, 0.04, 0.04, 0.02, (28, 30, 38))
        B(P, 0.1, 1.92 + bob, 0, 0.012, 0.06, 0.012, DARK)
        B(P, 0.13, 1.99 + bob, 0, 0.04, 0.012, 0.012, DARK)
        B(P, 0.14, 1.8 + bob, 0.1, 0.05, 0.05, 0.04, RUST)
    # 어깨
    B(P, 0.39, 1.44 + bob, 0, 0.11, 0.09, 0.13, c_gun)
    B(P, -0.39, 1.44 + bob, 0, 0.11, 0.09, 0.13, c_arm)
    if gun_ok:
        B(P, 0.39, 1.54 + bob, 0, 0.09, 0.015, 0.11, ACC, True)
    if arm_ok:
        B(P, -0.39, 1.54 + bob, 0, 0.09, 0.015, 0.11, ACC, True)
    # 사격 팔 (오른쪽, 앞으로 뻗음)
    if gun_ok:
        B(P, 0.39, 1.24 + bob, 0.04, 0.07, 0.14, 0.07, DARK)
        B(P, 0.39, 1.1 + bob, 0.38, 0.09, 0.09, 0.3, c_gun)
        B(P, 0.39, 1.1 + bob, 0.78, 0.05, 0.05, 0.14, DARK)
        B(P, 0.39, 1.1 + bob, 0.94, 0.06, 0.06, 0.03, (255, 240, 160) if firing else ACC, True)
    else:
        B(P, 0.39, 1.27 + bob, 0.1, 0.07, 0.1, 0.08, RUST)
        B(P, 0.39, 1.16 + bob, 0.25, 0.06, 0.06, 0.12, DARK)
    # 왼팔
    if arm_ok:
        B(P, -0.39, 1.24 + bob, -sw * 0.3, 0.07, 0.14, 0.07, DARK)
        B(P, -0.39, 1.0 + bob, -sw * 0.7 + 0.05, 0.065, 0.14, 0.065, c_arm)
        B(P, -0.39, 0.8 + bob, -sw + 0.08, 0.07, 0.06, 0.07, ACC)
    else:
        B(P, -0.39, 1.32 + bob, 0, 0.07, 0.08, 0.07, RUST)
        B(P, -0.41, 1.07 + bob, 0, 0.014, 0.16, 0.014, CABLE, True)
    return P


def draw_player(view, p, t, dying=None):
    parts = robot_parts(p, t, p.muzzle > 0)
    view.add_shadow(p.x, p.z, 0.8 / (1 + p.y * 0.4))
    if p.repair >= 5 and dying is None:
        view.add_flash(p.x, p.y + 1.0, p.z, 1.6 + 0.1 * math.sin(t * 5), (255, 215, 90), 55)
    if dying is not None:
        fall = clamp(dying / 0.9, 0.0, 1.0) * 1.45
        draw_parts(view, p, parts, fall)
        return
    draw_parts(view, p, parts)
    if p.shield_ready:
        view.add_flash(p.x, p.y + 1.0, p.z, 1.25, (110, 210, 255), 70)


# ------------------------------------------------------------
# 플레이어
# ------------------------------------------------------------
class Player:
    r = 0.55
    h = 1.9

    def __init__(self, diff):
        self.x = self.z = self.y = 0.0
        self.vx = self.vz = self.vy = 0.0
        self.kx = self.kz = 0.0
        self.yaw = 0.0
        self.on_ground = True
        self.moving = False
        self.flash = 0.0
        self.muzzle = 0.0
        self.max_hp = float(diff["php"])
        self.hp = self.max_hp
        self.dmg = 10.0
        self.fire_delay = 0.34
        self.fire_cd = 0.0
        self.speed = 7.0
        self.extra_jumps = 0
        self.air_left = 0
        self.bullets = 1
        self.pierce = 0
        self.explosive = 0
        self.lifesteal = 0.0
        self.regen = 0.0
        self.crit = 0.05
        self.shield_lvl = 0
        self.shield_ready = False
        self.shield_cd = 0.0
        self.missile = 0
        self.missile_cd = 2.0
        self.saw = 0
        self.saw_angle = 0.0
        self.inv = 0.0
        self.xp = 0
        self.level = 1
        self.kills = 0
        self.repair = 0
        self.aug = {}

    def xp_need(self):
        return 25 + 15 * (self.level - 1)


# ------------------------------------------------------------
# 일반 적 (모델 + AI)
# ------------------------------------------------------------
ETYPES = {
    "scrap": dict(r=0.55, h=1.6, hp=22, speed=3.0, dmg=10, score=10, xp=6, kind="ground"),
    "kami": dict(r=0.45, h=1.0, hp=14, speed=5.2, dmg=22, score=15, xp=8, kind="ground"),
    "drone": dict(r=0.55, h=0.8, hp=16, speed=3.6, dmg=8, score=14, xp=7, kind="fly", shoot=2.8, hover=3.2),
    "gunner": dict(r=0.5, h=1.9, hp=34, speed=2.4, dmg=8, score=22, xp=12, kind="ranged", shoot=1.8),
    "tank": dict(r=1.15, h=1.5, hp=100, speed=1.7, dmg=18, score=45, xp=25, kind="ranged", shoot=3.2),
}


def parts_scrap(e):
    P = []
    sw = math.sin(e.age * 9 + e.phase) * 0.25
    RU, ST, DK = (152, 100, 62), (124, 128, 140), (60, 42, 32)
    for sd in (-1, 1):
        B(P, sd * 0.2, 0.3, sw * sd, 0.1, 0.3, 0.11, DK)
        B(P, sd * 0.2, 0.05, sw * sd + 0.05, 0.12, 0.05, 0.16, (40, 34, 30))
    B(P, 0, 0.92, 0.04, 0.3, 0.3, 0.2, RU)
    B(P, 0.08, 0.98, 0.22, 0.17, 0.16, 0.02, ST)
    B(P, -0.1, 0.78, 0.22, 0.1, 0.05, 0.02, (90, 60, 40))
    B(P, 0.4, 1.12, 0, 0.1, 0.08, 0.15, ST)
    B(P, -0.4, 1.12, 0, 0.1, 0.08, 0.15, ST)
    B(P, 0, 1.4, 0.1, 0.17, 0.14, 0.15, ST)
    B(P, 0, 1.42, 0.26, 0.11, 0.04, 0.02, (255, 60, 40), True)
    B(P, 0.1, 1.62, 0, 0.012, 0.1, 0.012, DK)
    for sd in (-1, 1):
        B(P, sd * 0.42, 0.88, 0.3 + sw * sd * 0.3, 0.07, 0.07, 0.3, ST)
        B(P, sd * 0.42, 0.88, 0.62 + sw * sd * 0.3, 0.05, 0.03, 0.07, (200, 80, 60))
    return P


def parts_kami(e):
    P = []
    pulse = 0.5 + 0.5 * math.sin(e.age * (14 if e.hp < e.max_hp else 8))
    RD = lerpc((190, 46, 44), (255, 110, 70), pulse)
    B(P, 0, 0.5, 0, 0.3, 0.3, 0.3, RD)
    B(P, 0, 0.5, 0, 0.22, 0.38, 0.22, mulc(RD, 0.8))
    for sx, sz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        B(P, sx * 0.42, 0.5, sz * 0.42, 0.1 if sx else 0.05, 0.06, 0.1 if sz else 0.05, (240, 170, 120))
    B(P, 0, 0.5, 0.31, 0.12, 0.07, 0.02, (255, 255, 120) if int(e.age * 8) % 2 else (130, 20, 20), True)
    B(P, 0, 0.92, 0, 0.05, 0.07, 0.05, (255, 230, 90) if int(e.age * 10) % 2 else (200, 50, 40), True)
    for sx in (-1, 1):
        for sz in (-1, 1):
            B(P, sx * 0.2, 0.1, sz * 0.2, 0.07, 0.1, 0.07, (60, 44, 44))
    return P


def parts_drone(e):
    P = []
    BL, LB = (90, 140, 192), (140, 186, 230)
    B(P, 0, 0.25, 0, 0.26, 0.1, 0.26, BL)
    B(P, 0, 0.37, 0, 0.15, 0.05, 0.15, LB)
    B(P, 0, 0.22, 0.27, 0.09, 0.05, 0.02, (255, 70, 60), True)
    B(P, 0.38, 0.25, 0, 0.14, 0.02, 0.03, (60, 80, 100))
    B(P, -0.38, 0.25, 0, 0.14, 0.02, 0.03, (60, 80, 100))
    B(P, 0, 0.25, 0.38, 0.03, 0.02, 0.14, (60, 80, 100))
    B(P, 0, 0.25, -0.38, 0.03, 0.02, 0.14, (60, 80, 100))
    for rx, rz in ((0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5)):
        B(P, rx, 0.31, rz, 0.22, 0.01, 0.03, (210, 220, 230), False, e.age * 40)
    return P


def parts_gunner(e):
    P = []
    BL, LB, DK = (110, 122, 154), (150, 162, 192), (36, 40, 52)
    sw = math.sin(e.age * 6) * 0.1
    for sd in (-1, 1):
        B(P, sd * 0.13, 0.4, sw * sd, 0.06, 0.4, 0.07, DK)
        B(P, sd * 0.13, 0.04, sw * sd + 0.05, 0.08, 0.04, 0.12, DK)
    B(P, 0, 1.15, 0, 0.22, 0.32, 0.16, BL)
    B(P, 0, 1.3, 0.12, 0.16, 0.1, 0.06, LB)
    B(P, 0, 1.72, 0.02, 0.14, 0.13, 0.12, LB)
    B(P, 0, 1.74, 0.14, 0.1, 0.04, 0.02, (255, 70, 60), True)
    B(P, 0.25, 1.15, 0.45, 0.05, 0.06, 0.5, DK)
    B(P, 0.25, 1.24, 0.35, 0.03, 0.03, 0.1, (255, 120, 80), True)
    B(P, -0.1, 1.7, -0.14, 0.014, 0.22, 0.014, DK)
    return P


def parts_tank(e):
    P = []
    TR, OL, OL2, DK = (50, 54, 50), (92, 116, 82), (112, 138, 100), (36, 44, 36)
    for sd in (-1, 1):
        B(P, sd * 0.88, 0.26, 0, 0.26, 0.26, 1.05, TR)
        for k in range(4):
            B(P, sd * 0.88, 0.26, -0.75 + k * 0.5, 0.28, 0.16, 0.14, (88, 94, 88))
    B(P, 0, 0.58, 0, 0.62, 0.2, 0.98, OL)
    B(P, 0, 0.82, -0.12, 0.46, 0.12, 0.72, OL2)
    B(P, 0, 1.08, 0.0, 0.38, 0.18, 0.4, OL2)
    B(P, 0, 1.1, 0.9, 0.07, 0.07, 0.55, DK)
    glow = (255, 160, 60) if e.cd < 0.5 and e.cd > 0 else (90, 60, 40)
    B(P, 0, 1.1, 1.48, 0.09, 0.09, 0.04, glow, True)
    B(P, 0.55, 0.6, 0.98, 0.1, 0.06, 0.02, (255, 240, 180), True)
    B(P, -0.55, 0.6, 0.98, 0.1, 0.06, 0.02, (255, 240, 180), True)
    B(P, 0.2, 1.3, -0.1, 0.1, 0.04, 0.1, DK)
    return P


class Enemy:
    is_boss = False

    def __init__(self, g, t, x, z, y=0.0):
        cfg = ETYPES[t]
        self.t = t
        self.kind = cfg["kind"]
        self.r, self.h = cfg["r"], cfg["h"]
        st = g.stage - 1
        self.max_hp = cfg["hp"] * g.d["hp"] * (1 + 0.22 * st)
        self.hp = self.max_hp
        self.speed = min(cfg["speed"] * (1 + 0.04 * st), cfg["speed"] * 1.6) * random.uniform(0.92, 1.08)
        self.dmg = cfg["dmg"] * g.d["dmg"] * (1 + 0.08 * st)
        self.score = cfg["score"]
        self.xp = int(cfg["xp"] * (1 + 0.1 * st))
        self.shoot = cfg.get("shoot", 0)
        self.hover = cfg.get("hover", 0)
        self.cd = random.uniform(0.8, max(1.0, self.shoot)) if self.shoot else 0
        self.x, self.z, self.y = float(x), float(z), float(y if y else self.hover)
        self.yaw = random.uniform(0, math.tau)
        self.flash = 0.0
        self.grace = 0.8
        self.saw_cd = 0.0
        self.dead = False
        self.phase = random.random() * 6.28
        self.age = 0.0
        self.avoid_t = 0.0
        self.avoid_dir = 1
        self.strafe = random.choice((-1, 1))

    def parts(self, t):
        return {"scrap": parts_scrap, "kami": parts_kami, "drone": parts_drone,
                "gunner": parts_gunner, "tank": parts_tank}[self.t](self)

    def ground_move(self, mvx, mvz, dt):
        if self.avoid_t > 0:
            self.avoid_t -= dt
            c, s = math.cos(self.avoid_dir * 1.1), math.sin(self.avoid_dir * 1.1)
            mvx, mvz = mvx * c - mvz * s, mvx * s + mvz * c
        self.x += mvx * dt
        self.z += mvz * dt
        self.x, self.z, pushed = push_out(self.x, self.z, self.r, self.y)
        if pushed and self.avoid_t <= 0:
            self.avoid_t = 0.7
            self.avoid_dir = random.choice((-1, 1))
        self.x = clamp(self.x, -ARENA + self.r, ARENA - self.r)
        self.z = clamp(self.z, -ARENA + self.r, ARENA - self.r)

    def update(self, g, dt):
        self.age += dt
        self.grace = max(0.0, self.grace - dt)
        self.flash = max(0.0, self.flash - dt)
        self.saw_cd -= dt
        p = g.p
        dx, dz = p.x - self.x, p.z - self.z
        dist = math.hypot(dx, dz) + 1e-6
        ux, uz = dx / dist, dz / dist
        self.yaw = turn_toward(self.yaw, math.atan2(dx, dz), 9 * dt)
        spd = self.speed
        if self.kind == "fly":
            ang = self.phase + self.age * 0.7
            tx, tz = p.x + math.sin(ang) * 6.0, p.z + math.cos(ang) * 6.0
            ddx, ddz = tx - self.x, tz - self.z
            dd = math.hypot(ddx, ddz) + 1e-6
            step = min(dd, spd * dt)
            self.x = clamp(self.x + ddx / dd * step, -ARENA, ARENA)
            self.z = clamp(self.z + ddz / dd * step, -ARENA, ARENA)
            hy = self.hover + math.sin(self.age * 2 + self.phase) * 0.4
            self.y += (hy - self.y) * min(1.0, 3 * dt)
            self.cd -= dt
            if self.cd <= 0 and self.grace <= 0:
                self.cd = self.shoot * random.uniform(0.8, 1.2)
                g.aim_shot(self.x, self.y + 0.25, self.z, 9.0, self.dmg * 0.8, 0.16)
            return
        if self.t == "gunner":
            if dist > 11:
                mv = 1.0
            elif dist < 7:
                mv = -1.0
            else:
                mv = 0.0
            if self.age % 3.0 < dt:
                self.strafe = random.choice((-1, 1))
            self.ground_move(ux * mv * spd - uz * self.strafe * spd * 0.6,
                             uz * mv * spd + ux * self.strafe * spd * 0.6, dt)
        elif self.t == "tank":
            mv = 1.0 if dist > 8 else 0.0
            self.ground_move(ux * mv * spd, uz * mv * spd, dt)
        else:
            self.ground_move(ux * spd, uz * spd, dt)
        if self.shoot:
            self.cd -= dt
            if self.cd <= 0 and self.grace <= 0:
                self.cd = self.shoot * random.uniform(0.9, 1.2)
                if self.t == "tank":
                    g.aim_shot(self.x + math.sin(self.yaw) * 1.5, 1.1, self.z + math.cos(self.yaw) * 1.5,
                               9.0, self.dmg * 0.6, 0.3)
                else:
                    g.aim_shot(self.x + math.sin(self.yaw) * 0.8, 1.15, self.z + math.cos(self.yaw) * 0.8,
                               10.0, self.dmg, 0.16)


# ------------------------------------------------------------
# 보스
# ------------------------------------------------------------
def parts_boss(b):
    P = []
    en = b.enraged
    t = b.age
    pulse = 0.5 + 0.5 * math.sin(t * (12 if en else 6))
    core = lerpc((130, 24, 24), (255, 130, 90), pulse)

    def tint(c):
        return (min(255, c[0] + 45), max(0, c[1] - 15), max(0, c[2] - 15)) if en else c

    if b.idx == 0:       # 강철 골리앗
        sw = math.sin(t * 5) * 0.4 if b.y < 0.05 and not b.leaping else 0.0
        S1, S2, DK = tint((108, 114, 132)), tint((74, 78, 94)), (36, 38, 48)
        for sd in (-1, 1):
            B(P, sd * 0.9, 0.6, sw * sd, 0.5, 0.6, 0.55, S2)
            B(P, sd * 0.9, 1.5, sw * sd * 0.5, 0.45, 0.35, 0.5, S1)
            B(P, sd * 0.9, 0.1, sw * sd + 0.2, 0.55, 0.1, 0.75, DK)
        B(P, 0, 2.0, 0, 0.9, 0.3, 0.6, DK)
        B(P, 0, 3.0, 0, 1.5, 0.95, 0.9, S1)
        B(P, 0, 3.5, 0.45, 1.3, 0.3, 0.55, tint((136, 142, 160)))
        B(P, 0, 2.95, 0.92, 0.45, 0.45, 0.05, core, True)
        for sd in (-1, 1):
            B(P, sd * 2.0, 3.6, 0, 0.55, 0.45, 0.7, S2)
            B(P, sd * 2.0, 2.7, 0.2, 0.35, 0.9, 0.35, S1)
            B(P, sd * 2.0, 2.2, 1.1, 0.3, 0.3, 1.0, DK)
            B(P, sd * 2.0, 2.2, 2.15, 0.2, 0.2, 0.08, (255, 160, 80) if b.cd1 < 0.5 else (80, 60, 50), True)
            B(P, sd * 2.0, 4.1, 0, 0.1, 0.25, 0.1, (170, 176, 190))
        B(P, 0, 4.3, 0.1, 0.55, 0.4, 0.5, tint((136, 142, 160)))
        B(P, 0, 4.35, 0.6, 0.45, 0.07, 0.03, core, True)
    elif b.idx == 1:     # 하늘의 사신
        D1, D2, DK = tint((96, 32, 48)), tint((62, 26, 42)), (30, 20, 30)
        flap = math.sin(t * 4) * 0.35
        B(P, 0, 0.9, 0, 0.9, 0.4, 1.4, D1)
        B(P, 0, 1.3, 0.4, 0.6, 0.2, 0.7, D2)
        B(P, 0, 1.15, 1.35, 0.5, 0.3, 0.4, D2)
        B(P, 0, 1.15, 1.76, 0.4, 0.06, 0.03, core, True)
        B(P, 0, 0.45, 0, 0.5, 0.1, 0.5, core, True)
        B(P, 0, 0.95, -1.9, 0.18, 0.18, 0.6, D2)
        for sd in (-1, 1):
            B(P, sd * 2.4, 1.0 + flap * sd * 0.0 + flap, -0.2, 1.6, 0.06, 0.9, D2)
            B(P, sd * 4.2, 1.0 + flap * 1.8, -0.4, 0.9, 0.05, 0.6, D1)
            B(P, sd * 0.75, 0.5, 1.2, 0.12, 0.12, 0.55, DK)
            B(P, sd * 0.75, 0.5, 1.78, 0.08, 0.08, 0.03, (255, 150, 90), True)
    else:                # 오메가 코어
        P1, P2, DK = tint((62, 52, 108)), tint((98, 84, 160)), (30, 26, 46)
        for sx in (-1, 1):
            for sz in (-1, 1):
                B(P, sx * 1.0, 0.7, sz * 1.0, 0.3, 0.7, 0.3, DK)
        B(P, 0, 2.2, 0, 1.2, 1.2, 1.2, P1)
        B(P, 0, 2.2, 0, 0.9, 1.45, 0.9, P2)
        B(P, 0, 2.2, 1.22, 0.6, 0.4, 0.04, core, True)
        B(P, 0, 2.2, 1.24, 0.22, 0.22, 0.04, (20, 10, 20), True)
        for k in range(4):
            a = t * 1.6 + k * math.pi / 2
            B(P, math.cos(a) * 2.2, 2.2 + math.sin(t * 2 + k) * 0.3, math.sin(a) * 2.2, 0.35, 0.35, 0.35, tint((170, 150, 255)), False, a)
        B(P, 0, 2.2, 0, 2.0, 0.07, 0.12, tint((150, 130, 230)), False, t)
        B(P, 0, 2.2, 0, 2.0, 0.07, 0.12, tint((150, 130, 230)), False, t + math.pi / 2)
    return P


class Boss:
    is_boss = True
    NAMES = [("강철 골리앗", "IRON GOLIATH"), ("하늘의 사신", "SKY REAPER"), ("오메가 코어", "OMEGA CORE")]
    DIMS = [(2.1, 4.8), (2.4, 2.0), (1.9, 4.4)]

    def __init__(self, g, n):
        self.n = n
        self.idx = n % 3
        self.t = "boss"
        self.kind = "fly" if self.idx == 1 else "ground"
        self.r, self.h = self.DIMS[self.idx]
        self.max_hp = 450 * (1 + 0.55 * n) * g.d["hp"]
        self.hp = self.max_hp
        self.dmg = 22 * g.d["dmg"] * (1 + 0.08 * n)
        self.score = 300 * (n + 1)
        self.xp = 90
        p = g.p
        a = random.uniform(0, math.tau)
        self.x = clamp(p.x + math.sin(a) * 15, -ARENA + 3, ARENA - 3)
        self.z = clamp(p.z + math.cos(a) * 15, -ARENA + 3, ARENA - 3)
        self.y = 13.0
        self.vy = 0.0
        self.yaw = 0.0
        self.flash = 0.0
        self.grace = 1.8
        self.saw_cd = 0.0
        self.dead = False
        self.age = 0.0
        self.cd1, self.cd2 = 2.5, 5.0
        self.leaping = False
        self.leap_dx = self.leap_dz = 0.0
        self.orbit = random.uniform(0, 6.28)
        self.landed = False

    @property
    def name(self):
        return self.NAMES[self.idx][0] if KO else self.NAMES[self.idx][1]

    @property
    def enraged(self):
        return self.hp < self.max_hp * 0.5

    def parts(self, t):
        return parts_boss(self)

    def update(self, g, dt):
        self.age += dt
        self.grace = max(0.0, self.grace - dt)
        self.flash = max(0.0, self.flash - dt)
        self.saw_cd -= dt
        p = g.p
        dx, dz = p.x - self.x, p.z - self.z
        dist = math.hypot(dx, dz) + 1e-6
        ux, uz = dx / dist, dz / dist
        self.yaw = turn_toward(self.yaw, math.atan2(dx, dz), 3.0 * dt)
        rage = 0.65 if self.enraged else 1.0
        spd = 1.35 if self.enraged else 1.0
        active = self.grace <= 0
        chest = (p.x, p.y + 1.2, p.z)

        if self.idx == 1:     # 하늘의 사신: 플레이어 주위를 선회
            self.orbit += dt * 0.5 * spd
            tx = clamp(p.x + math.sin(self.orbit) * 9, -ARENA + 2, ARENA - 2)
            tz = clamp(p.z + math.cos(self.orbit) * 9, -ARENA + 2, ARENA - 2)
            k = min(1.0, 1.4 * dt)
            self.x += (tx - self.x) * k
            self.z += (tz - self.z) * k
            ty = 6.5 + math.sin(self.age * 1.4) * 0.6
            self.y += (ty - self.y) * min(1.0, 2.0 * dt)
            if active:
                self.cd1 -= dt
                if self.cd1 <= 0:
                    self.cd1 = 2.2 * rage
                    off = random.uniform(0, math.tau)
                    for k2 in range(12):
                        a = off + k2 * math.tau / 12
                        ca = math.cos(0.4)
                        g.enemy_dir(self.x, self.y + 0.8, self.z, math.sin(a) * ca, -math.sin(0.4), math.cos(a) * ca,
                                    9.0, self.dmg * 0.5, 0.2)
                self.cd2 -= dt
                if self.cd2 <= 0:
                    self.cd2 = 3.6 * rage
                    for o in (-0.18, 0.0, 0.18):
                        g.aim_shot(self.x, self.y + 0.8, self.z, 11.0, self.dmg * 0.6, 0.2, yaw_off=o)
            return

        # 지상 보스: 중력 + 착지 충격파
        self.vy -= GRAV * dt
        self.y += self.vy * dt
        if self.y <= 0:
            if self.vy < -6 and not self.landed:
                g.shockwave(self.x, self.z, 6.0, self.dmg * 0.8, self.grace <= 0)
            self.landed = True if self.vy < -6 else self.landed
            if self.vy < -6:
                self.landed = False
            self.y = 0.0
            self.vy = 0.0
            if self.leaping:
                self.leaping = False
        if self.idx == 0:     # 강철 골리앗
            if self.leaping:
                self.x += self.leap_dx * dt
                self.z += self.leap_dz * dt
            elif dist > 3.5:
                self.x += ux * 2.3 * spd * dt
                self.z += uz * 2.3 * spd * dt
            if active:
                self.cd1 -= dt
                if self.cd1 <= 0:
                    self.cd1 = 2.3 * rage
                    for o in (-0.22, 0.0, 0.22):
                        g.aim_shot(self.x, 2.4, self.z, 11.0, self.dmg * 0.55, 0.22, yaw_off=o)
                self.cd2 -= dt
                if self.cd2 <= 0 and self.y <= 0 and not self.leaping and dist > 5:
                    self.cd2 = 5.5 * rage
                    self.vy = 12.0
                    self.leaping = True
                    self.leap_dx, self.leap_dz = ux * 9.0, uz * 9.0
        else:                 # 오메가 코어
            if dist > 5:
                self.x += ux * 1.9 * spd * dt
                self.z += uz * 1.9 * spd * dt
            if active:
                self.cd1 -= dt
                if self.cd1 <= 0:
                    self.cd1 = 1.5 * rage
                    for o in (-0.4, -0.2, 0.0, 0.2, 0.4):
                        g.aim_shot(self.x, 2.2, self.z, 9.5, self.dmg * 0.45, 0.2, yaw_off=o)
                self.cd2 -= dt
                if self.cd2 <= 0:
                    self.cd2 = 6.0 * rage
                    g.rings.append(Ring(self.x, self.z, 0.5, 4.0, 0.5, (160, 120, 255), 3))
                    g.spawn_specific("scrap", self.x + 2.5, self.z)
                    g.spawn_specific("kami", self.x - 2.5, self.z)
        self.x, self.z, _ = push_out(self.x, self.z, self.r, self.y)
        self.x = clamp(self.x, -ARENA + self.r, ARENA - self.r)
        self.z = clamp(self.z, -ARENA + self.r, ARENA - self.r)


# ------------------------------------------------------------
# 게임 본체
# ------------------------------------------------------------
class Game:
    def __init__(self, diff_index):
        self.di = diff_index
        self.d = DIFFS[diff_index]
        self.p = Player(self.d)
        self.enemies, self.pb, self.eb = [], [], []
        self.sparks, self.rings, self.flashes, self.texts, self.delayed = [], [], [], [], []
        self.stage = 1
        self.stage_t = 0.0
        self.boss_count = 0
        self.spawn_t = 1.2
        self.score = 0
        self.total_t = 0.0
        self.anim = 0.0
        self.shake = 0.0
        self.banner = 0.0
        self.banner_text = ""
        self.pending_aug = 0
        self.choices = []
        self.card_rects = []
        self.state = "play"          # play / paused / augment / dying / over
        self.death_t = 0.0
        self.death_fx = 0.0
        self.saved = False
        self.rank = None
        self.cam_yaw = 0.0

    # ---------- 편의 ----------
    def nearest_enemy(self, x, y, z, maxd=40, need_visible=True):
        best, bd = None, maxd
        for e in self.enemies:
            if e.dead or (need_visible and e.grace > 0):
                continue
            d = math.sqrt((e.x - x) ** 2 + (e.y + e.h * 0.5 - y) ** 2 + (e.z - z) ** 2)
            if d < bd:
                best, bd = e, d
        return best

    def enemy_dir(self, x, y, z, dx, dy, dz, speed, dmg, r=0.18, color=(255, 90, 70)):
        n = math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-9
        self.eb.append(Bullet(x, y, z, dx / n * speed, dy / n * speed, dz / n * speed, dmg, False, r, color, life=5.0))

    def aim_shot(self, x, y, z, speed, dmg, r=0.18, yaw_off=0.0):
        p = self.p
        dx, dy, dz = p.x - x, p.y + 1.1 - y, p.z - z
        if yaw_off:
            c, s = math.cos(yaw_off), math.sin(yaw_off)
            dx, dz = dx * c + dz * s, -dx * s + dz * c
        self.enemy_dir(x, y, z, dx, dy, dz, speed, dmg, r)

    def popup(self, x, y, z, text, color=(255, 255, 255), big=False, life=1.0):
        if len(self.texts) < 40:
            self.texts.append(FloatText(x, y, z, text, color, big, life))

    # ---------- 이펙트 ----------
    def explode(self, x, y, z, size=1.0, color=(255, 170, 50)):
        self.flashes.append(Flash(x, y, z, 0.3 * size, 1.5 * size, 0.35, (255, 200, 110)))
        self.flashes.append(Flash(x, y, z, 0.15 * size, 0.8 * size, 0.2, (255, 250, 225)))
        self.rings.append(Ring(x, z, 0.3 * size, 2.4 * size, 0.4, (255, 190, 110), 3))
        if len(self.sparks) < 300:
            for _ in range(int(10 * size) + 6):
                a = random.uniform(0, math.tau)
                up = random.uniform(-0.2, 1.0)
                sp = random.uniform(2, 8) * (0.6 + 0.4 * size)
                col = random.choice([color, (255, 230, 100), (255, 110, 40), (210, 210, 210)])
                self.sparks.append(Spark(x, y, z, math.cos(a) * sp, up * sp, math.sin(a) * sp,
                                         random.uniform(0.35, 0.9), col, random.uniform(0.06, 0.12)))
            for _ in range(int(3 * size) + 2):
                a = random.uniform(0, math.tau)
                sp = random.uniform(2, 6)
                self.sparks.append(Spark(x, y, z, math.cos(a) * sp, random.uniform(3, 8), math.sin(a) * sp,
                                         random.uniform(0.7, 1.2), (96, 96, 104), random.uniform(0.1, 0.2), 14.0))
        self.shake = min(0.7, max(self.shake, 0.08 * size))

    def hit_spark(self, x, y, z, color):
        for _ in range(4):
            self.sparks.append(Spark(x, y, z, random.uniform(-3, 3), random.uniform(0, 3), random.uniform(-3, 3),
                                     0.25, color, 0.06, 6.0))

    def aoe(self, x, y, z, radius, dmg, exclude=None):
        self.rings.append(Ring(x, z, 0.2, radius, 0.25, (255, 170, 80), 3))
        self.flashes.append(Flash(x, y, z, radius * 0.2, radius * 0.7, 0.2, (255, 190, 100)))
        for e in self.enemies:
            if e.dead or e is exclude:
                continue
            d = math.sqrt((e.x - x) ** 2 + (e.y + e.h * 0.5 - y) ** 2 + (e.z - z) ** 2) - e.r
            if d <= radius:
                self.damage_enemy(e, dmg, False)

    def shockwave(self, x, z, radius, dmg, harmful=True):
        self.rings.append(Ring(x, z, 0.5, radius, 0.5, (255, 200, 120), 4))
        self.rings.append(Ring(x, z, 0.3, radius * 0.7, 0.4, (255, 240, 200), 2))
        self.shake = max(self.shake, 0.3)
        p = self.p
        if harmful and p.y < 0.9 and math.hypot(p.x - x, p.z - z) < radius:
            self.hurt_player(dmg, x, z)

    # ---------- 스테이지 / 보스 ----------
    def next_stage(self):
        self.stage += 1
        self.stage_t = 0.0
        boss = Boss(self, self.boss_count)
        self.boss_count += 1
        self.enemies.append(boss)
        self.banner = 3.0
        self.banner_text = T("경고! 보스 출현", "WARNING! BOSS APPROACHING")
        self.shake = max(self.shake, 0.3)

    def boss_killed(self, b):
        p = self.p
        for i in range(12):
            self.delayed.append([i * 0.13, b.x + random.uniform(-b.r, b.r), b.y + random.uniform(0.3, b.h),
                                 b.z + random.uniform(-b.r, b.r), random.uniform(1.0, 1.8)])
        self.delayed.append([1.7, b.x, b.y + b.h * 0.5, b.z, 3.2])
        self.eb = []
        p.hp = min(p.max_hp, p.hp + p.max_hp * 0.3)
        self.pending_aug += 1
        self.score += int(500 * self.stage * self.d["mult"])
        self.banner = 3.0
        self.banner_text = T("보스 격파! 보너스 증강", "BOSS DESTROYED! BONUS AUGMENT")

    # ---------- 적 생성 ----------
    def pick_type(self):
        pool = [("scrap", 10), ("drone", 6), ("gunner", 4), ("kami", 3 if self.stage >= 2 else 1)]
        if self.stage >= 2:
            pool.append(("tank", min(6, 1 + self.stage)))
        total = sum(w for _, w in pool)
        r = random.uniform(0, total)
        for t, w in pool:
            r -= w
            if r <= 0:
                return t
        return "scrap"

    def spawn_interval(self):
        base = 1.8 * self.d["spawn"] / (1 + 0.1 * (self.stage - 1))
        return max(0.35, base * random.uniform(0.8, 1.2))

    def spawn_specific(self, t, x, z):
        x = clamp(x, -ARENA + 1, ARENA - 1)
        z = clamp(z, -ARENA + 1, ARENA - 1)
        self.enemies.append(Enemy(self, t, x, z))

    def spawn_enemy(self):
        nonboss = [e for e in self.enemies if not e.is_boss and not e.dead]
        if len(nonboss) >= min(26, 7 + 2 * self.stage):
            return
        p = self.p
        t = self.pick_type()
        for _ in range(8):
            a = random.uniform(0, math.tau)
            d = random.uniform(15, 22)
            x = clamp(p.x + math.sin(a) * d, -ARENA + 1.5, ARENA - 1.5)
            z = clamp(p.z + math.cos(a) * d, -ARENA + 1.5, ARENA - 1.5)
            if math.hypot(x - p.x, z - p.z) > 11:
                self.enemies.append(Enemy(self, t, x, z))
                return

    # ---------- 전투 ----------
    def damage_enemy(self, e, dmg, crit=False):
        if e.dead:
            return
        e.hp -= dmg
        e.flash = 0.08
        self.popup(e.x + random.uniform(-0.4, 0.4), e.y + e.h + 0.3, e.z, str(int(dmg)),
                   (255, 230, 90) if crit else (255, 255, 255), crit, 0.6)
        if e.hp <= 0:
            self.kill_enemy(e)

    def kill_enemy(self, e, credit=True):
        e.dead = True
        if e.is_boss:
            self.boss_killed(e)
        else:
            self.explode(e.x, e.y + e.h * 0.5, e.z, 0.8 + e.r * 0.8)
        if not credit:
            return
        p = self.p
        self.score += int(e.score * self.d["mult"] * (1 + 0.1 * (self.stage - 1)))
        p.xp += e.xp
        p.kills += 1
        if p.lifesteal > 0 and p.hp < p.max_hp:
            p.hp = min(p.max_hp, p.hp + p.lifesteal)
        while p.xp >= p.xp_need():
            p.xp -= p.xp_need()
            p.level += 1
            self.pending_aug += 1
            self.popup(p.x, p.y + 2.6, p.z, T("레벨 업!", "LEVEL UP!"), (255, 255, 120), True, 1.4)
        while p.repair < 5 and p.kills >= REPAIR_AT[p.repair]:
            idx = p.repair
            p.repair += 1
            p.max_hp += 10
            p.hp = min(p.max_hp, p.hp + p.max_hp * 0.35)
            p.dmg *= 1.08
            name = REPAIR_NAMES[idx][0] if KO else REPAIR_NAMES[idx][1]
            self.popup(p.x, p.y + 3.1, p.z, T("수리 완료: ", "REPAIRED: ") + name, (120, 255, 170), True, 2.0)
            self.rings.append(Ring(p.x, p.z, 0.4, 3.0, 0.6, (120, 255, 170), 3))
            if p.repair >= 5:
                self.banner = 3.5
                self.banner_text = T("세계 제일의 로봇 완성!", "THE WORLD'S BEST ROBOT!")

    def hurt_player(self, amount, sx, sz):
        p = self.p
        if p.inv > 0 or self.state != "play":
            return
        if p.shield_ready:
            p.shield_ready = False
            p.shield_cd = max(4.0, 13.0 - 2.5 * p.shield_lvl)
            p.inv = 0.6
            self.rings.append(Ring(p.x, p.z, 0.6, 2.2, 0.3, (120, 220, 255), 3))
            self.popup(p.x, p.y + 2.3, p.z, T("방어!", "BLOCK!"), (120, 220, 255))
            return
        p.hp -= amount
        p.inv = 0.9
        d = math.hypot(p.x - sx, p.z - sz) + 1e-6
        p.kx, p.kz = (p.x - sx) / d * 9.0, (p.z - sz) / d * 9.0
        p.vy = max(p.vy, 4.0)
        p.on_ground = False
        self.shake = max(self.shake, 0.18)
        self.popup(p.x, p.y + 2.4, p.z, "-" + str(int(amount)), (255, 90, 90), True, 0.8)
        for _ in range(8):
            self.sparks.append(Spark(p.x, p.y + 1.0, p.z, random.uniform(-4, 4), random.uniform(1, 5),
                                     random.uniform(-4, 4), 0.4, (255, 200, 80), 0.07))
        if p.hp <= 0:
            p.hp = 0
            self.state = "dying"      # 게임 종료: HP 0 → 쓰러짐
            self.death_t = 0.0
            self.eb = []
            self.explode(p.x, p.y + 1.0, p.z, 1.5, (255, 120, 60))

    # ---------- 업데이트 ----------
    def update(self, dt, keys):
        if self.state == "play":
            self.update_play(dt, keys)
        elif self.state == "dying":
            self.update_dying(dt)

    def update_play(self, dt, keys):
        p = self.p
        self.total_t += dt
        self.anim += dt
        self.stage_t += dt
        if self.stage_t >= STAGE_TIME:
            self.next_stage()

        self.update_player(dt, keys)

        self.spawn_t -= dt
        if self.spawn_t <= 0:
            self.spawn_enemy()
            self.spawn_t = self.spawn_interval()

        for e in self.enemies:
            if not e.dead:
                e.update(self, dt)
        # 적끼리 겹치지 않게 밀어내기
        n = len(self.enemies)
        for i in range(n):
            a = self.enemies[i]
            if a.is_boss or a.kind == "fly":
                continue
            for j in range(i + 1, n):
                b = self.enemies[j]
                if b.is_boss or b.kind == "fly":
                    continue
                dx, dz = b.x - a.x, b.z - a.z
                rr = a.r + b.r
                if abs(dx) < rr and abs(dz) < rr:
                    d = math.hypot(dx, dz)
                    if 1e-6 < d < rr:
                        push = (rr - d) * 0.5
                        a.x -= dx / d * push
                        a.z -= dz / d * push
                        b.x += dx / d * push
                        b.z += dz / d * push

        for b in self.pb + self.eb:
            b.update(self, dt)

        # 내 탄 → 적
        for b in self.pb:
            if b.dead:
                continue
            for e in self.enemies:
                if e.dead or id(e) in b.hit:
                    continue
                if (math.hypot(e.x - b.x, e.z - b.z) < e.r + b.r and
                        e.y - 0.15 <= b.y <= e.y + e.h + 0.15):
                    self.damage_enemy(e, b.dmg, b.crit)
                    b.hit.add(id(e))
                    if b.explosive:
                        self.aoe(b.x, b.y, b.z, 1.0 + 0.5 * b.explosive, b.dmg * 0.6, exclude=e)
                    if b.pierce > 0:
                        b.pierce -= 1
                    else:
                        b.dead = True
                        self.hit_spark(b.x, b.y, b.z, b.color)
                    break

        # 적 탄 → 플레이어
        for b in self.eb:
            if b.dead:
                continue
            if (math.hypot(p.x - b.x, p.z - b.z) < p.r * 0.9 + b.r and
                    p.y - 0.1 <= b.y <= p.y + p.h + 0.1):
                b.dead = True
                self.hurt_player(b.dmg, b.x, b.z)

        # 적과 접촉해도 HP 감소 (점프로 피할 수 있음)
        for e in self.enemies:
            if e.dead or e.grace > 0:
                continue
            if (math.hypot(e.x - p.x, e.z - p.z) < e.r + p.r * 0.85 and
                    p.y < e.y + e.h and p.y + p.h > e.y + 0.1):
                self.hurt_player(e.dmg, e.x, e.z)
                if e.t == "kami":
                    self.explode(e.x, e.y + 0.5, e.z, 1.2, (255, 90, 60))
                    e.dead = True

        # 회전 톱날
        if p.saw > 0:
            p.saw_angle += 3.6 * dt
            for i in range(p.saw):
                a = p.saw_angle + i * math.tau / p.saw
                sx, sz = p.x + math.cos(a) * 2.6, p.z + math.sin(a) * 2.6
                sy = p.y + 0.9
                for e in self.enemies:
                    if e.dead or e.saw_cd > 0 or e.grace > 0:
                        continue
                    if (math.hypot(e.x - sx, e.z - sz) < e.r + 0.6 and e.y - 0.3 < sy < e.y + e.h + 0.3):
                        e.saw_cd = 0.35
                        self.damage_enemy(e, p.dmg * 1.1, False)

        self.pb = [b for b in self.pb if not b.dead]
        self.eb = [b for b in self.eb if not b.dead]
        self.enemies = [e for e in self.enemies if not e.dead]
        self.update_fx(dt)

        if self.pending_aug > 0 and self.state == "play":
            self.open_augment()

    def update_player(self, dt, keys):
        p = self.p
        ix = (1 if (keys[pygame.K_d]) else 0) - (1 if (keys[pygame.K_a]) else 0)
        iz = (1 if (keys[pygame.K_w]) else 0) - (1 if (keys[pygame.K_s]) else 0)
        rot = (1 if (keys[pygame.K_e] or keys[pygame.K_RIGHT]) else 0) - \
              (1 if (keys[pygame.K_q] or keys[pygame.K_LEFT]) else 0)
        self.cam_yaw += rot * 2.0 * dt
        sy, cy = math.sin(self.cam_yaw), math.cos(self.cam_yaw)
        mx, mz = ix * cy + iz * sy, -ix * sy + iz * cy
        n = math.hypot(mx, mz)
        p.moving = n > 0
        if n > 0:
            mx, mz = mx / n, mz / n
        k = min(1.0, 14 * dt)
        p.vx += (mx * p.speed - p.vx) * k
        p.vz += (mz * p.speed - p.vz) * k
        p.x += (p.vx + p.kx) * dt
        p.z += (p.vz + p.kz) * dt
        p.kx *= max(0.0, 1 - 8 * dt)
        p.kz *= max(0.0, 1 - 8 * dt)
        p.x = clamp(p.x, -ARENA + p.r, ARENA - p.r)
        p.z = clamp(p.z, -ARENA + p.r, ARENA - p.r)
        p.x, p.z, _ = push_out(p.x, p.z, p.r, p.y)
        sup = support_height(p.x, p.z, p.r, p.y)
        p.vy -= GRAV * dt
        p.y += p.vy * dt
        if p.y <= sup and p.vy <= 0:
            p.y = sup
            p.vy = 0.0
            p.on_ground = True
            p.air_left = p.extra_jumps
        else:
            p.on_ground = False

        p.inv = max(0.0, p.inv - dt)
        p.fire_cd -= dt
        p.muzzle = max(0.0, p.muzzle - dt)
        if p.regen > 0 and p.hp < p.max_hp:
            p.hp = min(p.max_hp, p.hp + p.regen * dt)
        if p.shield_lvl > 0 and not p.shield_ready:
            p.shield_cd -= dt
            if p.shield_cd <= 0:
                p.shield_ready = True
                self.popup(p.x, p.y + 2.3, p.z, T("실드 충전", "SHIELD READY"), (120, 220, 255))

        # 자동 조준 + 자동 발사
        cx, cy2, cz = p.x, p.y + 1.1, p.z
        target = self.nearest_enemy(cx, cy2, cz, 32)
        want = None
        if target:
            want = math.atan2(target.x - p.x, target.z - p.z)
        elif n > 0:
            want = math.atan2(mx, mz)
        if want is not None:
            p.yaw = turn_toward(p.yaw, want, 14 * dt)
        if target and p.fire_cd <= 0:
            p.fire_cd = p.fire_delay
            p.muzzle = 0.08
            gx = p.x + math.sin(p.yaw) * 0.9 + math.cos(p.yaw) * 0.39
            gz = p.z + math.cos(p.yaw) * 0.9 - math.sin(p.yaw) * 0.39
            gy = p.y + 1.1
            tx, ty, tz = target.x - gx, target.y + target.h * 0.55 - gy, target.z - gz
            dl = math.sqrt(tx * tx + ty * ty + tz * tz) + 1e-6
            tx, ty, tz = tx / dl, ty / dl, tz / dl
            nb = p.bullets
            for i in range(nb):
                o = (i - (nb - 1) / 2) * 0.12
                co, so = math.cos(o), math.sin(o)
                dx, dz = tx * co + tz * so, -tx * so + tz * co
                crit = random.random() < p.crit
                self.pb.append(Bullet(gx, gy, gz, dx * 26, ty * 26, dz * 26,
                                      p.dmg * (2.0 if crit else 1.0), True, 0.15,
                                      (255, 230, 90) if crit else (120, 230, 255),
                                      pierce=p.pierce, explosive=p.explosive, crit=crit, life=1.4))

        # 유도 미사일
        if p.missile > 0:
            p.missile_cd -= dt
            if p.missile_cd <= 0:
                tg = self.nearest_enemy(p.x, p.y + 1, p.z, 999)
                if tg:
                    p.missile_cd = max(0.8, 2.8 - 0.4 * p.missile)
                    a = random.uniform(0, math.tau)
                    self.pb.append(Bullet(p.x, p.y + 2.0, p.z, math.cos(a) * 3, 9, math.sin(a) * 3,
                                          p.dmg * 1.8 + 10, True, 0.2, (255, 140, 80),
                                          explosive=1, homing=True, life=3.5))

    def do_jump(self):
        p = self.p
        if self.state != "play":
            return
        if p.on_ground:
            p.vy = JUMP_V
            p.on_ground = False
        elif p.air_left > 0:
            p.air_left -= 1
            p.vy = JUMP_V * 0.95
            self.rings.append(Ring(p.x, p.z, 0.2, 1.3, 0.25, (200, 220, 255), 2))

    def update_fx(self, dt):
        for s in self.sparks:
            s.update(dt)
        for r in self.rings:
            r.update(dt)
        for f in self.flashes:
            f.update(dt)
        for tx in self.texts:
            tx.update(dt)
        self.sparks = [s for s in self.sparks if s.life > 0]
        self.rings = [r for r in self.rings if r.life > 0]
        self.flashes = [f for f in self.flashes if f.life > 0]
        self.texts = [t for t in self.texts if t.life > 0]
        for d in self.delayed:
            d[0] -= dt
            if d[0] <= 0:
                self.explode(d[1], d[2], d[3], d[4], (255, 150, 60))
        self.delayed = [d for d in self.delayed if d[0] > 0]
        self.shake = max(0.0, self.shake - dt)
        self.banner = max(0.0, self.banner - dt)
        p = self.p
        if p.repair < 5 and self.state == "play":
            if random.random() < (0.04 + (5 - p.repair) * 0.02) * dt * 60:
                self.sparks.append(Spark(p.x + random.uniform(-0.3, 0.3), p.y + random.uniform(0.5, 1.7),
                                         p.z + random.uniform(-0.3, 0.3), random.uniform(-1, 1), random.uniform(1, 3),
                                         random.uniform(-1, 1), 0.35, (255, 220, 80), 0.05, 8.0))

    def update_dying(self, dt):
        self.anim += dt
        self.death_t += dt
        self.death_fx -= dt
        if self.death_fx <= 0 and self.death_t < 1.8:
            self.death_fx = 0.15
            p = self.p
            self.explode(p.x + random.uniform(-0.5, 0.5), p.y + random.uniform(0.2, 1.6),
                         p.z + random.uniform(-0.5, 0.5), 0.7, (255, 140, 60))
        self.update_fx(dt)
        if self.death_t >= 2.2:
            self.state = "over"

    # ---------- 증강 ----------
    def open_augment(self):
        p = self.p
        cand = [a for a in AUGS if p.aug.get(a["key"], 0) < a["max"] and a["key"] != "heal"]
        random.shuffle(cand)
        self.choices = cand[:3]
        if len(self.choices) < 3:
            self.choices += [a for a in AUGS if a["key"] == "heal"]
        self.state = "augment"

    def pick_augment(self, i):
        if self.state != "augment" or i < 0 or i >= len(self.choices):
            return
        a = self.choices[i]
        a["fn"](self.p)
        self.p.aug[a["key"]] = self.p.aug.get(a["key"], 0) + 1
        self.popup(self.p.x, self.p.y + 2.5, self.p.z, aug_name(a), a["color"], True, 1.4)
        self.pending_aug -= 1
        if self.pending_aug > 0:
            self.open_augment()
        else:
            self.state = "play"

    # ---------- 그리기 ----------
    def draw_world(self, surf):
        t = self.anim
        p = self.p
        v = VIEW
        v.dist = 12.0
        sh = self.shake
        ox = random.uniform(-sh, sh) * 0.6 if sh > 0 else 0.0
        oy = random.uniform(-sh, sh) * 0.6 if sh > 0 else 0.0
        v.set_camera(p.x + ox, p.y * 0.5 + 1.4 + oy, p.z, self.cam_yaw)
        surf.blit(SKY, (0, 0))
        v.draw_floor(surf)
        draw_scene(v)

        # 적
        for e in self.enemies:
            v.add_shadow(e.x, e.z, e.r * 1.15 / (1 + e.y * 0.25))
            if e.grace > 0 and not e.is_boss:
                v.add_ring(e.x, e.z, 0.9 + 0.25 * math.sin(t * 12), (120, 200, 255), 2)
                if int(t * 18) % 2 == 0:
                    continue
            if e.is_boss and e.grace > 0:
                v.add_ring(e.x, e.z, e.r + 1.0 + 0.4 * math.sin(t * 12), (255, 120, 120), 3)
            draw_parts(v, e, e.parts(t))
        # 플레이어
        if self.state in ("dying", "over"):
            draw_player(v, p, t, self.death_t)
        elif not (p.inv > 0 and int(t * 20) % 2 == 0):
            draw_player(v, p, t)
        # 총알 / 톱날 / 이펙트
        for b in self.pb:
            b.draw(v)
        for b in self.eb:
            b.draw(v)
        if p.saw > 0 and self.state not in ("dying", "over"):
            for i in range(p.saw):
                a = p.saw_angle + i * math.tau / p.saw
                sx, sz = p.x + math.cos(a) * 2.6, p.z + math.sin(a) * 2.6
                v.add_box(sx, p.y + 0.9, sz, 0.45, 0.06, 0.45, a * 5, (214, 216, 228))
                v.add_box(sx, p.y + 0.9, sz, 0.45, 0.06, 0.45, a * 5 + 0.78, (170, 172, 188))
                v.add_box(sx, p.y + 0.95, sz, 0.12, 0.1, 0.12, a * 5, (60, 62, 76))
        for r in self.rings:
            r.draw(v)
        for s in self.sparks:
            s.draw(v)
        for f in self.flashes:
            f.draw(v)
        v.flush(surf)

        # 적 체력바 / 떠오르는 글자
        for e in self.enemies:
            if e.is_boss or e.hp >= e.max_hp or e.grace > 0:
                continue
            q = v.proj(e.x, e.y + e.h + 0.35, e.z)
            if q:
                w = 34
                pygame.draw.rect(surf, (40, 0, 0), (int(q[0] - w / 2), int(q[1]), w, 4))
                pygame.draw.rect(surf, (230, 60, 50), (int(q[0] - w / 2), int(q[1]), int(w * max(0, e.hp) / e.max_hp), 4))
        for tx in self.texts:
            q = v.proj(tx.x, tx.y, tx.z)
            if q:
                draw_text(surf, tx.text, F_M if tx.big else F_S, tx.color, (int(q[0]), int(q[1])), "center")
        self.draw_hud(surf)

    def draw_radar(self, surf):
        rc = (WORLD_W - 62, WORLD_H - 62)
        R = 50
        pygame.draw.circle(surf, (14, 18, 26), rc, R)
        pygame.draw.circle(surf, (80, 100, 130), rc, R, 2)
        pygame.draw.line(surf, (40, 50, 66), (rc[0] - R, rc[1]), (rc[0] + R, rc[1]), 1)
        pygame.draw.line(surf, (40, 50, 66), (rc[0], rc[1] - R), (rc[0], rc[1] + R), 1)
        p = self.p
        sy, cy = math.sin(self.cam_yaw), math.cos(self.cam_yaw)
        for e in self.enemies:
            dx, dz = e.x - p.x, e.z - p.z
            rx = dx * cy - dz * sy
            fz = dx * sy + dz * cy
            px, py = rc[0] + rx / 26.0 * R, rc[1] - fz / 26.0 * R
            if math.hypot(px - rc[0], py - rc[1]) > R - 3:
                a = math.atan2(py - rc[1], px - rc[0])
                px, py = rc[0] + math.cos(a) * (R - 3), rc[1] + math.sin(a) * (R - 3)
            pygame.draw.circle(surf, (255, 90, 60) if e.is_boss else (255, 200, 90), (int(px), int(py)), 5 if e.is_boss else 3)
        pygame.draw.polygon(surf, (120, 255, 200), [(rc[0], rc[1] - 6), (rc[0] - 4, rc[1] + 4), (rc[0] + 4, rc[1] + 4)])

    def draw_hud(self, surf):
        p = self.p
        pygame.draw.rect(surf, (20, 20, 25), (10, 8, 244, 22), border_radius=4)
        k = clamp(p.hp / p.max_hp, 0, 1)
        pygame.draw.rect(surf, lerpc((230, 60, 60), (90, 230, 120), k), (12, 10, int(240 * k), 18), border_radius=3)
        draw_text(surf, "HP %d / %d" % (math.ceil(p.hp), int(p.max_hp)), F_S, (255, 255, 255), (132, 19), "center")
        pygame.draw.rect(surf, (20, 20, 25), (10, 34, 244, 12), border_radius=3)
        pygame.draw.rect(surf, (110, 160, 255), (12, 36, int(240 * clamp(p.xp / p.xp_need(), 0, 1)), 8), border_radius=2)
        draw_text(surf, "LV %d" % p.level, F_S, (200, 220, 255), (262, 34))
        draw_text(surf, T("수리 ", "REPAIR ") + "%d/5" % p.repair, F_S, (170, 255, 200), (12, 52))
        for i in range(5):
            ok = p.repair > i
            rc = pygame.Rect(92 + i * 18, 52, 14, 14)
            pygame.draw.rect(surf, (90, 230, 140) if ok else (70, 70, 80), rc, border_radius=2)
            if not ok:
                pygame.draw.line(surf, (200, 70, 70), rc.topleft, rc.bottomright, 2)
                pygame.draw.line(surf, (200, 70, 70), rc.topright, rc.bottomleft, 2)

        boss = next((e for e in self.enemies if e.is_boss and not e.dead), None)
        if boss:
            bw, bx = 330, 300
            pygame.draw.rect(surf, (20, 10, 14), (bx - 2, 10, bw + 4, 18), border_radius=4)
            pygame.draw.rect(surf, (230, 50, 70) if not boss.enraged else (255, 130, 40),
                             (bx, 12, int(bw * clamp(boss.hp / boss.max_hp, 0, 1)), 14), border_radius=3)
            draw_text(surf, boss.name, F_S, (255, 255, 255), (bx + bw // 2, 19), "center")

        remain = max(0, STAGE_TIME - self.stage_t)
        draw_text(surf, "STAGE %d" % self.stage, F_L, (255, 230, 150), (WORLD_W - 12, 6), "topright")
        draw_text(surf, T("다음 보스 ", "NEXT BOSS ") + "%02d:%02d" % (int(remain) // 60, int(remain) % 60),
                  F_S, (255, 160, 140), (WORLD_W - 12, 44), "topright")
        draw_text(surf, T("점수 ", "SCORE ") + "%d" % self.score, F_M, (255, 255, 255), (WORLD_W - 12, 62), "topright")
        draw_text(surf, T("처치 ", "KILLS ") + "%d" % p.kills, F_S, (200, 200, 210), (WORLD_W - 12, 86), "topright")
        self.draw_radar(surf)

        # 보유 증강 아이콘
        x, y = 10, WORLD_H - 40
        got = [a for a in AUGS if p.aug.get(a["key"], 0) > 0]
        for a in got:
            n = p.aug[a["key"]]
            pygame.draw.rect(surf, (20, 22, 30), (x - 2, y - 2, 34, 34), border_radius=6)
            pygame.draw.rect(surf, a["color"], (x - 2, y - 2, 34, 34), 2, border_radius=6)
            surf.blit(make_icon(a["key"], a["color"], 28), (x + 1, y + 1))
            if n > 1:
                draw_text(surf, "x%d" % n, F_S, (255, 255, 255), (x + 31, y + 31), "bottomright")
            x += 40
            if x > 520:
                x = 10
                y -= 40
        if not got:
            draw_text(surf, T("레벨 업 / 보스 처치로 증강을 얻으세요", "Level up or defeat bosses to gain augments"),
                      F_S, (190, 190, 200), (10, WORLD_H - 26))

        if self.banner > 0 and (int(self.banner * 6) % 2 == 0 or self.banner < 1):
            draw_text(surf, self.banner_text, F_L, (255, 90, 90), (WORLD_W // 2, 130), "center")

    def draw_overlay(self, surf):
        cxw = PANEL_W + WORLD_W // 2
        if self.state == "augment":
            veil = pygame.Surface((WORLD_W, WORLD_H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 170))
            surf.blit(veil, (PANEL_W, 0))
            draw_text(surf, T("증강을 선택하세요  (1 / 2 / 3)", "Choose an augment  (1 / 2 / 3)"),
                      F_L, (255, 240, 150), (cxw, 90), "center")
            self.card_rects = []
            mx, my = pygame.mouse.get_pos()
            cw, ch, gap = 240, 270, 20
            total = len(self.choices) * cw + (len(self.choices) - 1) * gap
            x0 = cxw - total // 2
            for i, a in enumerate(self.choices):
                rc = pygame.Rect(x0 + i * (cw + gap), 140, cw, ch)
                self.card_rects.append(rc)
                hov = rc.collidepoint(mx, my)
                pygame.draw.rect(surf, (40, 44, 58) if not hov else (62, 68, 90), rc, border_radius=10)
                pygame.draw.rect(surf, a["color"], rc, 3, border_radius=10)
                pygame.draw.circle(surf, lerpc((20, 22, 30), a["color"], 0.25), (rc.centerx, rc.y + 70), 48)
                pygame.draw.circle(surf, a["color"], (rc.centerx, rc.y + 70), 48, 2)
                surf.blit(make_icon(a["key"], a["color"], 64), (rc.centerx - 32, rc.y + 38))
                draw_text(surf, str(i + 1), F_M, a["color"], (rc.x + 12, rc.y + 8))
                draw_text(surf, aug_name(a), F_M, (255, 255, 255), (rc.centerx, rc.y + 140), "center")
                draw_text(surf, aug_desc(a), F_S, (210, 210, 220), (rc.centerx, rc.y + 178), "center")
                n = self.p.aug.get(a["key"], 0)
                if a["max"] < 99:
                    draw_text(surf, "Lv %d / %d" % (n, a["max"]), F_S, (150, 150, 165), (rc.centerx, rc.y + 232), "center")
        elif self.state == "paused":
            veil = pygame.Surface((WORLD_W, WORLD_H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 150))
            surf.blit(veil, (PANEL_W, 0))
            draw_text(surf, T("일시정지", "PAUSED"), F_XL, (255, 255, 255), (cxw, 220), "center")
            draw_text(surf, T("P / ESC : 계속     M : 메뉴로", "P / ESC : Resume     M : Menu"),
                      F_M, (210, 210, 220), (cxw, 290), "center")
        elif self.state == "over":
            veil = pygame.Surface((WORLD_W, WORLD_H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 185))
            surf.blit(veil, (PANEL_W, 0))
            draw_text(surf, T("시스템 정지", "SYSTEM DOWN"), F_XL, (255, 80, 80), (cxw, 110), "center")
            lines = [
                (T("점수 ", "Score ") + str(int(self.score)), (255, 255, 255)),
                (T("도달 스테이지 ", "Stage reached ") + str(self.stage), (255, 230, 150)),
                (T("처치한 적 ", "Enemies destroyed ") + str(self.p.kills), (200, 200, 210)),
                (T("수리된 부위 ", "Parts repaired ") + "%d/5" % self.p.repair, (170, 255, 200)),
                (T("난이도 ", "Difficulty ") + dname(self.d), self.d["color"]),
            ]
            for i, (txt, col) in enumerate(lines):
                draw_text(surf, txt, F_M, col, (cxw, 185 + i * 34), "center")
            if self.rank:
                draw_text(surf, T("리더보드 %d위!" % self.rank, "Leaderboard rank #%d!" % self.rank),
                          F_M, (255, 220, 90), (cxw, 365), "center")
            draw_text(surf, T("R : 다시 도전     M : 메뉴", "R : Retry     M : Menu"),
                      F_M, (210, 210, 220), (cxw, 430), "center")


# ------------------------------------------------------------
# 왼쪽 리더보드 패널
# ------------------------------------------------------------
def draw_panel(surf, records, game=None):
    pygame.draw.rect(surf, (18, 20, 28), (0, 0, PANEL_W, WIN_H))
    pygame.draw.line(surf, (70, 75, 95), (PANEL_W - 1, 0), (PANEL_W - 1, WIN_H), 2)
    draw_text(surf, T("리더보드", "LEADERBOARD"), F_M, (255, 220, 120), (PANEL_W // 2, 22), "center")
    draw_text(surf, T("최고 기록 TOP 8", "BEST RECORDS TOP 8"), F_S, (140, 145, 165), (PANEL_W // 2, 44), "center")
    y = 66
    for i in range(8):
        if i < len(records):
            r = records[i]
            d = diff_by_key(r.get("diff", "veteran"))
            col = (255, 215, 90) if i == 0 else (225, 225, 235)
            draw_text(surf, "%d." % (i + 1), F_S, col, (10, y))
            draw_text(surf, "%d" % r["score"], F_M, col, (36, y - 3))
            draw_text(surf, "S%d  %s" % (r.get("stage", 1), dshort(d)), F_S, d["color"], (36, y + 17))
        else:
            draw_text(surf, "%d.  -" % (i + 1), F_S, (80, 82, 95), (10, y + 4))
        y += 42
    if game is not None:
        rank = 1 + sum(1 for r in records if r["score"] > game.score)
        pygame.draw.rect(surf, (36, 40, 56), (6, y + 2, PANEL_W - 14, 50), border_radius=6)
        draw_text(surf, T("현재 기록", "NOW"), F_S, (140, 200, 255), (14, y + 6))
        draw_text(surf, "%d" % game.score, F_M, (255, 255, 255), (14, y + 24))
        draw_text(surf, "#%d" % rank, F_M, (255, 220, 90), (PANEL_W - 14, y + 24), "topright")


# ------------------------------------------------------------
# 메뉴 (3D 로봇이 돌면서 수리 단계가 바뀌는 장면)
# ------------------------------------------------------------
class _Dummy:
    pass


def draw_menu_scene(world, t):
    p = Player(DIFFS[1])
    p.repair = int(t / 1.4) % 6
    p.on_ground = True
    p.moving = False
    p.yaw = 0.4
    v = VIEW
    v.dist = 7.5
    yaw = t * 0.45
    rx, rz = math.cos(yaw), -math.sin(yaw)
    v.set_camera(2.6 * rx, 1.2, 2.6 * rz, yaw)
    world.blit(SKY, (0, 0))
    v.draw_floor(world)
    draw_scene(v)
    draw_player(v, p, t)
    for k in range(5):
        a = t * 0.8 + k * 1.3
        v.add_dot(math.cos(a) * 3 + 0.2, 1 + 0.6 * math.sin(a * 1.7), math.sin(a) * 3, 0.05, (255, 220, 90))
    v.flush(world)
    v.dist = 12.0
    return p.repair


def draw_menu(surf, world, sel, records, t):
    rep = draw_menu_scene(world, t)
    surf.blit(world, (PANEL_W, 0))
    veil = pygame.Surface((WORLD_W, WORLD_H), pygame.SRCALPHA)
    veil.fill((0, 0, 0, 70))
    surf.blit(veil, (PANEL_W, 0))
    cx = PANEL_W + WORLD_W // 2
    draw_text(surf, T("폐허의 도시 : 리빌드 3D", "RUINED CITY : REBUILD 3D"), F_XL, (255, 210, 120), (cx, 52), "center")
    draw_text(surf, T("망가진 로봇이 적을 쓰러뜨리며 수리되어 세계 제일의 로봇이 된다!",
                      "A broken robot repairs itself with every kill and becomes the world's best!"),
              F_S, (230, 230, 240), (cx, 92), "center")
    draw_text(surf, T("수리 %d / 5" % rep, "REPAIR %d / 5" % rep), F_M, (170, 255, 200), (PANEL_W + 215, 460), "center")
    best = {}
    for r in records:
        best[r.get("diff")] = max(best.get(r.get("diff"), 0), r["score"])
    x0 = PANEL_W + 470
    draw_text(surf, T("난이도 선택  (↑ ↓ / 1~4 · Enter)", "Select difficulty  (UP/DOWN · Enter)"),
              F_M, (255, 255, 255), (x0 + 200, 140), "center")
    for i, d in enumerate(DIFFS):
        y = 170 + i * 62
        rc = pygame.Rect(x0, y, 400, 54)
        on = i == sel
        pygame.draw.rect(surf, (46, 50, 66) if on else (26, 28, 38), rc, border_radius=8)
        pygame.draw.rect(surf, d["color"] if on else (70, 72, 88), rc, 3 if on else 1, border_radius=8)
        draw_text(surf, ("> " if on else "") + dname(d), F_M, d["color"], (rc.x + 14, rc.y + 6))
        info = T("적 체력 x%.2g · 적 공격 x%.2g · 점수 x%.2g", "Enemy HP x%.2g · Dmg x%.2g · Score x%.2g") % (d["hp"], d["dmg"], d["mult"])
        draw_text(surf, info, F_S, (190, 190, 205), (rc.x + 14, rc.y + 32))
        draw_text(surf, T("최고 ", "BEST ") + str(best.get(d["key"], 0)), F_S, (255, 220, 120), (rc.right - 12, rc.y + 8), "topright")
    draw_text(surf, T("WASD 이동 · Space 점프 · Q/E 카메라 회전 · 사격은 자동 조준/발사 · P 일시정지",
                      "WASD move · Space jump · Q/E rotate camera · Auto-aim & fire · P pause"),
              F_S, (225, 225, 235), (cx, 490), "center")
    draw_text(surf, T("2분마다 보스 출현 · 스테이지 상승 · 레벨 업마다 증강 선택 · 끝없는 무한 모드",
                      "Boss every 2 min · Stage up · Augment each level-up · Endless mode"),
              F_S, (255, 170, 150), (cx, 512), "center")


# ------------------------------------------------------------
# 메인 루프
# ------------------------------------------------------------
def main():
    records = load_records()
    mode = "menu"
    sel = 1
    game = None
    world = pygame.Surface((WORLD_W, WORLD_H))
    menu_t = 0.0

    def leave_game():
        if game and not game.saved and game.score > 0:
            add_record(records, game)

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                leave_game()
                pygame.quit()
                sys.exit()

            if mode == "menu":
                if ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_UP, pygame.K_w):
                        sel = (sel - 1) % len(DIFFS)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        sel = (sel + 1) % len(DIFFS)
                    elif pygame.K_1 <= ev.key <= pygame.K_4:
                        sel = ev.key - pygame.K_1
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        game = Game(sel)
                        mode = "game"
                continue

            if ev.type == pygame.KEYDOWN:
                if game.state == "play":
                    if ev.key in (pygame.K_SPACE, pygame.K_UP):
                        game.do_jump()
                    elif ev.key in (pygame.K_p, pygame.K_ESCAPE):
                        game.state = "paused"
                elif game.state == "paused":
                    if ev.key in (pygame.K_p, pygame.K_ESCAPE):
                        game.state = "play"
                    elif ev.key == pygame.K_m:
                        leave_game()
                        mode = "menu"
                elif game.state == "augment":
                    if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        game.pick_augment(ev.key - pygame.K_1)
                elif game.state == "over":
                    if ev.key == pygame.K_r:
                        game = Game(game.di)
                    elif ev.key in (pygame.K_m, pygame.K_RETURN):
                        mode = "menu"
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if game.state == "augment":
                    for i, rc in enumerate(game.card_rects):
                        if rc.collidepoint(ev.pos):
                            game.pick_augment(i)
                            break

        if mode == "menu":
            menu_t += dt
            screen.fill((0, 0, 0))
            draw_panel(screen, records)
            draw_menu(screen, world, sel, records, menu_t)
            pygame.display.flip()
            continue

        keys = pygame.key.get_pressed()
        game.update(dt, keys)
        if game.state == "over" and not game.saved:
            game.rank = add_record(records, game)

        game.draw_world(world)
        screen.fill((0, 0, 0))
        screen.blit(world, (PANEL_W, 0))
        draw_panel(screen, records, game)
        game.draw_overlay(screen)
        pygame.display.flip()


if __name__ == "__main__":
    main()
