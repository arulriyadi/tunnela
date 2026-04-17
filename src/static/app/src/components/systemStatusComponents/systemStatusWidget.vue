<script setup>
import {computed, onBeforeUnmount, onMounted, ref} from "vue";
import {Line} from "vue-chartjs";
import {
	Chart,
	LineElement,
	LineController,
	LinearScale,
	Legend,
	Tooltip,
	CategoryScale,
	PointElement,
	Filler,
} from "chart.js";
import dayjs from "dayjs";
import {fetchGet} from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";
import CpuCore from "@/components/systemStatusComponents/cpuCore.vue";
import StorageMount from "@/components/systemStatusComponents/storageMount.vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {GetLocale} from "@/utilities/locale.js";

Chart.register(
	LineElement,
	LineController,
	LinearScale,
	Legend,
	Tooltip,
	CategoryScale,
	PointElement,
	Filler
);

const dashboardStore = DashboardConfigurationStore();
let interval = null;

/** Rolling samples from each /api/systemStatus poll (5s); ~4 minutes of history */
const MAX_HISTORY = 48;
const history = ref([]);

const sumNetworkRealtimeMbPerSec = (net) => {
	if (!net || typeof net !== "object") {
		return {recv: 0, sent: 0};
	}
	let recv = 0;
	let sent = 0;
	for (const iface of Object.values(net)) {
		const rt = iface?.realtime;
		if (rt) {
			recv += Number(rt.recv) || 0;
			sent += Number(rt.sent) || 0;
		}
	}
	return {recv, sent};
};

const pushHistorySample = (d) => {
	const {recv, sent} = sumNetworkRealtimeMbPerSec(d?.NetworkInterfaces);
	const next = [...history.value, {t: Date.now(), recv, sent}];
	while (next.length > MAX_HISTORY) {
		next.shift();
	}
	history.value = next;
};

onMounted(() => {
	getData();
	interval = setInterval(() => {
		getData();
	}, 5000);
});

onBeforeUnmount(() => {
	clearInterval(interval);
});

const getData = () => {
	fetchGet("/api/systemStatus", {}, (res) => {
		dashboardStore.SystemStatus = res.data;
		if (res?.data) {
			pushHistorySample(res.data);
		}
	});
};

const data = computed(() => {
	return dashboardStore.SystemStatus;
});

const networkChartData = computed(() => {
	const h = history.value;
	const labels = h.map((pt) => dayjs(pt.t).format("HH:mm:ss"));
	return {
		labels,
		datasets: [
			{
				label: GetLocale("Received"),
				data: h.map((pt) => pt.recv),
				fill: "start",
				borderColor: "#0d6efd",
				backgroundColor: "#0d6efd28",
				tension: 0.25,
				pointRadius: 0,
				pointHoverRadius: 3,
				borderWidth: 1.5,
			},
			{
				label: GetLocale("Sent"),
				data: h.map((pt) => pt.sent),
				fill: "start",
				borderColor: "#198754",
				backgroundColor: "#19875428",
				tension: 0.25,
				pointRadius: 0,
				pointHoverRadius: 3,
				borderWidth: 1.5,
			},
		],
	};
});

const networkChartOptions = computed(() => ({
	responsive: true,
	maintainAspectRatio: false,
	interaction: {mode: "index", intersect: false},
	plugins: {
		legend: {
			display: true,
			position: "top",
			labels: {boxWidth: 12},
		},
		tooltip: {
			callbacks: {
				label: (ctx) =>
					`${ctx.dataset.label}: ${Number(ctx.raw).toFixed(3)} MB/s`,
			},
		},
	},
	scales: {
		x: {
			ticks: {maxRotation: 0, autoSkip: true, maxTicksLimit: 10},
			grid: {display: false},
		},
		y: {
			min: 0,
			ticks: {
				callback: (val) => `${Number(val)} MB/s`,
			},
			grid: {display: true},
		},
	},
}));

const hostInfo = computed(() => data.value?.Host ?? {});

const serverIpDisplay = computed(() => {
	const ip = hostInfo.value?.primary_ipv4;
	return ip && String(ip).length > 0 ? ip : "—";
});

const uptimeFormatted = computed(() => {
	const sec = hostInfo.value?.uptime_seconds;
	if (sec == null || !Number.isFinite(Number(sec))) {
		return "—";
	}
	const s = Math.floor(Number(sec));
	const d = Math.floor(s / 86400);
	const h = Math.floor((s % 86400) / 3600);
	const m = Math.floor((s % 3600) / 60);
	return `${d}d ${h}h ${m}m`;
});

const siCpuPct = computed(() => {
	const n = Number(data.value?.CPU?.cpu_percent);
	return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 0;
});

const siMemPct = computed(() => {
	const n = Number(data.value?.Memory?.VirtualMemory?.percent);
	return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 0;
});

