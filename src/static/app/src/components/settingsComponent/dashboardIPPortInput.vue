<script>
import LocaleText from "@/components/text/localeText.vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchPost} from "@/utilities/fetch.js";
import {GetLocale} from "@/utilities/locale.js";

export default {
	name: "dashboardIPPortInput" ,
	components: {LocaleText},
	setup(){
		const store = DashboardConfigurationStore();
		return {store};
	},
	computed: {
		labelListenDirect() {
			return GetLocale("Gunicorn TCP (direct)");
		},
		labelListenNginxSocket() {
			return GetLocale("Behind Nginx (Unix socket)");
		},
	},
	data(){
		return{
			listenMode: "direct",
			socketPath: "",
			ipAddress:"",
			port: 0,
			systemdUnit: "",
			systemdUnitChanged: false,
			invalidFeedback: "",
			showInvalidFeedback: false,
			isValid: false,
			timeout: undefined,
			changed: false,
			socketPathChanged: false,
			updating: false,
			showRestartModal: false,
			restarting: false,
		}
	},
	mounted() {
		const s = this.store.Configuration?.Server;
		if (!s) return;
		this.listenMode = s.app_listen_mode === "nginx_socket" ? "nginx_socket" : "direct";
		this.socketPath = s.gunicorn_socket_path ?? "";
		this.ipAddress = s.app_ip ?? "";
		this.port = s.app_port ?? 0;
		this.systemdUnit = s.systemd_unit != null ? String(s.systemd_unit) : "";
	},
	methods: {
		async persistServerKey(targetData, value, el) {
			this.updating = true;
			await fetchPost("/api/updateDashboardConfigurationItem", {
				section: "Server",
				key: targetData,
				value: value
			}, (res) => {
				if (res.status){
					if (el) {
						el.classList.add("is-valid");
						clearTimeout(this.timeout);
						this.timeout = setTimeout(() => {
							el.classList.remove("is-valid");
						}, 5000);
					}
					this.showInvalidFeedback = false;
					this.store.Configuration.Server[targetData] = value;
				}else{
					this.isValid = false;
					this.showInvalidFeedback = true;
					this.invalidFeedback = res.message;
				}
				this.updating = false;
			});
		},
		async useValidation(e, targetData, value){
			if (this.changed){
				this.changed = false;
				await this.persistServerKey(targetData, value, e.target);
			}
		},
		async onListenModeChange() {
			const next = this.listenMode;
			const prev = this.store.Configuration.Server.app_listen_mode === "nginx_socket" ? "nginx_socket" : "direct";
			if (next === prev) return;
			this.updating = true;
			this.showInvalidFeedback = false;
			await fetchPost("/api/updateDashboardConfigurationItem", {
				section: "Server",
				key: "app_listen_mode",
				value: next
			}, (res) => {
				if (res.status) {
					this.store.Configuration.Server.app_listen_mode = next;
				} else {
					this.listenMode = prev;
					this.showInvalidFeedback = true;
					this.invalidFeedback = res.message;
				}
				this.updating = false;
			});
		},
		async onSocketPathBlur(e) {
			if (!this.socketPathChanged) return;
			this.socketPathChanged = false;
			await this.persistServerKey("gunicorn_socket_path", this.socketPath, e.target);
		},
		async onSystemdUnitBlur(e) {
			if (!this.systemdUnitChanged) return;
			this.systemdUnitChanged = false;
			await this.persistServerKey("systemd_unit", this.systemdUnit, e.target);
		},
		openRestartModal() {
			this.showRestartModal = true;
		},
		closeRestartModal() {
			if (this.restarting) return;
			this.showRestartModal = false;
		},
		runRestart() {
			if (this.restarting) return;
			this.restarting = true;
			fetchPost("/api/restartWgDashboardService", {delay_seconds: 2}, (res) => {
				this.restarting = false;
				if (res.status) {
					const msg = res.message || "";
					if (msg) {
						this.store.newMessage("WGDashboard", msg, "success");
					} else {
						this.store.newMessage("WGDashboard", "Restart scheduled.", "success");
					}
					this.showRestartModal = false;
					return;
				}
				this.store.newMessage("WGDashboard", res.message || "Restart failed.", "warning");
			});
		},
	}
}
</script>

