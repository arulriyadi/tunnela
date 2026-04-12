# Implementasi Nginx + Gunicorn (Unix socket)

Dokumen ini merencanakan **mode listen ganda** untuk WGDashboard: **TCP direct** (default, seperti sekarang) dan **Unix socket** di belakang **Nginx** reverse proxy. Konfigurasi tetap di **`wg-dashboard.ini`** (`[Server]`); **bukan** file WireGuard.

## Status: **selesai** (baseline fitur)

Implementasi utama **done** — mencakup INI + Gunicorn bind, UI listen/socket + kartu Nginx, deploy ke `/etc/nginx`, opsi `default_server` + hapus situs default bawaan, diagnostik socket → `curl` → Nginx, restart WGD dari UI, kunci opsional `systemd_unit`, contoh **`sudoers.wgdashboard.example`**, serta locale (`locale_template` / `id-ID`) untuk string terkait.

**Catatan operasional:** konfigurasi Nginx di host (mis. `/etc/nginx/sites-available/wgdashboard.conf`) adalah tanggung jawab admin/deploy; UI **Deploy** menulis file yang sama secara otomatis jika proses berjalan dengan izin yang cukup.

---

## Mulai dari mana? (yang disiapkan dulu)

Urutan disarankan **sebelum** menulis banyak kode UI:

1. **Keputusan produk (singkat)**  
   - Nama kunci di INI: mis. `app_listen_mode` = `direct` | `nginx_socket`, `gunicorn_socket_path` = path absolut `.sock`.  
   - **Tidak** meng-install Nginx lewat `./wgd.sh install` secara default; deteksi Nginx di UI hanya informatif.

2. **Lingkungan uji**  
   - Satu VM/server dengan WGDashboard jalan **direct** hari ini.  
   - Akses **SSH** cadangan (untuk rollback manual `wg-dashboard.ini` jika terkunci dari browser).  
   - Opsional: Nginx sudah terpasang di mesin yang sama untuk uji end-to-end.

3. **Path socket & permission (rencana)**  
   - Contoh: `/run/wgdashboard/gunicorn.sock` atau di bawah folder install dengan subfolder khusus.  
   - Dokumentasikan user OS yang menjalankan Gunicorn vs user `www-data` (Nginx): grup bersama / `chmod` / umask — **ini risiko utama operasional**.

4. **Baseline kode (titik sentuh)**  
   - `dashboard.py` → `gunicornConfig()`  
   - `gunicorn.conf.py` → `bind`  
   - `modules/DashboardConfig.py` → default + validasi `SetConfig`  
   - `static/app` → Settings (kartu IP/Port diperluas + kartu Nginx + snippet)  
   - Opsional API: `GET .../api/getNginxRuntimeInfo` (versi binary, not installed)

5. **Dokumentasi admin**  
   - Urutan deploy aman, peringatan lockout, cara revert ke `direct`.

Setelah itu barulah implementasi bertahap (backend bind → INI → UI → snippet → deteksi Nginx).

---

## Fase 0: Kunci INI dan fresh install

### Apa yang harus disiapkan (output Fase 0)

| Item | Contoh / catatan |
|------|------------------|
| Nama kunci final | `app_listen_mode`, `gunicorn_socket_path` (dan tetap pakai `app_ip`, `app_port`) |
| Nilai default aman | `app_listen_mode = direct`; path socket hanya **placeholder** untuk UI/snippet (mis. `/run/wgdashboard/gunicorn.sock`) — tidak mengaktifkan socket sampai user pilih + restart |
| Aturan validasi | Nilai mode yang diizinkan; path absolut di mode socket; panjang maks; penolakan karakter berbahaya |
| Kebijakan path default | Apakah default socket di `/run/...` (perlu `RuntimeDirectory` / mkdir saat start) atau di bawah folder install (lebih mudah permission) |

Tidak perlu “rapat panjang”: cukup **dicatat di dokumen ini + dicerminkan di kode** `DashboardConfig.__default` dan `__configValidation`.

### Fresh install & `./wgd.sh install` — bisa disiapkan di sana?

**Ya, tapi cara yang paling selaras dengan kode hari ini:**

