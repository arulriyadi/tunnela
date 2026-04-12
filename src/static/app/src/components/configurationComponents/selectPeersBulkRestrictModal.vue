<script setup>
import {ref, computed, watch} from "vue";
import LocaleText from "@/components/text/localeText.vue";
import {VueDatePicker} from "@vuepic/vue-datepicker";
import "@vuepic/vue-datepicker/dist/main.css";
import dayjs from "dayjs";
import {v4 as uuidv4} from "uuid";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {getUrl, getHeaders} from "@/utilities/fetch.js";
import {GetLocale} from "@/utilities/locale.js";

const props = defineProps({
	/** Full peer objects (id, name, configuration, jobs, …) from Select Peers. */
	peers: {
		type: Array,
		required: true,
	},
})

const emit = defineEmits(["close", "saved"])

const dashboardStore = DashboardConfigurationStore()
const restrictAfter = ref(null)
const applying = ref(false)
/** Set / Change / Remove — semua mode. */
const activeMode = ref("set")
/** Remove tab: user must confirm before bulk delete. */
const confirmRemove = ref(false)
/** Set tab: delete existing date/lgt/restrict jobs before creating a new one. */
const replaceExistingBulkRestrict = ref(false)

function isBulkRestrictJob(job) {
	return (
		job &&
		job.Field === "date" &&
		job.Operator === "lgt" &&
		job.Action === "restrict"
	)
}

function bulkRestrictJobsForPeer(peer) {
	const list = Array.isArray(peer.jobs) ? peer.jobs : []
	return list.filter(isBulkRestrictJob)
}

/** Peers yang punya ≥1 job date/lgt/restrict — dipakai Change & Remove. */
const bulkRestrictPlan = computed(() => {
	const rows = []
	let peersWithout = 0
	for (const peer of props.peers) {
		const jobs = bulkRestrictJobsForPeer(peer)
		if (jobs.length) {
			rows.push({peer, jobs})
		} else {
			peersWithout++
		}
	}
	const totalJobs = rows.reduce((acc, r) => acc + r.jobs.length, 0)
	return {rows, totalJobs, peersWithout}
})

watch(activeMode, (m) => {
	if (m !== "remove") {
		confirmRemove.value = false
	}
	if (m !== "set") {
		replaceExistingBulkRestrict.value = false
	}
})

const applyToPeersButtonLabel = computed(() => {
	const n = props.peers.length
	return n === 1
		? `Apply to ${n} peer`
		: `Apply to ${n} peers`
})

const updateJobsButtonLabel = computed(() => {
	const n = bulkRestrictPlan.value.totalJobs
	return n === 1 ? `Update ${n} job` : `Update ${n} jobs`
})

const removeJobsButtonLabel = computed(() => {
	const n = bulkRestrictPlan.value.totalJobs
	return n === 1 ? `Remove from ${n} job` : `Remove from ${n} jobs`
})

const interfaceSummary = computed(() => {
	const by = {}
	for (const p of props.peers) {
		const name = p.configuration?.Name ?? "?"
		by[name] = (by[name] || 0) + 1
	}
	return Object.entries(by)
		.map(([name, c]) => `${name}: ${c}`)
		.join(", ")
})

async function saveJobForPeer(peer, valueFormatted) {
	const cfg = peer.configuration?.Name
	const peerId = peer.id
	if (!cfg || !peerId) {
		return {
			ok: false,
			message: GetLocale("Missing configuration or peer id"),
		}
	}
	const job = {
		JobID: uuidv4(),
		Configuration: cfg,
		Peer: peerId,
		Field: "date",
		Operator: "lgt",
		Value: valueFormatted,
		CreationDate: "",
		ExpireDate: "",
		Action: "restrict",
	}
	try {
		const r = await fetch(getUrl("/api/savePeerScheduleJob"), {
			method: "POST",
			headers: getHeaders(),
			credentials: "same-origin",
			body: JSON.stringify({Job: job}),
		})
		let res = {}
		try {
			res = await r.json()
		} catch {
			res = {}
		}
		if (r.ok && res.status) {
			return {ok: true, message: ""}
		}
		return {
			ok: false,
			message: res.message || r.statusText || "savePeerScheduleJob failed",
		}
	} catch (e) {
		return {ok: false, message: e?.message || "network error"}
	}
}

