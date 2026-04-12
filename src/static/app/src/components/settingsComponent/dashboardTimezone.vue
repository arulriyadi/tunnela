<script>
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchGet, getUrl, getHeaders} from "@/utilities/fetch.js";
import {GetLocale} from "@/utilities/locale.js";
import LocaleText from "@/components/text/localeText.vue";

export default {
	name: "dashboardTimezone",
	components: {LocaleText},
	setup() {
		const store = DashboardConfigurationStore();
		return {store};
	},
	data() {
		return {
			zones: [],
			search: "",
			loading: true,
			saving: false,
			filterPh: GetLocale("Filter..."),
			/** Pending selection; synced from config until user picks another zone. */
			pendingTz: null,
			userPicked: false,
			serverInfo: {
				local_now: "",
				system_timezone: "",
			},
			serverInfoTimer: null,
		};
	},
	computed: {
		currentTz() {
			const v = this.store.Configuration?.Server?.dashboard_timezone;
			return v != null && String(v) !== "" ? String(v) : "Etc/UTC";
		},
		displayTz() {
			return this.pendingTz != null ? this.pendingTz : this.currentTz;
		},
		isDirty() {
			return this.displayTz !== this.currentTz;
		},
		filteredZones() {
			if (!this.zones.length) {
				return [];
			}
			const q = (this.search || "").trim().toLowerCase();
			if (!q) {
				return this.zones.slice(0, 200);
			}
			return this.zones.filter((z) => z.toLowerCase().includes(q)).slice(0, 400);
		},
	},
	watch: {
		currentTz() {
			if (!this.userPicked) {
				this.pendingTz = null;
			}
		},
	},
	mounted() {
		this.refreshServerInfo();
		this.serverInfoTimer = setInterval(() => {
			this.refreshServerInfo();
		}, 30000);
		fetchGet("/api/getAvailableTimezones", {}, (res) => {
			if (res.status && Array.isArray(res.data)) {
				this.zones = res.data;
			} else {
				this.zones = [];
			}
			this.loading = false;
		});
	},
	beforeUnmount() {
		if (this.serverInfoTimer) {
			clearInterval(this.serverInfoTimer);
		}
	},
	methods: {
		refreshServerInfo() {
			fetchGet("/api/getServerDateTimeInfo", {}, (res) => {
				if (res.status && res.data) {
					this.serverInfo = {
						local_now: res.data.local_now || "",
						system_timezone: res.data.system_timezone || "",
					};
				}
			});
		},
		selectTz(z) {
			this.pendingTz = z;
			this.userPicked = z !== this.currentTz;
			if (!this.userPicked) {
				this.pendingTz = null;
			}
			this.search = "";
		},
		async apply() {
			if (this.loading || this.saving) {
				return;
			}
			/* Nothing new to POST — dropdown matches Saved in WGDashboard; UI already shows "No unsaved changes." */
			if (!this.isDirty) {
				return;
			}
			this.saving = true;
			try {
				const r = await fetch(getUrl("/api/updateDashboardConfigurationItem"), {
					method: "POST",
					headers: getHeaders(),
					credentials: "same-origin",
					body: JSON.stringify({
						section: "Server",
						key: "dashboard_timezone",
						value: this.displayTz,
					}),
				});
				let res = {};
				try {
					res = await r.json();
				} catch {
					res = {};
				}
				if (r.status === 401) {
					this.store.newMessage(
						"WGDashboard",
						"Sign in session ended, please sign in again",
						"warning"
					);
					return;
				}
				if (!r.ok) {
					this.store.newMessage(
						"Server",
						res.message || r.statusText || "Request failed",
						"danger"
					);
					return;
				}
				if (res.status) {
					this.userPicked = false;
					this.pendingTz = null;
					await this.store.getConfiguration();
					this.refreshServerInfo();
					this.store.newMessage(
						"WGDashboard",
						GetLocale("Timezone saved (WGDashboard and Linux OS)"),
						"success"
					);
				} else {
					this.store.newMessage(
						"Server",
						res.message || "Timezone update failed",
						"danger"
					);
				}
			} catch (e) {
				this.store.newMessage(
					"Server",
					e?.message || "Request failed",
					"danger"
				);
			} finally {
				this.saving = false;
			}
		},
	},
};
</script>

