<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { fade } from 'svelte/transition';
	import { api } from '$lib/api';
	import { activeIncident, logLines, servicesStore } from '$lib/stream';
	import { isOwner } from '$lib/auth';
	import { cardReceive, cardSend, contentFly } from '$lib/animation';
	import AutonomyToggle from '$lib/components/AutonomyToggle.svelte';
	import OnboardingChecklist from '$lib/components/OnboardingChecklist.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import { groupByServer, serverRollup } from '$lib/grouping';
	import type { ActiveIncidentState, Service, UserSettings } from '$lib/types';

	let settings: UserSettings | null = null;
	// Services are owned by the layout, which keeps servicesStore fresh. See #74.
	$: services = $servicesStore;
	let loading = false;
	let viewKey = 'resting';
	let logContainer: HTMLPreElement | null = null;
	let previousIncidentId: string | null = null;

	const MAX_LOG_LINES = 500;

	onMount(() => {
		api.settings.get().then((s) => (settings = s));
	});

	$: if ($activeIncident) {
		viewKey = $activeIncident.view;
	} else {
		viewKey = 'resting';
	}

	$: if ($activeIncident?.incident_id !== previousIncidentId) {
		logLines.set([]);
		previousIncidentId = $activeIncident?.incident_id ?? null;
	}

	$: if (logContainer && $logLines.length) {
		logContainer.scrollTop = logContainer.scrollHeight;
	}

	$: trimmedLogLines = $logLines.slice(-MAX_LOG_LINES);
	$: serverGroups = groupByServer(services);

	async function updateAutonomy(mode: 'auto_fix' | 'ask_first') {
		if (!settings) return;
		settings = await api.settings.update({ autonomy: mode });
	}

	async function simulate() {
		loading = true;
		try {
			await api.simulate();
		} finally {
			loading = false;
		}
	}

	async function approve() {
		if ($activeIncident?.incident_id) {
			await api.incidents.approve($activeIncident.incident_id);
		}
	}

	async function takeOver() {
		if ($activeIncident?.incident_id) {
			await api.incidents.takeOver($activeIncident.incident_id);
		}
	}

	async function handBack() {
		if ($activeIncident?.incident_id) {
			await api.incidents.handBack($activeIncident.incident_id);
		}
	}

	async function manualResolve() {
		if ($activeIncident?.incident_id) {
			await api.incidents.resolve($activeIncident.incident_id);
		}
	}

	async function backToWatching() {
		activeIncident.set(null);
	}

	function dotClasses() {
		if ($activeIncident?.view === 'asking') {
			return 'border-2 border-dashed border-surface-800';
		}
		if ($activeIncident?.view === 'takeover') {
			return 'border-2 border-dashed border-surface-400';
		}
		if ($activeIncident?.view && !['resting', 'resolved'].includes($activeIncident.view)) {
			return 'bg-surface-900 animate-pulse';
		}
		if (services.some((s) => s.status === 'down')) {
			return 'bg-danger-500';
		}
		if (services.some((s) => s.status === 'degraded')) {
			return 'bg-warning-500';
		}
		if (services.length > 0) {
			return 'bg-success-500';
		}
		return 'bg-surface-500';
	}

	// The state pill's look, as Badge props (folds the old bespoke badge into the
	// shared primitive). See #50.
	function badgeProps(view?: string): { variant: 'solid' | 'outline' | 'dashed'; tone: 'dark' | 'neutral' } {
		if (view === 'asking') return { variant: 'dashed', tone: 'dark' };
		if (view === 'takeover') return { variant: 'dashed', tone: 'neutral' };
		if (view === 'resolved') return { variant: 'outline', tone: 'neutral' };
		return { variant: 'solid', tone: 'dark' };
	}
	$: badge = badgeProps($activeIncident?.view);

	function badgeLabel() {
		if (!$activeIncident) return '';
		if ($activeIncident.view === 'asking') return '? asking';
		if ($activeIncident.view === 'takeover') return '⌐ you';
		if ($activeIncident.view === 'resolved') return '✓ recovered';
		return '● down';
	}

	function shellClasses() {
		const base = 'bg-white border rounded-card shadow-card overflow-hidden transition-colors duration-300';
		if ($activeIncident?.view === 'asking') return `${base} border-surface-800`;
		if (['detecting', 'diagnosing', 'fixing', 'verifying'].includes($activeIncident?.view || '')) {
			return `${base} border-surface-900`;
		}
		return `${base} border-surface-300`;
	}

	function summaryText() {
		const down = services.filter((s) => s.status === 'down').length;
		const degraded = services.filter((s) => s.status === 'degraded').length;
		if (down === 1) return '1 service down';
		if (down > 1) return `${down} services down`;
		if (degraded === 1) return '1 service degraded';
		if (degraded > 1) return `${degraded} services degraded`;
		return 'All services healthy';
	}

	$: statusText = $activeIncident?.status_text || summaryText();

	const actionVerb = (a?: string | null) =>
		a === 'stop_container'
			? 'stop'
			: a === 'start_container'
				? 'start'
				: a === 'register_proxy_route'
					? 're-register the proxy route for'
					: 'restart';
	const actionGerund = (a?: string | null) =>
		a === 'stop_container'
			? 'stopping'
			: a === 'start_container'
				? 'starting'
				: a === 'register_proxy_route'
					? 're-registering the proxy route for'
					: 'restarting';
	// The command Mino would run, when it hasn't supplied one of its own. A
	// proxy-route fix is a kamal-proxy deploy, not a docker verb.
	const fixCommand = (i: ActiveIncidentState) =>
		i.proposed_fix ||
		(i.proposed_action === 'register_proxy_route'
			? `kamal-proxy deploy ${i.service_name}`
			: `${i.method === 'fly' ? 'fly machine' : 'docker'} ${actionVerb(i.proposed_action)} ${i.service_name}`);