<template>
<div>
	<div class="form-group mb-3">
		<label for="select_listen_mode" class="text-muted mb-1">
			<strong><small>
				<LocaleText t="Listen mode"></LocaleText>
			</small></strong>
		</label>
		<select
			id="select_listen_mode"
			class="form-select"
			v-model="this.listenMode"
			@change="onListenModeChange"
			:disabled="this.updating"
		>
			<option value="direct">{{ labelListenDirect }}</option>
			<option value="nginx_socket">{{ labelListenNginxSocket }}</option>
		</select>
	</div>

	<div
		v-if="listenMode === 'nginx_socket'"
		class="px-2 py-2 text-warning-emphasis bg-warning-subtle border border-warning-subtle rounded-2 mb-3"
	>
		<small><i class="bi bi-exclamation-triangle-fill me-2"></i>
			<LocaleText t="After switching to Unix socket, configure and start Nginx before restarting WGDashboard, or you may lose web access. Keep SSH available to edit wg-dashboard.ini and set listen mode back to direct if needed."></LocaleText>
		</small>
	</div>

	<div
		v-if="listenMode === 'nginx_socket'"
		class="px-2 py-2 text-info-emphasis bg-info-subtle border border-info-subtle rounded-2 mb-3"
	>
		<small><i class="bi bi-info-circle me-2"></i>
			<LocaleText t="No TCP fallback: Gunicorn does not listen on app_ip:app_port in this mode. Use Nginx (e.g. http://server/ on port 80), not :10086. To use TCP again, switch listen mode back to Gunicorn TCP (direct)."></LocaleText>
		</small>
	</div>

	<div class="row g-2" v-if="listenMode === 'direct'">
		<div class="col-sm">
			<div class="form-group">
				<label for="input_dashboard_ip" class="text-muted mb-1">
					<strong><small>
						<LocaleText t="IP Address / Hostname"></LocaleText>
					</small></strong>
				</label>
				<input type="text" class="form-control"
				       :class="{'is-invalid': showInvalidFeedback, 'is-valid': isValid}"
				       id="input_dashboard_ip"
				       v-model="this.ipAddress"
				       @keydown="this.changed = true"
				       @blur="useValidation($event, 'app_ip', this.ipAddress)"
				       :disabled="this.updating"
				>
				<div class="invalid-feedback">{{this.invalidFeedback}}</div>
			</div>
		</div>
		<div class="col-sm">
			<div class="form-group">
				<label for="input_dashboard_port" class="text-muted mb-1">
					<strong><small>
						<LocaleText t="Listen Port"></LocaleText>
					</small></strong>
				</label>
				<input type="number" class="form-control"
				       :class="{'is-invalid': showInvalidFeedback, 'is-valid': isValid}"
				       id="input_dashboard_port"
				       v-model="this.port"
				       @keydown="this.changed = true"
				       @blur="useValidation($event, 'app_port', this.port)"
				       :disabled="this.updating"
				>
				<div class="invalid-feedback">{{this.invalidFeedback}}</div>
			</div>
		</div>
	</div>

	<div v-else class="form-group mb-2">
		<label for="input_gunicorn_socket_path" class="text-muted mb-1">
			<strong><small>
				<LocaleText t="Unix socket path"></LocaleText>
			</small></strong>
		</label>
		<input
			type="text"
			class="form-control"
			:class="{'is-invalid': showInvalidFeedback, 'is-valid': isValid}"
			id="input_gunicorn_socket_path"
			v-model="this.socketPath"
			@keydown="this.socketPathChanged = true"
			@blur="onSocketPathBlur"
			:disabled="this.updating"
			autocomplete="off"
			spellcheck="false"
		>
		<div class="invalid-feedback">{{this.invalidFeedback}}</div>
		<small class="text-muted d-block mt-1">
			<LocaleText t="Must be an absolute path (e.g. /opt/wgdashboard/src/run/gunicorn.sock). IP and port are not used in this mode."></LocaleText>
		</small>
	</div>

	<div class="form-group mb-3">
		<label for="input_systemd_unit" class="text-muted mb-1">
			<strong><small>
				<LocaleText t="Systemd unit (optional)"></LocaleText>
			</small></strong>
		</label>
		<input
			type="text"
			class="form-control"
			id="input_systemd_unit"
			v-model="this.systemdUnit"
			@keydown="this.systemdUnitChanged = true"
			@blur="onSystemdUnitBlur"
			:disabled="this.updating"
			placeholder="wgdashboard"
			autocomplete="off"
			spellcheck="false"
		>
		<small class="text-muted d-block mt-1">
			<LocaleText t="Leave empty to restart via wgd.sh. Set if WGDashboard is managed by systemd, or set env WGDASHBOARD_SYSTEMD_UNIT on the server."></LocaleText>
		</small>
	</div>

	<div
		class="px-2 py-1 text-warning-emphasis bg-warning-subtle border border-warning-subtle rounded-2 d-inline-block mb-2 mt-2">
		<small><i class="bi bi-exclamation-triangle-fill me-2"></i>
			<LocaleText t="Manual restart of WGDashboard is needed to apply listen mode, IP, port, or socket path changes"></LocaleText>
		</small>
	</div>

	<div class="d-flex flex-wrap align-items-center gap-2 mb-1">
		<button
			type="button"
			class="btn btn-outline-primary btn-sm"
			:disabled="updating || restarting"
			@click="openRestartModal"
		>
			<span v-if="restarting" class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
			<i v-else class="bi bi-arrow-repeat me-1"></i>
			<LocaleText t="Restart WGDashboard now"></LocaleText>
		</button>
	</div>
	<p class="small text-muted mb-0">
		<LocaleText t="Applies saved listen settings by restarting the dashboard process. You may need to refresh the browser."></LocaleText>
	</p>

	<div
		v-if="showRestartModal"
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
						<LocaleText t="Restart WGDashboard"></LocaleText>
					</h6>
					<button type="button" class="btn-close" aria-label="Close" :disabled="restarting" @click="closeRestartModal"></button>
				</div>
				<div class="modal-body">
					<p class="small text-muted mb-0">
						<LocaleText t="This will restart the WGDashboard process. Your session may be interrupted; refresh the page after a few seconds."></LocaleText>
					</p>
				</div>
				<div class="modal-footer">
					<button type="button" class="btn btn-secondary btn-sm" :disabled="restarting" @click="closeRestartModal">
						<LocaleText t="Cancel"></LocaleText>
					</button>
					<button type="button" class="btn btn-primary btn-sm" :disabled="restarting" @click="runRestart">
						<span v-if="restarting" class="spinner-border spinner-border-sm me-1" role="status"></span>
						<LocaleText t="Restart"></LocaleText>
					</button>
				</div>
			</div>
		</div>
	</div>
</div>
</template>

<style scoped>

</style>
