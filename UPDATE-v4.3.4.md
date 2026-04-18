# WGDashboard / Tunnela — catatan rilis **v4.3.4**

Dokumen ini merangkum perubahan pada tree **`dev-2026-04-11`** untuk rilis **v4.3.4**: **panel System & Server Info** (layout key–value + baris **Hostname**, **Public IP**, **Server IP**, **Uptime**), perluasan **`GET /api/systemStatus`**, locale, dan **inventaris penuh** hasil `npm run build` di `src/static/dist/WGDashboardAdmin/`.

*(Naikkan `DashboardConfig.DashboardVersion`, `src/static/app/package.json`, dan string versi UI lain jika workflow rilis Anda mewajibkan angka yang sama.)*

**Build dokumen ini:** snapshot setelah `npm run build` (2026-04-19) — hash nama file di `assets/` berubah jika Anda build ulang.

---

## 1. Ringkasan

| Area | Isi singkat |
|------|-------------|
| **Home — System & Server Info** | Grid dua kolom (label rata kanan, nilai rata kiri). Metrik CPU / Memory / Storage / Swap seperti sebelumnya. Blok server: **Hostname** → **Public IP** (nilai = `[Peers] remote_endpoint`, sama dengan *Peer Remote Endpoint* di pengaturan) → **Server IP** (IPv4 lokal dari probe rute) → **Uptime**; lalu runtime. |
| **API** | `GET /api/systemStatus` mengisi `Host.hostname` (`socket.gethostname`) dan `Host.peer_remote_endpoint` (dari konfigurasi dashboard). |
| **Lokal** | `locale_template.json`, `id-ID.json`: kunci **Hostname**, **Public IP**. |
| **Build** | `npm run build` dari `src/static/app` → `src/static/dist/WGDashboardAdmin/`. |

---

## 2. Struktur direktori (relevan)

```
dev-2026-04-11/
├── UPDATE-v4.3.4.md
└── src/
    ├── dashboard.py                    ← API systemStatus (merge field Host)
    └── static/
        ├── locales/
        │   ├── locale_template.json
        │   └── id-ID.json
        ├── dist/
        │   └── WGDashboardAdmin/       ← hasil build (§4)
        └── app/
            └── src/
                └── components/
                    └── systemStatusComponents/
                        └── systemStatusWidget.vue
```

---

## 3. Daftar file yang berubah (sumber)

### Backend

| File | Perubahan utama |
|------|------------------|
| `src/dashboard.py` | `API_SystemStatus`: memanggil `SystemStatus.toJson()`, menambah pada `Host`: `hostname`, `peer_remote_endpoint` (dari `DashboardConfig.GetConfig("Peers", "remote_endpoint")`); respons `ResponseObject(data=body)`. Import `socket`. |

### Frontend

| File | Perubahan utama |
|------|------------------|
| `src/static/app/src/components/systemStatusComponents/systemStatusWidget.vue` | Baris **Hostname** & **Public IP** (computed `hostnameDisplay`, `publicEndpointDisplay`); urutan blok server sesuai §1. |

### Lokalisasi

| File | Perubahan utama |
|------|------------------|
| `src/static/locales/locale_template.json` | Kunci **Hostname**, **Public IP** (default Inggris kosong = teks kunci / fallback). |
| `src/static/locales/id-ID.json` | Terjemahan: *Nama host*, *IP publik*. |

### Dokumentasi

| File | Perubahan utama |
|------|------------------|
| `UPDATE-v4.3.4.md` | Catatan rilis (file ini). |

### Chunk build yang langsung terkait widget system status

- `src/static/dist/WGDashboardAdmin/assets/systemStatus-CQhPTuhD.js`
- `src/static/dist/WGDashboardAdmin/assets/systemStatus-DdUpBwt2.css`

*(Jika build ulang, ganti nama file sesuai output Vite.)*

---

## 4. Daftar lengkap hasil build (`src/static/dist/WGDashboardAdmin/`)

