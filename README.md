# Tunnela

**Tunnela** adalah fork / distribusi [WGDashboard](https://github.com/WGDashboard/WGDashboard) dengan penyesuaian untuk deployment (misalnya **Nginx + Unix socket**), dokumentasi instalasi dalam bahasa Indonesia, dan panduan operasional tambahan di folder `src/`.

Dashboard ini dipakai untuk **mengelola antarmuka WireGuard** (peer, QR code, konfigurasi, dan lain-lain) lewat **browser**.

---

## Isi dokumen ini

1. [Apa yang perlu disiapkan](#apa-yang-perlu-disiapkan-sebelum-mulai)  
2. [Mengunduh kode (clone)](#1-mengunduh-kode-dari-github)  
3. [Instalasi otomatis dengan `wgd.sh`](#2-instalasi-otomatis)  
4. [Menyalakan & mengakses dashboard](#3-menyalakan-dashboard)  
5. [File konfigurasi (`wg-dashboard.ini` dan lainnya)](#4-konfigurasi-file)  
6. [Opsional: Nginx, database, build UI](#5-opsional-lanjutan)  
7. [Masalah umum](#6-masalah-umum)  
8. [Lisensi](#lisensi)

Panduan **lebih detail** (alur, checklist, penjelasan tiap bagian `wg-dashboard.ini`): **[src/install-step-by-step.md](src/install-step-by-step.md)**.

---

## Apa yang perlu disiapkan sebelum mulai

| Kebutuhan | Penjelasan singkat |
|-----------|---------------------|
| **Server atau VM Linux** | Misalnya Ubuntu/Debian (disarankan). Script `wgd.sh` juga mendukung beberapa distro lain; lihat pesan error jika OS tidak didukung. |
| **Akses administrator (`sudo`)** | Diperlukan untuk menginstal paket Python, WireGuard, dan saat menjalankan proses dashboard (Gunicorn). |
| **Koneksi internet** | Untuk mengunduh dependensi Python dari internet (PyPI). Saat install, script bisa menawarkan **mirror** jika koneksi ke pypi.org lambat. |
| **Python 3.10, 3.11, atau 3.12** | Boleh diinstal dulu atau dibiarkan — script `install` bisa membantu menginstalnya di sistem yang didukung. |

**Tidak wajib di awal:** mengedit file konfigurasi secara manual, memasang Nginx, atau memasang PostgreSQL. Secara default aplikasi bisa **jalan dulu** dengan SQLite dan folder `db/` dibuat otomatis.

---

## 1. Mengunduh kode dari GitHub

**Pilih salah satu cara.**

### A. Unduh dengan HTTPS (paling sederhana)

```bash
git clone https://github.com/arulriyadi/tunnela.git
cd tunnela
```

Jika diminta login saat `git push` nanti, GitHub memakai **Personal Access Token** (bukan password akun).

### B. Unduh dengan SSH (jika Anda sudah punya kunci SSH di GitHub)

1. Pastikan **kunci publik** sudah ditambahkan di GitHub: **Settings → SSH and GPG keys**.  
2. **Kunci privat** hanya disimpan di mesin Anda; jangan dibagikan atau di-commit ke repo.

```bash
git clone git@github.com:arulriyadi/tunnela.git
cd tunnela
```

Jika kunci tidak di lokasi default, Anda bisa pakai **SSH config** (`~/.ssh/config`), contoh:

```text
Host github.com
  HostName github.com
  User git
  IdentityFile /path/ke/private-key-anda
  IdentitiesOnly yes
```

**Izin file kunci privat:** agar SSH mau memakainya, biasanya:

```bash
chmod 600 /path/ke/private-key-anda
```

Struktur folder setelah clone: kode aplikasi utama ada di **`src/`** (di dalamnya ada `wgd.sh`, `dashboard.py`, dll.).

---

## 2. Instalasi otomatis

Semua perintah di bawah dijalankan dari folder **`src/`** (bukan dari root repo `tunnela/`).

```bash
cd src
chmod +x wgd.sh
./wgd.sh install
```

**Apa yang terjadi saat `install` (secara garis besar)?**

- Membuat folder kerja seperti `log/`, `download/`, `db/` jika belum ada.  
- Membuat **virtual environment** Python (`venv/`) dan menginstal paket dari `requirements.txt`.  
- Membantu menginstal **WireGuard tools** jika belum ada di sistem.  
- Menyiapkan file `ssl-tls.ini` kosong jika diperlukan.

Jika ada **error**, buka **`log/install.txt`** untuk detail.

**Setelah `install` selesai tanpa error**, lanjut ke langkah berikutnya.

---

## 3. Menyalakan dashboard

Masih di folder **`src/`**:

```bash
./wgd.sh start
```

**Perintah lain yang berguna:**

| Perintah | Fungsi |
|----------|--------|
| `./wgd.sh stop` | Menghentikan dashboard. |
| `./wgd.sh restart` | Menghentikan lalu menyalakan lagi. |
| `./wgd.sh debug` | Menjalankan di foreground (cocok untuk debugging). |

**Pertama kali start**, aplikasi akan membuat atau melengkapi **`wg-dashboard.ini`** (nama bagian seperti `[Server]`, `[Account]`, dll.) dengan nilai default jika belum ada.

### Buka di browser

- Secara default dashboard mendengarkan **TCP** pada **`app_port`** di `wg-dashboard.ini` (sering **10086**).  
- Buka alamat: `http://IP-SERVER-ANDA:10086` (sesuaikan IP dan port).  
- Jika Anda memakai **Nginx + Unix socket**, ikuti **[src/implementasi-nginx-gunicorn-socket.md](src/implementasi-nginx-gunicorn-socket.md)** dan port **HTTP/HTTPS** mengikuti konfigurasi Nginx.

**Login pertama:** gunakan akun default yang dijelaskan di dokumentasi WGDashboard / template, lalu **ganti password** lewat pengaturan di dashboard.

---

## 4. Konfigurasi file

### `wg-dashboard.ini` (utama)

- **Boleh tidak diedit manual di awal** — banyak nilai diisi otomatis saat pertama kali start.  
- **Contoh lengkap** untuk referensi: **[templates/wg-dashboard.ini.template](templates/wg-dashboard.ini.template)**.  
- Untuk menyalin manual: salin template ke `src/wg-dashboard.ini` lalu sesuaikan (path WireGuard, port, timezone, mode listen `direct` vs `nginx_socket`, dll.).

### TLS / Certbot (opsional)

Hanya jika Anda memakai SSL/TLS atau Certbot sesuai fitur yang ada di proyek:

- Salin **`src/ssl-tls.ini.example`** → **`src/ssl-tls.ini`**  
- Salin **`src/certbot.ini.example`** → **`src/certbot.ini`**  
- Isi sesuai kebutuhan server Anda.

### Catatan keamanan repo

File seperti `wg-dashboard.ini` yang berisi **password** atau **data sensitif** **tidak** ikut di GitHub (diatur di **`.gitignore`**). Gunakan **template** dan **file `.example`** sebagai acuan.

### Konfigurasi di folder lain (opsional)

Jika Anda ingin **memisahkan** data dan konfigurasi dari folder `src/`, bisa memakai variabel lingkungan **`CONFIGURATION_PATH`** (penjelasan ada di **[src/install-step-by-step.md](src/install-step-by-step.md)**).

---

## 5. Opsional (lanjutan)

| Topik | Dokumen / catatan |
|--------|-------------------|
| **Nginx + socket Gunicorn** | [src/implementasi-nginx-gunicorn-socket.md](src/implementasi-nginx-gunicorn-socket.md) |
| **PostgreSQL / MySQL** | Isi bagian `[Database]` di `wg-dashboard.ini`; siapkan server DB dan user. Detail di `install-step-by-step.md`. |
| **Build ulang tampilan (Vue)** | `cd src/static/app` → `npm ci` atau `npm install` → `npm run build`. Repo ini sudah menyertakan hasil build di `src/static/dist` sehingga **tidak wajib** build untuk sekadar menjalankan dashboard. |
| **Izin `sudo` untuk deploy Nginx dari UI** | Lihat contoh [src/sudoers.wgdashboard.example](src/sudoers.wgdashboard.example) (sesuaikan user dan path). |

---

## 6. Masalah umum

| Gejala | Yang bisa dicek |
|--------|------------------|
| `install` gagal | Baca **`src/log/install.txt`**, pastikan **Python 3.10+** dan **sudo** tersedia. |
| Tidak bisa buka di browser | Cek firewall (buka port `app_port`), IP/URL yang benar, dan apakah `./wgd.sh start` sukses. |
| Ingin reset konfigurasi | **Hati-hati:** backup dulu. Sesuaikan dengan dokumentasi WGDashboard; jangan hapus file DB sembarangan jika ada data produksi. |
| `git push` ditolak | Pastikan remote SSH/HTTPS benar, token/SSH key untuk GitHub, dan Anda punya akses ke repo. |

---

## Lisensi

Mengikuti lisensi proyek hulu (**WGDashboard**; header sumber mengacu ke **Apache-2.0** dan pihak pengembang asli).

---

**Ringkas:** clone → `cd src` → `chmod +x wgd.sh` → `./wgd.sh install` → `./wgd.sh start` → buka browser → sesuaikan konfigurasi dan keamanan.  

**Detail & checklist:** [src/install-step-by-step.md](src/install-step-by-step.md).