async function deleteScheduleJob(job) {
	try {
		const r = await fetch(getUrl("/api/deletePeerScheduleJob"), {
			method: "POST",
			headers: getHeaders(),
			credentials: "same-origin",
			body: JSON.stringify({Job: job}),
		})
		let res = {}
		try {
			res = await r.json()
		} catch {
			res = {}
		}
		if (r.ok && res.status) {
			return {ok: true, message: ""}
		}
		return {
			ok: false,
			message: res.message || r.statusText || "deletePeerScheduleJob failed",
		}
	} catch (e) {
		return {ok: false, message: e?.message || "network error"}
	}
}

/** Update job yang sudah ada: JobID tetap, Value baru (backend `saveJob` branch update). */
async function saveJobUpdateJob(job, valueFormatted) {
	const base = JSON.parse(JSON.stringify(job))
	const payload = {
		...base,
		Field: "date",
		Operator: "lgt",
		Action: "restrict",
		Value: valueFormatted,
	}
	try {
		const r = await fetch(getUrl("/api/savePeerScheduleJob"), {
			method: "POST",
			headers: getHeaders(),
			credentials: "same-origin",
			body: JSON.stringify({Job: payload}),
		})
		let res = {}
		try {
			res = await r.json()
		} catch {
			res = {}
		}
		if (r.ok && res.status) {
			return {ok: true, message: ""}
		}
		return {
			ok: false,
			message: res.message || r.statusText || "savePeerScheduleJob failed",
		}
	} catch (e) {
		return {ok: false, message: e?.message || "network error"}
	}
}

async function onApplySet() {
	if (!restrictAfter.value) {
		dashboardStore.newMessage(
			"WGDashboard",
			"Please choose a date and time.",
			"warning"
		)
		return
	}
	const valueFormatted = dayjs(restrictAfter.value).format("YYYY-MM-DD HH:mm:ss")
	applying.value = true
	let ok = 0
	let fail = 0
	const errors = []
	for (const peer of props.peers) {
		if (replaceExistingBulkRestrict.value) {
			const existing = bulkRestrictJobsForPeer(peer)
			let delFail = false
			for (const j of existing) {
				const del = await deleteScheduleJob(j)
				if (!del.ok) {
					delFail = true
					const label = peer.name || peer.id
					errors.push(`${label}: ${del.message}`)
				}
			}
			if (delFail && existing.length) {
				fail++
				continue
			}
		}
		const result = await saveJobForPeer(peer, valueFormatted)
		if (result.ok) {
			ok++
		} else {
			fail++
			const label = peer.name || peer.id
			errors.push(`${label}: ${result.message}`)
		}
	}
	applying.value = false
	if (ok > 0 && fail === 0) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale(
				`Scheduled restrict after ${valueFormatted} for ${ok} peer(s).`
			),
			"success"
		)
	} else if (ok > 0 && fail > 0) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale(
				`Partial: ${ok} saved, ${fail} failed. ${errors.slice(0, 3).join("; ")}`
			),
			"warning"
		)
	} else {
		dashboardStore.newMessage(
			"Server",
			errors.length
				? errors.slice(0, 5).join("; ")
				: GetLocale("Could not save schedule jobs."),
			"danger"
		)
	}
	if (ok > 0) {
		emit("saved", {success: ok, failed: fail})
	}
}