Salin seluruh folder ke repo tujuan (path relatif dari root proyek):

```
src/static/dist/WGDashboardAdmin/index.html
src/static/dist/WGDashboardAdmin/json/manifest.json
src/static/dist/WGDashboardAdmin/assets/bootstrap-icons-BeopsB42.woff
src/static/dist/WGDashboardAdmin/assets/bootstrap-icons-mSm7cUeB.woff2
src/static/dist/WGDashboardAdmin/assets/browser-BBy5ICY5.js
src/static/dist/WGDashboardAdmin/assets/clients-BoB3INbi.css
src/static/dist/WGDashboardAdmin/assets/clients-FEXqAVPT.js
src/static/dist/WGDashboardAdmin/assets/clientsNetworkOverview-BUIJFm10.js
src/static/dist/WGDashboardAdmin/assets/clientsNetworkOverview-cPRqZxyV.css
src/static/dist/WGDashboardAdmin/assets/configuration-DE3nko4R.js
src/static/dist/WGDashboardAdmin/assets/configurationList-Dc93Dcz6.js
src/static/dist/WGDashboardAdmin/assets/configurationList-DtLs5EWV.css
src/static/dist/WGDashboardAdmin/assets/dashboardEmailSettings-CDozOzQ3.css
src/static/dist/WGDashboardAdmin/assets/dashboardEmailSettings-CP34vhZv.js
src/static/dist/WGDashboardAdmin/assets/dashboardHome-DAxlcMTJ.js
src/static/dist/WGDashboardAdmin/assets/dashboardHome-wZ30VBzL.css
src/static/dist/WGDashboardAdmin/assets/dashboardSettingsWireguardConfigurationAutostart-Byv7gw92.js
src/static/dist/WGDashboardAdmin/assets/dashboardSettingsWireguardConfigurationAutostart-D5UlSscq.css
src/static/dist/WGDashboardAdmin/assets/dashboardWebHooks-Dl-enc0Z.css
src/static/dist/WGDashboardAdmin/assets/dashboardWebHooks-P4uXigVR.js
src/static/dist/WGDashboardAdmin/assets/dayjs.min-DKix0j3G.js
src/static/dist/WGDashboardAdmin/assets/editConfiguration-EQmmV61G.css
src/static/dist/WGDashboardAdmin/assets/editConfiguration-fjS7w1tX.js
src/static/dist/WGDashboardAdmin/assets/galois-field-I2lBzzs-.js
src/static/dist/WGDashboardAdmin/assets/index-B2z7uwM3.js
src/static/dist/WGDashboardAdmin/assets/index-BtNa6MyZ.js
src/static/dist/WGDashboardAdmin/assets/index-BUTLdkoU.css
src/static/dist/WGDashboardAdmin/assets/index-Cdluc_gQ.js
src/static/dist/WGDashboardAdmin/assets/index-CffiZz1L.css
src/static/dist/WGDashboardAdmin/assets/index-D5AZF9CB.js
src/static/dist/WGDashboardAdmin/assets/index-RbMHefhQ.js
src/static/dist/WGDashboardAdmin/assets/localeText-DFOPmYSQ.js
src/static/dist/WGDashboardAdmin/assets/message-CBo0TZld.js
src/static/dist/WGDashboardAdmin/assets/message-CGSzI01q.css
src/static/dist/WGDashboardAdmin/assets/newConfiguration-B38yLLAR.css
src/static/dist/WGDashboardAdmin/assets/newConfiguration-Cy-KMxJ2.js
src/static/dist/WGDashboardAdmin/assets/osmap-CsoM1fIq.css
src/static/dist/WGDashboardAdmin/assets/osmap-CyfbkCte.js
src/static/dist/WGDashboardAdmin/assets/peerAddModal-B4gIHs91.css
src/static/dist/WGDashboardAdmin/assets/peerAddModal-Cdv9vpGA.js
src/static/dist/WGDashboardAdmin/assets/peerAssignModal--_bmFbmn.css
src/static/dist/WGDashboardAdmin/assets/peerAssignModal-CiCFAjt2.js
src/static/dist/WGDashboardAdmin/assets/peerConfigurationFile-B3WguzEi.js
src/static/dist/WGDashboardAdmin/assets/peerConfigurationFile-Dh6Sdp_z.css
src/static/dist/WGDashboardAdmin/assets/peerDefaultSettings-DB8Zwh8M.js
src/static/dist/WGDashboardAdmin/assets/peerDetailsModal-BH9MQZGS.css
src/static/dist/WGDashboardAdmin/assets/peerDetailsModal.vue_vue_type_script_setup_true_lang-u1IMfO-a.js
src/static/dist/WGDashboardAdmin/assets/peerJobsAllModal-C8izoJL_.js
src/static/dist/WGDashboardAdmin/assets/peerJobs-BOF5Trty.js
src/static/dist/WGDashboardAdmin/assets/peerJobs-D_dDl936.css
src/static/dist/WGDashboardAdmin/assets/peerJobsLogsModal-BBxqG5mm.js
src/static/dist/WGDashboardAdmin/assets/peerList-BEI5M0wb.css
src/static/dist/WGDashboardAdmin/assets/peerList-D9ekUdSz.js
src/static/dist/WGDashboardAdmin/assets/peerQRCode-BQTyLe4g.css
src/static/dist/WGDashboardAdmin/assets/peerQRCode-Dud21eDY.js
src/static/dist/WGDashboardAdmin/assets/peersDefaultSettingsInput-TJMhuQ7N.js
src/static/dist/WGDashboardAdmin/assets/peerSearchBar-B-JidFql.js
src/static/dist/WGDashboardAdmin/assets/peerSearchBar-Dtpovmxo.css
src/static/dist/WGDashboardAdmin/assets/peerSettings-EPktimtu.js
src/static/dist/WGDashboardAdmin/assets/peerSettings-uCRAwZ--.css
src/static/dist/WGDashboardAdmin/assets/peerShareLinkModal-B_XXfq86.js
src/static/dist/WGDashboardAdmin/assets/peerShareLinkModal-GoWqB_pD.css
src/static/dist/WGDashboardAdmin/assets/ping-CkYa7maj.js
src/static/dist/WGDashboardAdmin/assets/ping-DgbK5UF9.css
src/static/dist/WGDashboardAdmin/assets/protocolBadge-CphN3NXL.js
src/static/dist/WGDashboardAdmin/assets/restoreConfiguration-bRyn5AKC.js
src/static/dist/WGDashboardAdmin/assets/restoreConfiguration-CvbcHRwj.css
src/static/dist/WGDashboardAdmin/assets/schedulePeerJob-DSvEP5fX.js
src/static/dist/WGDashboardAdmin/assets/schedulePeerJob-DUtdD062.css
src/static/dist/WGDashboardAdmin/assets/selectPeersBulkRestrictModal-BeC8lmIT.js
src/static/dist/WGDashboardAdmin/assets/selectPeersBulkRestrictModal-pU0dnTRA.css
src/static/dist/WGDashboardAdmin/assets/selectPeers-CE2l08J9.css
src/static/dist/WGDashboardAdmin/assets/selectPeers-QzOjA_WV.js
src/static/dist/WGDashboardAdmin/assets/settings-Y-a0WTQv.js
src/static/dist/WGDashboardAdmin/assets/setup-nEKUyDSv.js
src/static/dist/WGDashboardAdmin/assets/share-DGWWYBqL.js
src/static/dist/WGDashboardAdmin/assets/share-e5E8P3Ro.css
src/static/dist/WGDashboardAdmin/assets/signin-Cj5jMGPN.js
src/static/dist/WGDashboardAdmin/assets/signin-Dpzb-6e5.css
src/static/dist/WGDashboardAdmin/assets/storageMount.vue_vue_type_style_index_0_scoped_9509d7a0_lang-Dw_GWfMx.js
src/static/dist/WGDashboardAdmin/assets/storageMount-wWOSNV8e.css
src/static/dist/WGDashboardAdmin/assets/systemStatus-CQhPTuhD.js
src/static/dist/WGDashboardAdmin/assets/systemStatus-DdUpBwt2.css
src/static/dist/WGDashboardAdmin/assets/totp-BfuqVr8m.js
src/static/dist/WGDashboardAdmin/assets/traceroute-B-N91oFO.js
src/static/dist/WGDashboardAdmin/assets/traceroute-D9mlT_ah.css
src/static/dist/WGDashboardAdmin/assets/Vector-5IlHN0Py.js
src/static/dist/WGDashboardAdmin/assets/Vector-BtPuoxOl.css
src/static/dist/WGDashboardAdmin/assets/vue-datepicker-D9Gbo_ii.js
src/static/dist/WGDashboardAdmin/assets/wgdashboardSettings-C8ZuJvWn.css
src/static/dist/WGDashboardAdmin/assets/wgdashboardSettings-DPjpEXDJ.js
src/static/dist/WGDashboardAdmin/assets/wireguardConfiguration-BQMRoF0f.js
src/static/dist/WGDashboardAdmin/assets/wireguardConfigurationSettings-Lgq3gLXp.js
src/static/dist/WGDashboardAdmin/assets/wireguardConfiguration-zhbrbjA7.css
src/static/dist/WGDashboardAdmin/img/Logo-1-128x128.png
src/static/dist/WGDashboardAdmin/img/Logo-1-256x256.png
src/static/dist/WGDashboardAdmin/img/Logo-1-384x384.png
src/static/dist/WGDashboardAdmin/img/Logo-1-512x512.png
src/static/dist/WGDashboardAdmin/img/Logo-1-Maskable-512x512.png
src/static/dist/WGDashboardAdmin/img/Logo-1-Rounded-128x128.png
src/static/dist/WGDashboardAdmin/img/Logo-1-Rounded-256x256.png
src/static/dist/WGDashboardAdmin/img/Logo-1-Rounded-384x384.png
src/static/dist/WGDashboardAdmin/img/Logo-1-Rounded-512x512.png
src/static/dist/WGDashboardAdmin/img/Logo-2-128x128.png
src/static/dist/WGDashboardAdmin/img/Logo-2-256x256.png
src/static/dist/WGDashboardAdmin/img/Logo-2-384x384.png
src/static/dist/WGDashboardAdmin/img/Logo-2-512x512.png
src/static/dist/WGDashboardAdmin/img/Logo-2-Rounded-128x128.png
src/static/dist/WGDashboardAdmin/img/Logo-2-Rounded-256x256.png
src/static/dist/WGDashboardAdmin/img/Logo-2-Rounded-384x384.png
src/static/dist/WGDashboardAdmin/img/Logo-2-Rounded-512x512.png
```

**Jumlah file:** 111 — `index.html`, `json/manifest.json`, **92** file di `assets/`, **17** di `img/`.

---

## 5. Deploy singkat (setelah copy ke repo)

1. Commit / salin: `src/dashboard.py`, `systemStatusWidget.vue`, `locale_template.json`, `id-ID.json`, dan seluruh `src/static/dist/WGDashboardAdmin/`.
2. Di server: dari folder `src` instalasi, `./wgd.sh restart` (atau unit systemd Anda).
3. Hard refresh browser.

---

## 6. Changelog (v4.3.4)

- **API:** Respons `GET /api/systemStatus` menyertakan `Host.hostname` dan `Host.peer_remote_endpoint` (dari `[Peers] remote_endpoint` / *Peer Remote Endpoint*).
- **UI:** Panel **System & Server Info** — layout key–value; urutan baris server: **Hostname**, **Public IP**, **Server IP**, **Uptime**; label **Public IP** menampilkan endpoint yang sama dengan pengaturan peer (bisa IP atau hostname).
- **i18n:** Kunci **Hostname**, **Public IP** (`locale_template`, `id-ID`).
