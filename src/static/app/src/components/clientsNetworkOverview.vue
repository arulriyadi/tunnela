<script setup>
import {computed, onBeforeUnmount, onMounted, ref, watch} from "vue";
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
import {GetLocale} from "@/utilities/locale.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";

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

const loading = ref(true);
const latest = ref(null);
const series24h = ref([]);
const intervalMs = ref(60000);
let pollTimer = null;

const clearPoll = () => {
	if (pollTimer !== null) {
		clearInterval(pollTimer);
		pollTimer = null;
	}
};

const schedulePoll = () => {
	clearPoll();
	const ms = Math.max(10000, intervalMs.value || 60000);
	pollTimer = setInterval(loadOverview, ms);
};

const loadOverview = async () => {
	await fetchGet("/api/getClientsNetworkOverview", {}, (res) => {
		if (res?.status) {
			const d = res.data;
			latest.value = d.latest ?? null;
			series24h.value = Array.isArray(d.series24h) ? d.series24h : [];
			if (typeof d.interval_ms === "number" && d.interval_ms > 0) {
				const next = d.interval_ms;
				if (next !== intervalMs.value) {
					intervalMs.value = next;
					schedulePoll();
				}
			}
		}
		loading.value = false;
	});
};

onMounted(() => {
	const raw = dashboardStore.Configuration?.Server?.clients_statistics_interval;
	const n = parseInt(raw, 10);
	if (!Number.isNaN(n) && n > 0) {
		intervalMs.value = n;
	}
	loadOverview();
	schedulePoll();
});

onBeforeUnmount(() => {
	clearPoll();
});

watch(
	() => dashboardStore.Configuration?.Server?.clients_statistics_interval,
	() => {
		const raw = dashboardStore.Configuration?.Server?.clients_statistics_interval;
		const n = parseInt(raw, 10);
		if (!Number.isNaN(n) && n > 0 && n !== intervalMs.value) {
			intervalMs.value = n;
			schedulePoll();
		}
	}
);

const sortedSeries = computed(() => {
	const s = [...series24h.value];
	s.sort((a, b) => {
		const ta = a.recorded_at ? Date.parse(a.recorded_at) : 0;
		const tb = b.recorded_at ? Date.parse(b.recorded_at) : 0;
		return ta - tb;
	});
	return s;
});

const trafficChartData = computed(() => {
	const labels = sortedSeries.value.map((pt) =>
		pt.recorded_at ? dayjs(pt.recorded_at).format("MMM D HH:mm") : "—"
	);
	const recv = sortedSeries.value.map((pt) => pt.metrics?.total_receive_gb ?? 0);
	const sent = sortedSeries.value.map((pt) => pt.metrics?.total_sent_gb ?? 0);
	return {
		labels,
		datasets: [
			{
				label: GetLocale("Data Received"),
				data: recv,
				fill: "start",
				borderColor: "#0d6efd",
				backgroundColor: "#0d6efd40",
				tension: 0.2,
				pointRadius: 2,
				borderWidth: 1.5,
			},
			{
				label: GetLocale("Data Sent"),
				data: sent,
				fill: "start",
				borderColor: "#198754",
				backgroundColor: "#19875440",
				tension: 0.2,
				pointRadius: 2,
				borderWidth: 1.5,
			},
		],
	};
});

const trafficChartOptions = computed(() => ({
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
				label: (ctx) => `${ctx.dataset.label}: ${Number(ctx.raw).toFixed(3)} GB`,
			},
		},
	},
	scales: {
		x: {
			ticks: {maxRotation: 45, minRotation: 0, autoSkip: true, maxTicksLimit: 8},
			grid: {display: true},
		},
		y: {
			ticks: {
				callback: (val) => `${Number(val).toFixed(2)} GB`,
			},
			grid: {display: true},
		},
	},
}));

const metrics = computed(() => latest.value?.metrics ?? null);

const fmtGb = (n) => {
	if (n == null || Number.isNaN(Number(n))) return "—";
	return `${Number(n).toFixed(3)} GB`;
};

