<script>
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchPost} from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";
import {GetLocale} from "@/utilities/locale.js";

/** Preset keys are milliseconds (string), same as other Server interval settings. */
export default {
	name: "dashboardClientsStatisticsInterval",
	components: {LocaleText},
	setup() {
		const store = DashboardConfigurationStore();
		return {store};
	},
	data() {
		return {
			customMinutes: 5,
			customInvalid: "",
			presets: {
				"60000": GetLocale("1 Minutes"),
				"120000": GetLocale("2 Minutes"),
				"300000": GetLocale("5 Minutes"),
				"600000": GetLocale("10 Minutes"),
				"900000": GetLocale("15 Minutes"),
				"1800000": GetLocale("30 Minutes"),
			},
		};
	},
	computed: {
		currentMs() {
			const v = this.store.Configuration?.Server?.clients_statistics_interval;
			return v != null && String(v) !== "" ? String(v) : "300000";
		},
		currentLabel() {
			if (this.presets[this.currentMs]) {
				return this.presets[this.currentMs];
			}
			const m = Math.round(parseInt(this.currentMs, 10) / 60000);
			return `${m} min`;
		},
	},
	watch: {
		currentMs() {
			this.syncCustomMinutesFromStore();
		},
	},
	mounted() {
		this.syncCustomMinutesFromStore();
	},
	methods: {
		syncCustomMinutesFromStore() {
			const m = Math.round(parseInt(this.currentMs, 10) / 60000);
			if (!Number.isNaN(m) && m >= 1 && m <= 60) {
				this.customMinutes = m;
			}
		},
		saveMs(msStr) {
			fetchPost(
				"/api/updateDashboardConfigurationItem",
				{
					section: "Server",
					key: "clients_statistics_interval",
					value: msStr,
				},
				(res) => {
					if (res.status) {
						this.store.getConfiguration();
						this.customInvalid = "";
					} else {
						this.customInvalid = res.message || "Save failed";
					}
				}
			);
		},
		selectPreset(msKey) {
			this.saveMs(msKey);
		},
		applyCustom() {
			let n = parseInt(String(this.customMinutes), 10);
			if (Number.isNaN(n) || n < 1) {
				this.customInvalid = GetLocale("Minimum is 1 minute");
				return;
			}
			if (n > 60) {
				n = 60;
				this.customMinutes = 60;
			}
			this.saveMs(String(n * 60000));
		},
	},
};
</script>

<template>
	<div class="d-flex flex-column gap-3">
		<p class="text-muted small mb-0">
			<LocaleText
				t="How often to collect Clients overview metrics (24h retention). Separate from peer list refresh."
			></LocaleText>
		</p>
		<div class="dropdown">
			<button
				type="button"
				data-bs-toggle="dropdown"
				class="btn btn-sm text-primary-emphasis bg-primary-subtle rounded-3 border border-primary-subtle d-inline-flex align-items-center gap-2"
			>
				<i class="bi bi-clock-history"></i>
				<LocaleText t="Collection interval"></LocaleText>
				<span class="badge text-bg-primary">{{ currentLabel }}</span>
			</button>
			<ul class="dropdown-menu rounded-3">
				<li v-for="(label, msKey) in presets" :key="msKey">
					<button
						type="button"
						class="dropdown-item d-flex align-items-center"
						@click="selectPreset(msKey)"
					>
						<small>{{ label }}</small>
						<small class="ms-auto">
							<i v-if="currentMs === msKey" class="bi bi-check-circle-fill"></i>
						</small>
					</button>
				</li>
			</ul>
		</div>
		<div class="d-flex flex-wrap align-items-end gap-2">
			<div>
				<label class="form-label small mb-1">
					<LocaleText t="Custom (minutes)"></LocaleText>
					<span class="text-muted"> (1–60)</span>
				</label>
				<input
					v-model.number="customMinutes"
					type="number"
					min="1"
					max="60"
					class="form-control form-control-sm rounded-3"
					style="max-width: 120px"
					@keyup.enter="applyCustom"
				/>
			</div>
			<button
				type="button"
				class="btn btn-sm btn-outline-primary rounded-3"
				@click="applyCustom"
			>
				<LocaleText t="Apply"></LocaleText>
			</button>
		</div>
		<div v-if="customInvalid" class="small text-danger">{{ customInvalid }}</div>
	</div>
</template>

<style scoped></style>
