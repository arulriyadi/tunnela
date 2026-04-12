<script setup>
import LocaleText from "@/components/text/localeText.vue";
import {computed, reactive, ref, useTemplateRef, watch} from "vue";
import {fetchGet, fetchPost} from "@/utilities/fetch.js";
import {useRoute} from "vue-router";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {GetLocale} from "@/utilities/locale.js";

const props = defineProps({
	configurationPeers: Array,
	/** Single-interface context (peer list). Omit on Clients when each peer has `configuration`. */
	configurationName: {
		type: String,
		default: undefined
	},
	/** Clients: show bulk “restrict after date” entry in this modal only. */
	showBulkRestrict: {
		type: Boolean,
		default: false
	}
})
const deleteConfirmation = ref(false)
const downloadConfirmation = ref(false)
const allowAccessConfirmation = ref(false)
const selectedPeers = ref([])
const selectPeersSearchInput = ref("")
/** all | restricted | not_restricted — filter daftar (tidak mengubah seleksi). */
const statusFilter = ref("all")

const togglePeers = (id) => {
	if (selectedPeers.value.find(x => x === id)){
		selectedPeers.value = selectedPeers.value.filter(x => x !== id)
	}else{
		selectedPeers.value.push(id)
	}
}

function peerMatchesStatusFilter(p) {
	if (statusFilter.value === "restricted") {
		return Boolean(p.restricted)
	}
	if (statusFilter.value === "not_restricted") {
		return !p.restricted
	}
	return true
}

const selectedRestrictedCount = computed(() => {
	return selectedPeers.value.filter((id) => {
		const p = props.configurationPeers.find((x) => x.id === id)
		return Boolean(p?.restricted)
	}).length
})

const searchPeers = computed(() => {
	if (
		deleteConfirmation.value ||
		downloadConfirmation.value ||
		allowAccessConfirmation.value
	) {
		return props.configurationPeers.filter((x) =>
			selectedPeers.value.find((y) => y === x.id)
		)
	}
	let list = (props.configurationPeers || []).filter(peerMatchesStatusFilter)
	if (selectPeersSearchInput.value.length > 0) {
		const q = selectPeersSearchInput.value
		list = list.filter((x) => {
			return (
				x.id.includes(q) ||
				(x.name && x.name.includes(q)) ||
				(x.configuration?.Name && x.configuration.Name.includes(q))
			)
		})
	}
	return list
})

const canSelectAllVisible = computed(() => {
	if (
		downloadConfirmation.value ||
		deleteConfirmation.value ||
		allowAccessConfirmation.value
	) {
		return false
	}
	return searchPeers.value.some((p) => !selectedPeers.value.includes(p.id))
})

function selectAllVisible() {
	selectedPeers.value = searchPeers.value.map((p) => p.id)
}

const showPeerInterface = computed(() => {
	const names = new Set(
		(props.configurationPeers || [])
			.map((p) => p.configuration?.Name)
			.filter(Boolean)
	)
	return names.size > 1
})

watch(selectedPeers, () => {
	if (selectedPeers.value.length === 0) {
		deleteConfirmation.value = false
		downloadConfirmation.value = false
		allowAccessConfirmation.value = false
	}
})

const route = useRoute()
const configId = computed(() => props.configurationName || route.params.id)

function configNameForPeerId(peerId) {
	const peer = props.configurationPeers.find((x) => x.id === peerId)
	return peer?.configuration?.Name || configId.value
}

const dashboardStore = DashboardConfigurationStore()
const emit = defineEmits(["refresh", "close", "bulkRestrict"])

function emitBulkRestrict() {
	const peers = selectedPeers.value
		.map((id) => {
			const p = props.configurationPeers.find((x) => x.id === id)
			return p ? JSON.parse(JSON.stringify(p)) : null
		})
		.filter(Boolean)
	emit("bulkRestrict", {peers})
	emit("close")
}
const submitting = ref(false)
const submitDelete = async () => {
	submitting.value = true
	const byConfig = {}
	for (const id of selectedPeers.value) {
		const cn = configNameForPeerId(id)
		if (!cn) {
			continue
		}
		if (!byConfig[cn]) {
			byConfig[cn] = []
		}
		byConfig[cn].push(id)
	}
	for (const cn of Object.keys(byConfig)) {
		await new Promise((resolve) => {
			fetchPost(
				`/api/deletePeers/${cn}`,
				{peers: byConfig[cn]},
				(res) => {
					dashboardStore.newMessage(
						"Server",
						res.message,
						res.status ? "success" : "danger"
					)
					resolve(res)
				}
			)
		})
	}
	selectedPeers.value = []
	deleteConfirmation.value = false
	emit("refresh")
	submitting.value = false
}

