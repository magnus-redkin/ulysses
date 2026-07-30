<script>
    let { children } = $props();
</script>

<!-- px-12 задает отступы ровно 3rem (3em) слева и справа. Верх и низ прижаты (py-0) -->
<div class="min-h-screen w-full bg-slate-950 text-slate-200 px-12 py-0 overflow-hidden flex flex-col">
    {@render children()}
</div>