<template>
	<div>
		<small class="text-muted d-block mb-1">
			<strong><LocaleText t="Server timezone"></LocaleText></strong>
		</small>
		<p class="small text-muted mb-2">
			<LocaleText
				t="Apply saves to WGDashboard and runs timedatectl set-timezone on the server (requires root). Used for schedule jobs and server-side date logic."
			></LocaleText>
		</p>
		<p class="small mb-2">
			<span class="text-muted"><LocaleText t="Saved in WGDashboard"></LocaleText>:</span>
			<strong class="ms-1 font-monospace">{{ currentTz }}</strong>
		</p>
		<p
			v-if="serverInfo.local_now || serverInfo.system_timezone"
			class="small mb-3 font-monospace text-body-secondary border rounded-3 px-3 py-2 bg-body-tertiary"
		>
			<i class="bi bi-hdd-network me-1"></i>
			<LocaleText t="Linux OS — local time"></LocaleText>:
			<strong class="text-body">{{ serverInfo.local_now }}</strong>
			<span class="text-muted mx-1">·</span>
			<LocaleText t="OS timezone"></LocaleText>:
			<strong class="text-body">{{ serverInfo.system_timezone }}</strong>
			<span class="d-block small text-muted mt-1 fst-normal">
				<LocaleText
					t="Live OS clock and zone (refreshed after Apply). If save fails, ensure WGDashboard runs as root or has permission to run timedatectl."
				></LocaleText>
			</span>
		</p>
		<div class="d-flex flex-wrap gap-2 align-items-stretch">
			<div class="dropdown flex-grow-1" style="min-width: 200px">
				<button
					class="btn bg-primary-subtle text-primary-emphasis dropdown-toggle w-100 rounded-3"
					type="button"
					data-bs-toggle="dropdown"
					aria-expanded="false"
					:disabled="loading"
				>
					<LocaleText t="Loading..." v-if="loading"></LocaleText>
					<span v-else class="text-truncate d-inline-block" style="max-width: 90%">{{
						displayTz
					}}</span>
				</button>
				<ul
					class="dropdown-menu rounded-3 shadow p-2 w-100"
					style="max-height: 380px; overflow-y: auto"
					@click.stop
				>
					<li class="mb-2 px-1">
						<input
							v-model="search"
							type="search"
							class="form-control form-control-sm rounded-3"
							:placeholder="filterPh"
							autocomplete="off"
							@click.stop
						/>
					</li>
					<li v-if="!search.trim() && zones.length > 200" class="px-2 small text-muted">
						<LocaleText t="Showing first 200 — type to filter the full list."></LocaleText>
					</li>
					<li v-for="z in filteredZones" :key="z">
						<button
							type="button"
							class="dropdown-item d-flex align-items-center rounded-2 py-1"
							@click="selectTz(z)"
						>
							<small class="me-auto mb-0 text-truncate">{{ z }}</small>
							<i
								v-if="displayTz === z"
								class="bi bi-check text-primary fs-5 flex-shrink-0 ms-1"
							></i>
						</button>
					</li>
				</ul>
			</div>
			<button
				type="button"
				class="btn btn-primary rounded-3 px-4 align-self-stretch"
				:disabled="loading || saving"
				:title="
					isDirty
						? ''
						: 'No unsaved changes — choose a different timezone first'
				"
				@click="apply"
			>
				<span
					v-if="saving"
					class="spinner-border spinner-border-sm me-1"
					role="status"
					aria-hidden="true"
				></span>
				<LocaleText t="Apply"></LocaleText>
			</button>
		</div>
		<p v-if="isDirty" class="small text-warning-emphasis mt-2 mb-0">
			<LocaleText t="Unsaved changes — click Apply to save."></LocaleText>
		</p>
		<p v-else-if="!loading" class="small text-muted mt-2 mb-0">
			<LocaleText t="No unsaved changes."></LocaleText>
		</p>
	</div>
</template>

<style scoped>
.dropdown-menu {
	width: 100%;
}

.dropdown-item {
	white-space: nowrap;
}
</style>
