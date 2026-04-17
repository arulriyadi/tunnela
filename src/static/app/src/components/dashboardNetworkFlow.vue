<script setup>
import {computed, onBeforeUnmount, onMounted, ref, watch} from "vue";
import {RouterLink} from "vue-router";
import {WireguardConfigurationsStore} from "@/stores/WireguardConfigurationsStore.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchGet} from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";
import ProtocolBadge from "@/components/protocolBadge.vue";

const wireguardStore = WireguardConfigurationsStore();
const dashboardStore = DashboardConfigurationStore();

const loading = ref(true);
/** From /api/systemStatus — keys match interface names (e.g. wg0); realtime in MB/s */
const networkIfaces = ref({});
/** Mbps from delta of DataUsage (GiB) between config polls — aligns with WG peer totals */
const tunnelRateMbps = ref({});
/** Previous DataUsage sample per tunnel name */
const prevTunnelUsage = ref({});
let pollTimer = null;
let netPollTimer = null;

const refreshMs = computed(() => {
	const raw = dashboardStore.Configuration?.Server?.dashboard_refresh_interval;
	const n = parseInt(raw, 10);
	return !Number.isNaN(n) && n > 0 ? n : 10000;
});

const sortedConfigs = computed(() =>
	[...(wireguardStore.Configurations || [])].sort((a, b) =>
		(a.Name || "").localeCompare(b.Name || "", undefined, {sensitivity: "base"})
	)
);

/** SVG user units: branches meet at (joinX, midY), trunk runs to (100, midY). */
const mergeVbH = computed(() => {
	const n = sortedConfigs.value.length;
	/* Taller rows after traffic block; SVG stretches (preserveAspectRatio none) to grid height */
	return Math.max(1, n) * 115;
});

const mergeJoinX = 26;
/** Horizontal run after each merge curve (before long trunk segment) */
const mergeTrunkPad = 8;

const svgN = (v) => Number(v.toFixed(3));

/**
 * Smooth “fan-in” like reference UI: cubic Bézier with horizontal tangents at start and end.
 * P1 = (cx, y), P2 = (cx, midY) → S-curve from (0,y) to trunk.
 */
const branchPathBezier = (y, midY, joinX) => {
	const trunkX0 = joinX + mergeTrunkPad;
	const cx = joinX * 0.5;
	if (Math.abs(y - midY) < 0.02) {
		return `M 0 ${svgN(midY)} L ${svgN(trunkX0)} ${svgN(midY)}`;
	}
	return `M 0 ${svgN(y)} C ${svgN(cx)} ${svgN(y)} ${svgN(cx)} ${svgN(midY)} ${svgN(trunkX0)} ${svgN(midY)}`;
};

const mergeBranchPaths = computed(() => {
	const n = sortedConfigs.value.length;
	const H = mergeVbH.value;
	const midY = H / 2;
	const joinX = mergeJoinX;
	const paths = [];
	for (let i = 0; i < n; i++) {
		const y = ((i + 0.5) / n) * H;
		paths.push(branchPathBezier(y, midY, joinX));
	}
	return paths;
});

const mergeTrunkPath = computed(() => {
	const H = mergeVbH.value;
	const midY = H / 2;
	const joinX = mergeJoinX;
	const trunkX0 = joinX + mergeTrunkPad;
	return `M ${svgN(trunkX0)} ${svgN(midY)} L 100 ${svgN(midY)}`;
});

const flowRowCount = computed(() => Math.max(1, sortedConfigs.value.length));

const GIB_TO_MBPS_PER_S = (8 * 1024 * 1024 * 1024) / 1e6;

const fetchSystemStatus = async () => {
	await fetchGet("/api/systemStatus", {}, (res) => {
		if (res?.status && res.data?.NetworkInterfaces) {
			networkIfaces.value = res.data.NetworkInterfaces;
		}
	});
};

const updateTunnelDerivedRates = () => {
	const cfgs = wireguardStore.Configurations || [];
	const now = Date.now();
	const prev = prevTunnelUsage.value;
	const nextPrev = {...prev};
	const rates = {...tunnelRateMbps.value};

	for (const c of cfgs) {
		const name = c?.Name;
		if (!name) {
			continue;
		}
		const recv = Number(c.DataUsage?.Receive);
		const sent = Number(c.DataUsage?.Sent);
		if (!Number.isFinite(recv) || !Number.isFinite(sent)) {
			continue;
		}
		const p = prev[name];
		if (p && now > p.t) {
			const dt = (now - p.t) / 1000;
			if (dt >= 0.4) {
				const dr = recv - p.recv;
				const ds = sent - p.sent;
				if (dr >= -1e-6 && ds >= -1e-6) {
					rates[name] = {
						down: dt > 0 ? (dr * GIB_TO_MBPS_PER_S) / dt : 0,
						up: dt > 0 ? (ds * GIB_TO_MBPS_PER_S) / dt : 0,
					};
				}
			}
		}
		nextPrev[name] = {t: now, recv, sent};
	}
	prevTunnelUsage.value = nextPrev;
	tunnelRateMbps.value = rates;
};