</script>

<div class="px-4 sm:px-10 py-7 sm:py-9 pb-20">
	<div class="max-w-[680px] mx-auto">
		<div class="flex flex-wrap gap-3 justify-between items-center mb-6">
			<div class="font-serif text-[22px] leading-none text-surface-900 tracking-tight">Now</div>
			<div class="inline-flex items-center gap-2.5">
				<span class="font-mono text-[11px] text-surface-500 tracking-widest uppercase">autonomy</span>
				{#if $isOwner}
					<AutonomyToggle value={settings?.autonomy || 'auto_fix'} on:change={(e) => updateAutonomy(e.detail)} />
				{:else}
					<span class="px-2 py-0.5 rounded-full bg-surface-100 text-surface-700 font-mono text-[11px]">{settings?.autonomy === 'auto_fix' ? 'auto-fix' : 'ask first'}</span>
				{/if}
			</div>
		</div>

		<div class="relative">
			{#key viewKey}
				<div
					class={shellClasses()}
					in:cardReceive={{ key: viewKey }}
					out:cardSend={{ key: viewKey }}
					aria-live="polite"
				>
					{#if !$activeIncident || $activeIncident.view === 'resting'}
						{#if $isOwner && services.length === 0}
							<div class="p-6 sm:p-10" in:contentFly|local>
								<OnboardingChecklist {settings} />
							</div>
						{:else}
						<div class="p-6 sm:p-10" in:contentFly|local>
							<div class="inline-flex items-center gap-2 font-mono text-xs text-surface-500 tracking-wide">
										<span class="w-2 h-2 rounded-full {dotClasses()}"></span>
								{statusText}
							</div>
							<div class="mt-7 font-serif text-display text-surface-900 tracking-tight">Everything's fine.</div>
							<div class="mt-4 font-sans text-base leading-relaxed text-surface-600">
								{summaryText()} · watching <strong class="font-semibold text-surface-900">{services.length} service{services.length === 1 ? '' : 's'}</strong>
								{#if serverGroups.length > 1}across <strong class="font-semibold text-surface-900">{serverGroups.length} servers</strong>{/if}.
							</div>
							{#if serverGroups.length > 0}
								<div class="mt-5 flex flex-col divide-y divide-surface-100 border-t border-b border-surface-100">
									{#each serverGroups as group (group.name)}
										<button
											type="button"
											class="flex items-center justify-between gap-3 py-2.5 bg-transparent border-none cursor-pointer text-left hover:opacity-70"
											on:click={() => goto('/fleet')}
										>
											<span class="flex items-center gap-2.5 min-w-0">
												<span class="w-1.5 h-1.5 rounded-full flex-shrink-0 {group.down ? 'bg-danger-500' : group.degraded ? 'bg-surface-400' : 'bg-surface-300'}"></span>
												<span class="font-mono text-[13px] text-surface-800 truncate">{group.name}</span>
												<span class="font-sans text-[11px] text-surface-400">{group.services.length} service{group.services.length === 1 ? '' : 's'}</span>
											</span>
											<span class="font-mono text-[11px] flex-shrink-0 {group.down ? 'text-danger-600' : group.degraded ? 'text-surface-600' : 'text-surface-400'}">{serverRollup(group)}</span>
										</button>
									{/each}
								</div>
							{/if}
							{#if $isOwner}
								<div class="mt-7 pt-5 border-t border-surface-200">
									<button
										class="bg-transparent border-none cursor-pointer font-mono text-xs text-surface-500 underline underline-offset-[3px] decoration-surface-400 hover:text-surface-900 disabled:opacity-50"
										on:click={simulate}
										disabled={loading}
									>
										▸ {loading ? 'stopping a container…' : 'stop a container to test recovery'}
									</button>
								</div>
							{/if}
						</div>
						{/if}
					{:else if $activeIncident.view === 'asking'}
						<div class="p-5 sm:p-9" in:contentFly|local>
							<div class="flex justify-between items-start gap-4">
								<div class="font-serif text-title leading-snug text-surface-900 tracking-tight">
									{#if $activeIncident.method === 'url' && !$activeIncident.can_approve}
										{$activeIncident.service_name} is unreachable and there's nothing I can run for it. Here's what I found.
									{:else if !$activeIncident.can_approve}
										{$activeIncident.service_name} is down. A restart won't fix this. Here's what I found.
									{:else}
										{$activeIncident.service_name} is down. I can {actionVerb($activeIncident.proposed_action)} it. Want me to?
									{/if}
								</div>
								<Badge pill variant={badge.variant} tone={badge.tone}>{badgeLabel()}</Badge>
							</div>
							{#if $activeIncident.llm_diagnosis}
								<div class="mt-5 px-4 py-3 rounded-lg bg-surface-50 border border-surface-200">
									<div class="font-mono text-[11px] text-surface-500 tracking-wide uppercase">Diagnosis</div>
									<div class="mt-1.5 font-sans text-[15px] leading-relaxed text-surface-700">
										{$activeIncident.llm_diagnosis}
									</div>
									{#if $activeIncident.llm_confidence}
										<div class="mt-1.5 inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-200 text-surface-700 font-sans text-[11px]">
											confidence: {$activeIncident.llm_confidence}
										</div>
									{/if}
								</div>
							{:else}
								<div class="mt-5 px-4 py-3 rounded-lg bg-surface-50 border border-surface-200">
									<div class="font-mono text-[11px] text-surface-500 tracking-wide uppercase">Diagnosis</div>
									<div class="mt-1.5 font-sans text-[15px] leading-relaxed {$activeIncident.diagnosis_unavailable ? 'text-surface-500' : 'text-surface-700'}">
										{#if $activeIncident.diagnosis_unavailable}No diagnosis, LLM unavailable{:else}Diagnosis pending…{/if}
									</div>
								</div>
							{/if}
							<div class="mt-4">
								<Timeline items={$activeIncident.timeline} />
							</div>
							{#if $activeIncident.proposed_fix}
								<div class="mt-4 px-4 py-3 rounded-lg bg-surface-50 border border-surface-200">
									<div class="font-mono text-[11px] text-surface-500 tracking-wide uppercase">suggested fix</div>
									<div class="mt-1.5 font-sans text-[15px] leading-relaxed text-surface-700">
										<span class="font-mono text-[13px]">{$activeIncident.proposed_fix}</span>
									</div>
								</div>
							{/if}
							<div class="mt-5 border border-surface-300 rounded-xl overflow-hidden">
								<div class="px-4 py-2.5 bg-surface-50 border-b border-surface-300 flex justify-between items-center">
									<div class="font-mono text-[11px] text-surface-600 tracking-wide uppercase">Live logs · {$activeIncident.service_name}</div>
									<button
										type="button"
										on:click={() => logLines.set([])}
										class="font-sans text-[11px] text-surface-500 hover:text-surface-900"
									>
										Clear
									</button>
								</div>
								<pre
									bind:this={logContainer}
									class="h-48 p-4 bg-surface-950 text-surface-200 font-mono text-[12px] leading-snug overflow-y-auto whitespace-pre-wrap"
									>{#if trimmedLogLines.length}{trimmedLogLines.join('\n')}{:else}<span class="text-surface-500">Waiting for log lines from the agent…</span>{/if}</pre>
							</div>
							<div class="mt-5 pt-5 border-t border-surface-200 flex flex-col sm:flex-row sm:items-center gap-3">
								{#if $activeIncident.can_approve}
									<Button size="lg" on:click={approve}>Approve</Button>
								{/if}
								<Button size="lg" variant="secondary" on:click={takeOver}>I'll handle it</Button>
							</div>
						</div>
					{:else if ['detecting', 'diagnosing', 'fixing', 'verifying'].includes($activeIncident.view)}
						<div class="p-5 sm:p-9" in:contentFly|local>
							<div class="flex justify-between items-start gap-4">
								<div class="font-serif text-title leading-snug text-surface-900 tracking-tight">
									{$activeIncident.service_name} is stuck. I'm {actionGerund($activeIncident.proposed_action)} it.
								</div>
								<Badge pill variant={badge.variant} tone={badge.tone}>{badgeLabel()}</Badge>
							</div>
							{#if $activeIncident.llm_diagnosis}
								<div class="mt-5 px-4 py-3 rounded-lg bg-surface-50 border border-surface-200">
									<div class="font-mono text-[11px] text-surface-500 tracking-wide uppercase">Diagnosis</div>
									<div class="mt-1.5 font-sans text-[15px] leading-relaxed text-surface-700">
										{$activeIncident.llm_diagnosis}
									</div>
									{#if $activeIncident.llm_confidence}
										<div class="mt-1.5 inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-200 text-surface-700 font-sans text-[11px]">
											confidence: {$activeIncident.llm_confidence}
										</div>
									{/if}
								</div>
							{:else}
								<div class="mt-5 px-4 py-3 rounded-lg bg-surface-50 border border-surface-200">
									<div class="font-mono text-[11px] text-surface-500 tracking-wide uppercase">Diagnosis</div>
									<div class="mt-1.5 font-sans text-[15px] leading-relaxed {$activeIncident.diagnosis_unavailable ? 'text-surface-500' : 'text-surface-700'}">
										{#if $activeIncident.diagnosis_unavailable}No diagnosis, LLM unavailable{:else}Diagnosis pending…{/if}
									</div>
								</div>
							{/if}
							<div class="mt-4">
								<Timeline items={$activeIncident.timeline} />
							</div>
							{#if $activeIncident.proposed_fix}
								<div class="mt-4 px-4 py-3 rounded-lg bg-surface-50 border border-surface-200">
									<div class="font-mono text-[11px] text-surface-500 tracking-wide uppercase">suggested fix</div>
									<div class="mt-1.5 font-sans text-[15px] leading-relaxed text-surface-700">
										<span class="font-mono text-[13px]">{$activeIncident.proposed_fix}</span>
									</div>
								</div>
							{/if}
							<div class="mt-5 border border-surface-300 rounded-xl overflow-hidden">
								<div class="px-4 py-2.5 bg-surface-50 border-b border-surface-300 flex justify-between items-center">
									<div class="font-mono text-[11px] text-surface-600 tracking-wide uppercase">Live logs · {$activeIncident.service_name}</div>
									<button
										type="button"
										on:click={() => logLines.set([])}
										class="font-sans text-[11px] text-surface-500 hover:text-surface-900"
									>
										Clear
									</button>
								</div>
								<pre
									bind:this={logContainer}
									class="h-48 p-4 bg-surface-950 text-surface-200 font-mono text-[12px] leading-snug overflow-y-auto whitespace-pre-wrap"
									>{#if trimmedLogLines.length}{trimmedLogLines.join('\n')}{:else}<span class="text-surface-500">Waiting for log lines from the agent…</span>{/if}</pre>
							</div>
							<div class="mt-5 pt-5 border-t border-surface-200 flex flex-wrap justify-between items-center gap-3">
								<div class="flex items-center gap-3">
									<Button size="lg" on:click={takeOver}>Take over</Button>
								</div>
								<span class="font-mono text-[12px] text-surface-500 flex items-center gap-1.5">
									<span class="text-surface-900">✓</span> messaged your phone
								</span>
							</div>
						</div>
					{:else if $activeIncident.view === 'resolved'}
						<div class="p-5 sm:p-9" in:contentFly|local>
							<Badge pill variant={badge.variant} tone={badge.tone}>{badgeLabel()}</Badge>
							<div class="mt-4 font-serif text-title leading-tight text-surface-900 tracking-tight">{$activeIncident.service_name} is back.</div>
							<div class="mt-3.5 font-sans text-base leading-relaxed text-surface-600">
								Down for <span class="font-mono text-sm text-surface-900">{$activeIncident.elapsed}s</span>. Health check is green again.
							</div>
							{#if $activeIncident.llm_diagnosis}
								<div class="mt-4 px-4 py-3 rounded-lg bg-surface-50 border border-surface-200">
									<div class="font-mono text-[11px] text-surface-500 tracking-wide uppercase">Diagnosis</div>
									<div class="mt-1.5 font-sans text-[15px] leading-relaxed text-surface-700">
										{$activeIncident.llm_diagnosis}
									</div>
									{#if $activeIncident.llm_confidence}
										<div class="mt-1.5 inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-200 text-surface-700 font-sans text-[11px]">
											confidence: {$activeIncident.llm_confidence}
										</div>
									{/if}
								</div>
							{/if}
							{#if $activeIncident.proposed_fix}
								<div class="mt-4 px-4 py-3 rounded-lg bg-surface-50 border border-surface-200">
									<div class="font-mono text-[11px] text-surface-500 tracking-wide uppercase">suggested fix</div>
									<div class="mt-1.5 font-sans text-[15px] leading-relaxed text-surface-700">
										<span class="font-mono text-[13px]">{$activeIncident.proposed_fix}</span>
									</div>
								</div>
							{/if}
							<div class="mt-5 border border-surface-300 rounded-xl overflow-hidden">
								<div class="px-4 py-2.5 bg-surface-50 border-b border-surface-300 flex justify-between items-center">
									<div class="font-mono text-[11px] text-surface-600 tracking-wide uppercase">Logs · {$activeIncident.service_name}</div>
									<button
										type="button"
										on:click={() => logLines.set([])}
										class="font-sans text-[11px] text-surface-500 hover:text-surface-900"
									>
										Clear
									</button>
								</div>
								<pre
									bind:this={logContainer}
									class="h-48 p-4 bg-surface-950 text-surface-200 font-mono text-[12px] leading-snug overflow-y-auto whitespace-pre-wrap"
									>{#if trimmedLogLines.length}{trimmedLogLines.join('\n')}{:else}<span class="text-surface-500">No logs captured.</span>{/if}</pre>
							</div>
							<div class="mt-7 pt-5 border-t border-surface-200 flex flex-wrap justify-between items-center gap-3">
								<Button size="lg" on:click={backToWatching}>Back to watching</Button>
								<button
									class="bg-transparent border-none cursor-pointer font-mono text-xs text-surface-500 underline underline-offset-[3px] decoration-surface-400 hover:text-surface-900"
									on:click={() => goto('/incidents')}
								>
									added to incidents →
								</button>
							</div>
						</div>
					{:else if $activeIncident.view === 'takeover'}
						<div class="p-5 sm:p-9" in:contentFly|local>
							<Badge pill variant={badge.variant} tone={badge.tone}>{badgeLabel()}</Badge>
							<div class="mt-4 font-serif text-title leading-snug text-surface-900 tracking-tight">Okay, it's yours.</div>
							{#if !$activeIncident.proposed_action}
								<div class="mt-3.5 font-serif text-base leading-relaxed text-surface-600">
									I've stepped back. There's nothing I can run for this one. Here's what I found:
								</div>
								<div class="mt-4 bg-surface-50 border border-surface-200 rounded-xl px-[18px] py-4 font-sans text-label leading-relaxed text-surface-700">
									{$activeIncident.proposed_fix || $activeIncident.llm_diagnosis || 'The endpoint failed its health check. Check that it is up and reachable.'}
								</div>
							{:else}
								<div class="mt-3.5 font-serif text-base leading-relaxed text-surface-600">
									I've stepped back and won't touch anything. Here's the fix I was about to run, if it helps:
								</div>
								<div class="mt-4 bg-surface-950 rounded-xl px-[18px] py-4 font-mono text-label leading-relaxed text-surface-300">
									<span class="text-surface-500">$</span> {fixCommand($activeIncident)}
								</div>
							{/if}
							<div class="mt-3.5 flex gap-4">
								<button class="bg-transparent border-none cursor-pointer font-medium text-xs font-mono text-surface-600 underline underline-offset-[3px] decoration-surface-400 hover:text-surface-900">view logs ↗</button>
								<button class="bg-transparent border-none cursor-pointer font-medium text-xs font-mono text-surface-600 underline underline-offset-[3px] decoration-surface-400 hover:text-surface-900">open /healthz ↗</button>
							</div>
							<div class="mt-6 pt-5 border-t border-surface-200 flex flex-col sm:flex-row sm:items-center gap-3">
								<Button size="lg" on:click={manualResolve}>Mark it resolved</Button>
								<Button size="lg" variant="secondary" on:click={handBack}>Hand back to the agent</Button>
							</div>
						</div>
					{/if}
				</div>
			{/key}
		</div>
	</div>
</div>
