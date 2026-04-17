<script setup>
import SystemStatus from "@/components/systemStatusComponents/systemStatusWidget.vue";
import DashboardWireguardOverview from "@/components/dashboardWireguardOverview.vue";
import DashboardNetworkFlow from "@/components/dashboardNetworkFlow.vue";
</script>

<template>
	<div class="mt-md-5 mt-3">
		<div class="container-fluid">
			<DashboardWireguardOverview />
			<SystemStatus />
			<DashboardNetworkFlow />
		</div>
	</div>
</template>