const loadAll = async () => {
	const firstLoad = !(wireguardStore.Configurations && wireguardStore.Configurations.length);
	if (firstLoad) {
		loading.value = true;
	}
	await wireguardStore.getConfigurations();
	updateTunnelDerivedRates();
	await fetchSystemStatus();
	if (firstLoad) {
		loading.value = false;
	}
};

const schedulePoll = () => {
	if (pollTimer !== null) {
		clearInterval(pollTimer);
	}
	pollTimer = setInterval(loadAll, refreshMs.value);
	if (netPollTimer !== null) {
		clearInterval(netPollTimer);
	}
	/* Psutil ~1s sample; refresh more often than configs so live Mbps reacts like the chart */
	netPollTimer = setInterval(fetchSystemStatus, 2500);
};

onMounted(async () => {
	if (!dashboardStore.Configuration) {
		await dashboardStore.getConfiguration();
	}
	await loadAll();
	schedulePoll();
});

watch(refreshMs, schedulePoll);

onBeforeUnmount(() => {
	if (pollTimer !== null) {
		clearInterval(pollTimer);
		pollTimer = null;
	}
	if (netPollTimer !== null) {
		clearInterval(netPollTimer);
		netPollTimer = null;
	}
});

const connectedCount = (c) => Math.max(0, Number(c?.ConnectedPeers) || 0);

const fmtGb = (n) => {
	if (n == null || Number.isNaN(Number(n))) {
		return "—";
	}
	return `${Number(n).toFixed(3)} GB`;
};

/**
 * Live Mbps: psutil per-interface (1s window) merged with WG DataUsage delta (between config polls).
 * Chart sums all NICs; tunnel row uses max(psutil_wg, wg_derived) so WG traffic still shows when psutil lags.
 */
const ifaceLiveMbps = (c) => {
	const name = c?.Name;
	let psDown = null;
	let psUp = null;
	if (name) {
		const raw = networkIfaces.value?.[name] ?? networkIfaces.value?.[name.toLowerCase?.()];
		const rt = raw?.realtime;
		if (rt) {
			const d = Number(rt.recv) * 8;
			const u = Number(rt.sent) * 8;
			if (Number.isFinite(d)) {
				psDown = d;
			}
			if (Number.isFinite(u)) {
				psUp = u;
			}
		}
	}
	const wg = name ? tunnelRateMbps.value[name] : null;
	const merge = (a, b) => {
		const fa = a != null && Number.isFinite(a);
		const fb = b != null && Number.isFinite(b);
		if (fa && fb) {
			return Math.max(a, b);
		}
		if (fa) {
			return a;
		}
		if (fb) {
			return b;
		}
		return null;
	};
	return {
		down: merge(psDown, wg?.down),
		up: merge(psUp, wg?.up),
	};
};

const fmtMbps = (n) => {
	if (n == null || !Number.isFinite(n)) {
		return "—";
	}
	if (n < 10) {
		return `${n.toFixed(2)} Mbps`;
	}
	return `${n.toFixed(1)} Mbps`;
};
</script>

