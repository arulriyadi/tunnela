<script>
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {fetchPost} from "@/utilities/fetch.js";
import LocaleText from "@/components/text/localeText.vue";
import {GetLocale} from "@/utilities/locale.js";

export default {
	name: "dashboardLoginCopyright",
	components: {LocaleText},
	setup() {
		const store = DashboardConfigurationStore();
		return {store};
	},
	data() {
		return {
			textDraft: "",
			urlDraft: "",
			saving: false,
			error: "",
			success: false,
			draftsInitialized: false,
		};
	},
	computed: {
		savedText() {
			const v = this.store.Configuration?.Server?.login_copyright_text;
			return v != null ? String(v) : "";
		},
		savedUrl() {
			const v = this.store.Configuration?.Server?.login_copyright_url;
			return v != null ? String(v) : "";
		},
		versionPreview() {
			const v = this.store.Configuration?.Server?.version;
			return v != null && String(v) !== "" ? String(v) : "v4.3.3";
		},
		previewLine() {
			return (this.textDraft || "").replace(/\{version\}/g, this.versionPreview);
		},
		previewFooterParts() {
			const text = this.previewLine;
			const url = (this.urlDraft || "").trim();
			if (!url) {
				return {prefix: text, linkText: null, href: null};
			}
			const by = " by ";
			const i = text.lastIndexOf(by);
			if (i === -1) {
				return {prefix: `${text} `, linkText: "GitHub", href: url};
			}
			const rest = text.slice(i + by.length).trim();
			return {
				prefix: text.slice(0, i + by.length),
				linkText: rest || "Link",
				href: url,
			};
		},
		isDirty() {
			return (
				this.textDraft !== this.savedText ||
				this.urlDraft.trim() !== (this.savedUrl || "").trim()
			);
		},
	},
	watch: {
		"store.Configuration.Server": {
			deep: true,
			handler() {
				this.hydrateFromStore();
			},
		},
	},
	methods: {
		hydrateFromStore() {
			if (!this.store.Configuration?.Server || this.draftsInitialized) {
				return;
			}
			this.textDraft = this.savedText;
			this.urlDraft = this.savedUrl;
			this.draftsInitialized = true;
		},
		syncFromStore() {
			this.textDraft = this.savedText;
			this.urlDraft = this.savedUrl;
			this.error = "";
			this.success = false;
		},
		save() {
			this.saving = true;
			this.error = "";
			this.success = false;
			const textVal = this.textDraft;
			const urlVal = this.urlDraft.trim();
			fetchPost(
				"/api/updateDashboardConfigurationItem",
				{section: "Server", key: "login_copyright_text", value: textVal},
				(res1) => {
					if (!res1.status) {
						this.saving = false;
						this.error = res1.message || GetLocale("Save failed");
						return;
					}
					fetchPost(
						"/api/updateDashboardConfigurationItem",
						{section: "Server", key: "login_copyright_url", value: urlVal},
						(res2) => {
							this.saving = false;
							if (!res2.status) {
								this.error = res2.message || GetLocale("Save failed");
								return;
							}
							this.store.getConfiguration();
							this.success = true;
						}
					);
				}
			);
		},
	},
	mounted() {
		this.hydrateFromStore();
	},
};
</script>

<template>
	<div class="d-flex flex-column gap-3">
		<p class="text-muted small mb-0">
			<LocaleText t="Shown at the bottom of the sign-in page."></LocaleText>
			<span> </span>
			<LocaleText t="Sign-in copyright version hint"></LocaleText>
		</p>
		<div>
			<label class="form-label small text-muted mb-1">
				<LocaleText t="Copyright line"></LocaleText>
			</label>
			<input
				v-model="textDraft"
				type="text"
				class="form-control rounded-3"
				maxlength="600"
				autocomplete="off"
			/>
		</div>
		<div>
			<label class="form-label small text-muted mb-1">
				<LocaleText t="Link URL (e.g. GitHub)"></LocaleText>
			</label>
			<input
				v-model="urlDraft"
				type="url"
				class="form-control rounded-3"
				placeholder="https://"
				autocomplete="off"
			/>
			<small class="text-muted d-block mt-1">
				<LocaleText t="Leave the URL empty for plain text only. If a URL is set, the text after the last by becomes the link label."></LocaleText>
			</small>
		</div>
		<div class="rounded-3 bg-body-secondary p-3 small">
			<div class="text-muted mb-1">
				<LocaleText t="Preview"></LocaleText>
			</div>
			<span class="text-body">{{ previewFooterParts.prefix }}</span>
			<a
				v-if="previewFooterParts.href"
				:href="previewFooterParts.href"
				target="_blank"
				rel="noopener noreferrer"
			>
				<strong>{{ previewFooterParts.linkText }}</strong>
			</a>
		</div>
		<div class="d-flex flex-wrap align-items-center gap-2">
			<button
				type="button"
				class="btn btn-primary rounded-3"
				:disabled="saving || !isDirty"
				@click="save"
			>
				<span v-if="!saving"><LocaleText t="Save"></LocaleText></span>
				<span v-else class="spinner-border spinner-border-sm" role="status"></span>
			</button>
			<button
				type="button"
				class="btn btn-outline-secondary rounded-3"
				:disabled="saving || !isDirty"
				@click="syncFromStore"
			>
				<LocaleText t="Reset"></LocaleText>
			</button>
			<span v-if="error" class="text-danger small">{{ error }}</span>
			<span v-else-if="success && !isDirty" class="text-success small">
				<LocaleText t="Saved"></LocaleText>
			</span>
		</div>
	</div>
</template>

<style scoped>
</style>
