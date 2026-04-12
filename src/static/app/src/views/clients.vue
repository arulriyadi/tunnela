<script setup>
import {
	computed,
	defineAsyncComponent,
	nextTick,
	onBeforeUnmount,
	ref,
	watch,
} from "vue";
import {fetchGet} from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";
import {GetLocale} from "@/utilities/locale.js";
import {WireguardConfigurationsStore} from "@/stores/WireguardConfigurationsStore.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {parseCidr} from "cidr-tools";
import Peer from "@/components/configurationComponents/peer.vue";
import ProtocolBadge from "@/components/protocolBadge.vue";
import PeerSearch from "@/components/configurationComponents/peerSearch.vue";
import PeerListModals from "@/components/configurationComponents/peerListComponents/peerListModals.vue";
import PeerDetailsModal from "@/components/configurationComponents/peerDetailsModal.vue";

const PeerJobsAllModal = defineAsyncComponent(() =>
	import("@/components/configurationComponents/peerJobsAllModal.vue")
)
const PeerJobsLogsModal = defineAsyncComponent(() =>
	import("@/components/configurationComponents/peerJobsLogsModal.vue")
)
const SelectPeersModal = defineAsyncComponent(() =>
	import("@/components/configurationComponents/selectPeers.vue")
)
const SelectPeersBulkRestrictModal = defineAsyncComponent(() =>
	import(
		"@/components/configurationComponents/selectPeersBulkRestrictModal.vue"
	)
)
const ClientsNetworkOverview = defineAsyncComponent(() =>
	import("@/components/clientsNetworkOverview.vue")
)

const wireguardStore = WireguardConfigurationsStore()
const dashboardStore = DashboardConfigurationStore()

const loading = ref(true)
const sections = ref([])
const bulkRestrictOpen = ref(false)
const bulkRestrictPeers = ref([])

function onSelectPeersBulkRestrict({peers}) {
	bulkRestrictPeers.value = peers
	configurationModals.value.selectPeers.modalOpen = false
	nextTick(() => {
		bulkRestrictOpen.value = true
	})
}

function closeBulkRestrictModal() {
	bulkRestrictOpen.value = false
	bulkRestrictPeers.value = []
}

function onBulkRestrictSaved() {
	loadAll({showLoading: false})
	closeBulkRestrictModal()
}
const configurationModalSelectedPeer = ref({})
const configurationModals = ref({
	peerSetting: {modalOpen: false},
	peerQRCode: {modalOpen: false},
	peerScheduleJobs: {modalOpen: false},
	peerShare: {modalOpen: false},
	peerConfigurationFile: {modalOpen: false},
	assignPeer: {modalOpen: false},
	peerDetails: {modalOpen: false},
	peerScheduleJobsAll: {modalOpen: false},
	peerScheduleJobsLogs: {modalOpen: false},
	selectPeers: {modalOpen: false},
})

/** First configuration in list (same order as sidebar); used for toolbar actions that target one interface. */
const primaryToolbarConfiguration = computed(() => {
	if (!sections.value.length) return null
	return sections.value[0].configurationInfo
})

const primaryToolbarPeers = computed(() => {
	if (!primaryToolbarConfiguration.value) return []
	const sec = sections.value.find(
		(s) => s.configurationInfo.Name === primaryToolbarConfiguration.value.Name
	)
	return sec ? sec.peers : []
})

/** All peers across interfaces — same order as on-screen lists (per-interface sort). */
const allClientsPeersForSelect = computed(() =>
	sections.value.flatMap((s) => sortPeersLikePeerList(s.peers))
)

/** All interface names on Clients page — tag definitions sync to each. */
const syncPeerGroupsConfigurationNames = computed(() =>
	sections.value.map((s) => s.configurationInfo.Name)
)

/** Snapshot of PeerGroups per interface (clone) for merge when saving tags to all configs. */
const peerGroupsByConfiguration = computed(() => {
	const o = {}
	for (const sec of sections.value) {
		const pg = sec.configurationInfo.Info?.PeerGroups
		o[sec.configurationInfo.Name] = pg ? JSON.parse(JSON.stringify(pg)) : {}
	}
	return o
})

/** Refresh list data without hiding the header (avoids unmounting Tags popup while saving). */
const afterPeerGroupsSynced = async () => {
	await loadAll({ showLoading: false })
}

const peerFilter = computed({
	get() {
		return wireguardStore.searchString ?? ""
	},
	set(v) {
		wireguardStore.searchString = v
	},
})

