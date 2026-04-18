# WGDashboard / Tunnela — catatan rilis **v4.3.3**

Dokumen ini merangkum perubahan pada tree **`dev-2026-04-11`** (development) untuk rilis **v4.3.3**: file yang terdampak, struktur referensi, dan changelog.  
*(Versi di `DashboardConfig.DashboardVersion` / `package.json` dapat dinaikkan ke `v4.3.3` saat Anda siap menandai rilis.)*

---

## 1. Ringkasan

| Area | Isi singkat |
|------|-------------|
| **Cek update GitHub** | Repo `owner/repo` bisa dikonfigurasi (`wg-dashboard.ini` + env), bukan hardcode upstream saja. |
| **Home — alur jaringan** | Kartu alur tunnel → server → merge → Internet; garis merge dibuat halus (Bézier), gaya teal. |
| **Home — status sistem** | Widget throughput, **System & Server Info** (metrik teks + runtime), penyelarasan tinggi grafik dengan panel kanan. |
| **Konfigurasi** | Halaman daftar konfigurasi: komponen System Status di header dihilangkan (tetap di Home). |
| **Backend status** | Snapshot Host (IP, uptime), CPU (core + model), RAM/swap `used`, disk per mount, **RuntimeVersions** (Python, Gunicorn, Nginx, Flask, WireGuard tools, OpenSSL). |
| **Lokal / i18n** | Penambahan dan penyesuaian string (`locale_template.json`, `id-ID.json`). |

---

## 2. Struktur direktori (hanya yang relevan)

```
dev-2026-04-11/
├── UPDATE-v4.3.3.md                 ← file ini
├── WGDashboard-version-check-flow.txt  ← dokumentasi alur cek update (API + wgd.sh)
├── templates/
│   └── wg-dashboard.ini.template    ← contoh / template konfigurasi (termasuk update_github_repo)
└── src/
    ├── dashboard.py                 ← API routes (getDashboardUpdate, resolve_update_github_repo, …)
    ├── wg-dashboard.ini             ← konfigurasi aktif (lokal; jangan commit secret)
    ├── wgd.sh                       ← install / update / restart (baca update_github_repo)
    ├── modules/
    │   ├── DashboardConfig.py       ← default Server.*, DashboardVersion, update_github_repo
    │   └── SystemStatus.py          ← Host, CPU/Memory/Disk, RuntimeVersions
    └── static/
        ├── locales/
        │   ├── locale_template.json
        │   └── id-ID.json
        ├── dist/
        │   └── WGDashboardAdmin/    ← hasil `npm run build` (assest hash berubah tiap build)
        └── app/
            └── src/
                ├── views/
                │   ├── dashboardHome.vue
                │   └── configurationList.vue
                └── components/
                    ├── dashboardNetworkFlow.vue
                    └── systemStatusComponents/
                        └── systemStatusWidget.vue
```

---

## 3. Daftar file yang berubah (menurut kategori)

### Backend / skrip

| File | Perubahan utama |
|------|------------------|
| `src/modules/DashboardConfig.py` | Default `[Server] update_github_repo`; komentar konfigurasi. Versi konstanta `DashboardVersion` (naik ke v4.3.3 saat rilis). |
| `src/dashboard.py` | `resolve_update_github_repo()`; `GET /api/getDashboardUpdate` memakai `https://api.github.com/repos/<owner>/<repo>/releases/latest`. |
| `src/modules/SystemStatus.py` | `_host_snapshot()` (Host); info CPU statis (core, model); `Memory.used`; `RuntimeVersions` + cache; helper nginx/wg/openssl. |
| `src/wgd.sh` | `_read_update_github_repo`; `update` memakai repo + API yang sama dengan UI. |
| `src/wg-dashboard.ini` | Contoh: `update_github_repo` (sesuaikan deployment Anda). |
| `templates/wg-dashboard.ini.template` | Template termasuk `update_github_repo` (sesuaikan fork). |

### Frontend (Vue / build)

| File | Perubahan utama |
|------|------------------|
| `src/static/app/src/views/dashboardHome.vue` | Menyusun blok Home (alur jaringan + system status widget). |
| `src/static/app/src/components/dashboardNetworkFlow.vue` | Kartu alur WG, merge SVG Bézier, gaya garis, polling. |
| `src/static/app/src/components/systemStatusComponents/systemStatusWidget.vue` | Baris 4-kolom CPU/Storage/Memory/Swap; throughput **Line** chart; panel **System & Server Info** (teks + runtime); sink tinggi kartu throughput ↔ panel kanan (`useElementSize`); locale untuk label storage/runtime. |
| `src/static/app/src/views/configurationList.vue` | Menghapus `SystemStatus` dari area atas halaman. |

