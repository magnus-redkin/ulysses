<script>
    let { form } = $props();
</script>

<div class="flex min-h-screen items-center justify-center bg-slate-950 p-4 w-full">
    <div class="w-full max-w-md space-y-6 rounded-2xl bg-slate-900 p-8 border border-slate-800 shadow-xl">
        <div class="text-center">
            <h1 class="text-2xl font-bold text-slate-100 tracking-tight">Вход в панель</h1>
            <p class="mt-2 text-sm text-slate-400">Введите пароль администратора для доступа к системе</p>
        </div>

        <form method="POST" action="?/login" class="space-y-4">
            <div>
                <label for="password" class="block text-sm font-medium text-slate-300 mb-1.5">Пароль</label>
                <input
                    id="password"
                    name="password"
                    type="password"
                    required
                    placeholder="••••••••"
                    class="w-full p-3 bg-slate-950 border border-slate-800 text-white rounded-lg focus:outline-none focus:border-blue-500 transition-colors"
                />
            </div>

            {#if form?.incorrect}
                <div class="p-3 text-sm rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 text-center animate-pulse">
                    {form.message || 'Неверный пароль'}
                </div>
            {/if}

            <button type="submit" class="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors shadow-lg shadow-blue-600/20 cursor-pointer font-bold">
                Войти в систему
            </button>
        </form>
    </div>
</div>
