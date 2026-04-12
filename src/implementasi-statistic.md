# Implementasi statistik Clients (Network overview)

## Status implementasi

**Status keseluruhan: selesai (Fase 1–3).** Build frontend + `./wgd.sh restart` sudah dijalankan; UI **Client List Management** diverifikasi: kartu ringkas, tabel **By configuration**, chart **Aggregate traffic (snapshots)** dengan titik waktu mengikuti interval koleksi, **Last updated** konsisten dengan snapshot terakhir.

- **Fase 1 (1–6):** Selesai — backend + API + scheduler (lihat bagian *Update status*).
- **Fase 2:** Selesai — **Settings → WGDashboard Settings** → kartu **“Clients list statistics”** (`dashboardClientsStatisticsInterval.vue`): preset 1 / 2 / 5 / 10 / 15 / 30 menit + **Custom 1–60 menit**; simpan lewat `updateDashboardConfigurationItem` (`clients_statistics_interval` di-clamp server-side); **`reschedule_clients_network_overview_job()`** dipanggil otomatis dari `API_updateDashboardConfigurationItem` setelah simpan.
- **Fase 3:** Selesai — di halaman **Client List Management**, di bawah judul: komponen `clientsNetworkOverview.vue` (async) memuat `GET /api/getClientsNetworkOverview`, kartu ringkas (peer aktif, total peer, RX/TX agregat), tabel per interface, chart garis `series24h` (total received/sent GB); polling mengikuti `interval_ms` dari API (min 10 s) dan diselaraskan dengan `clients_statistics_interval` di store bila berubah.

---

Dokumen ini merencanakan fitur agregat metrik untuk halaman **Client List Management**: kartu ringkas + deret waktu ~24 jam. Data disimpan di **PostgreSQL yang sudah dipakai WGDashboard** (`wgdashboard`), retensi **rolling24 jam** (hapus data lebih tua). Pengumpulan dijadwalkan dari **aplikasi** dengan **APScheduler** (bukan crontab wajib); dependensi ikut terpasang lewat `./wgd.sh install` selama `APScheduler` tercantum di `requirements.txt`.

---

## Prinsip urutan kerja

Urutan yang paling aman dan tidak bikin UI “ngambang”:

**Rekomendasi: backend dulu sampai “ada data nyata”, lalu UI**

**Alasan:** chart & kartu butuh kontrak API + isi tabel. Kalau UI duluan, nanti bolak-balik ubah shape JSON.

---

## Fase 1 — Backend (sampai bisa diverifikasi tanpa UI)

1. **`requirements.txt`** — tambah APScheduler (versi pin mis. `APScheduler>=3.10,<4`).
2. **Tabel Postgres** di DB `wgdashboard` — mis. `clients_network_overview_snapshots` (`id`, `recorded_at TIMESTAMPTZ`, kolom metrik atau `JSONB`), **index** `recorded_at`.
3. **Modul Python** — fungsi: kumpulkan metrik (loop config/peer seperti kode yang sudah ada), `INSERT`, lalu `DELETE WHERE recorded_at < now() - interval '24 hours'`.
4. **Config** — key baru `clients_statistics_interval` (ms), default & **clamp** min 1 menit; default di `DashboardConfig` / `wg-dashboard.ini` mengikuti pola yang sudah dipakai.
5. **APScheduler** — start dari `dashboard.py` (atau satu modul init). **Perhatian:** multi-worker Gunicorn — nanti: satu worker saja atau advisory lock agar tidak double insert.
6. **API** — mis. `GET /api/getClientsNetworkOverview` → `{ latest, series24h }` (auth sama seperti endpoint lain).

**Cek:** panggil API / lihat baris bertambah di DB setelah beberapa menit.

---

## Fase 2 — Settings

- **WGDashboard Settings** — preset 1 / 5 / 10 menit (+ opsi lain) + **custom** dengan **minimum 1 menit**, simpan ke config yang sama (`clients_statistics_interval` dalam ms).

---

## Fase 3 — UI

- **`clients.vue`** — overview di bawah judul “Client List Management”: `ClientsNetworkOverview` → fetch API, chart + kartu (lihat `clientsNetworkOverview.vue`).

---

## Alternatif cepat (vertical slice)

Kalau mau cepat ada end-to-end: tabel + job + **satu endpoint** yang isinya cuma **active count + timestamp** → satu angka di UI → baru lengkapi metrik lain & chart. Kurang ideal untuk arsitektur akhir, tapi enak untuk tes alur.

---

## Kesimpulan

Rencana awal (backend → Settings → UI) sudah dijalankan sampai tuntas. **Tidak ada pekerjaan wajib tersisa** untuk MVP statistik Clients; penyempurnaan opsional hanya metrik lanjutan dan hardening multi-worker (lihat tabel isu di bawah).

**Lanjutan opsional:** isi `connections_24h` / `network_load_percent`; mitigasi Gunicorn jika `workers` &gt; 1.