async function onApplyChange() {
	if (!restrictAfter.value) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale("Please choose a date and time."),
			"warning"
		)
		return
	}
	const {rows, totalJobs} = bulkRestrictPlan.value
	if (totalJobs === 0) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale(
				"No matching restrict-after jobs to change. Refresh the client list if schedules are missing."
			),
			"warning"
		)
		return
	}
	const valueFormatted = dayjs(restrictAfter.value).format("YYYY-MM-DD HH:mm:ss")
	applying.value = true
	let ok = 0
	let fail = 0
	const errors = []
	for (const {peer, jobs} of rows) {
		for (const job of jobs) {
			const result = await saveJobUpdateJob(job, valueFormatted)
			if (result.ok) {
				ok++
			} else {
				fail++
				const label = peer.name || peer.id
				const jid = (job.JobID || "").slice(0, 8)
				errors.push(
					jid
						? `${label} (${jid}…): ${result.message}`
						: `${label}: ${result.message}`
				)
			}
		}
	}
	applying.value = false
	if (ok > 0 && fail === 0) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale(`Updated ${ok} scheduled restrict job(s) to ${valueFormatted}.`),
			"success"
		)
	} else if (ok > 0 && fail > 0) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale(
				`Partial: ${ok} updated, ${fail} failed. ${errors.slice(0, 3).join("; ")}`
			),
			"warning"
		)
	} else {
		dashboardStore.newMessage(
			"Server",
			errors.length
				? errors.slice(0, 5).join("; ")
				: GetLocale("Could not update schedule jobs."),
			"danger"
		)
	}
	if (ok > 0) {
		emit("saved", {success: ok, failed: fail})
	}
}

async function onApplyRemove() {
	const {rows, totalJobs} = bulkRestrictPlan.value
	if (totalJobs === 0) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale("No matching restrict-after jobs to remove. Refresh the client list if schedules are missing."),
			"warning"
		)
		return
	}
	if (!confirmRemove.value) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale("Please confirm removal below."),
			"warning"
		)
		return
	}
	applying.value = true
	let ok = 0
	let fail = 0
	const errors = []
	for (const {peer, jobs} of rows) {
		for (const job of jobs) {
			const result = await deleteScheduleJob(job)
			if (result.ok) {
				ok++
			} else {
				fail++
				const label = peer.name || peer.id
				const jid = (job.JobID || "").slice(0, 8)
				errors.push(
					jid
						? `${label} (${jid}…): ${result.message}`
						: `${label}: ${result.message}`
				)
			}
		}
	}
	applying.value = false
	if (ok > 0 && fail === 0) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale(`Removed ${ok} scheduled restrict job(s).`),
			"success"
		)
	} else if (ok > 0 && fail > 0) {
		dashboardStore.newMessage(
			"WGDashboard",
			GetLocale(
				`Partial: ${ok} removed, ${fail} failed. ${errors.slice(0, 3).join("; ")}`
			),
			"warning"
		)
	} else {
		dashboardStore.newMessage(
			"Server",
			errors.length
				? errors.slice(0, 5).join("; ")
				: GetLocale("Could not remove schedule jobs."),
			"danger"
		)
	}
	if (ok > 0) {
		emit("saved", {success: ok, failed: fail})
	}
}
</script>