const submitAllowAccess = async () => {
	submitting.value = true
	const byConfig = {}
	for (const id of selectedPeers.value) {
		const peer = props.configurationPeers.find((x) => x.id === id)
		if (!peer?.restricted) {
			continue
		}
		const cn = configNameForPeerId(id)
		if (!cn) {
			continue
		}
		if (!byConfig[cn]) {
			byConfig[cn] = []
		}
		byConfig[cn].push(id)
	}
	for (const cn of Object.keys(byConfig)) {
		await new Promise((resolve) => {
			fetchPost(
				`/api/allowAccessPeers/${cn}`,
				{peers: byConfig[cn]},
				(res) => {
					dashboardStore.newMessage(
						"Server",
						res.message,
						res.status ? "success" : "danger"
					)
					resolve(res)
				}
			)
		})
	}
	selectedPeers.value = []
	allowAccessConfirmation.value = false
	emit("refresh")
	submitting.value = false
}

const downloaded = reactive({
	success: [],
	failed: []
})
const cardBody = useTemplateRef('card-body');
const el = useTemplateRef("sp")
const submitDownload = async () => {
	downloadConfirmation.value = true
	for (const x of selectedPeers.value) {
		const cn = configNameForPeerId(x)
		cardBody.value.scrollTo({
			top: el.value.find(y => y.dataset.id === x).offsetTop - 20,
			behavior: 'smooth'
		})
		await fetchGet("/api/downloadPeer/"+cn, {
			id: x
		}, (res) => {
			if (res.status){
				const blob = new Blob([res.data.file], { type: "text/plain" });
				const jsonObjectUrl = URL.createObjectURL(blob);
				const filename = `${res.data.fileName}.conf`;
				const anchorEl = document.createElement("a");
				anchorEl.href = jsonObjectUrl;
				anchorEl.download = filename;
				anchorEl.click();
				downloaded.success.push(x)
			}else{
				downloaded.failed.push(x)
			}
		})
	}
}
const clearDownload = () => {
	downloaded.success = []
	downloaded.failed = []
	downloadConfirmation.value = false;
}
</script>