### Lokalisasi

| File | Perubahan utama |
|------|------------------|
| `src/static/locales/locale_template.json` | String baru (network flow, system info, storage, runtime, GB, cores, …); default Inggris untuk kunci yang tidak boleh kosong. |
| `src/static/locales/id-ID.json` | Terjemahan Indonesia untuk string di atas. |

### Dokumentasi di root repo

| File | Keterangan |
|------|------------|
| `WGDashboard-version-check-flow.txt` | Alur API GitHub, env, wgd.sh, checklist persiapan. |
| `UPDATE-v4.3.3.md` | File ini. |

### Output build (jangan edit manual)

| Path | Keterangan |
|------|------------|
| `src/static/dist/WGDashboardAdmin/**` | Hasil `npm run build` dari `src/static/app`; file hash berubah setiap build. |

### Versi aplikasi (naik saat rilis)

| File | Field |
|------|--------|
| `src/modules/DashboardConfig.py` | `DashboardVersion = 'v4.3.3'` |
| `src/static/app/package.json` | `"version": "4.3.3"` |

---

## 4. Changelog (detail)

### Konfigurasi & update

- **`[Server] update_github_repo`** — format `owner/repo` untuk endpoint GitHub `releases/latest` dan untuk `git pull` di `./wgd.sh update`.
- **Env `WGDASHBOARD_UPDATE_GITHUB_REPO`** — mengesampingkan nilai INI jika diset.
- **Fallback** — pola tidak valid → `WGDashboard/WGDashboard`.
- Dokumentasi alur ada di **`WGDashboard-version-check-flow.txt`**.

### Home — Network flow (`dashboardNetworkFlow.vue`)

- Alur per konfigurasi WireGuard: peer terhubung → server → merge → Internet.
- Merge path memakai **kurva Bézier** (fan-in), warna **teal** (`#34d3a6`), garis putus-putus + animasi (hormati `prefers-reduced-motion`).
- Throughput / Mbps dan penyalinan teks terkait home network (sesuai iterasi di branch).

### Home — System status (`systemStatusWidget.vue`)

- **Baris atas:** empat blok (CPU + core mini, Storage + mount, Memory, Swap) dengan progress bar seperti sebelumnya.
- **Baris bawah:** grafik **Network throughput** (semua interface, sampel rolling).
- **Kolom kanan satu kartu** berjudul **“System & Server Info”**:
  - CPU: % beban + teks core / model;
  - Memory & Swap: % + penggunaan dalam GB;
  - Storage: % + mount `/` (atau partisi pertama) + baris terpakai / bebas dalam GB;
  - Server IP, Uptime;
  - **Runtime:** Python, Gunicorn, Nginx, Flask, WireGuard tools, OpenSSL (dari backend `RuntimeVersions`).
- **Tinggi grafik** diselaraskan dengan tinggi kartu System & Server Info (`@vueuse/core` `useElementSize`) agar tidak ada area kosong besar di bawah panel kanan.
- **Locale:** label seperti `sysinfo storage used/free`, `GB`, `cores`, dsb. diisi di template + `id-ID`.

### Backend — `SystemStatus.py`

- **`Host`**: `primary_ipv4`, `uptime_seconds`.
- **`CPU`**: `logical_cores`, `physical_cores`, `model` (cache); persen tetap dari polling.
- **`Memory`**: **`used`** untuk virtual & swap (selain total / available / percent).
- **`RuntimeVersions`** (cache singkat): versi Python, Gunicorn (metadata atau CLI), Nginx (`-v`), Flask, `wg --version`, `openssl version`.

### Konfigurasi WireGuard — daftar

- **`configurationList.vue`**: widget System Status di header halaman dihapus (informasi serupa tetap di Home).

### i18n

- Entri baru untuk alur jaringan, throughput, info sistem, storage, runtime, dll.

---

## 5. Build & deploy (referensi)

```bash
cd src/static/app && npm run build
cd ../../.. && cd src && ./wgd.sh restart
```

*(Sesuaikan path jika struktur deployment berbeda.)*

---

## 6. Catatan

- **Repo private:** API `releases/latest` tanpa token tidak andal; untuk fork privat pertimbangkan token atau mekanisme lain.
- **Cek versi di UI** tetap membandingkan tag GitHub dengan **`DashboardConfig.DashboardVersion`**; pastikan angka rilis selaras saat tagging di Git.

---

*Dokumen ini dibuat untuk membantu review rilis v4.3.3; sesuaikan detail jika ada commit tambahan di luar daftar di atas.*