---

## Referensi keputusan desain (ringkas)

| Topik | Pilihan |
|--------|---------|
| Database | Postgres existing (`wgdashboard`), satu tabel baru |
| Retensi | Rolling24 jam: hapus baris `recorded_at` lebih tua dari `now() - 24 hours` |
| Waktu di DB | `TIMESTAMPTZ` (UTC); tampilan zona waktu di UI/API jika perlu |
| Interval koleksi | Terpisah dari `dashboard_refresh_interval`; preset + custom, min 1 menit |
| Deploy | `APScheduler` di `requirements.txt` → `./wgd.sh install` menginstal ke `venv` |

---

## Update status (inventory & isu)

*Terakhir diselaraskan dengan kode di branch/repo `dev-2026-04-11/src` (2026-04-12). UI end-to-end sudah dicek di lingkungan deploy (kartu, tabel per interface, chart 24h).*

### Sudah terimplementasi

| Area | Isi |
|------|-----|
| Dependensi | `APScheduler>=3.10,<4` di `requirements.txt` |
| Config default | `Server.clients_statistics_interval` = `300000` (ms) di `DashboardConfig`; clamp lewat `ClientsNetworkOverviewStats.clamp_interval_ms` / `get_interval_ms` (60 000–3 600 000); **POST** `updateDashboardConfigurationItem` juga menormalisasi nilai sebelum `SetConfig` |
| Tabel DB | `clients_network_overview_snapshots` (`snapshot_id`, `recorded_at`, `metrics` JSON, index `recorded_at`) — dibuat lewat `metadata.create_all` saat init manager |
| Koleksi metrik | `ClientsNetworkOverviewStats.build_metrics` / `collect_and_persist`: agregat peer aktif (`running`), total peer (Peers + restricted), RX/TX GB per interface & total; field `connections_24h` & `network_load_percent` di JSON masih `null` (placeholder) |
| Retensi | Setelah setiap `INSERT`, `DELETE` baris dengan `recorded_at` lebih tua dari 24 jam (UTC) |
| Scheduler | `ClientsNetworkOverviewScheduler`: `BackgroundScheduler`, job pertama `next_run_time` ~segera, `max_instances=1`, `coalesce=True` |
| Start job | `gunicorn.conf.py` → `post_worker_init` memanggil `dashboard.start_clients_network_overview_scheduler()`; `dashboard.py` `if __name__` juga (mode debug) |
| API | `GET {app_prefix}/api/getClientsNetworkOverview` → `data`: `latest`, `series24h`, `interval_ms` (auth sama endpoint API lain) |
| Integrasi app | `ClientsNetworkOverviewStatsManager` di `dashboard.py`; UI Settings interval di `wgdashboardSettings.vue` + `dashboardClientsStatisticsInterval.vue` |
| Reschedule | Setelah simpan `clients_statistics_interval` via API → `reschedule_clients_network_overview_job()` (bukan hanya dari UI manual) |
| UI Clients | `clients.vue` memuat `ClientsNetworkOverview` → `clientsNetworkOverview.vue` (kartu + tabel per config + line chart dari `latest` / `series24h`) |

### Belum / menyusul

- **Metrik lanjutan:** isi nyata untuk `connections_24h` dan `network_load_percent` (butuh definisi + mungkin logika tambahan).

### Isu / catatan (bukan bug blocker jika operasi standar)

| Isu | Tingkat | Penjelasan singkat |
|-----|---------|-------------------|
| Multi-worker Gunicorn | **Perhatian** | Stock `gunicorn.conf.py` memakai **`workers = 1`**. Jika `workers` dinaikkan tanpa lock, tiap worker bisa menjalankan scheduler → **kemungkinan double insert**. Mitigasi: tetap 1 worker, advisory lock DB, atau jalankan job hanya di satu worker. |
| Ubah interval lewat file INI saja | **Perhatian** | Edit manual `wg-dashboard.ini` tanpa **restart** proses: nilai di disk ≠ memori sampai reload; jadwal APScheduler tetap mengikuti nilai saat process start / terakhir **reschedule** (mis. dari Settings API). **Restart** amankan sinkron. |
| `latest` null | **Normal sementara** | Sesaat setelah start, sebelum job pertama selesai, API bisa mengembalikan `latest: null`. Setelah job jalan, terisi. |
| SQLite vs Postgres | **Aman** | Tabel memakai tipe SQLAlchemy yang umum (`DateTime(timezone=True)`, `JSON`); Postgres adalah target utama; SQLite/MySQL tetap konsisten dengan pola DB lain di proyek. |

**Kesimpulan singkat:** untuk deployment standar (Gunicorn 1 worker, Postgres, restart setelah ubah dependency), **tidak ada isu terbuka yang memblokir** penggunaan API + job; risiko utama hanya jika **workers Gunicorn &gt; 1** tanpa mitigasi.
