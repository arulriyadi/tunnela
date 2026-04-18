# WGDashboard — ringkasan struktur & sistem

Dokumen ini merangkum isi repo [WGDashboard/WGDashboard](https://github.com/WGDashboard/WGDashboard) dari struktur folder sampai alur kode utama. Versi konfigurasi di kode mengacu ke `DashboardConfig.DashboardVersion` (saat ini **v4.3.4** di `modules/DashboardConfig.py`).

---

## 1. Struktur repositori (atas ke bawah)

| Path | Fungsi |
|------|--------|
| `src/` | **Semua runtime aplikasi**: Python (Flask), modul bisnis, aset frontend yang sudah di-build, skrip ops. |
| `src/dashboard.py` | Entry WSGI/Flask: inisialisasi app, API admin, thread latar belakang, route `index`. |
| `src/client.py` | Blueprint **portal klien** (bukan admin): signup/signin, peer assignment, dll. |
| `src/modules/` | Logika terpisah per domain (WireGuard, peer, job, konfig dashboard, OIDC, email, …). |
| `src/static/dist/WGDashboardAdmin/` | UI admin **Vue** (hasil build): `index.html` + chunk JS/CSS. |
| `src/static/dist/WGDashboardClient/` | UI klien (build terpisah). |
| `src/static/locales/` | Terjemahan JSON + `locale_manager.py`. |
| `src/wgd.sh` | Installer/start/stop/update: venv, dependensi OS, **Gunicorn**. |
| `src/gunicorn.conf.py` | Binding host/port dari `wg-dashboard.ini`, worker, log, hook `post_worker_init` untuk thread. |
| `src/wg-dashboard.service` | Contoh unit systemd (referensi). |
| `templates/wg-dashboard.ini.template` | Contoh isi `wg-dashboard.ini` setelah instalasi. |
| `docker/` | Opsi deploy container (di luar scope “native” tapi ada di repo). |

**Catatan penting:** menjalankan stack dari sumber biasanya dilakukan dari dalam **`src/`** (di sinilah `dashboard.py`, `wgd.sh`, dan `wg-dashboard.ini` hidup setelah install).

---

## 2. Cara sistem dijalankan (runtime)

1. **`./wgd.sh install`** (sekali): OS package (Python, net-tools, venv, …), venv `./venv`, `requirements`, salin template config, log di `./log/install.txt`.
2. Konfig utama: **`wg-dashboard.ini`** (path bisa diarahkan dengan env **`CONFIGURATION_PATH`** — default `.` relatif ke cwd).
3. **`./wgd.sh start`**: menjalankan **`gunicorn`** dengan **`gunicorn.conf.py`** → memuat **`dashboard:app`**.
4. **Gunicorn** `post_worker_init` memanggil **`dashboard.startThreads()`** dan **`DashboardPlugins.startThreads()`** — thread daemon untuk refresh data WireGuard dan jadwal job peer.

Port dan bind: section **`[Server]`** — `app_ip`, `app_port` (default template: `0.0.0.0` dan `10086`).

---

## 3. Arsitektur aplikasi (bertahap)

### Lapisan 1 — Web server & SPA

- **Flask** `app` memakai `template_folder` = `static/dist/WGDashboardAdmin` → route **`GET {APP_PREFIX}/`** me-`render_template('index.html')` (admin SPA).
- Admin UI memanggil REST di bawah **`{APP_PREFIX}/api/...`**.
- **CORS** dibuka untuk `{APP_PREFIX}/api/*` (origins `*`, header termasuk `wg-dashboard-apikey`).

### Lapisan 2 — Autentikasi & akses API

- **`@app.before_request` `auth_req`** (`dashboard.py`): jika `auth_req` aktif, request ke API (selain whitelist) butuh sesi admin (`session['role'] == 'admin'`) atau **API key** valid di header **`wg-dashboard-apikey`** (jika `dashboard_api_key` diaktifkan).
- Endpoint login: **`POST .../api/authenticate`** — bcrypt untuk password akun di `[Account]`, opsional TOTP.
- Respon API memakai pola JSON **`ResponseObject(status, message, data)`**.

### Lapisan 3 — Konfigurasi global & database app

- **`DashboardConfig`** (`modules/DashboardConfig.py`): membaca/menulis `wg-dashboard.ini` (RawConfigParser), mengisi default jika key belum ada, menyimpan **versi dashboard**.
- **SQLAlchemy** `engine` di `DashboardConfig` memakai **`getConnectionString('wgdashboard')`**:
  - default **`[Database] type = sqlite`** → file di subfolder **`db/`** (mis. metadata/API keys global),
  - bisa dialihkan ke **postgresql** atau **mysql** lewat section `[Database]` (lihat `getConnectionString` — untuk Postgres memakai `postgresql+psycopg2`, sedangkan `ConnectionString.py` memakai varian `postgresql+psycopg`; perlu diperhatikan saat menyamakan dependency).
- **`modules/ConnectionString.py`**: helper serupa yang membaca `wg-dashboard.ini` dari cwd — dipakai beberapa modul (termasuk **`WireguardConfiguration`**) untuk engine **per basis data konfigurasi WireGuard**.

### Lapisan 4 — WireGuard sebagai domain inti

- **`WireguardConfigurations`**: dict global `nama → WireguardConfiguration` di `dashboard.py`.
- **`InitWireguardConfigurationsList()`**: scan **`wg_conf_path`** (`/etc/wireguard`) untuk `*.conf`, instansiasi **`WireguardConfiguration`**; jika binary **AmneziaWG** ada, scan **`awg_conf_path`** dan pakai **`AmneziaWireguardConfiguration`**.
- **`WireguardConfiguration`** (`modules/WireguardConfiguration.py`):
  - Membaca/menulis file **`.conf`** WireGuard (parser mirip INI dengan `optionxform` untuk menjaga case key).
  - Menyimpan state peer dan metadata aplikasi di DB lewat SQLAlchemy (`create_engine(ConnectionString("wgdashboard"))` + tabel metadata per deployment).
  - Mengoperasikan antarmuka sistem: **`subprocess`** ke utilitas **`wg`** / **`wg-quick`** (start/stop, status) — intinya dashboard adalah **wrapper** di atas konfigurasi nyata di filesystem server.

### Lapisan 5 — Peer, job, dan utilitas jaringan

- **`Peer`**: model/satu peer dalam satu konfigurasi.
- **`PeerJobs` / `PeerJob`**: penjadwalan tugas terkait peer; thread #2 memanggil **`AllPeerJobs.runJob()`** secara periodik.
- **`PeerShareLinks`**, **`PeerShareLink`**: Berbagi konfig peer via link publik (ada route whitelist **`sharePeer/get`**).
- Ping/traceroute: **`icmplib`** di `dashboard.py` untuk fitur diagnosa dari UI.

### Lapisan 6 — Fitur tambahan

- **`DashboardClients`** + blueprint di **`client.py`**: portal end-user terpisah (prefix `{app_prefix}/client`), email reset password via **`EmailSender`**, OIDC opsional.
- **`DashboardPlugins`**: ekstensi dengan thread sendiri.
- **`DashboardWebHooks`**: webhook dan sesi pengiriman.
- **`SystemStatus`**, **`DashboardLogger`**, **`NewConfigurationTemplates`**: status sistem, logging, template konfig baru.

### Thread latar belakang

| Thread | Fungsi |
|--------|--------|
| #1 `peerInformationBackgroundThread` | Untuk tiap konfigurasi aktif: handshake terbaru, transfer, endpoint, traffic logging, restricted peers, dll. |
| #2 `peerJobScheduleBackgroundThread` | Menjalankan **`AllPeerJobs.runJob()`** setiap ~3 menit. |

---

## 4. Peta API admin (contoh kelompok)

Semua di bawah prefix **`APP_PREFIX`** + `/api/` (bisa string kosong).

- **Auth / tema / locale:** `authenticate`, `validateAuthentication`, `getDashboardTheme`, `locale`, …
- **Konfigurasi WireGuard:** `getWireguardConfigurations`, `addWireguardConfiguration`, `toggleWireguardConfiguration`, `updateWireguardConfiguration`, backup/restore, …
- **Peer:** `addPeers`, `deletePeers`, `updatePeerSettings`, download QR/config, restrict, share, …
- **Dashboard:** `getDashboardConfiguration`, `updateDashboardConfigurationItem`, API keys, …
- **Klien admin:** CRUD client di bawah `/api/clients/...`
- **Webhook:** `/api/webHooks/...`

Daftar lengkap: grep `@app.` di `dashboard.py` atau telusuri file yang sama.

---

## 5. Dependensi penting (dari kode)

- **Flask**, **flask-cors**, **gunicorn**, **SQLAlchemy**, **sqlalchemy-utils**
- **bcrypt**, **pyotp** — autentikasi admin (TOTP opsional)
- **psutil**, **icmplib** — sistem & diagnostika jaringan
- Driver DB opsional: **psycopg2** / **psycopg** (Postgres), MySQL sesuai `getConnectionString`

WireGuard/Amnezia: bergantung pada **`wg`**, **`wg-quick`**, dan opsional **`awg`** / **`awg-quick`** di PATH.

---

## 6. File kode “mulai baca di sini”

| Prioritas | File | Alasan |
|-----------|------|--------|
| 1 | `src/dashboard.py` | App Flask, auth, hampir semua route API admin, inisialisasi global. |
| 2 | `modules/DashboardConfig.py` | INI, engine DB global, versi. |
| 3 | `modules/WireguardConfiguration.py` | Inti domain: file `.conf`, DB peer, subprocess. |
| 4 | `client.py` | Alur klien terpisah dari admin. |
| 5 | `gunicorn.conf.py` + `wgd.sh` | Produksi vs debug, lifecycle. |

---

## 7. Integrasi dengan PostgreSQL terpisah (opsional)

Section `[Database]` di `wg-dashboard.ini` mendukung **`type = postgresql`** dengan host, port, username, password. Itu memisahkan penyimpanan metadata WGDashboard dari SQLite default — **bukan** menggantikan fakta bahwa peer dan WireGuard tetap berkaitan erat dengan file di `wg_conf_path` dan tools kernel/userspace di server.

**URL koneksi di kode:** `modules/DashboardConfig.py` dan `modules/ConnectionString.py` membangun DSN SQLAlchemy. Paket di `requirements.txt` adalah **psycopg 3**; gunakan skema **`postgresql+psycopg://`** (bukan `psycopg2`).

**Beberapa nama database:** Aplikasi memuat lewat `ConnectionString(<nama>)` — antara lain `wgdashboard`, `wgdashboard_job`, `wgdashboard_log`. Di PostgreSQL, fungsi `create_database` di jalur startup membutuhkan user dengan hak membuat DB (misalnya **`ALTER ROLE ... CREATEDB`**) atau buat ketiga database itu manual lebih dulu.

---

## 8. Paritas singkat: image Docker vs monolit di host

Berdasarkan `docker/Dockerfile` dan `docker/entrypoint.sh` di repo ini:

| Aspek | Docker | Monolit (contoh di lingkungan ini) |
|--------|--------|-------------------------------------|
| Working directory | `/opt/wgdashboard/src` | `dev-wgd/src` |
| Proses | `venv/bin/gunicorn --config gunicorn.conf.py` | Sama (`./wgd.sh start`) |
| Config | `/data/wg-dashboard.ini` → symlink ke `src/wg-dashboard.ini` | Langsung `src/wg-dashboard.ini` (di-ignore git) |
| SQLite | `/data/db` → symlink `src/db` | Folder `src/db` (kosong jika pakai Postgres) |
| WireGuard | `wg`/`wg-quick`, template `wg0.conf`, `NET_ADMIN` | Paket `wireguard` di host; tanpa Docker perlu hak root untuk antarmuka/MAC |
| Port UI | `10086/tcp` (mapping compose) | `app_ip`/`app_port` di INI (default `0.0.0.0:10086`) |

`entrypoint.sh` tidak mengisi section Postgres; untuk DB eksternal tetap lewat `[Database]` di INI.

---

*Dokumen ini dibuat untuk mempercepat onboarding pada clone lokal; untuk instalasi resmi dan peringatan keamanan ikuti README upstream dan rilis terbaru di GitHub.*
