<script setup>
import {computed, onBeforeUnmount, onMounted, ref, watch} from "vue";
import {RouterLink} from "vue-router";
import {WireguardConfigurationsStore} from "@/stores/WireguardConfigurationsStore.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchGet} from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";
import ProtocolBadge from "@/components/protocolBadge.vue";
import dayjs from "dayjs";

const wireguardStore = WireguardConfigurationsStore();
const dashboardStore = DashboardConfigurationStore();

const configsLoading = ref(true);
const snapshotRecordedAt = ref(null);

let pollTimer = null;

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

const stats = computed(() => {
	const cfgs = sortedConfigs.value;
	let activeIf = 0;
	let totalPeers = 0;
	let connected = 0;
	let recv = 0;
	let sent = 0;
	for (const c of cfgs) {
		if (c.Status) {
			activeIf++;
		}
		totalPeers += c.TotalPeers ?? 0;
		connected += c.ConnectedPeers ?? 0;
		recv += c.DataUsage?.Receive ?? 0;
		sent += c.DataUsage?.Sent ?? 0;
	}
	return {
		totalIf: cfgs.length,
		activeIf,
		totalPeers,
		connected,
		recv,
		sent,
	};
});

const fmtGb = (n) => {
	if (n == null || Number.isNaN(Number(n))) {
		return "—";
	}
	return `${Number(n).toFixed(3)} GB`;
};

const loadSnapshotMeta = () => {
	fetchGet("/api/getClientsNetworkOverview", {}, (res) => {
		if (res?.status && res.data?.latest?.recorded_at) {
			snapshotRecordedAt.value = res.data.latest.recorded_at;
		}
	});
};

const loadAll = async () => {
	configsLoading.value = true;
	await wireguardStore.getConfigurations();
	configsLoading.value = false;
	loadSnapshotMeta();
};

const schedulePoll = () => {
	if (pollTimer !== null) {
		clearInterval(pollTimer);
	}
	pollTimer = setInterval(loadAll, refreshMs.value);
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
});
</script>

