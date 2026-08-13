from w3a import MiniW3W

# Khởi tạo hệ thống cho vùng bạn muốn (thay bbox theo thành phố của bạn)
system = MiniW3W(
    lat_min=10.02937, lon_min=105.76206,
    lat_max=10.03218, lon_max=105.76594,
    cell_size_m=5.0,
    dict_size=4096,
)

# Toạ độ -> 3 từ
w1, w2, w3 = system.to_words(10.03198,105.76555)
print(w1, w2, w3)

# 3 từ -> toạ độ (tâm ô)
lat, lon = system.to_latlon(w1, w2, w3)
print(lat, lon)