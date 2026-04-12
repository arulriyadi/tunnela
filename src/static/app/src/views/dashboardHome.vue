<script setup>
import SystemStatus from "@/components/systemStatusComponents/systemStatusWidget.vue";
import DashboardWireguardOverview from "@/components/dashboardWireguardOverview.vue";
</script>

<template>
	<div class="mt-md-5 mt-3">
		<div class="container-fluid">
			<DashboardWireguardOverview />
			<SystemStatus />
		</div>
	</div>
</template>