1. **`./wgd.sh install`** saat ini **tidak** wajib mengubah `wg-dashboard.ini` untuk kunci ini. Cukup pastikan setelah fitur jadi, **default ada di `DashboardConfig.py`** (`__default["Server"]`).

2. **Kapan kunci muncul di `wg-dashboard.ini`?**  
   Saat **`DashboardConfig()` pertama kali dijalankan** (biasanya saat **`./wgd.sh start`** / Gunicorn memuat `dashboard.py`). Konstruktor sudah punya loop: jika kunci belum ada di INI → **`SetConfig(..., init=True)`** menulis default.  
   Jadi **fresh install**: user jalankan `install` → `start` → file INI otomatis berisi `app_listen_mode` + `gunicorn_socket_path` (default) **tanpa** edit manual.

3. **Apa yang *tidak* perlu dimasukkan ke `wgd.sh install` (Fase 0)?**  
   - Install paket **Nginx** (tetap opsional / manual admin).  
   - Membuat folder socket / `chmod` — bisa ditunda ke **Fase 3** atau saat **start** Gunicorn (bukan wajib di `install`).

4. **Opsional ke depan**  
   Jika ingin konsistensi visual, `install_wgd` boleh **mencetak satu baris** ke log: *“Setelah start, cek `wg-dashboard.ini` untuk mode listen; default direct.”* — ini hanya UX dokumentasi, bukan syarat teknis.

**Kesimpulan:** Fase 0 = **kunci + default + validasi** di kode (`DashboardConfig`). **Fresh install ter-cover** lewat mekanisme default yang sudah ada saat pertama kali app start; **`wgd.sh install` tidak wajib diperluas** kecuali untuk pesan bantu atau tugas opsional (mkdir socket) yang Anda putuskan di Fase 3.

### Implementasi Fase 0 (di codebase)

- **`modules/DashboardConfig.py`**
  - `[Server].app_listen_mode` default `direct`.
  - `[Server].gunicorn_socket_path` default `os.path.join(ConfigurationPath, "run", "gunicorn.sock")` — **satu pohon dengan `wg-dashboard.ini`** (`{CONFIGURATION_PATH}/run/gunicorn.sock`).
  - Validasi non-init: `validate_app_listen_mode`, `validate_gunicorn_socket_path` (path absolut, tanpa `..`, panjang max512).
- **Setelah Fase 2:** Gunicorn membaca `app_listen_mode` / `gunicorn_socket_path` lewat `gunicornConfig()` + `gunicorn.conf.py`. **UI** mengatur kunci ini di Fase 4+.

### Implementasi Fase 1

- **`dashboard.py`** — `POST .../updateDashboardConfigurationItem`: `strip` untuk `app_listen_mode` dan `gunicorn_socket_path` sebelum `SetConfig`.
- **`DashboardConfig.validate_gunicorn_socket_path`** — jika **parent** path sudah ada di disk: harus **direktori** dan **writable**; jika parent belum ada, nilai tetap boleh (nanti `mkdir` di Fase 3 / start).

### Implementasi Fase 2

- **`dashboard.gunicornConfig()`** — mengembalikan `(bind, app_listen_mode)`: `bind` = string Gunicorn (`host:port` atau `unix:/path`); mode tidak dikenal di INI → diperlakukan sebagai `direct`.
- **`gunicorn.conf.py`** — `bind` dan log startup memakai pasangan tersebut (`app_listen_mode=… bind=…`).
- **`nginx_socket` dengan path kosong** → `RuntimeError` saat load config (perbaiki INI atau setel kembali ke `direct`).

### Implementasi Fase 3

- **Lokasi socket (best practice untuk proyek ini):** direktori **`run/`** di bawah **`CONFIGURATION_PATH`** (folder yang sama dengan `wg-dashboard.ini`), bukan `/run` sistem — permission dan backup lebih mudah.
- **`dashboard._ensure_gunicorn_socket_parent_dir`** — dipanggil dari `gunicornConfig()` saat `nginx_socket`: `os.makedirs(..., 0o755, exist_ok=True)` pada parent path socket.
- **`wgd.sh`** — `_precreate_gunicorn_unix_socket_parent`: baca `wg-dashboard.ini` (hindari double `_check_and_set_venv`), jika `app_listen_mode=nginx_socket` maka `sudo mkdir -p` + `chmod 755` pada parent socket sebelum `gunicorn`.

