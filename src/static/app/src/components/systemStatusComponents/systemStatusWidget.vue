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
import {useElementSize} from "@vueuse/core";

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

/** Match throughput card height to System & Server Info (no stretch gap / empty footer). */
const systemInfoCardRef = ref(null);
const {height: systemInfoCardHeight} = useElementSize(systemInfoCardRef);

const throughputCardStyle = computed(() => {
	const h = systemInfoCardHeight.value;
	if (!Number.isFinite(h) || h < 80) {
		return {minHeight: "260px"};
	}
	return {height: `${Math.round(h)}px`, minHeight: "240px"};
});

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

const fmtGB = (bytes) => {
	if (bytes == null || !Number.isFinite(Number(bytes)) || Number(bytes) < 0) {
		return null;
	}
	return (Number(bytes) / 1073741824).toFixed(1);
};

const fmtGBPair = (used, total) => {
	const u = fmtGB(used);
	const t = fmtGB(total);
	if (u == null || t == null) {
		return "—";
	}
	return `${u} / ${t} ${GetLocale("GB")}`;
};

const rootDisk = computed(() => {
	const disks = data.value?.Disks;
	if (!Array.isArray(disks) || disks.length === 0) {
		return null;
	}
	return disks.find((x) => x.mountPoint === "/") ?? disks[0];
});

const cpuSubtitle = computed(() => {
	const c = data.value?.CPU;
	if (!c) {
		return "";
	}
	const n = Number(c.logical_cores);
	const cores =
		Number.isFinite(n) && n > 0 ? `${Math.round(n)} ${GetLocale("cores")}` : "";
	const model = (c.model || "").trim();
	const parts = [];
	if (cores) {
		parts.push(cores);
	}
	if (model) {
		parts.push(model);
	}
	return parts.join(" · ");
});

const memGbLine = computed(() => {
	const m = data.value?.Memory?.VirtualMemory;
	if (!m) {
		return "—";
	}
	return fmtGBPair(m.used, m.total);
});

const storageUsedLine = computed(() => {
	const d = rootDisk.value;
	if (!d) {
		return "—";
	}
	const u = fmtGB(d.used);
	const t = fmtGB(d.total);
	if (u == null || t == null) {
		return "—";
	}
	return `${GetLocale("sysinfo storage used")}: ${u} / ${t} ${GetLocale("GB")}`;
});

const storageFreeLine = computed(() => {
	const d = rootDisk.value;
	if (!d) {
		return "—";
	}
	const f = fmtGB(d.free);
	const t = fmtGB(d.total);
	if (f == null || t == null) {
		return "—";
	}
	return `${GetLocale("sysinfo storage free")}: ${f} / ${t} ${GetLocale("GB")}`;
});

const storageMountHint = computed(() => {
	const mp = rootDisk.value?.mountPoint;
	return mp ? mp : "";
});

const swapGbLine = computed(() => {
	const s = data.value?.Memory?.SwapMemory;
	if (!s || !Number(s.total)) {
		return GetLocale("sysinfo no swap");
	}
	return fmtGBPair(s.used, s.total);
});

