"""
Backend Flask cho mini-what3words.

Chạy:
    python3 app.py

Rồi mở trình duyệt: http://localhost:5000
"""

import os
import re

from flask import Flask, request, jsonify, send_from_directory

from w3w_mini import MiniW3W, load_word_list_from_file

app = Flask(__name__, static_folder="static", static_url_path="")

# ---------------------------------------------------------------------------
# Nap tu dien tieng Viet + khoi tao he thong 1 lan duy nhat khi server start
# ---------------------------------------------------------------------------
WORD_FILE = os.path.join(os.path.dirname(__file__), "vietnamese_words.txt")
vi_words = load_word_list_from_file(WORD_FILE)

system = MiniW3W(
    # Trung tam TP Can Tho (khu Ninh Kieu - Ben Ninh Kieu), vung ~6km x 6km
    lat_min=10.006, lon_min=105.756,
    lat_max=10.060, lon_max=105.810,
    cell_size_m=5.0,
    word_list=vi_words,
)


# ---------------------------------------------------------------------------
# API 0: cau hinh vung ban do (de frontend tu ve luoi)
# ---------------------------------------------------------------------------
@app.route("/api/config", methods=["GET"])
def config():
    g = system.grid
    return jsonify({
        "lat_min": g.lat_min, "lon_min": g.lon_min,
        "lat_max": g.lat_max, "lon_max": g.lon_max,
        "cell_size_m": g.cell_size,
        "m_per_deg_lat": g.m_per_deg_lat,
        "m_per_deg_lon": g.m_per_deg_lon,
        "num_cols": g.num_cols, "num_rows": g.num_rows,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "UP"})


# ---------------------------------------------------------------------------
# API 1: toa do -> 3 tu
# ---------------------------------------------------------------------------
@app.route("/api/to-words", methods=["GET"])
def to_words():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)

    if lat is None or lon is None:
        return jsonify({"error": "Thieu tham so 'lat' hoac 'lon'"}), 400

    if not (system.grid.lat_min <= lat <= system.grid.lat_max and
            system.grid.lon_min <= lon <= system.grid.lon_max):
        return jsonify({
            "error": "Toa do nam ngoai vung ban do ho tro",
            "bounds": {
                "lat_min": system.grid.lat_min, "lat_max": system.grid.lat_max,
                "lon_min": system.grid.lon_min, "lon_max": system.grid.lon_max,
            }
        }), 400

    row, col = system.grid.latlon_to_cell(lat, lon)
    w1, w2, w3 = system.to_words(lat, lon)
    lat_sw, lon_sw, lat_ne, lon_ne = system.grid.cell_bounds(row, col)
    return jsonify({
        "lat": lat,
        "lon": lon,
        "words": [w1, w2, w3],
        "address": f"{w1}.{w2}.{w3}",
        "bounds": {"sw": [lat_sw, lon_sw], "ne": [lat_ne, lon_ne]},
    })


# ---------------------------------------------------------------------------
# API 2: 3 tu -> toa do
# ---------------------------------------------------------------------------
@app.route("/api/to-coordinate", methods=["GET"])
def to_coordinate():
    raw_address = request.args.get("address", type=str, default="")

    # 1) Cat khoang trang thua o dau/cuoi toan bo chuoi
    #    (vi du: "  hoa.la.cay  " -> "hoa.la.cay")
    address = raw_address.strip()

    if not address:
        return jsonify({"error": "Thieu tham so 'address'"}), 400

    # 2) Tach theo dau '.' roi cat khoang trang tung phan
    #    (vi du: "hoa . la . cay" -> ["hoa", "la", "cay"])
    parts = [p.strip() for p in address.split(".")]

    # 3) Phat hien phan rong do dau cham kep hoac thieu tu
    #    (vi du: "hoa..cay" hoac "hoa.la." se bi bat o day thay vi bi am tham bo qua)
    if len(parts) != 3 or any(p == "" for p in parts):
        return jsonify({
            "error": "Dinh dang khong hop le. Can dung dung 3 tu ngan cach boi dau '.', "
                     "vi du: 'hoa.la.cay'"
        }), 400

    # 4) Chuan hoa khoang trang NAM GIUA 1 tu ghep thanh dau gach duoi, vi tu dien
    #    luu tu ghep dang "khuon_mat" chu khong phai "khuon mat".
    #    Dung \s+ de gop luon nhieu khoang trang lien tiep thanh 1 dau '_'.
    #    (vi du: "khuon  mat" hoac "khuon   mat" -> "khuon_mat")
    parts = [re.sub(r"\s+", "_", p) for p in parts]

    # 5) Chuan hoa chu thuong de tra tu dien khong phan biet hoa/thuong
    #    (vi du: "Hoa.La.Cay" hoac "HOA.LA.CAY" van tra dung)
    w1, w2, w3 = (p.lower() for p in parts)

    for w in (w1, w2, w3):
        if w not in system.mapper.index_of:
            return jsonify({"error": f"Tu '{w}' khong ton tai trong tu dien"}), 404

    try:
        lat, lon = system.to_latlon(w1, w2, w3)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    row, col = system.grid.latlon_to_cell(lat, lon)
    lat_sw, lon_sw, lat_ne, lon_ne = system.grid.cell_bounds(row, col)
    return jsonify({
        "address": f"{w1}.{w2}.{w3}",
        "lat": lat,
        "lon": lon,
        "bounds": {"sw": [lat_sw, lon_sw], "ne": [lat_ne, lon_ne]},
    })


# ---------------------------------------------------------------------------
# Phuc vu frontend tinh
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/map")
def map_page():
    return send_from_directory("static", "map.html")


if __name__ == "__main__":
    print(f"Tu dien: {len(vi_words)} tu tieng Viet ({WORD_FILE})")
    print(f"Vung ban do: lat[{system.grid.lat_min}, {system.grid.lat_max}] "
          f"lon[{system.grid.lon_min}, {system.grid.lon_max}]")
    print(f"Tong so o: {system.grid.num_cells:,}")
    app.run(host="0.0.0.0", port=5000, debug=True)