<template>
	<div class="peerSettingContainer w-100 h-100 position-absolute top-0 start-0 overflow-y-scroll" ref="selectPeersContainer">
		<div class="container d-flex h-100 w-100">
			<div class="m-auto modal-dialog-centered dashboardModal" style="width: 700px">
				<div class="card rounded-3 shadow flex-grow-1">
					<div class="card-header bg-transparent d-flex align-items-center gap-2 p-4 flex-column pb-3">
						<div class="mb-2 w-100 d-flex">
							<h4 class="mb-0">
								<LocaleText t="Select Peers"></LocaleText>
							</h4>
							<button type="button" class="btn-close ms-auto"
							        @click="emit('close')"></button>
						</div>
						<div class="d-flex w-100 align-items-center gap-2 flex-wrap">
							<div class="d-flex gap-3 align-items-center">
								<a
									role="button"
									v-if="canSelectAllVisible"
									class="text-decoration-none text-body"
									@click="selectAllVisible"
								>
									<small>
										<i class="bi bi-check-all me-2"></i>
										<LocaleText t="Select All"></LocaleText>
									</small>
								</a>
								<a
									role="button"
									class="text-decoration-none text-body"
									@click="selectedPeers = []"
									v-if="
										selectedPeers.length > 0 &&
										!downloadConfirmation &&
										!allowAccessConfirmation &&
										!deleteConfirmation
									"
								>
									<small>
										<i class="bi bi-x-circle-fill me-2"></i>
										<LocaleText t="Clear Selection"></LocaleText>
									</small>
								</a>
							</div>
							<div
								class="d-flex align-items-center gap-2 ms-auto flex-wrap justify-content-end"
							>
								<label class="small text-muted mb-0 d-flex align-items-center gap-1">
									<LocaleText t="Status"></LocaleText>
									<select
										v-model="statusFilter"
										class="form-select form-select-sm rounded-3"
										style="width: auto; min-width: 9rem"
										:disabled="
											deleteConfirmation ||
											downloadConfirmation ||
											allowAccessConfirmation
										"
									>
										<option value="all">{{ GetLocale("All Peers") }}</option>
										<option value="restricted">
											{{ GetLocale("Restricted") }}
										</option>
										<option value="not_restricted">
											{{ GetLocale("Not restricted") }}
										</option>
									</select>
								</label>
								<label class="mb-0" for="selectPeersSearchInput">
									<i class="bi bi-search"></i>
								</label>
								<input
									id="selectPeersSearchInput"
									v-model="selectPeersSearchInput"
									class="form-control form-control-sm rounded-3"
									style="width: 200px !important"
									type="text"
								/>
							</div>
						</div>
					</div>
					<div class="card-body px-4 flex-grow-1 d-flex gap-2 flex-column position-relative" 
					     ref="card-body"
					     style="overflow-y: scroll">
						<button
							type="button"
							class="btn w-100 peerBtn text-start rounded-3 d-flex align-items-center gap-2"
							:class="{
								active: selectedPeers.find((x) => x === p.id),
								'border-warning': p.restricted,
							}"
							@click="togglePeers(p.id)"
							:key="p.id"
							:disabled="
								deleteConfirmation ||
								downloadConfirmation ||
								allowAccessConfirmation
							"
							ref="sp"
							:data-id="p.id"
							v-for="p in searchPeers"
						>
							<span v-if="!downloadConfirmation">
								<i
									class="bi"
									:class="[
										selectedPeers.find((x) => x === p.id)
											? 'bi-check-circle-fill'
											: 'bi-circle',
									]"
								></i>
							</span>
							<span class="d-flex flex-column flex-grow-1 min-w-0">
								<small class="fw-bold text-truncate">
									{{ p.name ? p.name : GetLocale("Untitled Peer") }}
									<samp
										v-if="showPeerInterface && p.configuration?.Name"
										class="ms-2 text-muted fw-normal"
									>{{ p.configuration.Name }}</samp>
								</small>
								<small class="text-muted text-truncate">
									<samp>{{ p.id }}</samp>
								</small>
							</span>
							<span
								v-if="!downloadConfirmation"
								class="flex-shrink-0 ms-1 text-end select-peer-status"
							>
								<span
									v-if="p.restricted"
									class="badge rounded-pill text-bg-warning small fw-normal"
								>
									<i class="bi bi-lock-fill me-1"></i>
									<LocaleText t="Access Restricted"></LocaleText>
								</span>
								<span
									v-else
									class="badge rounded-pill small fw-normal"
									:class="
										p.status === 'running'
											? 'text-bg-success'
											: 'text-bg-secondary'
									"
								>
									<i
										class="bi me-1"
										:class="
											p.status === 'running'
												? 'bi-wifi'
												: 'bi-wifi-off'
										"
									></i>
									<LocaleText
										v-if="p.status === 'running'"
										t="Connected"
									></LocaleText>
									<LocaleText v-else t="Disconnected"></LocaleText>
								</span>
							</span>
							<span v-if="downloadConfirmation" class="ms-auto">
								<span class="spinner-border spinner-border-sm" role="status"
								     v-if="!downloaded.success.find(x => x === p.id) && !downloaded.failed.find(x => x === p.id)">
								</span>
								<i class="bi"
								   v-else
								   :class="[downloaded.failed.find(x => x === p.id) ? 'bi-x-circle-fill':'bi-check-circle-fill']"
								></i>
							</span>
						</button>
					</div>
					<div class="card-footer px-4 py-3 gap-2 d-flex flex-wrap align-items-center">
						<template
							v-if="
								!deleteConfirmation &&
								!downloadConfirmation &&
								!allowAccessConfirmation
							"
						>
							<button class="btn bg-primary-subtle text-primary-emphasis border-primary-subtle rounded-3"
							        :disabled="selectedPeers.length === 0 || submitting"
							        @click="submitDownload()"
							>
								<i class="bi bi-download"></i>
							</button>
							<button
								v-if="selectedRestrictedCount > 0"
								type="button"
								class="btn bg-success-subtle text-success-emphasis border border-success-subtle rounded-3"
								:disabled="submitting"
								:title="GetLocale('Allow Access')"
								@click="allowAccessConfirmation = true"
							>
								<i class="bi bi-unlock"></i>
							</button>
							<button
								v-if="showBulkRestrict && selectedPeers.length > 0"
								type="button"
								class="btn bg-warning-subtle text-warning-emphasis border border-warning-subtle rounded-3"
								:disabled="submitting"
								:title="GetLocale('Bulk restrict after date')"
								@click="emitBulkRestrict"
							>
								<i class="bi bi-calendar-event"></i>
							</button>
							<span v-if="selectedPeers.length > 0" class="flex-grow-1 text-center">
								<i class="bi bi-check-circle-fill me-2"></i>
								<LocaleText :t="selectedPeers.length + ' Peer' + (selectedPeers.length > 1 ? 's':'')"></LocaleText>
							</span>
							<button class="btn bg-danger-subtle text-danger-emphasis border-danger-subtle ms-auto rounded-3"
							        @click="deleteConfirmation = true"
							        :disabled="selectedPeers.length === 0 || submitting"
							>
								<i class="bi bi-trash"></i>
							</button>
						</template>
						<template v-else-if="downloadConfirmation">
							<strong v-if="downloaded.failed.length + downloaded.success.length < selectedPeers.length" class="flex-grow-1 text-center">
								<LocaleText t="Downloading" /> <LocaleText :t="selectedPeers.length + ' Peer' + (selectedPeers.length > 1 ? 's':'')"></LocaleText>...
							</strong>
							<template v-else>
								<strong>
									<LocaleText t="Download Finished"></LocaleText>
								</strong>
								<button 
									@click="clearDownload()"
									class="btn bg-secondary-subtle text-secondary-emphasis border border-secondary-subtle rounded-3 ms-auto">
									<LocaleText t="Done"></LocaleText>
								</button>
							</template>
						</template>
						<template v-else-if="allowAccessConfirmation">
							<button
								class="btn btn-success rounded-3"
								:disabled="selectedRestrictedCount === 0 || submitting"
								@click="submitAllowAccess()"
							>
								<LocaleText t="Yes"></LocaleText>
							</button>
							<strong
								v-if="selectedRestrictedCount > 0"
								class="flex-grow-1 text-center small"
							>
								{{
									GetLocale(
										`Are you sure to allow access for ${selectedRestrictedCount} restricted peer(s)?`
									)
								}}
							</strong>
							<button
								class="btn bg-secondary-subtle text-secondary-emphasis border border-secondary-subtle ms-auto rounded-3"
								:disabled="submitting"
								@click="allowAccessConfirmation = false"
							>
								<LocaleText t="No"></LocaleText>
							</button>
						</template>
						<template v-else-if="deleteConfirmation">
							<button class="btn btn-danger rounded-3"
							        :disabled="selectedPeers.length === 0 || submitting"
							        @click="submitDelete()"
							>
								<LocaleText t="Yes"></LocaleText>
							</button>
							<strong v-if="selectedPeers.length > 0" class="flex-grow-1 text-center">
								<LocaleText t="Are you sure to delete"></LocaleText> <LocaleText :t="selectedPeers.length + ' Peer' + (selectedPeers.length > 1 ? 's':'')"></LocaleText>?
							</strong>
							<button class="btn bg-secondary-subtle text-secondary-emphasis border border-secondary-subtle ms-auto rounded-3"
							        :disabled="selectedPeers.length === 0 || submitting"
							        @click="deleteConfirmation = false"
							>
								<LocaleText t="No"></LocaleText>
							</button>
						</template>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
	.card{
		height: 100%;
	}
	
	.dashboardModal{
		height: calc(100% - 1rem) !important;
	}
	
	@media screen and (min-height: 700px) {
		.card{
			height: 700px;
		}
	}
	
	.peerBtn{
		border: var(--bs-border-width) solid var(--bs-border-color);
	}
	.peerBtn.active{
		border: var(--bs-border-width) solid var(--bs-body-color);
	}
	
</style>