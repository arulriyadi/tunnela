<script>
import LocaleText from "@/components/text/localeText.vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchGet, fetchPost} from "@/utilities/fetch.js";

export default {
	name: "dashboardNginxReverseProxyCard",
	components: {LocaleText},
	setup() {
		const store = DashboardConfigurationStore();
		return {store};
	},
	data() {
		return {
			nginxInfo: null,
			loading: true,
			copyDone: false,
			copyTimer: null,
			serverName: "",
			showDeployModal: false,
			deploying: false,
			deployError: "",
			restartAfterDeploy: true,
			schedulingRestart: false,
			defaultServerForPort80: false,
			disableStockDefaultSite: true,
			diagnostics: null,
			diagnosticsLoading: false,
		};
	},
	computed: {
		listenMode() {
			const m = this.store.Configuration?.Server?.app_listen_mode;
			return (m === "nginx_socket") ? "nginx_socket" : "direct";
		},
		resolvedSocketForSnippet() {
			const s = this.store.Configuration?.Server;
			let sock = (s?.gunicorn_socket_path || "").trim();
			if (!sock) {
				return "/path/to/wgdashboard/run/gunicorn.sock";
			}
			if (sock.startsWith("/")) {
				return sock;
			}
			return sock;
		},
		socketPathLooksRelative() {
			const s = this.store.Configuration?.Server?.gunicorn_socket_path;
			if (!s) return false;
			return !String(s).trim().startsWith("/");
		},
		/** Main "Deploy" button: only needs Nginx + nginx_socket mode (server_name is set in the modal). */
		canShowDeployButton() {
			if (this.loading || !this.nginxInfo?.installed) return false;
			if (this.listenMode !== "nginx_socket") return false;
			return true;
		},
		/** Confirm inside modal — valid server_name, or default_server for port 80. */
		canConfirmDeploy() {
			if (!this.canShowDeployButton) return false;
			if (this.defaultServerForPort80) return true;
			const sn = (this.serverName || "").trim();
			if (sn.length < 1 || sn.length > 253) return false;
			return /^[a-zA-Z0-9._-]+$/.test(sn);
		},
		snippetText() {
			const sock = this.resolvedSocketForSnippet;
			const prefix = (this.store.Configuration?.Server?.app_prefix || "").trim().replace(/\/$/, "");
			const prefixNote = prefix
				? `# app_prefix in wg-dashboard.ini is "${prefix}" — you may need location ${prefix}/ and matching proxy paths.\n`
				: "";
			return (
				`${prefixNote}` +
				`# Example only. Replace server_name, add SSL if needed, then install into sites-enabled.\n` +
				`server {\n` +
				`    listen 80;\n` +
				`    server_name your-domain.example;\n\n` +
				`    location / {\n` +
				`        proxy_set_header Host $host;\n` +
				`        proxy_set_header X-Real-IP $remote_addr;\n` +
				`        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n` +
				`        proxy_set_header X-Forwarded-Proto $scheme;\n` +
				`        proxy_pass http://unix:${sock}:;\n` +
				`    }\n` +
				`}\n`
			);
		},
	},
	mounted() {
		this.loadNginxInfo();
		if (this.listenMode === "nginx_socket") {
			this.loadDiagnostics();
		}
	},
	beforeUnmount() {
		if (this.copyTimer) {
			clearTimeout(this.copyTimer);
		}
	},
	methods: {
		loadNginxInfo() {
			this.loading = true;
			fetchGet("/api/getNginxRuntimeInfo", {}, (res) => {
				this.loading = false;
				if (res.status && res.data) {
					this.nginxInfo = res.data;
				} else {
					this.nginxInfo = {
						installed: false,
						binary_path: null,
						version_line: null,
						error: null,
					};
				}
			});
		},
		recheckNginx() {
			if (this.loading) return;
			this.loadNginxInfo();
			if (this.listenMode === "nginx_socket") {
				this.loadDiagnostics();
			}
		},
		loadDiagnostics() {
			if (this.listenMode !== "nginx_socket") return;
			this.diagnosticsLoading = true;
			fetchGet("/api/getListenStackDiagnostics", {}, (res) => {
				this.diagnosticsLoading = false;
				if (res.status && res.data) {
					this.diagnostics = res.data;
				} else {
					this.diagnostics = null;
				}
			});
		},
		openDeployModal() {
			this.deployError = "";
			this.schedulingRestart = false;
			this.showDeployModal = true;
		},
		closeDeployModal() {
			if (this.deploying || this.schedulingRestart) return;
			this.showDeployModal = false;
		},
		afterDeploySuccess(res) {
			const msg = res.message || "";
			if (msg) {
				this.store.newMessage("WGDashboard", msg, "success");
			} else if (res.data?.reload === "ok") {
				this.store.newMessage(
					"WGDashboard",
					"Nginx config deployed and reloaded.",
					"success",
				);
			} else {
				this.store.newMessage("WGDashboard", "Nginx config written.", "success");
			}
			this.showDeployModal = false;
			this.loadDiagnostics();
			if (!this.restartAfterDeploy) {
				return;
			}
			this.schedulingRestart = true;
			fetchPost("/api/restartWgDashboardService", {delay_seconds: 2}, (r2) => {
				this.schedulingRestart = false;
				if (r2.status) {
					const m2 = r2.message || "";
					if (m2) {
						this.store.newMessage("WGDashboard", m2, "success");
					}
					return;
				}
				this.store.newMessage(
					"WGDashboard",
					r2.message || "Restart could not be scheduled.",
					"warning",
				);
			});
		},
		runDeploy() {
			if (!this.canConfirmDeploy || this.deploying || this.schedulingRestart) return;
			this.deploying = true;
			this.deployError = "";
			const sn = (this.serverName || "").trim();
			fetchPost(
				"/api/deployWgDashboardNginx",
				{
					server_name: sn,
					default_server: this.defaultServerForPort80,
					disable_stock_default_site: this.disableStockDefaultSite,
				},
				(res) => {
					this.deploying = false;
					if (res.status) {
						this.afterDeploySuccess(res);
						return;
					}
					this.deployError = res.message || "Deploy failed.";
				},
			);
		},
		async copySnippet() {
			try {
				await navigator.clipboard.writeText(this.snippetText);
				this.copyDone = true;
				if (this.copyTimer) {
					clearTimeout(this.copyTimer);
				}
				this.copyTimer = setTimeout(() => {
					this.copyDone = false;
				}, 2500);
			} catch (e) {
				this.store.newMessage("WGDashboard", "Could not copy to clipboard", "warning");
			}
		},
	},
};
</script>

