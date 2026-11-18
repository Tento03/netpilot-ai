# Bukti Phase 1: pengukuran di WiFi nyata (simulated: false)

Data kantor (SSID, BSSID, hostname, IP lokal, DNS) disamarkan oleh `ai-service/scripts/redact_evidence.py`.
Gateway dibiarkan karena menjadi bukti inti. Output mentah ada di `evidence/_raw/` (tidak di-commit).

| Tool | Hasil |
|---|---|
| ping_host gateway | 10/10, avg 3.0 ms, min 2, max 6, jitter 1.2 ms |
| ping_host 8.8.8.8 | 10/10, avg 21.2 ms, min 16, max 50, jitter 9.2 ms |
| check_dns (sistem) | 10.7 ms dan 15.8 ms (dua run, jeda 20 detik) |
| check_dns resolver 1.1.1.1 | 6.6 ms, 29.4 ms, dan satu timeout 3113.3 ms |
| check_tcp_port google:443 | open, 36.1 ms |
| check_tcp_port gateway:80 | timeout (kemungkinan difilter, bukan gateway rusak) |
| http_timing google | 200, TLSv1.3, dns 5.9 / tcp 39.2 / tls 47.6 / ttfb 56.0 / total 173.8 ms |
| measure_download | 24.32 Mbps (perkiraan kasar satu koneksi; sampel lain 6.97 dan 19.28) |
| get_wifi_link_info | 5 GHz, channel 36, 802.11ac, WPA2-Personal, Rx/Tx 780 Mbps (kecepatan radio ke AP, bukan kecepatan internet) |

## Catatan interpretasi
- Jaringan berfluktuasi dalam hitungan menit. Hasil lambat sesaat harus diulang sebelum disimpulkan.
- Throughput satu koneksi adalah batas bawah, bukan kecepatan internet.
- Status tool `ok` tidak berarti semua resolver berhasil; periksa `results[].ok` di check_dns.
