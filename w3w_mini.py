"""
Mini-what3words: anh xa 1 o vuong 5x5m -> 3 tu, cho pham vi mot thanh pho.

Cach hoat dong (tom tat):
  toa do (lat, lon)
      -> chi so o luoi (row, col)          [chia luoi 5m]
      -> cell_id = row * num_cols + col     [so nguyen duy nhat]
      -> cell_id xao tron bang LCG chu ky day du (bijection)
      -> tach so da xao thanh 3 chi so co so W
      -> tra tu dien -> 3 tu

Chieu nguoc lai (3 tu -> toa do) lam nguoc lai tung buoc, dung nghich
dao modular cua LCG.
"""

import math
from math import gcd


# ---------------------------------------------------------------------------
# 1) CAU HINH VUNG BAN DO VA LUOI
# ---------------------------------------------------------------------------

class GridConfig:
    def __init__(self, lat_min, lon_min, lat_max, lon_max, cell_size_m=5.0):
        self.lat_min = lat_min
        self.lon_min = lon_min
        self.lat_max = lat_max
        self.lon_max = lon_max
        self.cell_size = cell_size_m

        # Xap xi phang (equirectangular) - du chinh xac cho pham vi ~vai chuc km.
        # 1 do vi do ~ 111_320 m. 1 do kinh do phu thuoc vi do (co lai gan cuc).
        self.lat0 = (lat_min + lat_max) / 2.0
        self.m_per_deg_lat = 111_320.0
        self.m_per_deg_lon = 111_320.0 * math.cos(math.radians(self.lat0))

        width_m = (lon_max - lon_min) * self.m_per_deg_lon
        height_m = (lat_max - lat_min) * self.m_per_deg_lat

        self.num_cols = max(1, math.ceil(width_m / cell_size_m))
        self.num_rows = max(1, math.ceil(height_m / cell_size_m))
        self.num_cells = self.num_cols * self.num_rows

    def latlon_to_cell(self, lat, lon):
        x_m = (lon - self.lon_min) * self.m_per_deg_lon
        y_m = (lat - self.lat_min) * self.m_per_deg_lat
        col = int(x_m // self.cell_size)
        row = int(y_m // self.cell_size)
        col = min(max(col, 0), self.num_cols - 1)
        row = min(max(row, 0), self.num_rows - 1)
        return row, col

    def cell_to_latlon_center(self, row, col):
        x_m = (col + 0.5) * self.cell_size
        y_m = (row + 0.5) * self.cell_size
        lon = self.lon_min + x_m / self.m_per_deg_lon
        lat = self.lat_min + y_m / self.m_per_deg_lat
        return lat, lon

    def cell_bounds(self, row, col):
        """Tra ve 4 goc cua 1 o: (lat_sw, lon_sw, lat_ne, lon_ne)."""
        x0_m = col * self.cell_size
        y0_m = row * self.cell_size
        x1_m = (col + 1) * self.cell_size
        y1_m = (row + 1) * self.cell_size
        lon_sw = self.lon_min + x0_m / self.m_per_deg_lon
        lat_sw = self.lat_min + y0_m / self.m_per_deg_lat
        lon_ne = self.lon_min + x1_m / self.m_per_deg_lon
        lat_ne = self.lat_min + y1_m / self.m_per_deg_lat
        return lat_sw, lon_sw, lat_ne, lon_ne

    def cell_to_id(self, row, col):
        return row * self.num_cols + col

    def id_to_cell(self, cell_id):
        row = cell_id // self.num_cols
        col = cell_id % self.num_cols
        return row, col


# ---------------------------------------------------------------------------
# 2) HOAN VI TOAN ANH (LCG chu ky day du) - "xao tron" cell_id
# ---------------------------------------------------------------------------
#
# Dinh ly Hull-Dobell: LCG  y = (a*x + c) mod M  co chu ky day du (di qua
# TAT CA gia tri 0..M-1 dung 1 lan) khi va chi khi:
#   1) gcd(c, M) = 1
#   2) (a - 1) chia het cho moi thua so nguyen to cua M
#   3) (a - 1) chia het cho 4 neu M chia het cho 4
#
# => Day la mot BIJECTION tren [0, M), khong phai ma hoa an toan, chi la
#    mot cach "xao tron trong deu" de 2 o gan nhau khong ra tu gan nhau.

def mod_inverse(a, m):
    """Nghich dao modular cua a theo modulo m (m khong nhat thiet la so nguyen to)."""
    g, x, _ = _extended_gcd(a, m)
    if g != 1:
        raise ValueError("Khong ton tai nghich dao modular")
    return x % m


def _extended_gcd(a, b):
    if a == 0:
        return b, 0, 1
    g, x1, y1 = _extended_gcd(b % a, a)
    x = y1 - (b // a) * x1
    y = x1
    return g, x, y


class Shuffler:
    """Bijection tren [0, M). M nen la luy thua cua 2 de de chon a,c hop le."""

    def __init__(self, M, a=None, c=None):
        self.M = M
        if a is None:
            # a-1 phai chia het cho tat ca thua so nguyen to cua M va cho 4 (neu M%4==0)
            # Voi M = 2^k, chi can (a-1) chia het cho 4 (k>=2) => chon a = 5 (mod 8) bat ky co dinh
            a = 2_654_435_769 % M
            if a % 4 != 1:
                a = (a - (a % 4) + 1) % M
        if c is None:
            c = 40_503_47 % M
            if gcd(c, M) != 1:
                c |= 1  # dam bao c le -> gcd(c, 2^k)=1
        self.a = a
        self.c = c
        self.a_inv = mod_inverse(a, M)

    def forward(self, x):
        return (self.a * x + self.c) % self.M

    def inverse(self, y):
        return (self.a_inv * (y - self.c)) % self.M


# ---------------------------------------------------------------------------
# 3) TU DIEN VA TACH/GHEP 3 TU
# ---------------------------------------------------------------------------

def load_word_list_from_file(path):
    """Doc danh sach tu tu file text (moi dong 1 tu, dong bat dau bang '#' la comment).
    Tu dong loai bo dong trong va tu trung lap (giu thu tu xuat hien dau tien)."""
    words = []
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if not w or w.startswith("#"):
                continue
            if "." in w:
                raise ValueError(f"Tu '{w}' chua dau '.' - khong hop le (dau cham dung de phan cach dia chi)")
            if w not in seen:
                seen.add(w)
                words.append(w)
    return words


def generate_word_list(n):
    """Sinh n 'tu' de doc (khong can file tu dien ngoai) bang to hop am tiet.
    Trong san pham that, ban se thay bang mot danh sach ~2500-8000 tu that."""
    consonants = list("bcdfghjklmnpqrstvwxyz")
    vowels = list("aeiou")
    words = []
    seen = set()
    i = 0
    while len(words) < n:
        # tao am tiet CVC hoac CVCVC dua tren chi so i de deterministic
        c1 = consonants[i % len(consonants)]
        v1 = vowels[(i // len(consonants)) % len(vowels)]
        c2 = consonants[(i // (len(consonants) * len(vowels))) % len(consonants)]
        v2 = vowels[(i // (len(consonants) * len(vowels) * len(consonants))) % len(vowels)]
        c3 = consonants[(i // (len(consonants) * len(vowels) * len(consonants) * len(vowels))) % len(consonants)]
        w = f"{c1}{v1}{c2}{v2}{c3}"
        i += 1
        if w not in seen:
            seen.add(w)
            words.append(w)
    return words


class WordMapper:
    def __init__(self, word_list):
        self.words = word_list
        self.W = len(word_list)
        self.index_of = {w: i for i, w in enumerate(word_list)}
        self.M = self.W ** 3  # tong so to hop 3-tu
        self.shuffler = Shuffler(self.M)

    def cellid_to_words(self, cell_id):
        if not (0 <= cell_id < self.M):
            raise ValueError("cell_id vuot qua khong gian tu (tang W hoac giam vung ban do)")
        y = self.shuffler.forward(cell_id)
        i1 = y // (self.W * self.W)
        i2 = (y // self.W) % self.W
        i3 = y % self.W
        return self.words[i1], self.words[i2], self.words[i3]

    def words_to_cellid(self, w1, w2, w3):
        i1 = self.index_of[w1]
        i2 = self.index_of[w2]
        i3 = self.index_of[w3]
        y = i1 * self.W * self.W + i2 * self.W + i3
        cell_id = self.shuffler.inverse(y)
        return cell_id


# ---------------------------------------------------------------------------
# 4) API CHINH: toa do <-> 3 tu
# ---------------------------------------------------------------------------

class MiniW3W:
    def __init__(self, lat_min, lon_min, lat_max, lon_max, cell_size_m=5.0,
                 dict_size=4096, word_list=None):
        self.grid = GridConfig(lat_min, lon_min, lat_max, lon_max, cell_size_m)
        needed = self.grid.num_cells

        if word_list is not None:
            self.words = word_list
        else:
            self.words = generate_word_list(dict_size)

        assert len(self.words) ** 3 >= needed, (
            f"Tu dien co {len(self.words)} tu (W^3={len(self.words)**3:,}) qua nho so voi "
            f"{needed:,} o can bieu dien. Hay them tu vao tu dien hoac giam vung ban do."
        )
        self.mapper = WordMapper(self.words)

    def to_words(self, lat, lon):
        row, col = self.grid.latlon_to_cell(lat, lon)
        cell_id = self.grid.cell_to_id(row, col)
        return self.mapper.cellid_to_words(cell_id)

    def to_latlon(self, w1, w2, w3):
        cell_id = self.mapper.words_to_cellid(w1, w2, w3)
        # Khong gian tu (M = W^3) luon LON HON so o thuc te tren ban do (num_cells),
        # vi can du "cho trong" de LCG hoat dong dung va de mo rong vung sau nay.
        # => Khong phai to hop 3 tu nao cung ung voi 1 o thuc: neu cell_id roi ra
        # ngoai [0, num_cells) thi day la dia chi khong ton tai tren ban do nay.
        if not (0 <= cell_id < self.grid.num_cells):
            raise ValueError(
                f"Dia chi '{w1}.{w2}.{w3}' khong tuong ung voi vi tri nao "
                f"tren ban do nay (co the la 3 tu dung nhung khong tao thanh dia chi hop le)"
            )
        row, col = self.grid.id_to_cell(cell_id)
        return self.grid.cell_to_latlon_center(row, col)


# ---------------------------------------------------------------------------
# 5) DEMO / TEST
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    word_file = os.path.join(os.path.dirname(__file__), "vietnamese_words.txt")
    if os.path.exists(word_file):
        vi_words = load_word_list_from_file(word_file)
        print(f"Da nap {len(vi_words)} tu tieng Viet tu {word_file}")
    else:
        vi_words = None
        print("Khong tim thay vietnamese_words.txt, dung tu sinh tu dong.")

    # Vi du: mot vung xap xi trung tam TP.HCM ~ 12km x 12km
    system = MiniW3W(
        lat_min=10.72, lon_min=106.62,
        lat_max=10.83, lon_max=106.73,
        cell_size_m=5.0,
        dict_size=4096,
        word_list=vi_words,
    )

    print(f"So cot: {system.grid.num_cols}, so hang: {system.grid.num_rows}, "
          f"tong so o: {system.grid.num_cells:,}")
    print(f"Khong gian tu co the bieu dien: {system.mapper.M:,} to hop")

    test_points = [
        (10.7769, 106.7009),  # gan Nha tho Duc Ba
        (10.762622, 106.660172),
        (10.8, 106.65),
    ]

    ok = True
    for lat, lon in test_points:
        w1, w2, w3 = system.to_words(lat, lon)
        back_lat, back_lon = system.to_latlon(w1, w2, w3)
        # sai so cho phep: nua canh o (cell_size/2) doi ra do
        dlat = abs(back_lat - lat)
        dlon = abs(back_lon - lon)
        print(f"({lat}, {lon}) -> {w1}.{w2}.{w3} -> ({back_lat:.6f}, {back_lon:.6f})  "
              f"lech~ {dlat*111320:.1f}m/{dlon*111320*math.cos(math.radians(10.77)):.1f}m")

    # Test tinh duy nhat: 2 diem trong 2 o khac nhau phai ra 3 tu khac nhau
    w_a = system.to_words(10.7769, 106.7009)
    w_b = system.to_words(10.7770, 106.7009)  # cach ~11m -> khac o
    print("\nHai o gan nhau co tu khac nhau ro ret (khong doan duoc pattern):")
    print(" ", w_a)
    print(" ", w_b)

    # Test round-trip tren nhieu o ngau nhien de chac chan bijection dung
    import random
    random.seed(42)
    fails = 0
    for _ in range(2000):
        cid = random.randrange(system.grid.num_cells)
        row, col = system.grid.id_to_cell(cid)
        w1, w2, w3 = system.mapper.cellid_to_words(cid)
        cid2 = system.mapper.words_to_cellid(w1, w2, w3)
        if cid2 != cid:
            fails += 1
    print(f"\nRound-trip test tren 2000 o ngau nhien: {'PASS' if fails==0 else f'FAIL ({fails} loi)'}")