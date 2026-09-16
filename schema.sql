-- ============================================================
--  Bellwether  ·  Supabase schema
--  Run this ONCE in your Supabase project:
--    Dashboard -> SQL Editor -> New query -> paste all -> Run
--
--  Every table is locked to its owner by Row-Level Security, so
--  the public anon key that ships in the app can never read or
--  write another user's rows.
--
--  Tables are prefixed bw_ so this can live safely alongside
--  another app's tables in a shared project.
-- ============================================================

-- ---------- WATCHLIST ----------
-- id is the ticker itself: one row per symbol per user.
create table if not exists public.bw_watchlist (
  user_id    uuid not null references auth.users(id) on delete cascade,
  id         text not null,
  sym        text,
  note       text not null default '',
  added_at   timestamptz not null default now(),
  -- Sync bookkeeping. updated_at drives last-write-wins across devices;
  -- deleted_at is a tombstone, so a delete on one device propagates to the
  -- others instead of the row simply reappearing on their next push.
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  primary key (user_id, id)
);
alter table public.bw_watchlist enable row level security;
drop policy if exists "own watchlist" on public.bw_watchlist;
create policy "own watchlist" on public.bw_watchlist
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- LOTS ----------
-- One row per purchase, not per holding: two buys of the same stock stay
-- separate so each keeps its own cost basis and sale history.
create table if not exists public.bw_lots (
  user_id    uuid not null references auth.users(id) on delete cascade,
  id         text not null,
  sym        text,
  shares     numeric check (shares is null or shares >= 0),
  price      numeric check (price is null or price >= 0),
  fees       numeric not null default 0 check (fees >= 0),
  bought_on  date,
  note       text not null default '',
  -- Sales are always read and edited together with their lot, so they live
  -- here as an array rather than in a table of their own.
  -- [{ id, shares, price, fees, date }]
  sells      jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  primary key (user_id, id)
);
alter table public.bw_lots enable row level security;
drop policy if exists "own lots" on public.bw_lots;
create policy "own lots" on public.bw_lots
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- JOURNAL ----------
create table if not exists public.bw_journal (
  user_id    uuid not null references auth.users(id) on delete cascade,
  id         text not null,
  sym        text,
  action     text not null default 'note',   -- buy | sell | hold | watch | note
  entry_date date,
  thesis     text not null default '',
  risks      text not null default '',
  conviction int check (conviction is null or conviction between 1 and 5),
  tags       text[] not null default '{}',
  -- Null until the call is closed out.
  -- { result: number (percent), date: 'YYYY-MM-DD', lessons: text }
  outcome    jsonb,
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  primary key (user_id, id)
);
alter table public.bw_journal enable row level security;
drop policy if exists "own journal" on public.bw_journal;
create policy "own journal" on public.bw_journal
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- PREFERENCES ----------
-- One row per user, id is always 'prefs'. Deliberately does NOT hold the
-- Finnhub or Twelve Data keys: those stay in the browser that entered them.
create table if not exists public.bw_prefs (
  user_id    uuid not null references auth.users(id) on delete cascade,
  id         text not null default 'prefs',
  currency   text not null default '$',
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  primary key (user_id, id)
);
alter table public.bw_prefs enable row level security;
drop policy if exists "own prefs" on public.bw_prefs;
create policy "own prefs" on public.bw_prefs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- PULL INDEXES ----------
-- Every sync asks the same question: what changed since I last looked?
create index if not exists bw_watchlist_sync on public.bw_watchlist (user_id, updated_at);
create index if not exists bw_lots_sync      on public.bw_lots      (user_id, updated_at);
create index if not exists bw_journal_sync   on public.bw_journal   (user_id, updated_at);
