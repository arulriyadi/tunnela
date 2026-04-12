# Implementasi bulk expiry → restrict (Client List / Select Peers)

## Status

- **Fase 0 (verifikasi kontrak):** selesai di sisi **analisis kode** — lihat [Fase 0 — Hasil verifikasi](#fase-0--hasil-verifikasi). **Uji manual di browser** (satu job Date → restrict) tetap disarankan.
- **Fase 1 (UI + alur modal):** selesai — `selectPeers.vue` + `selectPeersBulkRestrictModal.vue` + `clients.vue`.
- **Fase 2 (bulk Set / `savePeerScheduleJob`):** selesai — loop per peer, template `date` / `lgt` / `restrict`, refresh Clients.
- **Fase 3 (bulk Remove / `deletePeerScheduleJob`):** selesai — heuristik `date` + `lgt` + `restrict`, hapus per job (multi-job per peer), checkbox konfirmasi + ringkasan.
- **Fase 4 (bulk Change / `savePeerScheduleJob` update):** selesai — `JobID` tetap, `Value` baru per job cocok; ringkasan skipped jika peer tanpa job.
- **Fase 5 (polish):** selesai — string di `locale_template.json` + terjemahan `id-ID.json`; tombol dinamis lewat `GetLocale`; mode **Set**: checkbox **Replace existing date-restrict jobs** (hapus job `date`/`lgt`/`restrict` lalu tambah job baru); tooltip tombol kalender di Select Peers. Uji manual lintas interface + checklist merge tetap disarankan.

---

## Tujuan produk

- Kebutuhan utama: **setelah tanggal/waktu tertentu, peer otomatis di-restrict** (bukan form job generik untuk user).
- **Bulk**: operasi yang sama untuk **banyak peer sekaligus**, lintas interface (**wg0**, **wg1**, …).
- **Titik masuk**: hanya dari **popup Select Peers** (bukan tombol baru di toolbar halaman Client).

---

## Alur UX (yang disepakati)

1. User buka **Select Peers** dari halaman **Client List Management**.
2. User mencentang peer (mis. a, b, c).
3. User klik tombol di **footer** modal (sejajar unduh / hapus), mis. **“Restrict after…”** / **“Bulk expiry”**.
4. **Modal Select Peers ditutup**; aplikasi tetap menyimpan daftar **peer terpilih** (id + `configuration` per peer).
5. Muncul **modal kedua** — judul mis. **“Restrict peers after date”**:
   - Ringkasan: *N peers selected* (opsional pecah per `wg`).
   - **Mode** (tab / segmented): **Set** | **Change** | **Remove**
 - **Set / Change**: satu **datetime picker** (satu nilai untuk semua target yang relevan).
   - **Remove**: konfirmasi hapus jadwal restrict-otomatis (bukan langsung restrict manual dari UI ini).
   - Footer: **Cancel** + **Apply** / **Remove from N peers**.
6. Saat proses: loading + opsional progress; selesai: toast / ringkasan sukses-gagal; tutup modal.

**Active Jobs** tetap untuk **overview + log**; bukan tempat utama aksi bulk ini.

---

## Kontrak teknis (tanpa API baru untuk MVP)

Backend sudah punya:

- `POST /api/savePeerScheduleJob` — body `{ Job: { JobID, Configuration, Peer, Field, Operator, Value, CreationDate, ExpireDate, Action } }`
- `POST /api/deletePeerScheduleJob` — body `{ Job: { … } }` (per job)

**Template job “restrict setelah tanggal sistem”** (selaras dengan dropdown di `WireguardConfigurationsStore` → `PeerScheduleJobs`):

| Properti   | Nilai        | Keterangan |
|-----------|--------------|------------|
| `Field`   | `date`       | Tipe “Date” di store |
| `Operator`| `lgt`        | “larger than” — saat **tanggal (now) > Value**, aksi jalan (sesuai evaluator job di server) |
| `Action`  | `restrict`   | Restrict Peer |
| `Value`   | string       | Format seperti UI job: `YYYY-MM-DD HH:mm:ss` (lihat `schedulePeerJob.vue` + `dayjs`) |
| `JobID`   | UUID baru    | Satu UUID per job per peer (`v4` seperti `peerJobs.vue`) |
| `Configuration` | nama wg | Dari `peer.configuration.Name` |
| `Peer`    | public key   | `peer.id` |
| `CreationDate` / `ExpireDate` | dikirim sesuai pola simpan job yang sudah ada | Cek payload job yang sudah tersimpan dari UI satu-peer |

**Identifikasi job “tipe bulk expiry”** untuk mode **Change** / **Remove** (heuristik di frontend):

- `Field === 'date' && Operator === 'lgt' && Action === 'restrict'`

Jika satu peer punya **lebih dari satu** job yang cocok, perlu kebijakan: ubah/hapus **semua** yang cocok, atau **hanya yang terbaru** — catat di implementasi (disarankan: **satu job aktif** per peer untuk tipe ini; jika banyak, hapus/merge sesuai produk).

**Data `jobs` per peer di halaman Clients:**

- Pastikan objek peer yang dipakai untuk bulk punya **`jobs`** terisi (dari `getWireguardConfigurationInfo`). Jika modal dibuka dari Select Peers tanpa refresh, pertimbangkan **fetch ringkas** atau pakai data dari `sections` terakhir; jika kosong, mode Change/Remove bisa menampilkan *skipped* atau memaksa refresh.

---

## File / komponen terkait (referensi)

| Area | File |
|------|------|
| Modal pilih peer + unduh/hapus | `static/app/src/components/configurationComponents/selectPeers.vue` |
| Job satu peer | `static/app/src/components/configurationComponents/peerJobs.vue`, `peerScheduleJobsComponents/schedulePeerJob.vue` |
| Dropdown field/operator/action | `static/app/src/stores/WireguardConfigurationsStore.js` (`PeerScheduleJobs`) |
| Halaman Client | `static/app/src/views/clients.vue` (pass `configurationPeers`, refresh `loadAll`) |
| API | `dashboard.py` — `API_savePeerScheduleJob`, `API_deletePeerScheduleJob` |

---

## Fase 0 — Hasil verifikasi

### Semantika scheduler (backend)

Dari `PeerJobs.runJob()` + `__runJob_Compare()`:

- Untuk `Field === "date"`: `x = datetime.now()`, `y = datetime.strptime(job.Value, "%Y-%m-%d %H:%M:%S")`.
- Untuk `Operator === "lgt"`: aksi jalan jika **`x > y`** → **waktu sekarang sudah melewati** nilai `Value` (strict `>`, bukan `>=`).
- Jika kondisi terpenuhi dan `Action === "restrict"`: dipanggil `configuration.restrictPeers([peer.id])`, lalu job di-**soft-delete** (`deleteJob` → `ExpireDate` diisi).

Jadi template bulk: **`Field: "date"`**, **`Operator: "lgt"`**, **`Action: "restrict"`**, **`Value: "YYYY-MM-DD HH:mm:ss"`** (sama format seperti `schedulePeerJob.vue` / `dayjs`).

### Payload API `POST .../api/savePeerScheduleJob`

Body: `{ "Job": { ... } }`. Kunci wajib: `JobID`, `Configuration`, `Peer`, `Field`, `Operator`, `Value`, `Action`.`CreationDate` / `ExpireDate` ikut dikirim dari UI; **untuk insert baru**, `PeerJobs.saveJob()` memakai **`datetime.now()`** untuk `CreationDate` di DB dan **`ExpireDate: null`** (mengabaikan string kosong dari klien).

**Contoh isi `Job` (job baru — selaras dengan pola UI setelah user pilih Date):**

```json
{
  "JobID": "<uuid-v4>",
  "Configuration": "wg0",
  "Peer": "<public-key>",
  "Field": "date",
  "Operator": "lgt",
  "Value": "2026-12-31 23:59:00",
  "CreationDate": "",
  "ExpireDate": "",
  "Action": "restrict"
}
```

**Update job (mode Change):** `JobID` tetap; kirim `Field` / `Operator` / `Value` / `Action` baru; `CreationDate`/`ExpireDate` bisa disalin dari objek job yang sudah dimuat dari API agar konstruktor `PeerJob` di server konsisten (atau diselaraskan dengan perilaku API saat ini).

**Delete:** `POST .../api/deletePeerScheduleJob` dengan objek `Job` yang memuat **`JobID`** (dan field lain seperti UI); backend men-set **`ExpireDate`** pada baris job (bukan hard delete).

### Catatan UI “Add Job” saat ini

Di `peerJobs.vue`, job baru default memakai **`Field` pertama di store = `total_receive`**, bukan `date`. Untuk **uji manual Fase 0** di browser: buka Schedule Jobs satu peer → **ubah dropdown ke “Date”** → pilih tanggal → simpan — itu yang meniru bulk nanti.

### Checklist uji manual (opsional tapi bagus)

1. Satu peer non-restrict → buat job Date / larger than / Restrict / `Value` beberapa menit ke depan.
2. Pastikan job tampil di **Active Jobs** / daftar job peer.
3. Tunggu lewat `Value` (atau sesuaikan jam server); pastikan peer **restrict** (atau cek log job).
4. Di DevTools → Network, simpan request **`savePeerScheduleJob`** sebagai referensi byte-per-byte.

### Basis data — tabel **`PeerJobs`** (engine `wgdashboard_job` / connection di config): kolom termasuk `JobID`, `Configuration`, `Peer`, `Field`, `Operator`, `Value`, `CreationDate`, `ExpireDate`, `Action`. Job “aktif” di-load dengan **`ExpireDate IS NULL`** (`__getJobs`).

---

## Urutan implementasi (dimulai dari mana)

Rekomendasi **dari tipis ke tebal** agar bisa diuji end-to-end lebih cepat:

### Fase 0 — Verifikasi cepat

- **Kode:** selesai — lihat bagian [Fase 0 — Hasil verifikasi](#fase-0--hasil-verifikasi).
- **Manual:** jalankan checklist uji di browser + Network tab bila perlu bukti runtime di lingkungan kamu.

### Fase 1 — Kerangka UI + alur tutup/buka modal

- Tombol baru di **footer** `selectPeers.vue` (hanya jika `selectedPeers.length > 0` dan **hanya untuk konteks Clients** — opsi prop `showBulkRestrict?: boolean` dari `clients.vue` agar peer list satu-interface tidak menampilkan tombol ini kecuali disengaja).
- Klik → `emit('bulkRestrict', { peerIds, peers })` atau simpan snapshot peer terpilih; parent (`clients.vue`) **tutup** Select Peers, buka komponen modal baru mis. `selectPeersBulkRestrictModal.vue`.
- Modal baru: judul + tab **Set** saja + datetime + **Cancel** / **Apply** (belum panggil API sungguhan atau mock).

### Fase 2 — Mode **Set** (bulk add) sungguhan

- Untuk tiap peer terpilih: bangun objek `Job` dengan template di atas, `JobID` baru, `Value` dari datetime.
- Loop `fetchPost('/api/savePeerScheduleJob', { Job })` (urut atau batch terbatas); agregasi pesan sukses/gagal.
- `emit('refresh')` / `loadAll()` di Clients.

### Fase 3 — Mode **Remove**

- Untuk tiap peer: cari job yang cocok heuristik; untuk tiap job → `deletePeerScheduleJob`.
- Konfirmasi UI sebelum eksekusi.

### Fase 4 — Mode **Change**

- Untuk tiap peer dengan tepat satu job cocok: **update** `Value` (dan field lain jika perlu) + `savePeerScheduleJob` dengan **JobID yang sama** (backend `saveJob` sudah support update by `JobID`).
- Peer tanpa job cocok → laporkan di ringkasan *skipped*.

### Fase 5 — Polish

- i18n (`LocaleText`) untuk label Indonesia/Inggris.
- Opsional: checkbox **“Replace existing date-restrict jobs”** di mode Set.
- Uji lintas **wg0 + wg1** dalam satu seleksi.

---

## Risiko / catatan

- **Multi-worker Gunicorn** + scheduler job: tidak spesifik fitur ini; ikut perilaku existing PeerJobs.
- **Heuristik** `date` + `lgt` + `restrict`: jika produk nanti menambah variasi job, pertimbangkan flag eksplisit atau tipe job di DB (fase berikutnya).

---

## Checklist sebelum merge

- [ ] Bulk Set menguji minimal 2 peer di2 interface berbeda.
- [ ] Remove tidak menghapus job non-expiry-restrict.
- [ ] Change mempertahankan `JobID` (bukan membuat duplikat).
- [ ] Tombol bulk tidak muncul di konteks yang tidak diinginkan (jika dibatasi ke Clients saja).
- [ ] `npm run build` + smoke test manual.