const activeConfigurations = computed(() => {
	const cfgs = metrics.value?.configurations;
	return Array.isArray(cfgs) ? cfgs : [];
});
</script>

<template>
	<div class="clients-network-overview mb-4">
		<div
			class="d-flex flex-wrap align-items-center gap-2 mb-3"
		>
			<h3 class="h6 mb-0 text-body-secondary d-flex align-items-center gap-2">
				<i class="bi bi-graph-up-arrow" aria-hidden="true"></i>
				<LocaleText t="Network overview (24h)"></LocaleText>
			</h3>
			<small
				v-if="latest?.recorded_at"
				class="text-muted ms-md-auto"
			>
				<LocaleText t="Last updated"></LocaleText>
				{{ " " }}{{ dayjs(latest.recorded_at).format("YYYY-MM-DD HH:mm:ss") }}
			</small>
		</div>

		<div v-if="loading && !latest" class="card rounded-3 border border-secondary-subtle">
			<div class="card-body py-5 text-center text-muted">
				<div class="spinner-border spinner-border-sm me-2" role="status"></div>
				<LocaleText t="Loading statistics..."></LocaleText>
			</div>
		</div>

		<template v-else>
			<div class="row g-3 mb-3">
				<div class="col-6 col-md-3">
					<div class="card rounded-3 h-100 border border-secondary-subtle">
						<div class="card-body py-3">
							<div
								class="d-flex align-items-start justify-content-between gap-2"
							>
								<div class="flex-grow-1 min-w-0">
									<small class="text-muted d-block mb-1">
										<LocaleText t="Active connections"></LocaleText>
									</small>
									<div class="fs-4 fw-semibold tabular-nums">
										{{ metrics?.active_connections ?? "—" }}
									</div>
								</div>
								<span
									class="active-vpn-glyph flex-shrink-0"
									aria-hidden="true"
								>
									<svg
										class="active-vpn-svg"
										viewBox="0 0 48 48"
										width="44"
										height="44"
										xmlns="http://www.w3.org/2000/svg"
									>
										<path
											class="active-vpn-shield"
											d="M24 4.5 38 9.2v12.6c0 9.1-5.7 17.8-14 21.7h-.1C15.7 39.6 10 30.9 10 21.8V9.2L24 4.5z"
											fill="rgba(25, 135, 84, 0.12)"
											stroke="rgba(255, 255, 255, 0.42)"
											stroke-width="1.2"
											stroke-linejoin="round"
										/>
										<circle
											class="active-vpn-node"
											cx="18.2"
											cy="19"
											r="2.35"
											fill="currentColor"
										/>
										<path
											d="M20.6 19h6.8"
											fill="none"
											stroke="currentColor"
											stroke-width="1.85"
											stroke-linecap="round"
										/>
										<circle
											class="active-vpn-node"
											cx="29.8"
											cy="19"
											r="2.35"
											fill="currentColor"
										/>
										<text
											x="24"
											y="32"
											text-anchor="middle"
											fill="currentColor"
											font-size="8.25"
											font-weight="700"
											font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
										>
											VPN
										</text>
									</svg>
								</span>
							</div>
						</div>
					</div>
				</div>
				<div class="col-6 col-md-3">
					<div class="card rounded-3 h-100 border border-secondary-subtle">
						<div class="card-body py-3">
							<div
								class="d-flex align-items-start justify-content-between gap-2"
							>
								<div class="flex-grow-1 min-w-0">
									<small class="text-muted d-block mb-1">
										<LocaleText t="Total peers"></LocaleText>
									</small>
									<div class="fs-4 fw-semibold tabular-nums">
										{{ metrics?.total_peers ?? "—" }}
									</div>
								</div>
								<span
									class="total-peers-glyph flex-shrink-0"
									aria-hidden="true"
								>
									<svg
										class="total-peers-svg"
										viewBox="0 0 48 48"
										width="44"
										height="44"
										xmlns="http://www.w3.org/2000/svg"
									>
										<g
											fill="none"
											stroke="currentColor"
											stroke-width="1.35"
											stroke-linecap="round"
											stroke-linejoin="round"
										>
											<circle cx="14" cy="17" r="3.15" />
											<path
												d="M14 21.2c-4.2 0-7.2 3.1-7.2 7.3h14.4c0-4.2-3-7.3-7.2-7.3z"
											/>
											<circle cx="34" cy="17" r="3.15" />
											<path
												d="M34 21.2c-4.2 0-7.2 3.1-7.2 7.3h14.4c0-4.2-3-7.3-7.2-7.3z"
											/>
											<circle cx="24" cy="14.5" r="3.45" />
											<path
												d="M24 19.1c-4.6 0-7.8 3.3-7.8 7.9h15.6c0-4.6-3.2-7.9-7.8-7.9z"
											/>
										</g>
									</svg>
								</span>
							</div>
						</div>
					</div>
				</div>
				<div class="col-6 col-md-3">
					<div class="card rounded-3 h-100 border border-secondary-subtle">
						<div class="card-body py-3">
							<div
								class="d-flex align-items-start justify-content-between gap-2"
							>
								<div class="flex-grow-1 min-w-0">
									<small class="text-muted d-block mb-1">
										<LocaleText t="Total received"></LocaleText>
									</small>
									<div class="fs-5 fw-semibold tabular-nums text-primary">
										{{ fmtGb(metrics?.total_receive_gb) }}
									</div>
								</div>
								<span
									class="traffic-rx-glyph flex-shrink-0"
									aria-hidden="true"
								>
									<svg
										viewBox="0 0 48 48"
										width="44"
										height="44"
										xmlns="http://www.w3.org/2000/svg"
									>
										<path
											d="M24 9v23"
											fill="none"
											stroke="currentColor"
											stroke-width="2.6"
											stroke-linecap="round"
										/>
										<path
											d="M14.5 24.5 24 35 33.5 24.5"
											fill="none"
											stroke="currentColor"
											stroke-width="2.6"
											stroke-linecap="round"
											stroke-linejoin="round"
										/>
									</svg>
								</span>
							</div>
						</div>
					</div>
				</div>
				<div class="col-6 col-md-3">
					<div class="card rounded-3 h-100 border border-secondary-subtle">
						<div class="card-body py-3">
							<div
								class="d-flex align-items-start justify-content-between gap-2"
							>
								<div class="flex-grow-1 min-w-0">
									<small class="text-muted d-block mb-1">
										<LocaleText t="Total sent"></LocaleText>
									</small>
									<div class="fs-5 fw-semibold tabular-nums text-success">
										{{ fmtGb(metrics?.total_sent_gb) }}
									</div>
								</div>
								<span
									class="traffic-tx-glyph flex-shrink-0"
									aria-hidden="true"
								>
									<svg
										viewBox="0 0 48 48"
										width="44"
										height="44"
										xmlns="http://www.w3.org/2000/svg"
									>
										<path
											d="M24 39V16"
											fill="none"
											stroke="currentColor"
											stroke-width="2.6"
											stroke-linecap="round"
										/>
										<path
											d="M14.5 23.5 24 13 33.5 23.5"
											fill="none"
											stroke="currentColor"
											stroke-width="2.6"
											stroke-linecap="round"
											stroke-linejoin="round"
										/>
									</svg>
								</span>
							</div>
						</div>
					</div>
				</div>
			</div>

			<div
				v-if="activeConfigurations.length"
				class="card rounded-3 mb-3 border border-secondary-subtle"
			>
				<div class="card-header bg-transparent border-secondary-subtle py-2">
					<small class="text-muted">
						<LocaleText t="By configuration"></LocaleText>
					</small>
				</div>
				<div class="card-body py-2 px-3">
					<div class="table-responsive mb-0">
						<table class="table table-sm table-borderless mb-0 small">
							<thead>
								<tr class="text-muted">
									<th scope="col">
										<LocaleText t="Interface"></LocaleText>
									</th>
									<th scope="col" class="text-end">
										<LocaleText t="Peers"></LocaleText>
									</th>
									<th scope="col" class="text-end">
										<LocaleText t="Received"></LocaleText>
									</th>
									<th scope="col" class="text-end">
										<LocaleText t="Sent"></LocaleText>
									</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="c in activeConfigurations"
									:key="c.name"
								>
									<td>
										<span
											class="dot me-2 align-middle"
											:class="{active: c.active}"
										></span>
										<samp>{{ c.name }}</samp>
									</td>
									<td class="text-end tabular-nums">{{ c.total }}</td>
									<td class="text-end tabular-nums">
										{{ fmtGb(c.receive_gb) }}
									</td>
									<td class="text-end tabular-nums">
										{{ fmtGb(c.sent_gb) }}
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>

			<div class="card rounded-3 border border-secondary-subtle">
				<div class="card-header bg-transparent border-secondary-subtle py-2">
					<small class="text-muted">
						<LocaleText t="Aggregate traffic (snapshots)"></LocaleText>
					</small>
				</div>
				<div class="card-body pt-2 pb-3" style="min-height: 260px">
					<Line
						v-if="sortedSeries.length > 0"
						:data="trafficChartData"
						:options="trafficChartOptions"
						style="width: 100%; height: 220px"
					/>
					<p v-else class="text-muted small mb-0 py-5 text-center">
						<LocaleText t="No history yet. Statistics will appear after the next collection."></LocaleText>
					</p>
				</div>
			</div>
		</template>
	</div>