const runtimeRows = computed(() => {
	const rv = data.value?.RuntimeVersions ?? {};
	const rows = [
		{key: "python", labelKey: "Python"},
		{key: "gunicorn", labelKey: "Gunicorn"},
		{key: "nginx", labelKey: "Nginx"},
		{key: "flask", labelKey: "Flask"},
		{key: "wireguard_tools", labelKey: "WireGuard tools"},
		{key: "openssl", labelKey: "OpenSSL"},
	];
	return rows.map((r) => ({
		...r,
		value:
			rv[r.key] && String(rv[r.key]).length ? String(rv[r.key]) : "—",
	}));
});
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
					<div class="progress-bar" :style="{ width: `${data?.CPU.cpu_percent}%` }"></div>
				</div>
				<div class="d-flex mt-2 gap-1 flex-wrap">
					<CpuCore
						v-for="(cpu, count) in data?.CPU.cpu_percent_per_cpu"
						:key="count"
						:align="(count + 1) > Math.round((data?.CPU?.cpu_percent_per_cpu?.length || 0) / 2)"
						:core_number="count"
						:percentage="cpu"
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
						:style="{
							width: `${data?.Disks?.find((x) => x.mountPoint === '/')?.percent ?? data?.Disks?.[0]?.percent ?? 0}%`,
						}"
					></div>
				</div>
				<div class="d-flex mt-2 gap-1 flex-wrap">
					<StorageMount
						v-for="(disk, count) in data?.Disks"
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
					<div
						class="progress-bar bg-info"
						:style="{ width: `${data?.Memory.VirtualMemory.percent}%` }"
					></div>
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
					<div
						class="progress-bar bg-warning"
						:style="{ width: `${data?.Memory.SwapMemory.percent}%` }"
					></div>
				</div>
			</div>
		</div>

		<div class="row g-3 mb-5 align-items-start">
			<div class="col-lg-8">
				<div
					class="card rounded-3 border border-secondary-subtle w-100 d-flex flex-column network-throughput-card overflow-hidden"
					:style="throughputCardStyle"
				>
					<div class="card-header bg-transparent border-secondary-subtle py-2 d-flex align-items-center gap-2 flex-shrink-0">
						<small class="text-muted mb-0">
							<i class="bi bi-diagram-3 me-1" aria-hidden="true"></i>
							<LocaleText t="Network throughput (all interfaces, recent)"></LocaleText>
						</small>
					</div>
					<div
						class="card-body pt-2 pb-3 px-3 d-flex flex-column flex-grow-1 network-throughput-body"
					>
						<div
							v-if="history.length >= 2"
							class="network-throughput-chart-wrap"
						>
							<Line
								:data="networkChartData"
								:options="networkChartOptions"
							/>
						</div>
						<p v-else class="text-muted small mb-0 py-5 text-center flex-grow-1 d-flex align-items-center justify-content-center">
							<LocaleText t="Collecting samples…"></LocaleText>
						</p>
					</div>
				</div>
			</div>
			<div class="col-lg-4">
				<div
					ref="systemInfoCardRef"
					class="card server-info-panel rounded-3 border border-secondary-subtle"
				>
					<div class="card-header bg-transparent border-secondary-subtle py-2 px-3">
						<small class="text-body-secondary mb-0 fw-semibold">
							<i class="bi bi-pc-display-horizontal me-1" aria-hidden="true"></i>
							<LocaleText t="System & Server Info"></LocaleText>
						</small>
					</div>
					<div class="card-body px-3 py-3 d-flex flex-column">
						<div class="si-metric mb-3">
							<div class="d-flex justify-content-between align-items-baseline gap-2 mb-1">
								<span class="si-label text-body-secondary small">
									<LocaleText t="CPU"></LocaleText>
								</span>
								<span class="si-value small fw-medium tabular-nums flex-shrink-0">{{ siCpuLabel }}</span>
							</div>
							<p
								v-if="cpuSubtitle"
								class="si-cpu-detail small text-body-secondary mb-0"
								:title="cpuSubtitle"
							>
								{{ cpuSubtitle }}
							</p>
						</div>
						<div class="si-metric mb-3">
							<div class="d-flex justify-content-between align-items-baseline mb-1">
								<span class="si-label text-body-secondary small">
									<LocaleText t="Memory"></LocaleText>
								</span>
								<span class="si-value small fw-medium tabular-nums">{{ siMemLabel }}</span>
							</div>
							<div class="si-detail-line small text-body-secondary tabular-nums">
								{{ memGbLine }}
							</div>
						</div>
						<div class="si-metric mb-3">
							<div class="d-flex justify-content-between align-items-baseline mb-1">
								<span class="si-label text-body-secondary small">
									<LocaleText t="Storage"></LocaleText>
								</span>
								<span class="si-value small fw-medium tabular-nums">{{ siStorageLabel }}</span>
							</div>
							<div v-if="storageMountHint" class="text-muted small mb-1 font-monospace">
								{{ storageMountHint }}
							</div>
							<div class="si-detail-line small text-body-secondary mb-1 tabular-nums">
								{{ storageUsedLine }}
							</div>
							<div class="si-detail-line small text-body-secondary tabular-nums">
								{{ storageFreeLine }}
							</div>
						</div>
						<div class="si-metric mb-3">
							<div class="d-flex justify-content-between align-items-baseline mb-1">
								<span class="si-label text-body-secondary small">
									<LocaleText t="Swap Memory"></LocaleText>
								</span>
								<span class="si-value small fw-medium tabular-nums">{{ siSwapLabel }}</span>
							</div>
							<div class="si-detail-line small text-body-secondary tabular-nums">
								{{ swapGbLine }}
							</div>
						</div>

						<hr class="si-divider my-2 opacity-25" />

						<div class="d-flex justify-content-between align-items-baseline small">
							<span class="text-body-secondary">
								<LocaleText t="Server IP"></LocaleText>
							</span>
							<span class="text-body font-monospace text-break text-end ps-2">{{ serverIpDisplay }}</span>
						</div>
						<div class="d-flex justify-content-between align-items-baseline small mt-2 mb-2">
							<span class="text-body-secondary">
								<LocaleText t="Uptime"></LocaleText>
							</span>
							<span class="si-uptime fw-semibold tabular-nums text-end ps-2">{{ uptimeFormatted }}</span>
						</div>

						<hr class="si-divider my-2 opacity-25" />

						<div
							v-for="row in runtimeRows"
							:key="row.key"
							class="d-flex justify-content-between align-items-start gap-2 small py-1"
						>
							<span class="text-body-secondary flex-shrink-0">
								<LocaleText :t="row.labelKey"></LocaleText>
							</span>
							<span
								class="text-body font-monospace text-break text-end rv-version"
								:title="row.value"
							>{{ row.value }}</span>
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
	transition: all 1s cubic-bezier(0.42, 0, 0.22, 1);
}

.server-info-panel {
	background: color-mix(in srgb, var(--bs-body-bg) 92%, var(--bs-secondary-color) 8%);
}

.si-cpu-detail {
	line-height: 1.3;
	max-height: 3.9rem;
	overflow: hidden;
	display: -webkit-box;
	-webkit-box-orient: vertical;
	-webkit-line-clamp: 3;
	word-break: break-word;
}

.si-detail-line {
	font-size: 0.78rem;
}

.rv-version {
	font-size: 0.75rem;
	max-width: 68%;
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

/* Chart fills card body; card outer height tracks System & Server Info (see throughputCardStyle). */
.network-throughput-body {
	flex: 1 1 auto;
	min-height: 0;
	display: flex;
	flex-direction: column;
}

.network-throughput-chart-wrap {
	position: relative;
	width: 100%;
	flex: 1 1 auto;
	min-height: 0;
}

.network-throughput-chart-wrap :deep(> div) {
	height: 100%;
	min-height: 0;
}

.network-throughput-chart-wrap :deep(canvas) {
	max-width: 100%;
}
</style>