### Implementasi Fase 4

- **Settings → WGDashboard** — kartu diperluas: **Dashboard listen (TCP or Unix socket)**.
- **`dashboardIPPortInput.vue`** — `Listen mode` (`direct` / `nginx_socket`) disimpan lewat `POST /api/updateDashboardConfigurationItem`; mode **direct** menampilkan IP + port seperti semula; **nginx_socket** menampilkan field **Unix socket path** (absolut) + peringatan lockout; teks restart memakai semua jenis perubahan tersebut.
- **Locale** — kunci baru di `locale_template.json` dan terjemahan `id-ID.json`.

### Implementasi Fase 5

- **`dashboard.py`** — `GET {APP_PREFIX}/api/getNginxRuntimeInfo`: `shutil.which("nginx")`, lalu `nginx -v` (stderr/stdout), respons `{ installed, binary_path?, version_line?, error? }`; hanya lewat sesi admin (bukan whitelist publik).
- **`dashboardNginxReverseProxyCard.vue`** — status Nginx di host, pratinjau snippet `proxy_pass http://unix:…:` + header proxy, komentar `app_prefix` bila ada, tombol salin.
- **Locale** — kunci kartu + status + salin di `locale_template.json` / `id-ID.json`.

---

## Tujuan

- **direct**: Gunicorn `bind = app_ip:app_port` (perilaku sekarang).  
- **nginx_socket**: Gunicorn `bind = unix:PATH`; Nginx `proxy_pass` ke socket; pengguna mengakses HTTP(S) lewat Nginx.

---

## Alur konfigurasi (ringkas)

| Langkah | direct | nginx_socket |
|--------|--------|----------------|
| Simpan dari UI | `wg-dashboard.ini` | `wg-dashboard.ini` |
| Restart | `./wgd.sh stop && ./wgd.sh start` | sama |
| Listen ke internet | Gunicorn (TCP) | Nginx (80/443) |
| Gunicorn | `ip:port` | `unix:…sock` |

**Satu** proses Gunicorn, **satu** `gunicorn.conf.py`; hanya **nilai `bind`** yang bercabang.

---

## Kunci konfigurasi (usulan)

Di `[Server]`:

| Kunci | Tipe | Default | Keterangan |
|--------|------|---------|------------|
| `app_listen_mode` | string | `direct` | `direct` \| `nginx_socket` |
| `app_ip` | string | `0.0.0.0` | Dipakai jika `direct` |
| `app_port` | string | `10086` | Dipakai jika `direct` |
| `gunicorn_socket_path` | string | `{CONFIGURATION_PATH}/run/gunicorn.sock` | Path absolut; dipakai jika `nginx_socket` (default relatif ke folder konfigurasi / cwd) |

Validasi (backend):

- `app_listen_mode` hanya nilai yang diizinkan.  
- `gunicorn_socket_path`: tidak kosong di mode socket; path absolut; panjang wajar; parent directory — opsional cek exists/writable (heuristik).  
- URL / karakter berbahaya pada path ditolak.

---

## Perubahan backend

### 1. `dashboard.py` — `gunicornConfig()`

- Baca `app_listen_mode`.  
- Jika `direct`: kembalikan `(app_ip, app_port)` seperti sekarang; `gunicorn.conf.py` set `bind = f"{host}:{port}"`.  
- Jika `nginx_socket`: kembalikan sentinel atau tuple khusus, mis. `None, None` + path socket terpisah — atau ubah signature menjadi `(bind_kind, bind_value)` dengan `bind_kind in ("tcp", "unix")`.

**Catatan:** Gunicorn menerima `bind` sebagai string `host:port` atau `unix:/path`.

### 2. `gunicorn.conf.py`

- Impor hasil `gunicornConfig()` yang sudah disesuaikan.  
- Set `bind` ke TCP **atau** `unix:PATH` sesuai mode.  
- Log baris startup mencetak bind yang dipakai (tanpa menyembunyikan mode).

### 3. `DashboardConfig.py`

- Tambah default di `__default["Server"]`.  
- `__configValidation` untuk kunci baru.

### 4. `dashboard.py` — API (opsional tapi berguna)