<template>
	<div class="dashboard-wg-overview mb-4">
		<div
			class="d-flex flex-wrap align-items-center gap-2 mb-3"
		>
			<h2 class="h5 mb-0 text-body d-flex align-items-center gap-2">
				<i class="bi bi-shield-lock" aria-hidden="true"></i>
				<LocaleText t="WireGuard overview"></LocaleText>
			</h2>
			<div class="d-flex flex-wrap align-items-center gap-2 ms-md-auto">
				<small
					v-if="snapshotRecordedAt"
					class="text-muted"
				>
					<LocaleText t="Stats snapshot"></LocaleText>
					{{ " " }}{{ dayjs(snapshotRecordedAt).format("YYYY-MM-DD HH:mm") }}
				</small>
				<RouterLink
					:to="{ name: 'Clients' }"
					class="btn btn-sm btn-outline-primary rounded-3"
				>
					<i class="bi bi-people me-1"></i>
					<LocaleText t="Client List Management"></LocaleText>
				</RouterLink>
				<RouterLink
					:to="{ name: 'WireGuard Management Home' }"
					class="btn btn-sm btn-outline-secondary rounded-3"
				>
					<i class="bi bi-hdd-network me-1"></i>
					<LocaleText t="WireGuard Configurations"></LocaleText>
				</RouterLink>
			</div>
		</div>

		<div v-if="configsLoading && sortedConfigs.length === 0" class="py-5 text-center text-muted">
			<div class="spinner-border spinner-border-sm me-2" role="status"></div>
			<LocaleText t="Loading..."></LocaleText>
		</div>

		<template v-else-if="sortedConfigs.length === 0">
			<div class="card rounded-3 border border-secondary-subtle">
				<div class="card-body py-5 text-center text-muted">
					<p class="mb-3">
						<LocaleText t="No WireGuard configuration yet"></LocaleText>
					</p>
					<RouterLink
						:to="{ name: 'WireGuard Configuration New' }"
						class="btn btn-primary rounded-3"
					>
						<i class="bi bi-plus-lg me-1"></i>
						<LocaleText t="New Configuration"></LocaleText>
					</RouterLink>
				</div>
			</div>
		</template>

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
										<LocaleText t="Interfaces"></LocaleText>
									</small>
									<div class="fs-4 fw-semibold tabular-nums">
										<span class="text-success">{{ stats.activeIf }}</span>
										<span class="text-muted fs-5">/</span>
										<span>{{ stats.totalIf }}</span>
									</div>
									<small class="text-muted">
										<LocaleText t="active / total"></LocaleText>
									</small>
								</div>
								<span
									class="wg-interfaces-glyph flex-shrink-0"
									aria-hidden="true"
								>
									<svg
										viewBox="0 0 48 48"
										width="44"
										height="44"
										xmlns="http://www.w3.org/2000/svg"
									>
										<g
											fill="none"
											stroke="currentColor"
											stroke-width="1.5"
											stroke-linejoin="round"
										>
											<rect
												x="6"
												y="14"
												width="14"
												height="22"
												rx="2.5"
											/>
											<rect
												x="28"
												y="14"
												width="14"
												height="22"
												rx="2.5"
											/>
											<path
												d="M21 25h6"
												stroke-linecap="round"
											/>
										</g>
										<circle
											cx="13"
											cy="20"
											r="2"
											fill="currentColor"
										/>
										<circle
											cx="35"
											cy="20"
											r="2"
											fill="currentColor"
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
										<LocaleText t="Total peers"></LocaleText>
									</small>
									<div class="fs-4 fw-semibold tabular-nums">
										{{ stats.totalPeers }}
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
										<LocaleText t="Peers (running)"></LocaleText>
									</small>
									<div class="fs-4 fw-semibold tabular-nums text-success">
										{{ stats.connected }}
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
											d="M24 4.5 38 9.2v12.6c0 9.1-5.7 17.8-14 21.7h-.1C15.7 39.6 10 30.9 10 21.8V9.2L24 4.5z"
											fill="rgba(25, 135, 84, 0.12)"
											stroke="rgba(255, 255, 255, 0.42)"
											stroke-width="1.2"
											stroke-linejoin="round"
										/>
										<circle
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
										<LocaleText t="Peer traffic (cumulative)"></LocaleText>
									</small>
									<div class="small">
										<div class="text-primary fw-semibold">
											↓ {{ fmtGb(stats.recv) }}
										</div>
										<div class="text-success fw-semibold">
											↑ {{ fmtGb(stats.sent) }}
										</div>
									</div>
								</div>
								<div
									class="d-flex flex-column align-items-end gap-1 flex-shrink-0 traffic-stack"
								>
									<span
										class="traffic-rx-glyph"
										aria-hidden="true"
									>
										<svg
											viewBox="0 0 48 48"
											width="34"
											height="34"
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
									<span
										class="traffic-tx-glyph"
										aria-hidden="true"
									>
										<svg
											viewBox="0 0 48 48"
											width="34"
											height="34"
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
			</div>

			<div class="card rounded-3 border border-secondary-subtle">
				<div class="card-header bg-transparent border-secondary-subtle py-2 d-flex align-items-center">
					<small class="text-muted mb-0">
						<LocaleText t="Configurations"></LocaleText>
					</small>
				</div>
				<div class="card-body py-2 px-0">
					<div class="table-responsive mb-0">
						<table class="table table-sm table-borderless mb-0 align-middle">
							<thead class="small text-muted">
								<tr>
									<th class="ps-3" scope="col">
										<LocaleText t="Interface"></LocaleText>
									</th>
									<th scope="col">
										<LocaleText t="Protocol"></LocaleText>
									</th>
									<th scope="col">
										<LocaleText t="Status"></LocaleText>
									</th>
									<th class="text-end" scope="col">
										<LocaleText t="Peers"></LocaleText>
									</th>
									<th class="text-end" scope="col">
										<LocaleText t="Running"></LocaleText>
									</th>
									<th class="text-end pe-3" scope="col"></th>
								</tr>
							</thead>
							<tbody class="small">
								<tr
									v-for="c in sortedConfigs"
									:key="c.Name"
								>
									<td class="ps-3">
										<samp class="fw-medium">{{ c.Name }}</samp>
									</td>
									<td>
										<ProtocolBadge :protocol="c.Protocol"></ProtocolBadge>
									</td>
									<td>
										<span
											class="dot d-inline-block rounded-circle me-1 align-middle"
											:class="c.Status ? 'bg-success' : 'bg-secondary'"
											style="width: 0.55rem; height: 0.55rem"
										></span>
										<span v-if="c.Status">
											<LocaleText t="Active"></LocaleText>
										</span>
										<span v-else>
											<LocaleText t="Inactive"></LocaleText>
										</span>
									</td>
									<td class="text-end tabular-nums">
										{{ c.TotalPeers ?? 0 }}
									</td>
									<td class="text-end tabular-nums text-success">
										{{ c.ConnectedPeers ?? 0 }}
									</td>
									<td class="text-end pe-3">
										<RouterLink
											:to="`/configuration/${c.Name}/peers`"
											class="btn btn-sm btn-link text-decoration-none p-0"
										>
											<LocaleText t="Open"></LocaleText>
											<i class="bi bi-box-arrow-up-right ms-1 small"></i>
										</RouterLink>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>
		</template>
	</div>
</template>

<style scoped>
.tabular-nums {
	font-variant-numeric: tabular-nums;
}

/* Dua “NIC” — interface aktif / total */
.wg-interfaces-glyph {
	color: #fbbf24;
	line-height: 0;
	filter: drop-shadow(0 0 6px rgba(251, 191, 36, 0.35))
		drop-shadow(0 0 1px rgba(253, 224, 71, 0.55));
}

.wg-interfaces-glyph svg {
	display: block;
}

/* Sama seperti Clients: grup peer (biru) */
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

/* Peer running — badge VPN hijau + pulse */
.active-vpn-glyph {
	--active-vpn-green: #4ade80;
	color: var(--active-vpn-green);
	line-height: 0;
	filter: drop-shadow(0 0 6px rgba(74, 222, 128, 0.55))
		drop-shadow(0 0 2px rgba(134, 239, 172, 0.85));
	animation: home-active-vpn-glow 2.6s ease-in-out infinite;
}

.active-vpn-svg {
	display: block;
}

@media (prefers-reduced-motion: reduce) {
	.active-vpn-glyph {
		animation: none;
	}
}

@keyframes home-active-vpn-glow {
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

.traffic-stack {
	line-height: 0;
}
</style>
