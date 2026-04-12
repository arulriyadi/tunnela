<script>
import LocaleText from "@/components/text/localeText.vue";

export default {
	name: "WireGuardConfiguration",
	components: { LocaleText },
};
</script>

<template>
	<div class="wireguard-configuration mt-md-4 mt-2 text-body">
		<div class="container-fluid px-md-4">
			<div class="row g-3 align-items-start">
				<!-- Lebar kolom sama seperti Navbar utama (col-md-3 col-lg-2) -->
				<div class="col-12 col-md-3 col-lg-2">
					<nav
						class="sidebar bg-body-tertiary border rounded-3 shadow overflow-y-scroll wg-conf-local-nav h-100">
						<div class="sidebar-sticky">
							<ul class="nav flex-column px-2 gap-1">
								<li class="nav-item">
									<RouterLink
										class="nav-link rounded-3"
										active-class="active"
										to="/wireguard_configuration/new">
										<i class="bi bi-plus-circle me-2"></i>
										<LocaleText t="New Configuration"></LocaleText>
									</RouterLink>
								</li>
								<li class="nav-item">
									<RouterLink
										class="nav-link rounded-3"
										active-class="active"
										to="/wireguard_configuration/restore">
										<i class="bi bi-cloud-upload me-2"></i>
										<LocaleText t="Restore Configuration"></LocaleText>
									</RouterLink>
								</li>
							</ul>
						</div>
					</nav>
				</div>
				<div class="col-12 col-md-9 col-lg-10 min-w-0">
					<RouterView />
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
/* Supaya panel tidak melebihi tinggi viewport di layar pendek */
.wg-conf-local-nav {
	max-height: min(100vh, 100%);
}
</style>