</template>

<style scoped>
.tabular-nums {
	font-variant-numeric: tabular-nums;
}

.dot {
	display: inline-block;
	width: 0.55rem;
	height: 0.55rem;
	border-radius: 50%;
	background: var(--bs-secondary);
	vertical-align: middle;
}

.dot.active {
	background: var(--bs-success);
}

/* Inline VPN badge: hijau “nyala” + glow, cocok dark theme */
.active-vpn-glyph {
--active-vpn-green: #4ade80;
	color: var(--active-vpn-green);
	line-height: 0;
	filter: drop-shadow(0 0 6px rgba(74, 222, 128, 0.55))
		drop-shadow(0 0 2px rgba(134, 239, 172, 0.85));
	animation: active-vpn-glow 2.6s ease-in-out infinite;
}

.active-vpn-svg {
	display: block;
}

@media (prefers-reduced-motion: reduce) {
	.active-vpn-glyph {
		animation: none;
	}
}

@keyframes active-vpn-glow {
	0%,
	100% {
		filter: drop-shadow(0 0 5px rgba(74, 222, 128, 0.45))
			drop-shadow(0 0 1px rgba(187, 247, 208, 0.75));
	}
	50% {
		filter: drop-shadow(0 0 11px rgba(74, 222, 128, 0.72))
			drop-shadow(0 0 3px rgba(187, 247, 208, 0.95));
	}
}

/* Total peers: grup siluet peer, aksen biru (inventori), glow statis — beda dari hijau “aktif” */
.total-peers-glyph {
	--total-peers-accent: #7dd3fc;
	color: var(--total-peers-accent);
	line-height: 0;
	filter: drop-shadow(0 0 6px rgba(125, 211, 252, 0.35))
		drop-shadow(0 0 1px rgba(186, 230, 253, 0.55));
}

.total-peers-svg {
	display: block;
}

/* Received / sent: panah turun & naik, selaras warna kartu */
.traffic-rx-glyph {
	color: #60a5fa;
	line-height: 0;
	filter: drop-shadow(0 0 5px rgba(96, 165, 250, 0.4))
		drop-shadow(0 0 1px rgba(147, 197, 253, 0.65));
}

.traffic-tx-glyph {
	color: #4ade80;
	line-height: 0;
	filter: drop-shadow(0 0 5px rgba(74, 222, 128, 0.4))
		drop-shadow(0 0 1px rgba(187, 247, 208, 0.65));
}

.traffic-rx-glyph svg,
.traffic-tx-glyph svg {
	display: block;
}
</style>