<template>
	<div class="card rounded-3">
		<div class="card-header">
			<h6 class="my-2">
				<i class="bi bi-diagram-3 me-2"></i>
				<LocaleText t="Nginx reverse proxy (example)"></LocaleText>
			</h6>
		</div>
		<div class="card-body">
			<div class="mb-3">
				<div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-1">
					<strong><small class="text-muted">
						<LocaleText t="Nginx on this server"></LocaleText>
					</small></strong>
					<button
						type="button"
						class="btn btn-outline-secondary btn-sm"
						:disabled="loading"
						@click="recheckNginx"
					>
						<span v-if="loading" class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
						<i v-else class="bi bi-arrow-clockwise me-1"></i>
						<LocaleText t="Recheck"></LocaleText>
					</button>
				</div>
				<div v-if="loading" class="small text-muted mt-1">
					<LocaleText t="Checking..."></LocaleText>
				</div>
				<div v-else-if="nginxInfo && nginxInfo.installed" class="mt-1">
					<div class="d-flex flex-wrap align-items-start gap-2">
						<i class="bi bi-check-circle-fill text-success fs-5" title="" aria-hidden="true"></i>
						<div>
							<span class="badge text-bg-success me-2">
								<LocaleText t="Detected"></LocaleText>
							</span>
							<span class="small text-muted text-break" v-if="nginxInfo.version_line">{{ nginxInfo.version_line }}</span>
							<span class="small text-muted d-block text-break" v-if="nginxInfo.binary_path">{{ nginxInfo.binary_path }}</span>
							<span class="small text-warning d-block" v-if="nginxInfo.error">{{ nginxInfo.error }}</span>
						</div>
					</div>
				</div>
				<div v-else class="mt-1">
					<div class="d-flex flex-wrap align-items-start gap-2 mb-1">
						<i class="bi bi-x-circle text-secondary fs-5" aria-hidden="true"></i>
						<div>
							<span class="badge text-bg-secondary me-2">
								<LocaleText t="Not found"></LocaleText>
							</span>
							<span class="small text-muted">
								<LocaleText t="Install Nginx on the host, or ensure the binary is under PATH or a common path (/usr/sbin/nginx)."></LocaleText>
							</span>
						</div>
					</div>
					<p class="small text-muted mb-0 ps-1">
						<LocaleText t="After installing Nginx, click Recheck."></LocaleText>
					</p>
				</div>
			</div>
			<p class="small text-muted mb-2">
				<LocaleText t="Snippet for proxying to the Gunicorn Unix socket (nginx_socket listen mode). Deploy writes to /etc/nginx when you use Deploy below."></LocaleText>
			</p>
			<p v-if="socketPathLooksRelative" class="small text-warning mb-2">
				<LocaleText t="Relative socket paths are resolved on the server from CONFIGURATION_PATH; absolute paths are clearer. Deploy does not restart WGDashboard."></LocaleText>
			</p>
			<pre
				class="bg-body-secondary border rounded p-2 small mb-2"
				style="max-height: 320px; overflow: auto; white-space: pre-wrap; word-break: break-word;"
			><code>{{ snippetText }}</code></pre>
			<div class="d-flex flex-wrap gap-2 align-items-center">
				<button
					type="button"
					class="btn btn-outline-primary btn-sm"
					@click="copySnippet"
				>
					<i class="bi bi-clipboard me-1"></i>
					<LocaleText t="Copy snippet"></LocaleText>
					<span v-if="copyDone" class="ms-2 text-success">
						<LocaleText t="Copied"></LocaleText>
					</span>
				</button>
				<button
					type="button"
					class="btn btn-primary btn-sm"
					:disabled="!canShowDeployButton"
					@click="openDeployModal"
				>
					<i class="bi bi-cloud-upload me-1"></i>
					<LocaleText t="Deploy to nginx"></LocaleText>
				</button>
				<button
					v-if="listenMode === 'nginx_socket'"
					type="button"
					class="btn btn-outline-secondary btn-sm"
					:disabled="diagnosticsLoading"
					@click="loadDiagnostics"
				>
					<span v-if="diagnosticsLoading" class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
					<i v-else class="bi bi-activity me-1"></i>
					<LocaleText t="Run listen stack diagnostics"></LocaleText>
				</button>
			</div>
			<div v-if="listenMode === 'nginx_socket'" class="mt-3">
				<strong class="small text-muted d-block mb-1">
					<LocaleText t="Listen stack diagnostics (socket, curl, Nginx)"></LocaleText>
				</strong>
				<p class="small text-muted mb-1">
					<LocaleText t="curl HTTP code via Unix socket should be 200, 302, or 401 if Gunicorn is up. If stock default sites exist, deploy with “Remove Nginx default site” checked."></LocaleText>
				</p>
				<pre
					v-if="diagnostics"
					class="bg-body-secondary border rounded p-2 small mb-0"
					style="max-height: 280px; overflow: auto; white-space: pre-wrap; word-break: break-word;"
				><code>{{ JSON.stringify(diagnostics, null, 2) }}</code></pre>
				<p v-else-if="!diagnosticsLoading" class="small text-muted mb-0">
					<LocaleText t="Click Run listen stack diagnostics."></LocaleText>
				</p>
			</div>
			<p v-if="listenMode !== 'nginx_socket'" class="small text-muted mt-2 mb-0">
				<LocaleText t="Switch listen mode to Behind Nginx (Unix socket) to enable Deploy."></LocaleText>
			</p>
		</div>

		<div
			v-if="showDeployModal"
			class="modal fade show d-block"
			tabindex="-1"
			style="background: rgba(0,0,0,0.45);"
			role="dialog"
			aria-modal="true"
		>
			<div class="modal-dialog modal-dialog-centered">
				<div class="modal-content">
					<div class="modal-header">
						<h6 class="modal-title">
							<LocaleText t="Deploy to nginx"></LocaleText>
						</h6>
						<button type="button" class="btn-close" aria-label="Close" :disabled="deploying" @click="closeDeployModal"></button>
					</div>
					<div class="modal-body">
						<p class="small text-muted">
							<LocaleText t="Writes /etc/nginx/sites-available/wgdashboard.conf (or conf.d on some distros), runs nginx -t, then reloads. Requires root (typical: sudo ./wgd.sh start)."></LocaleText>
						</p>
						<div class="form-check mb-2">
							<input
								id="chk_nginx_default_server"
								v-model="defaultServerForPort80"
								class="form-check-input"
								type="checkbox"
								:disabled="deploying || schedulingRestart"
							>
							<label class="form-check-label small" for="chk_nginx_default_server">
								<LocaleText t="Default site on port 80 (for access by IP — use if you still see the Welcome to nginx page)"></LocaleText>
							</label>
						</div>
						<p v-if="defaultServerForPort80" class="small text-warning mb-2">
							<LocaleText t="If nginx -t fails with duplicate default_server, disable the stock site: sudo rm /etc/nginx/sites-enabled/default (then nginx -t && reload)."></LocaleText>
						</p>
						<div class="mb-2">
							<label class="form-label small" for="inp_nginx_server_name">
								<LocaleText t="server_name (hostname for this site)"></LocaleText>
							</label>
							<input
								id="inp_nginx_server_name"
								v-model="serverName"
								type="text"
								class="form-control form-control-sm"
								placeholder="dashboard.example.com"
								:disabled="deploying || defaultServerForPort80"
								autocomplete="off"
								spellcheck="false"
							>
							<p v-if="!defaultServerForPort80" class="small text-muted mb-0 mt-1">
								<LocaleText t="Tip: for http://YOUR_IP/ only, either enable “Default site on port 80” above or set server_name to that IP (e.g. 172.32.1.226)."></LocaleText>
							</p>
						</div>
						<div class="form-check mb-2">
							<input
								id="chk_disable_stock_default"
								v-model="disableStockDefaultSite"
								class="form-check-input"
								type="checkbox"
								:disabled="deploying || schedulingRestart"
							>
							<label class="form-check-label small" for="chk_disable_stock_default">
								<LocaleText t="Remove Nginx stock default site (sites-enabled/default) so port 80 uses the proxy"></LocaleText>
							</label>
						</div>
						<div class="form-check mb-2">
							<input
								id="chk_restart_after_deploy"
								v-model="restartAfterDeploy"
								class="form-check-input"
								type="checkbox"
								:disabled="deploying || schedulingRestart"
							>
							<label class="form-check-label small" for="chk_restart_after_deploy">
								<LocaleText t="Restart WGDashboard after successful deploy (applies listen settings)"></LocaleText>
							</label>
						</div>
						<div v-if="deployError" class="alert alert-danger small py-2 mb-0">{{ deployError }}</div>
					</div>
					<div class="modal-footer">
						<button type="button" class="btn btn-secondary btn-sm" :disabled="deploying || schedulingRestart" @click="closeDeployModal">
							<LocaleText t="Cancel"></LocaleText>
						</button>
						<button type="button" class="btn btn-primary btn-sm" :disabled="!canConfirmDeploy || deploying || schedulingRestart" @click="runDeploy">
							<span v-if="deploying || schedulingRestart" class="spinner-border spinner-border-sm me-1" role="status"></span>
							<LocaleText t="Deploy"></LocaleText>
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
</style>