<template>
	<div
		class="peerSettingContainer w-100 h-100 position-absolute top-0 start-0 overflow-y-scroll"
		style="z-index: 1050"
	>
		<div class="container d-flex h-100 w-100">
			<div class="m-auto modal-dialog-centered dashboardModal" style="width: 520px">
				<div class="card rounded-3 shadow flex-grow-1">
					<div class="card-header bg-transparent border-0 p-4 pb-2">
						<div class="d-flex align-items-center gap-2">
							<h4 class="mb-0 fw-normal">
								<LocaleText t="Restrict peers after date"></LocaleText>
							</h4>
							<button
								type="button"
								class="btn-close ms-auto"
								aria-label="Close"
								:disabled="applying"
								@click="emit('close')"
							></button>
						</div>
						<small class="text-muted d-block mt-2">
							<i class="bi bi-check-circle-fill me-1"></i>
							<template v-if="peers.length === 1">
								1 <LocaleText t="Peer"></LocaleText>
							</template>
							<template v-else>
								{{ peers.length }}
								<LocaleText t="Peers"></LocaleText>
							</template>
							<span v-if="interfaceSummary"> — {{ interfaceSummary }}</span>
						</small>
					</div>
					<div class="card-body px-4 pt-0">
						<ul class="nav nav-pills gap-2 mb-3 small">
							<li class="nav-item">
								<button
									type="button"
									class="nav-link py-1 px-3"
									:class="{active: activeMode === 'set'}"
									:disabled="applying"
									@click="activeMode = 'set'"
								>
									<LocaleText t="Set"></LocaleText>
								</button>
							</li>
							<li class="nav-item">
								<button
									type="button"
									class="nav-link py-1 px-3"
									:class="{active: activeMode === 'change'}"
									:disabled="applying"
									@click="activeMode = 'change'"
								>
									<LocaleText t="Change"></LocaleText>
								</button>
							</li>
							<li class="nav-item">
								<button
									type="button"
									class="nav-link py-1 px-3"
									:class="{active: activeMode === 'remove'}"
									:disabled="applying"
									@click="activeMode = 'remove'"
								>
									<LocaleText t="Remove"></LocaleText>
								</button>
							</li>
						</ul>

						<template v-if="activeMode === 'set'">
							<label class="form-label small text-muted mb-1">
								<LocaleText t="Restrict on or after"></LocaleText>
							</label>
							<VueDatePicker
								:is24="true"
								:min-date="new Date()"
								v-model="restrictAfter"
								time-picker-inline
								format="yyyy-MM-dd HH:mm:ss"
								preview-format="yyyy-MM-dd HH:mm:ss"
								:clearable="false"
								:disabled="applying"
								:dark="
									dashboardStore.Configuration.Server.dashboard_theme ===
									'dark'
								"
								class="w-100"
							/>
							<p class="small text-muted mt-2 mb-0">
								<LocaleText
									t="Peers will be restricted when the server time passes this moment (same as Schedule Jobs date rule)."
								></LocaleText>
							</p>
							<div class="form-check mt-3 mb-0">
								<input
									id="bulkRestrictReplaceExisting"
									v-model="replaceExistingBulkRestrict"
									class="form-check-input"
									type="checkbox"
									:disabled="applying"
								/>
								<label
									class="form-check-label small"
									for="bulkRestrictReplaceExisting"
								>
									<LocaleText
										t="Replace existing date-restrict jobs for selected peers before adding a new schedule"
									></LocaleText>
								</label>
								<p class="small text-muted mb-0 mt-1 ms-4 ps-1">
									<LocaleText
										t="If unchecked, a new job is added even when one already exists (may create duplicates)."
									></LocaleText>
								</p>
							</div>
						</template>

						<template v-else-if="activeMode === 'change'">
							<p class="small text-muted mb-2">
								<LocaleText
									t="Updates the restrict-after date for existing Date / larger than / Restrict jobs (same Job ID). Peers without such a job are skipped."
								></LocaleText>
							</p>
							<div
								v-if="bulkRestrictPlan.totalJobs > 0"
								class="alert alert-secondary py-2 small mb-2"
							>
								<strong>{{ bulkRestrictPlan.totalJobs }}</strong>
								<LocaleText t=" job(s) on "></LocaleText>
								<strong>{{ bulkRestrictPlan.rows.length }}</strong>
								<LocaleText t=" peer(s) will be updated."></LocaleText>
								<span
									v-if="bulkRestrictPlan.peersWithout > 0"
									class="d-block mt-1"
								>
									<LocaleText t="Skipped:"></LocaleText>
									{{ bulkRestrictPlan.peersWithout }}
									<LocaleText
										t=" peer(s) with no matching job."
									></LocaleText>
								</span>
							</div>
							<div v-else class="alert alert-warning py-2 small mb-2">
								<LocaleText
									t="No Date → larger than → Restrict jobs found for this selection. Reload the Clients page if you expect schedules here."
								></LocaleText>
							</div>
							<label class="form-label small text-muted mb-1">
								<LocaleText t="New restrict on or after"></LocaleText>
							</label>
							<VueDatePicker
								:is24="true"
								:min-date="new Date()"
								v-model="restrictAfter"
								time-picker-inline
								format="yyyy-MM-dd HH:mm:ss"
								preview-format="yyyy-MM-dd HH:mm:ss"
								:clearable="false"
								:disabled="applying"
								:dark="
									dashboardStore.Configuration.Server.dashboard_theme ===
									'dark'
								"
								class="w-100"
							/>
							<p class="small text-muted mt-2 mb-0">
								<LocaleText
									t="Each existing job keeps its Job ID; only the scheduled time changes."
								></LocaleText>
							</p>
						</template>

						<template v-else-if="activeMode === 'remove'">
							<p class="small text-muted mb-2">
								<LocaleText
									t="Removes automatic restrict-after schedules (Date / larger than / Restrict) for selected peers. Manual peer restrictions are not changed."
								></LocaleText>
							</p>
							<div
								v-if="bulkRestrictPlan.totalJobs > 0"
								class="alert alert-secondary py-2 small mb-2"
							>
								<strong>{{ bulkRestrictPlan.totalJobs }}</strong>
								<LocaleText t=" job(s) on "></LocaleText>
								<strong>{{ bulkRestrictPlan.rows.length }}</strong>
								<LocaleText t=" peer(s) will be removed."></LocaleText>
								<span
									v-if="bulkRestrictPlan.peersWithout > 0"
									class="d-block mt-1"
								>
									<LocaleText t="Skipped:"></LocaleText>
									{{ bulkRestrictPlan.peersWithout }}
									<LocaleText t=" peer(s) with no matching job."></LocaleText>
								</span>
							</div>
							<div v-else class="alert alert-warning py-2 small mb-2">
								<LocaleText
									t="No Date → larger than → Restrict jobs found for this selection. Reload the Clients page if you expect schedules here."
								></LocaleText>
							</div>
							<div v-if="bulkRestrictPlan.totalJobs > 0" class="form-check mb-0">
								<input
									id="bulkRestrictConfirmRemove"
									v-model="confirmRemove"
									class="form-check-input"
									type="checkbox"
									:disabled="applying"
								/>
								<label
									class="form-check-label small"
									for="bulkRestrictConfirmRemove"
								>
									<LocaleText
										t="I understand these schedule jobs will be removed."
									></LocaleText>
								</label>
							</div>
						</template>
					</div>
					<div
						class="card-footer bg-transparent border-0 px-4 py-3 d-flex flex-wrap gap-2 justify-content-end"
					>
						<button
							type="button"
							class="btn bg-secondary-subtle text-secondary-emphasis border border-secondary-subtle rounded-3"
							:disabled="applying"
							@click="emit('close')"
						>
							<LocaleText t="Cancel"></LocaleText>
						</button>
						<button
							v-if="activeMode === 'set'"
							type="button"
							class="btn bg-primary text-white rounded-3"
							:disabled="applying"
							@click="onApplySet"
						>
							<span
								v-if="applying"
								class="spinner-border spinner-border-sm me-1"
								role="status"
								aria-hidden="true"
							></span>
							<LocaleText
								:t="
									'Apply to ' +
									peers.length +
									' peer' +
									(peers.length !== 1 ? 's' : '')
								"
							></LocaleText>
						</button>
						<button
							v-else-if="activeMode === 'change'"
							type="button"
							class="btn bg-primary text-white rounded-3"
							:disabled="
								applying ||
								!restrictAfter ||
								bulkRestrictPlan.totalJobs === 0
							"
							@click="onApplyChange"
						>
							<span
								v-if="applying"
								class="spinner-border spinner-border-sm me-1"
								role="status"
								aria-hidden="true"
							></span>
							<LocaleText :t="updateJobsButtonLabel"></LocaleText>
						</button>
						<button
							v-else
							type="button"
							class="btn btn-danger rounded-3"
							:disabled="
								applying ||
								bulkRestrictPlan.totalJobs === 0 ||
								!confirmRemove
							"
							@click="onApplyRemove"
						>
							<span
								v-if="applying"
								class="spinner-border spinner-border-sm me-1"
								role="status"
								aria-hidden="true"
							></span>
							<LocaleText :t="removeJobsButtonLabel"></LocaleText>
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.dashboardModal {
	max-height: calc(100vh - 2rem);
}
.nav-pills .nav-link.active {
	background-color: var(--bs-primary);
	color: var(--bs-white);
}
</style>