const siStoragePct = computed(() => {
	const n = Number(
		data.value?.Disks?.find((x) => x.mountPoint === "/")?.percent ??
			data.value?.Disks?.[0]?.percent
	);
	return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 0;
});

const siSwapPct = computed(() => {
	const n = Number(data.value?.Memory?.SwapMemory?.percent);
	return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 0;
});

const siCpuLabel = computed(() => `${Math.round(siCpuPct.value)}%`);
const siMemLabel = computed(() => `${Math.round(siMemPct.value)}%`);
const siStorageLabel = computed(() => `${siStoragePct.value.toFixed(1)}%`);
const siSwapLabel = computed(() => `${siSwapPct.value.toFixed(1)}%`);
</script>

<template>
	<div class="system-status-widget">
		<div class="row text-body g-3 mb-3">
			<div class="col-md-6 col-sm-12 col-xl-3">
				<div class="d-flex align-items-center">
					<h6 class="text-muted">
						<i class="bi bi-cpu-fill me-2"></i>
						<LocaleText t="CPU"></LocaleText>
					</h6>
					<h6 class="ms-auto">
						<span v-if="data">
							{{ data.CPU.cpu_percent }}%
						</span>
						<span v-else class="spinner-border spinner-border-sm"></span>
					</h6>
				</div>
				<div class="progress" role="progressbar" style="height: 6px">
					<div class="progress-bar" :style="{width: `${data?.CPU.cpu_percent}%` }"></div>
				</div>
				<div class="d-flex mt-2 gap-1">
					<CpuCore
						v-for="(cpu, count) in data?.CPU.cpu_percent_per_cpu"
						:key="count"
						:align="(count + 1) > Math.round((data?.CPU?.cpu_percent_per_cpu?.length || 0) / 2)"
						:core_number="count" :percentage="cpu"
					></CpuCore>
				</div>
			</div>
			<div class="col-md-6 col-sm-12 col-xl-3">
				<div class="d-flex align-items-center">
					<h6 class="text-muted">
						<i class="bi bi-device-ssd-fill me-2"></i>
						<LocaleText t="Storage"></LocaleText>
					</h6>
					<h6 class="ms-auto">
						<span v-if="data">
							{{ (data?.Disks?.find((x) => x.mountPoint === '/')?.percent ?? data?.Disks?.[0]?.percent ?? 0) }}%
						</span>
						<span v-else class="spinner-border spinner-border-sm"></span>
					</h6>
				</div>
				<div class="progress" role="progressbar" style="height: 6px">
					<div
						class="progress-bar bg-success"
						:style="{ width: `${(data?.Disks?.find((x) => x.mountPoint === '/')?.percent ?? data?.Disks?.[0]?.percent ?? 0)}%` }"
					></div>
				</div>
				<div class="d-flex mt-2 gap-1">
					<StorageMount v-for="(disk, count) in data?.Disks"
					              v-if="data"
					              :key="disk.mountPoint"
					              :align="(count + 1) > Math.round(data?.Disks.length / 2)"
					              :mount="disk"
					></StorageMount>
				</div>
			</div>
			<div class="col-md-6 col-sm-12 col-xl-3">
				<div class="d-flex align-items-center">
					<h6 class="text-muted">
						<i class="bi bi-memory me-2"></i>
						<LocaleText t="Memory"></LocaleText>
					</h6>
					<h6 class="ms-auto">
						<span v-if="data">
							{{ data?.Memory.VirtualMemory.percent }}%
						</span>
						<span v-else class="spinner-border spinner-border-sm"></span>
					</h6>
				</div>
				<div class="progress" role="progressbar" style="height: 6px">
					<div class="progress-bar bg-info" :style="{width: `${data?.Memory.VirtualMemory.percent}%` }"></div>
				</div>
			</div>
			<div class="col-md-6 col-sm-12 col-xl-3">
				<div class="d-flex align-items-center">
					<h6 class="text-muted">
						<i class="bi bi-memory me-2"></i>
						<LocaleText t="Swap Memory"></LocaleText>
					</h6>
					<h6 class="ms-auto">
						<span v-if="data">
							{{ data?.Memory.SwapMemory.percent }}%
						</span>
						<span v-else class="spinner-border spinner-border-sm"></span>
					</h6>
				</div>
				<div class="progress" role="progressbar" style="height: 6px">
					<div class="progress-bar bg-warning" :style="{width: `${data?.Memory.SwapMemory.percent}%` }"></div>
				</div>
			</div>
		</div>

		<div class="row g-3 mb-5 align-items-stretch">
			<div class="col-lg-8">
				<div class="card rounded-3 h-100 border border-secondary-subtle">
					<div class="card-header bg-transparent border-secondary-subtle py-2 d-flex align-items-center gap-2">
						<small class="text-muted mb-0">
							<i class="bi bi-diagram-3 me-1" aria-hidden="true"></i>
							<LocaleText t="Network throughput (all interfaces, recent)"></LocaleText>
						</small>
					</div>
					<div class="card-body pt-2 pb-3" style="min-height: 240px">
						<Line
							v-if="history.length >= 2"
							:data="networkChartData"
							:options="networkChartOptions"
							style="width: 100%; height: 220px"
						/>
						<p v-else class="text-muted small mb-0 py-5 text-center">
							<LocaleText t="Collecting samples…"></LocaleText>
						</p>
					</div>
				</div>
			</div>
			<div class="col-lg-4">
				<div class="card server-info-panel h-100 rounded-3 border border-secondary-subtle">
					<div class="card-header bg-transparent border-secondary-subtle py-2 px-3">
						<small class="text-body-secondary mb-0 fw-semibold">
							<i class="bi bi-pc-display-horizontal me-1" aria-hidden="true"></i>
							<LocaleText t="System & Server Info"></LocaleText>
						</small>
					</div>
					<div class="card-body px-3 py-3 d-flex flex-column">
						<div class="si-metric mb-3">
							<div class="d-flex justify-content-between align-items-baseline mb-1">
								<span class="si-label text-body-secondary small">
									<LocaleText t="CPU"></LocaleText>
								</span>
								<span class="si-value small fw-medium tabular-nums">{{ siCpuLabel }}</span>
							</div>
							<div class="si-track" role="presentation">
								<div
									class="si-fill si-fill-cpu"
									:style="{ width: `${siCpuPct}%` }"
								></div>
							</div>
						</div>
						<div class="si-metric mb-3">
							<div class="d-flex justify-content-between align-items-baseline mb-1">
								<span class="si-label text-body-secondary small">
									<LocaleText t="Memory"></LocaleText>
								</span>
								<span class="si-value small fw-medium tabular-nums">{{ siMemLabel }}</span>
							</div>
							<div class="si-track" role="presentation">
								<div
									class="si-fill si-fill-mem"
									:style="{ width: `${siMemPct}%` }"
								></div>
							</div>
						</div>
						<div class="si-metric mb-3">
							<div class="d-flex justify-content-between align-items-baseline mb-1">
								<span class="si-label text-body-secondary small">
									<LocaleText t="Storage"></LocaleText>
								</span>
								<span class="si-value small fw-medium tabular-nums">{{ siStorageLabel }}</span>
							</div>
							<div class="si-track" role="presentation">
								<div
									class="si-fill si-fill-storage"
									:style="{ width: `${siStoragePct}%` }"
								></div>
							</div>
						</div>
						<div class="si-metric mb-3">
							<div class="d-flex justify-content-between align-items-baseline mb-1">
								<span class="si-label text-body-secondary small">
									<LocaleText t="Swap Memory"></LocaleText>
								</span>
								<span class="si-value small fw-medium tabular-nums">{{ siSwapLabel }}</span>
							</div>
							<div class="si-track" role="presentation">
								<div
									class="si-fill si-fill-swap"
									:style="{ width: `${siSwapPct}%` }"
								></div>
							</div>
						</div>

						<hr class="si-divider my-1 opacity-25" />

						<div class="d-flex justify-content-between align-items-baseline small mt-2">
							<span class="text-body-secondary">
								<LocaleText t="Server IP"></LocaleText>
							</span>
							<span class="text-body font-monospace text-break text-end ps-2">{{ serverIpDisplay }}</span>
						</div>
						<div class="d-flex justify-content-between align-items-baseline small mt-2 mb-0">
							<span class="text-body-secondary">
								<LocaleText t="Uptime"></LocaleText>
							</span>
							<span class="si-uptime fw-semibold tabular-nums text-end ps-2">{{ uptimeFormatted }}</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.progress-bar {
	width: 0;
	transition: all 1s cubic-bezier(0.42, 0, 0.22, 1.0);
}

.server-info-panel {
	background: color-mix(in srgb, var(--bs-body-bg) 92%, var(--bs-secondary-color) 8%);
}

.si-track {
	height: 5px;
	border-radius: 3px;
	background: color-mix(in srgb, var(--bs-body-color) 12%, transparent);
	overflow: hidden;
}

.si-fill {
	height: 100%;
	border-radius: 3px;
	width: 0;
	transition: width 1s cubic-bezier(0.42, 0, 0.22, 1);
}

.si-fill-cpu {
	background: #6b7280;
}

.si-fill-mem {
	background: #22c55e;
}

.si-fill-storage {
	background: #f97316;
}

.si-fill-swap {
	background: #38bdf8;
}

.si-divider {
	border-color: var(--bs-border-color);
}

.si-uptime {
	color: #4ade80;
}

[data-bs-theme="light"] .si-uptime {
	color: var(--bs-success);
}

.tabular-nums {
	font-variant-numeric: tabular-nums;
}
</style>