- `GET /api/getNginxRuntimeInfo` (admin only): jalankan `nginx -v` (capture stderr), atau `shutil.which("nginx")`; kembalikan `{ installed, version_line?, error? }`.  
- Jangan eksekusi perintah arbitrer dari input user.

### 5. Socket & permission (opsional di `wgd.sh` atau Python pre-start)

- Sebelum start: `mkdir -p` parent socket, `chown`/`chmod` sesuai kebijakan — **hati-hati** dengan user yang menjalankan `sudo gunicorn` hari ini.

---

## Perubahan frontend (Settings → WGDashboard)

1. **Kartu “Dashboard listen”** (ganti/perluas “IP Address & Listen Port”):  
   - Pilihan: **Gunicorn langsung (TCP)** | **Lewat Nginx (Unix socket)**.  
   - Mode direct: field IP + port (seperti sekarang).  
   - Mode socket: field path socket; teks bantuan + **peringatan lockout** + checklist urutan deploy.

2. **Kartu “Nginx configuration”**  
   - Status: Nginx **not installed** / terdeteksi + **versi** (dari API).  
   - Pratinjau **snippet** read-only (dari placeholder: `server_name`, `listen`, path socket, header proxy).  
   - Tombol salin ke clipboard.

3. **Locale**  
   - String baru di `locale_template.json` + `id-ID.json` (dan lainnya jika perlu).

---

## Snippet Nginx (konsep)