<template>
	<div class="dashboard-network-flow mb-4">
		<div class="d-flex flex-wrap align-items-center gap-2 mb-3">
			<h2 class="h5 mb-0 text-body d-flex align-items-center gap-2">
				<i class="bi bi-diagram-3-fill" aria-hidden="true"></i>
				<LocaleText t="Network flow"></LocaleText>
			</h2>
			<small class="text-muted">
				<LocaleText t="Connected peers per tunnel to the internet"></LocaleText>
			</small>
		</div>

		<div
			v-if="loading && sortedConfigs.length === 0"
			class="py-5 text-center text-muted"
		>
			<div class="spinner-border spinner-border-sm me-2" role="status"></div>
			<LocaleText t="Loading..."></LocaleText>
		</div>

		<div
			v-else-if="sortedConfigs.length === 0"
			class="card rounded-3 border border-secondary-subtle"
		>
			<div class="card-body py-4 text-center text-muted small">
				<LocaleText t="No WireGuard configuration yet"></LocaleText>
			</div>
		</div>

		<div
			v-else
			class="card rounded-3 border border-secondary-subtle network-flow-card overflow-hidden"
		>
			<div class="card-body p-0 p-md-3">
				<div class="network-flow-scroll">
					<div
						class="network-flow-grid"
						:style="{ '--flow-n': flowRowCount }"
					>
						<template
							v-for="(c, idx) in sortedConfigs"
							:key="c.Name"
						>
							<div
								class="nf-client py-3 px-2 px-md-3"
								:style="{ gridRow: idx + 1 }"
							>
								<div class="flow-node flow-node-client rounded-3 px-3 py-2">
									<div class="d-flex align-items-baseline gap-2 flex-wrap">
										<span class="flow-count tabular-nums">{{ connectedCount(c) }}</span>
										<span class="small text-body-secondary">
											<template v-if="connectedCount(c) === 1">
												<LocaleText t="connected peer"></LocaleText>
											</template>
											<template v-else>
												<LocaleText t="connected peers"></LocaleText>
											</template>
										</span>
									</div>
								</div>
							</div>
							<div
								class="nf-c1 py-3 px-0"
								:style="{ gridRow: idx + 1 }"
							>
								<div class="flow-connector-wrap">
									<svg
										class="flow-connector-svg"
										xmlns="http://www.w3.org/2000/svg"
										preserveAspectRatio="none"
										viewBox="0 0 120 12"
									>
										<line
											x1="0"
											y1="6"
											x2="120"
											y2="6"
											class="flow-line-glow"
										/>
									</svg>
								</div>
							</div>
							<div
								class="nf-server py-3 px-2"
								:style="{ gridRow: idx + 1 }"
							>
								<div class="flow-node flow-node-server rounded-3 px-3 py-2">
									<div class="d-flex align-items-center gap-2 flex-wrap">
										<samp class="fw-semibold mb-0">{{ c.Name }}</samp>
										<ProtocolBadge :protocol="c.Protocol"></ProtocolBadge>
										<span
											class="dot rounded-circle flex-shrink-0"
											:class="c.Status ? 'bg-success' : 'bg-secondary'"
											style="width: 0.45rem; height: 0.45rem"
										></span>
										<span class="small text-body-secondary">
											<LocaleText v-if="c.Status" t="Active"></LocaleText>
											<LocaleText v-else t="Inactive"></LocaleText>
										</span>
									</div>
									<RouterLink
										:to="`/configuration/${c.Name}/peers`"
										class="small link-secondary text-decoration-none d-inline-flex align-items-center gap-1 mt-1"
									>
										<LocaleText t="Peers"></LocaleText>
										<i class="bi bi-box-arrow-up-right"></i>
									</RouterLink>
									<div class="nf-traffic mt-2 pt-2 border-top border-secondary-subtle">
										<div class="row g-2 g-md-3 align-items-start">
											<div class="col-12 col-md-6 order-md-1">
												<div class="text-body-secondary text-uppercase nf-traffic-label">
													<LocaleText t="Interface throughput (live)"></LocaleText>
												</div>
												<div class="d-flex flex-row flex-nowrap align-items-center gap-2 gap-md-3 mt-1 small nf-traffic-pair">
													<span
														class="nf-live-down fw-medium tabular-nums d-inline-flex align-items-center gap-1 text-nowrap"
													>
														<i class="bi bi-arrow-down" aria-hidden="true"></i>
														{{ fmtMbps(ifaceLiveMbps(c).down) }}
													</span>
													<span
														class="nf-live-up fw-medium tabular-nums d-inline-flex align-items-center gap-1 text-nowrap"
													>
														<i class="bi bi-arrow-up" aria-hidden="true"></i>
														{{ fmtMbps(ifaceLiveMbps(c).up) }}
													</span>
												</div>
											</div>
											<div class="col-12 col-md-6 order-md-2">
												<div class="text-body-secondary text-uppercase nf-traffic-label">
													<LocaleText t="Tunnel traffic (cumulative)"></LocaleText>
												</div>
												<div class="d-flex flex-row flex-nowrap align-items-center gap-2 gap-md-3 mt-1 small nf-traffic-pair">
													<span
														class="nf-cum-down fw-medium tabular-nums d-inline-flex align-items-center gap-1 text-nowrap"
														:title="fmtGb(c.DataUsage?.Receive)"
													>
														<i class="bi bi-arrow-down" aria-hidden="true"></i>
														{{ fmtGb(c.DataUsage?.Receive) }}
													</span>
													<span
														class="nf-cum-up fw-medium tabular-nums d-inline-flex align-items-center gap-1 text-nowrap"
														:title="fmtGb(c.DataUsage?.Sent)"
													>
														<i class="bi bi-arrow-up" aria-hidden="true"></i>
														{{ fmtGb(c.DataUsage?.Sent) }}
													</span>
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>
						</template>

						<div class="nf-merge">
							<svg
								class="nf-merge-svg"
								xmlns="http://www.w3.org/2000/svg"
								:viewBox="`0 0 100 ${mergeVbH}`"
								preserveAspectRatio="none"
							>
								<path
									v-for="(d, bi) in mergeBranchPaths"
									:key="'br-' + bi"
									class="flow-line-glow"
									fill="none"
									:d="d"
								/>
								<path
									class="flow-line-glow flow-line-trunk"
									fill="none"
									:d="mergeTrunkPath"
								/>
							</svg>
						</div>

						<div class="nf-internet py-3 px-2 px-md-3">
							<div
								class="flow-node flow-node-internet rounded-3 px-3 py-3 text-center w-100 d-flex flex-column justify-content-center"
							>
								<i
									class="bi bi-cloud-arrow-up fs-3 mb-2 flow-internet-icon"
									aria-hidden="true"
								></i>
								<div class="fw-semibold small">
									<LocaleText t="Internet"></LocaleText>
								</div>
								<div class="text-body-secondary smaller mt-1">
									<LocaleText t="Common destination"></LocaleText>
								</div>
							</div>
						</div>
					</div>
				</div>
				<p class="small text-muted mb-0 px-3 py-2 d-md-none">
					<LocaleText t="Swipe sideways to see the full flow"></LocaleText>
				</p>
			</div>
		</div>
	</div>
