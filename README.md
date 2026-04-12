# Tunnela

Fork / distribusi WGDashboard dengan penyesuaian deployment (Nginx + Unix socket, dokumentasi instalasi, dll.).

## Instalasi

Ikuti **[src/install-step-by-step.md](src/install-step-by-step.md)** (flow, checklist sebelum `./wgd.sh install`, dan penjelasan `wg-dashboard.ini`).

## Konfigurasi lokal

- Salin **`templates/wg-dashboard.ini.template`** ke `src/wg-dashboard.ini` lalu sesuaikan, **atau** biarkan file dibuat otomatis saat pertama `./wgd.sh start`.
- Salin contoh TLS / Certbot jika perlu:
  - `src/ssl-tls.ini.example` → `src/ssl-tls.ini`
  - `src/certbot.ini.example` → `src/certbot.ini`

File `*.ini` di `src/` yang berisi secret **tidak** di-commit (lihat `.gitignore`).

## Lisensi

Mengikuti lisensi proyek hulu (WGDashboard / Apache-2.0 sesuai header sumber).