- `upstream` atau `proxy_pass` ke `unix:/path/to.sock` dengan skema yang didukung distro (dokumentasikan variasi `http://unix:` vs `unix:`).  
- Header minimal: `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` (jika HTTPS di Nginx).  
- Menulis ke `/etc/nginx/` tersedia lewat **Deploy to nginx** (`POST …/deployWgDashboardNginx`) — lihat bagian [Deploy konfigurasi Nginx dari UI](#deploy-konfigurasi-nginx-dari-ui).

---

## Uji

1. Default baru: instalasi lama tanpa kunci → perilaku **direct** tidak berubah.  
2. Simpan direct → restart → akses `http://ip:port`.  
3. Simpan socket → restart → cek file socket ada; `curl --unix-socket ...`; pasang Nginx → uji dari browser.  
4. Rollback: SSH, set `app_listen_mode=direct`, restart.

---

## Fase implementasi (urutan kerja)

| Fase | Isi | Status |
|------|-----|--------|
| **0** | Kunci INI final + default di `DashboardConfig` + validasi + catatan fresh install (lihat [Fase 0: Kunci INI dan fresh install](#fase-0-kunci-ini-dan-fresh-install)) | **selesai** — `app_listen_mode`, `gunicorn_socket_path` di `DashboardConfig.py` |
| **1** | Normalisasi API (`strip`) untuk kunci listen/socket; validasi heuristik parent direktori socket (ada → harus folder + writable); tabel fase diselaraskan | **selesai** — `dashboard.py` + `validate_gunicorn_socket_path` |
| **2** | `gunicornConfig()` + `gunicorn.conf.py` (bind TCP vs unix) | **selesai** — `dashboard.py`, `gunicorn.conf.py` |
| **3** | `wgd.sh` + Python: pre-create parent direktori socket (default `{CONFIGURATION_PATH}/run/`) | **selesai** — `wgd.sh`, `dashboard.py` |
| **4** | UI: mode listen + path socket + simpan via API existing | **selesai** — `dashboardIPPortInput.vue`, `wgdashboardSettings.vue`, `locale_template.json`, `id-ID.json` |
| **5** | UI: kartu Nginx (snippet + salin + status versi API) | **selesai** — `GET .../getNginxRuntimeInfo`, `dashboardNginxReverseProxyCard.vue` |
| **6** | Locale + teks peringatan | **selesai** — string listen/Nginx/deploy/diagnostics/restart di `locale_template.json` & `id-ID.json` |
| **7** | Uji manual + pembaruan README singkat (opsional) | **uji manual OK** (login, Settings, proxy port 80); README proyek upstream **tidak wajib** diubah |

---

## Risiko & mitigasi

| Risiko | Mitigasi |
|--------|----------|
| Lockout setelah pindah socket tanpa Nginx | Peringatan UI; urutan deploy; rollback lewat SSH + INI |
| Permission socket vs Nginx | Dokumentasi grup/chmod; uji di VM |
| Dua `v` pada versi di teks copyright | Gunakan `{version}` tanpa prefix `v` di template jika `version` sudah `v4.x` |

---

## Referensi file (codebase saat ini)

- `wgd.sh` → `gunicorn_start` memanggil `gunicorn --config ./gunicorn.conf.py`  
- `gunicorn.conf.py` → `bind, app_listen_mode = dashboard.gunicornConfig()` (TCP `host:port` atau `unix:/path`)  
- `dashboard.py` → `gunicornConfig()`, `_ensure_gunicorn_socket_parent_dir`; `GET …/getNginxRuntimeInfo`; `GET …/getListenStackDiagnostics`; `POST …/deployWgDashboardNginx` (body: `server_name`, `default_server`, `disable_stock_default_site`); `POST …/restartWgDashboardService`  
- `modules/DashboardConfig.py` → `__default` (`app_listen_mode`, `gunicorn_socket_path`, `systemd_unit`), `SetConfig`, validasi  
- Settings UI: `wgdashboardSettings.vue`, `dashboardIPPortInput.vue`, `dashboardNginxReverseProxyCard.vue`  
- Contoh sudoers (opsional): `sudoers.wgdashboard.example`

---

## Deploy konfigurasi Nginx dari UI

- **Endpoint:** `POST …/api/deployWgDashboardNginx` (hanya **admin**, sesi login — bukan API key sembarangan untuk otomasi tanpa konteks).
- **Isi body:** `{ "server_name": "hostname.atau.ip" }` (karakter aman, panjang wajar). Opsional: **`"default_server": true`** — `listen 80 default_server;` + `server_name _;` untuk **`http://IP/`**. Opsional: **`"disable_stock_default_site": true`** — menghapus symlink **`/etc/nginx/sites-enabled/default`** (dan `default.conf` jika ada) sebelum `nginx -t`, dengan rollback jika tes gagal (supaya port 80 tidak tetap ke halaman statis bawaan).
- **Diagnostik (read-only):** `GET …/api/getListenStackDiagnostics` — path socket ter-resolve, **`curl --unix-socket`** ke Gunicorn (kode HTTP), baris `proxy_pass` di `wgdashboard.conf` jika ada, status file default bawaan Nginx.
- **Prasyarat:** `app_listen_mode = nginx_socket`, `gunicorn_socket_path` **absolut**, binary Nginx terdeteksi, layout host punya **`/etc/nginx/sites-available` + `sites-enabled`** (Debian/Ubuntu) **atau** **`/etc/nginx/conf.d`**.
- **File yang ditulis:** `sites-available/wgdashboard.conf` + symlink `sites-enabled/wgdashboard.conf` (jika layout sites), atau **`conf.d/wgdashboard.conf`**.
- **Setelah tulis:** `nginx -t` — jika gagal, perubahan di-**rollback** (file + symlink). Jika OK: **reload** Nginx (`systemctl` / `service` / `nginx -s reload`).
- **Deploy sendiri tidak me-restart WGDashboard** — hanya menulis konfigurasi Nginx dan reload **layanan Nginx**. Di UI: centang **“Restart WGDashboard setelah deploy berhasil”** (default aktif) untuk menjadwalkan restart setelah deploy sukses, atau gunakan tombol **Restart WGDashboard** di kartu listen.
- **Restart dari UI:** `POST …/api/restartWgDashboardService` dengan body opsional `{ "delay_seconds": 2 }`. Proses menjadwalkan **restart tertunda** (subprocess `sleep` lalu `systemctl restart` **atau** `./wgd.sh restart` dari direktori `dashboard.py`) agar respons HTTP selesai sebelum proses mati. Prioritas unit systemd: environment **`WGDASHBOARD_SYSTEMD_UNIT`**, lalu **`systemd_unit`** di `wg-dashboard.ini` (Server; kosong = pakai `wgd.sh`).
- **Tidak ada fallback otomatis ke TCP** jika deploy gagal: `wg-dashboard.ini` tidak diubah oleh Deploy; jika Anda sudah set `app_listen_mode=nginx_socket` dan restart WGD lalu terkunci, kembalikan mode lewat **SSH** seperti di dokumentasi risiko.

### Izin (penting)

| Skenario | Perilaku |
|----------|----------|
| **`./wgd.sh start` memakai `sudo`** (Gunicorn jalan sebagai **root**) | Deploy biasanya **langsung jalan** — bisa menulis `/etc/nginx` dan menjalankan `nginx -t` / reload. **Ini yang disarankan** untuk fitur Deploy. |
| Gunicorn jalan sebagai **user non-root** tanpa kemampuan menulis `/etc/nginx` | Deploy akan gagal dengan *Permission denied*. **Utama:** `sudo ./wgd.sh start` (proses root). **Alternatif (akses admin/lokal):** beri NOPASSWD **hanya** ke binary + **path file tetap** di bawah — bukan `tee` tanpa path (itu berbahaya). |

**Whitelist sudo (NOPASSWD) — skenario non-root:** file contoh lengkap ada di repositori: **`sudoers.wgdashboard.example`** (salin ke `/etc/sudoers.d/wgdashboard`, sesuaikan user Linux, path `wgd.sh`, dan nama unit `*.service`, lalu `visudo -cf` + `chmod 440`). Isinya mencakup antara lain:

| Kebutuhan | Perintah yang di-whitelist (contoh) |
|-----------|-------------------------------------|
| Deploy / reload Nginx dari UI | `nginx -t`, `nginx -s reload`, `systemctl reload nginx`, `service nginx reload` |
| Tulis snippet lewat `sudo tee` (opsional) | `tee` hanya ke `/etc/nginx/sites-available/wgdashboard.conf` dan `/etc/nginx/conf.d/wgdashboard.conf` (duplikat untuk `/usr/bin/tee` dan `/bin/tee`) |
| Restart dari UI (`restartWgDashboardService`) | `systemctl restart <unit>` — samakan dengan **`systemd_unit`** / **`WGDASHBOARD_SYSTEMD_UNIT`** |
| `wgd.sh` | `start`, `stop`, `restart` pada path absolut instalasi |
| Timezone dari UI | `timedatectl set-timezone *` (sama seperti entri otomatis `wgdashboard-timedatectl` dari `wgd.sh`) |
| Parent direktori socket (opsional) | `mkdir -p` / `chmod` ke path **tetap** yang Anda pakai untuk `gunicorn_socket_path` — barisnya dikomentari di contoh; aktifkan jika perlu |

**Jangan** memakai `NOPASSWD` untuk `tee`, `kill`, atau `chmod` tanpa path/argumen yang ketat. **Jangan** mem-whitelist `NOPASSWD: ALL`.

*Bawaan backend menulis file Nginx langsung dari Python (tanpa `sudo tee`); entri `tee` di contoh berguna jika Anda mengubah deploy memakai wrapper `sudo tee`.*

**Paling sederhana:** jalankan WGDashboard sebagai root dengan **`sudo ./wgd.sh start`** — maka Deploy Nginx dan banyak operasi tidak memerlukan sudoers tambahan (tetap pastikan layanan Nginx bisa di-reload).

### Gejala umum: `:10086` tidak bisa & halaman “Welcome to nginx!”

- **Port `app_port` (mis. 10086) tidak jalan setelah pindah ke `nginx_socket`:** ini **bukan bug** dan **bukan “fallback”** yang gagal. Di mode ini Gunicorn **hanya** bind ke **Unix socket** (`gunicorn_socket_path`); `app_ip` / `app_port` **tidak dipakai**. Akses UI lewat **Nginx** (biasanya port **80**), bukan `http://IP:10086`.
- **Port 80 masih menampilkan halaman default “Welcome to nginx!”:** Deploy dari UI dengan centang **“Situs default di port 80”** (mengirim `default_server: true`), **atau** isi **`server_name`** dengan **IP** yang Anda buka di browser (mis. `172.32.1.226`). Pastikan symlink **`sites-enabled/wgdashboard.conf`**, `nginx -t` OK, reload Nginx. Jika *duplicate default_server*, nonaktifkan **`sites-enabled/default`**.

---

*Implementasi baseline selesai; revisi berikutnya hanya jika produk menambah fitur (mis. dual bind TCP+socket) atau mengubah kontrak API.*