const loadAll = async (options = {}) => {
	const showLoading = options.showLoading !== false
	if (showLoading) {
		loading.value = true
	}
	try {
		await wireguardStore.getConfigurations()
		const names = wireguardStore.sortConfigurations.map((c) => c.Name)
		const results = await Promise.all(
			names.map(
				(name) =>
					new Promise((resolve) => {
						fetchGet(
							"/api/getWireguardConfigurationInfo",
							{configurationName: name},
							(res) => {
								if (res.status) {
									const peers = [...res.data.configurationPeers]
									peers.forEach((p) => {
										p.restricted = false
									})
									res.data.configurationRestrictedPeers.forEach((x) => {
										x.restricted = true
										peers.push(x)
									})
									peers.forEach((p) => {
										if (!p.configuration) {
											p.configuration = res.data.configurationInfo
										}
									})
									resolve({
										configurationInfo: res.data.configurationInfo,
										peers,
									})
								} else resolve(null)
							}
						)
					})
			)
		)
		sections.value = results.filter(Boolean)
	} finally {
		if (showLoading) {
			loading.value = false
		}
	}
}

await loadAll()

let fetchInterval
const setFetchInterval = () => {
	clearInterval(fetchInterval)
	fetchInterval = setInterval(
		loadAll,
		parseInt(dashboardStore.Configuration.Server.dashboard_refresh_interval, 10)
	)
}
setFetchInterval()
onBeforeUnmount(() => {
	clearInterval(fetchInterval)
})
watch(
	() => dashboardStore.Configuration.Server.dashboard_refresh_interval,
	() => {
		setFetchInterval()
	}
)

/** Same tag visibility rules as peerList.vue (HiddenTags + Show All Peers switch). */
function hiddenPeerIdsForConfiguration(configurationInfo) {
	const ids = []
	const pg = configurationInfo?.Info?.PeerGroups ?? {}
	for (const tagKey of wireguardStore.Filter.HiddenTags) {
		const list = pg[tagKey]?.Peers
		if (Array.isArray(list)) {
			ids.push(...list)
		}
	}
	return ids
}

function taggedPeerIdsForConfiguration(configurationInfo) {
	const pg = configurationInfo?.Info?.PeerGroups ?? {}
	return Object.values(pg).flatMap((g) => (Array.isArray(g?.Peers) ? g.Peers : []))
}

function peerPassesClientsTagFilter(peer, configurationInfo) {
	if (hiddenPeerIdsForConfiguration(configurationInfo).includes(peer.id)) {
		return false
	}
	if (wireguardStore.Filter.ShowAllPeersWhenHiddenTags) {
		return true
	}
	return taggedPeerIdsForConfiguration(configurationInfo).includes(peer.id)
}

/** Match peerList.vue ordering so Sort By applies to every interface block on Clients. */
function firstAllowedIPCount(allowed_ip) {
	try {
		return parseCidr(allowed_ip.replace(" ", "").split(",")[0]).start
	} catch {
		return 0
	}
}

function sortPeersLikePeerList(peers) {
	const sortKey = dashboardStore.Configuration.Server.dashboard_sort
	const copy = [...peers]
	if (sortKey === "restricted") {
		return copy.sort((a, b) => {
			if (a[sortKey] < b[sortKey]) {
				return 1
			}
			if (a[sortKey] > b[sortKey]) {
				return -1
			}
			return 0
		})
	}
	if (sortKey === "allowed_ip") {
		return copy.sort((a, b) => {
			if (
				firstAllowedIPCount(a[sortKey]) <
				firstAllowedIPCount(b[sortKey])
			) {
				return -1
			}
			if (
				firstAllowedIPCount(a[sortKey]) >
				firstAllowedIPCount(b[sortKey])
			) {
				return 1
			}
			return 0
		})
	}
	return copy.sort((a, b) => {
		if (a[sortKey] < b[sortKey]) {
			return -1
		}
		if (a[sortKey] > b[sortKey]) {
			return 1
		}
		return 0
	})
}