</template>

<style scoped>
.network-flow-card {
	background: color-mix(in srgb, var(--bs-body-bg) 96%, var(--bs-secondary-bg) 4%);
}

.flow-node {
	border: 1px solid var(--bs-border-color);
	background: var(--bs-body-bg);
}

.flow-node-client {
	min-width: 8rem;
}

.flow-node-server {
	min-width: 0;
}

.flow-count {
	font-size: 1.35rem;
	font-weight: 600;
	line-height: 1.2;
}

.flow-node-internet {
	min-width: 7.5rem;
	border-color: color-mix(in srgb, var(--bs-success) 45%, var(--bs-border-color));
	box-shadow: 0 0 0 1px color-mix(in srgb, var(--bs-success) 25%, transparent);
}

.flow-internet-icon {
	color: var(--bs-success);
	filter: drop-shadow(0 0 8px color-mix(in srgb, var(--bs-success) 55%, transparent));
}

.smaller {
	font-size: 0.7rem;
}

.flow-connector-wrap {
	width: 100%;
	min-width: 3rem;
	height: 24px;
	display: flex;
	align-items: center;
}

.flow-connector-svg {
	width: 100%;
	height: 24px;
	display: block;
}

.network-flow-scroll {
	overflow-x: auto;
	-webkit-overflow-scrolling: touch;
}

.network-flow-grid {
	display: grid;
	grid-template-columns: auto minmax(48px, 1fr) auto minmax(4.5rem, 1.15fr) minmax(112px, auto);
	grid-template-rows: repeat(var(--flow-n, 1), auto);
	align-items: center;
	column-gap: 0.1rem;
	min-width: 640px;
}

.nf-client {
	grid-column: 1;
}

.nf-c1 {
	grid-column: 2;
}

.nf-server {
	grid-column: 3;
}

.nf-merge {
	grid-column: 4;
	grid-row: 1 / -1;
	align-self: stretch;
	position: relative;
	min-width: 4.5rem;
	min-height: 3rem;
}

.nf-merge-svg {
	position: absolute;
	inset: 0;
	width: 100%;
	height: 100%;
	display: block;
}

.nf-internet {
	grid-column: 5;
	grid-row: 1 / -1;
	align-self: stretch;
	display: flex;
	align-items: center;
}

.flow-line-glow {
	fill: none;
	/* Teal-leaning glow, closer to reference diagrams */
	stroke: #34d3a6;
	stroke-width: 2.35;
	stroke-linecap: round;
	stroke-linejoin: round;
	stroke-dasharray: 10 8;
	filter: drop-shadow(0 0 5px rgba(52, 211, 166, 0.75));
	animation: flow-dash 0.9s linear infinite;
}

.flow-line-trunk {
	stroke-width: 2.6;
}

@keyframes flow-dash {
	to {
		stroke-dashoffset: -18;
	}
}

@media (prefers-reduced-motion: reduce) {
	.flow-line-glow {
		animation: none;
	}
}

.tabular-nums {
	font-variant-numeric: tabular-nums;
}

.nf-traffic-label {
	font-size: 0.62rem;
	letter-spacing: 0.04em;
}

.nf-traffic-pair {
	min-width: 0;
	overflow-x: auto;
	scrollbar-width: thin;
}

/* Live: classic blue / green */
.nf-live-down {
	color: var(--bs-primary);
}

.nf-live-up {
	color: var(--bs-success);
}

/* Cumulative: violet / amber — distinct from live, readable on dark UI */
.nf-cum-down {
	color: #c4b5fd;
}

.nf-cum-up {
	color: #fdba74;
}

[data-bs-theme="light"] .nf-cum-down {
	color: #6d28d9;
}

[data-bs-theme="light"] .nf-cum-up {
	color: #c2410c;
}
</style>
