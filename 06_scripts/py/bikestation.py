import requests
import json

# İstasyon bilgileri
url_info = "https://gbfs.theta.fifteen.eu/gbfs/2.2/montpellier/en/station_information.json"
url_status = "https://gbfs.theta.fifteen.eu/gbfs/2.2/montpellier/en/station_status.json"

info = requests.get(url_info).json()
status = requests.get(url_status).json()

# Kaydet
with open("station_information.json", "w") as f:
    json.dump(info, f, indent=2, ensure_ascii=False)

with open("station_status.json", "w") as f:
    json.dump(status, f, indent=2, ensure_ascii=False)

# Kaç istasyon var?
stations = info["data"]["stations"]
print(f"Toplam istasyon: {len(stations)}")
print(f"İlk istasyon: {stations[0]}")