const filteredSections = computed(() => {
	const s = (wireguardStore.searchString || "").trim().toLowerCase()
	return sections.value
		.map((sec) => {
			const hadPeersFromApi = sec.peers.length > 0
			let peers = !s
				? sec.peers
				: sec.peers.filter((p) => {
						return (
							(p.name && p.name.toLowerCase().includes(s)) ||
							(p.id && p.id.toLowerCase().includes(s)) ||
							(p.allowed_ip && p.allowed_ip.toLowerCase().includes(s))
						)
					})
			peers = peers.filter((p) => peerPassesClientsTagFilter(p, sec.configurationInfo))
			peers = sortPeersLikePeerList(peers)
			return {...sec, peers, hadPeersFromApi}
		})
		.filter(
			(sec) => sec.peers.length > 0 || (!s && !sec.hadPeersFromApi)
		)
		.map(({hadPeersFromApi: _h, ...sec}) => sec)
})

const detailsSelectedPeer = computed(() => {
	if (!configurationModalSelectedPeer.value?.id) return undefined
	for (const sec of sections.value) {
		const p = sec.peers.find((x) => x.id === configurationModalSelectedPeer.value.id)
		if (p) return p
	}
	return configurationModalSelectedPeer.value
})
</script>

<template>
	<div class="mt-md-5 mt-3 text-body w-100 pb-2">
		<div class="container-fluid">
			<div
				class="d-flex mb-4 clients-page-title align-items-md-center gap-2 flex-column flex-md-row"
			>
				<h2 class="text-body d-flex mb-0 fw-semibold">
					<LocaleText t="Client List Management"></LocaleText>
				</h2>
			</div>
			<ClientsNetworkOverview />
			<div class="w-100 card rounded-3">
				<div class="overflow-y-auto clients-peer-scroll d-flex flex-column">
					<div
						class="flex-shrink-0 border-bottom clients-header-sticky bg-body-tertiary rounded-top-3"
						style="border-top-right-radius: 0 !important"
					>
						<div
							class="d-flex flex-wrap align-items-center gap-2 px-3 py-3 clients-header-toolbar"
						>
							<div class="d-flex align-items-center gap-2 clients-header-search flex-shrink-0">
								<label for="searchPeersAll"><i class="bi bi-search me-2"></i></label>
								<input
									id="searchPeersAll"
									v-model="peerFilter"
									class="form-control rounded-3 form-control-sm"
									:placeholder="GetLocale('Search Peers...')"
									type="search"
									style="width: auto; min-width: 200px; max-width: 280px"
								/>
							</div>
							<div
								v-if="!loading && sections.length > 0 && primaryToolbarConfiguration"
								class="clients-header-peersearch flex-grow-1 ms-md-auto"
							>
								<PeerSearch
									embedded
									hide-download-all
									:configuration="primaryToolbarConfiguration"
									sync-peer-groups-to-all
									:sync-peer-groups-configuration-names="syncPeerGroupsConfigurationNames"
									:peer-groups-by-configuration="peerGroupsByConfiguration"
									@jobsAll="configurationModals.peerScheduleJobsAll.modalOpen = true"
									@selectPeers="configurationModals.selectPeers.modalOpen = true"
									@peer-groups-updated="afterPeerGroupsSynced"
								/>
							</div>
						</div>
					</div>
					<div class="p-3 flex-grow-1 clients-peer-list">
						<div v-if="loading" class="text-muted py-5 text-center">
							<div class="spinner-border" role="status">
								<span class="visually-hidden">Loading</span>
							</div>
						</div>
						<template v-else>
							<div
								v-for="sec in filteredSections"
								:key="sec.configurationInfo.Name"
								class="mb-5"
							>
								<div
									class="d-flex flex-wrap align-items-center gap-2 mb-3 pb-2 border-bottom"
								>
									<div class="d-flex align-items-center gap-3 flex-wrap">
										<h5 class="mb-0">
											<ProtocolBadge
												:protocol="sec.configurationInfo.Protocol"
											></ProtocolBadge>
										</h5>
										<h4 class="mb-0">
											<samp>{{ sec.configurationInfo.Name }}</samp>
										</h4>
										<div
											class="dot"
											:class="{active: sec.configurationInfo.Status}"
										></div>
									</div>
									<RouterLink
										:to="`/configuration/${sec.configurationInfo.Name}/peers`"
										class="btn btn-sm bg-primary-subtle text-primary-emphasis rounded-3 border border-primary-subtle ms-auto"
									>
										<i class="bi bi-box-arrow-up-right me-1"></i>
										<LocaleText t="Open configuration"></LocaleText>
									</RouterLink>
								</div>
								<div v-if="sec.peers.length === 0" class="text-muted small py-2">
									<LocaleText t="No peers in this configuration"></LocaleText>
								</div>
								<div v-else class="row gx-2 gy-2">
									<div
										v-for="(peer, order) in sec.peers"
										:key="sec.configurationInfo.Name + '_' + peer.id"
										class="col-12"
										:class="{
											'col-lg-6 col-xl-4':
												dashboardStore.Configuration.Server
													.dashboard_peer_list_display === 'grid',
										}"
									>
										<Peer
											menu-prefer-down
											:Peer="peer"
											:ConfigurationInfo="sec.configurationInfo"
											:order="order"
											:searchPeersLength="sec.peers.length"
											@details="
												configurationModals.peerDetails.modalOpen = true;
												configurationModalSelectedPeer = peer;
											"
											@share="
												configurationModals.peerShare.modalOpen = true;
												configurationModalSelectedPeer = peer;
											"
											@refresh="loadAll()"
											@jobs="
												configurationModals.peerScheduleJobs.modalOpen = true;
												configurationModalSelectedPeer = peer;
											"
											@setting="
												configurationModals.peerSetting.modalOpen = true;
												configurationModalSelectedPeer = peer;
											"
											@qrcode="
												configurationModalSelectedPeer = peer;
												configurationModals.peerQRCode.modalOpen = true;
											"
											@configurationFile="
												configurationModalSelectedPeer = peer;
												configurationModals.peerConfigurationFile.modalOpen = true;
											"
											@assign="
												configurationModalSelectedPeer = peer;
												configurationModals.assignPeer.modalOpen = true;
											"
										/>
									</div>
								</div>
							</div>
							<p
								v-if="filteredSections.length === 0"
								class="text-muted text-center py-5 mb-0"
							>
								<LocaleText t="No peers match your search"></LocaleText>
							</p>
						</template>
					</div>
				</div>
			</div>
		</div>
		<TransitionGroup name="zoom">
			<PeerJobsAllModal
				v-if="configurationModals.peerScheduleJobsAll.modalOpen"
				key="ClientsPeerJobsAllModal"
				:configurationPeers="primaryToolbarPeers"
				@refresh="loadAll()"
				@allLogs="configurationModals.peerScheduleJobsLogs.modalOpen = true"
				@close="configurationModals.peerScheduleJobsAll.modalOpen = false"
			/>
			<PeerJobsLogsModal
				v-if="
					configurationModals.peerScheduleJobsLogs.modalOpen &&
					primaryToolbarConfiguration
				"
				key="ClientsPeerJobsLogsModal"
				:configurationInfo="primaryToolbarConfiguration"
				@close="configurationModals.peerScheduleJobsLogs.modalOpen = false"
			/>
		</TransitionGroup>
		<SelectPeersModal
			v-if="configurationModals.selectPeers.modalOpen && sections.length > 0"
			show-bulk-restrict
			:configurationPeers="allClientsPeersForSelect"
			@refresh="loadAll()"
			@bulk-restrict="onSelectPeersBulkRestrict"
			@close="configurationModals.selectPeers.modalOpen = false"
		/>
		<Transition name="zoom">
			<SelectPeersBulkRestrictModal
				v-if="bulkRestrictOpen && bulkRestrictPeers.length > 0"
				key="SelectPeersBulkRestrictModal"
				:peers="bulkRestrictPeers"
				@close="closeBulkRestrictModal"
				@saved="onBulkRestrictSaved"
			/>
		</Transition>
		<PeerListModals
			:configurationModals="configurationModals"
			:configurationModalSelectedPeer="configurationModalSelectedPeer"
			@refresh="loadAll()"
		/>
		<Transition name="zoom">
			<PeerDetailsModal
				v-if="configurationModals.peerDetails.modalOpen && detailsSelectedPeer"
				:selectedPeer="detailsSelectedPeer"
				@close="configurationModals.peerDetails.modalOpen = false"
			/>
		</Transition>
	</div>
</template>

<style scoped>
.clients-peer-scroll {
	max-height: calc(100vh - 220px);
}

/* Sticky bar lives inside the same scroll container as peer cards so peer menus (higher z-index) stack above it */
.clients-header-sticky {
	position: sticky;
	top: 0;
	z-index: 10;
}

@media (min-width: 768px) {
	.clients-header-toolbar {
		justify-content: flex-start;
	}
}

@media (max-width: 767.98px) {
	.clients-header-peersearch {
		flex-basis: 100%;
	}
}
</style>
