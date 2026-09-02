import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Newspaper,
  Cpu,
  Briefcase,
  FlaskConical,
  Landmark,
  Globe2,
  RefreshCw,
  Activity,
  Flame,
  Zap,
  ArrowUpRight,
  Sun,
  Moon,
  ChevronDown,
  Inbox,
  Layers,
  X,
  ExternalLink,
  MessageSquare,
  Send,
  Bot,
  User,
  ChevronRight,
  Tag,
  BarChart2,
  Sparkles,
  MapPin,
  Trophy,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "NewsFlow Live Dashboard" },
      { name: "description", content: "Real-time clustered news intelligence with AI briefings, sentiment and trending entities." },
      { property: "og:title", content: "NewsFlow: Live News Dashboard" },
      { property: "og:description", content: "Real-time clustered news intelligence with AI briefings, sentiment and trending entities." },
    ],
  }),
  component: Dashboard,
});

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
const PAGE_SIZE = 12;

const CATEGORIES = [
  { key: "All", label: "All News", icon: Globe2 },
  { key: "Nigeria", label: "Nigeria", icon: MapPin },
  { key: "Politics", label: "Politics", icon: Landmark },
  { key: "Economy", label: "Economy", icon: Briefcase },
  { key: "Tech", label: "Technology", icon: Cpu },
  { key: "Health", label: "Health", icon: Activity },
  { key: "Science", label: "Science", icon: FlaskConical },
  { key: "Conflict", label: "Conflict", icon: Flame },
  { key: "Climate", label: "Climate", icon: Globe2 },
  { key: "Culture", label: "Culture", icon: Newspaper },
  { key: "Sports", label: "Sports", icon: Trophy },
] as const;

type Cluster = {
  cluster_id?: string;
  rep_title: string;
  summary: string;
  source_count: number;
  sentiment_score: number;
  sentiment_label?: string;
  category: string;
  representative_url?: string;
  rep_source?: string;
  entity_union?: string[];
  published_at?: string;
};

type ClusterDetail = Cluster & {
  articles: {
    title: string;
    url: string;
    source: string;
    published_at: string;
    description: string;
  }[];
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type DashboardStats = {
  sentiment_by_category: Record<string, number>;
  trending_entities: { entity: string; count: number }[];
  cluster_counts?: Record<string, number>;
  last_pipeline_at?: string | null;
  server_time?: string;
};

const EASE: [number, number, number, number] = [0.23, 1, 0.32, 1];

async function safeJson<T>(url: string, opts?: RequestInit): Promise<T | null> {
  try {
    const r = await fetch(url, opts);
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function Dashboard() {
  const [category, setCategory] = useState<string>("All");
  const [clusters, setClusters] = useState<Cluster[] | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [briefing, setBriefing] = useState<string | null>(null);
  const [briefingTime, setBriefingTime] = useState<string | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  // SSR-safe: both server and client start with `true` so the initial render
  // matches and React does not throw a hydration mismatch.
  // The real persisted preference is applied after hydration via useEffect.
  const [isDark, setIsDark] = useState(true);

  // On client mount only: read the saved preference and apply it.
  // This runs AFTER hydration is complete so there is no mismatch.
  useEffect(() => {
    const stored = localStorage.getItem("newsflow_dark_mode");
    if (stored !== null) setIsDark(stored === "true");
  }, []);

  // Keep <html> class and localStorage in sync whenever isDark changes.
  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
    localStorage.setItem("newsflow_dark_mode", String(isDark));
  }, [isDark]);

  // Story detail drawer state
  const [selectedCluster, setSelectedCluster] = useState<Cluster | null>(null);
  const [clusterDetail, setClusterDetail] = useState<ClusterDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  // Tracks whether the pipeline was running on the previous poll tick
  const wasRunningRef = useRef<boolean>(false);
  const pollRef = useRef<number | null>(null);
  const categoryRef = useRef<string>("All");

  const loadClusters = useCallback(async (cat: string, off = 0) => {
    if (off === 0) setClusters(null);
    const qs =
      cat === "All"
        ? `limit=${PAGE_SIZE}&offset=${off}`
        : `category=${encodeURIComponent(cat)}&limit=${PAGE_SIZE}&offset=${off}`;
    const data = await safeJson<{ clusters: Cluster[]; has_more: boolean; total?: number }>(`${API}/api/clusters?${qs}`);
    if (off === 0) {
      setClusters(data?.clusters ?? []);
      setTotalCount(data?.total ?? null);
    } else {
      setClusters((prev) => [...(prev ?? []), ...(data?.clusters ?? [])]);
    }
    setHasMore(data?.has_more ?? false);
    setOffset(off);
  }, []);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    await loadClusters(category, offset + PAGE_SIZE);
    setLoadingMore(false);
  }, [category, offset, loadClusters]);

  const loadBriefing = useCallback(async (cat: string) => {
    setBriefing(null);
    setBriefingTime(null);
    const data = await safeJson<{ content: string; generated_at?: string }>(
      `${API}/api/briefings/${cat}`,
    );
    setBriefing(data?.content ?? "Briefing not available.");
    setBriefingTime(data?.generated_at ?? null);
  }, []);

  const loadStats = useCallback(async () => {
    const data = await safeJson<DashboardStats>(`${API}/api/dashboard`);
    if (data) setStats(data);
  }, []);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([loadClusters(category, 0), loadBriefing(category), loadStats()]);
    setRefreshing(false);
  }, [category, loadClusters, loadBriefing, loadStats]);

  // Keep categoryRef in sync so the polling callback always refreshes the right category
  useEffect(() => {
    categoryRef.current = category;
  }, [category]);

  useEffect(() => {
    void loadClusters(category, 0);
    void loadBriefing(category);
  }, [category, loadClusters, loadBriefing]);

  // Background pipeline status poller — runs every 5 seconds for the lifetime
  // of the dashboard. When it detects a pipeline run just *finished* (was
  // running → now idle) it automatically refreshes all dashboard data so the
  // user sees fresh stories without having to do anything.
  useEffect(() => {
    const tick = async () => {
      const data = await safeJson<{ running: boolean }>(`${API}/api/pipeline/status`);
      if (!data) return;

      const running = data.running;
      setPipelineRunning(running);

      // Transition: was running → now idle  →  pull fresh data + show toast
      if (wasRunningRef.current && !running) {
        const cat = categoryRef.current;
        const [freshClusters] = await Promise.all([
          safeJson<{ clusters: { cluster_id: string }[]; total?: number }>(
            `${API}/api/clusters?limit=${PAGE_SIZE}&offset=0`
          ),
          loadBriefing(cat),
          loadStats(),
        ]);
        await loadClusters(cat, 0);
        // Show toast with new story count
        const newCount = freshClusters?.total ?? freshClusters?.clusters?.length ?? 0;
        const msg = newCount > 0 ? `✦ ${newCount} stories refreshed` : "✦ News feed updated";
        setToast(msg);
        if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
        toastTimerRef.current = window.setTimeout(() => setToast(null), 4000);
      }

      wasRunningRef.current = running;
    };

    // First tick immediately so the header badge is accurate right away
    void tick();
    void loadStats();

    pollRef.current = window.setInterval(tick, 5000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Open story detail drawer
  const openStory = useCallback(async (cluster: Cluster) => {
    setSelectedCluster(cluster);
    setClusterDetail(null);
    if (cluster.cluster_id) {
      setDetailLoading(true);
      const detail = await safeJson<ClusterDetail>(`${API}/api/clusters/${cluster.cluster_id}`);
      setClusterDetail(detail);
      setDetailLoading(false);
    }
  }, []);

  const closeStory = useCallback(() => {
    setSelectedCluster(null);
    setClusterDetail(null);
  }, []);

  // Close drawer on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeStory();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [closeStory]);

  const activeLabel = CATEGORIES.find((c) => c.key === category)?.label ?? "All News";

  const clusterCounts = stats?.cluster_counts ?? {};
  const lastPipelineAt = stats?.last_pipeline_at ?? null;

  // Client-side search filter
  const filteredClusters = useMemo(() => {
    if (!clusters) return null;
    if (!searchQuery.trim()) return clusters;
    const q = searchQuery.toLowerCase();
    return clusters.filter(c => 
      c.rep_title.toLowerCase().includes(q) || 
      (c.summary && c.summary.toLowerCase().includes(q)) ||
      (c.entity_union && c.entity_union.some(e => e.toLowerCase().includes(q)))
    );
  }, [clusters, searchQuery]);

  return (
    <div className="min-h-screen bg-[var(--color-paper)] text-[var(--color-ink)] font-sans antialiased">
      <div className="mx-auto flex min-h-screen max-w-[1600px]">
        <Sidebar active={category} onSelect={setCategory} counts={clusterCounts} stats={stats} />
        <TabletSidebar active={category} onSelect={setCategory} counts={clusterCounts} pipelineRunning={pipelineRunning} />
        <main className="flex-1 border-x border-[var(--color-line)] min-w-0">
          <Header
            activeCategory={category}
            onSelectCategory={setCategory}
            onRefresh={refreshAll}
            refreshing={refreshing}
            lastPipelineAt={lastPipelineAt}
            isDark={isDark}
            toggleDark={() => setIsDark(!isDark)}
            pipelineRunning={pipelineRunning}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
          />
          <div className="px-8 pb-16 pt-6 space-y-8">
            <Briefing content={briefing} category={activeLabel} generatedAt={briefingTime} />
            <StoriesGrid
              clusters={filteredClusters}
              totalCount={totalCount}
              hasMore={hasMore}
              loadingMore={loadingMore}
              onLoadMore={loadMore}
              activeCategory={category}
              pipelineRunning={pipelineRunning}
              onOpenStory={openStory}
            />
          </div>
        </main>
        <RightPanel
          stats={stats}
        />
      </div>

      {/* Story Detail Drawer */}
      <StoryDrawer
        cluster={selectedCluster}
        detail={clusterDetail}
        detailLoading={detailLoading}
        onClose={closeStory}
      />

      {/* Toast notification */}
      <AnimatePresence>
        {toast && (
          <motion.div
            key="toast"
            initial={{ opacity: 0, y: 24, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 420, damping: 36 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2.5 rounded-full border border-[var(--color-accent)]/30 bg-[var(--color-paper)] px-5 py-3 shadow-2xl text-sm font-semibold text-[var(--color-ink)]"
          >
            <Sparkles className="h-4 w-4 text-[var(--color-accent)]" strokeWidth={2} />
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---------- Sidebar ---------- */

function Sidebar({
  active,
  onSelect,
  counts,
  stats,
}: {
  active: string;
  onSelect: (k: string) => void;
  counts: Record<string, number>;
  stats: DashboardStats | null;
}) {
  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col justify-between py-8 px-4 sticky top-0 h-screen overflow-y-auto">
      <div>
        <button onClick={() => window.location.reload()} className="flex items-center gap-2.5 px-3 mb-12 hover:opacity-80 transition cursor-pointer text-left">
          <div className="h-7 w-7 rounded-md bg-[var(--color-ink)] grid place-items-center">
            <Newspaper className="h-4 w-4 text-[var(--color-paper)]" strokeWidth={2.25} />
          </div>
          <span className="font-display text-lg font-semibold tracking-tight">
            NewsFlow
          </span>
        </button>

        <nav className="flex flex-col gap-0.5">
          {CATEGORIES.map((c) => {
            const Icon = c.icon;
            const isActive = active === c.key;
            const count = c.key === "All"
              ? Object.values(counts).reduce((s, n) => s + n, 0)
              : (counts[c.key] ?? 0);
            return (
              <button
                key={c.key}
                onClick={() => onSelect(c.key)}
                className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition active:scale-[0.97] w-full text-left ${
                  isActive
                    ? "text-[var(--color-ink)]"
                    : "text-[var(--color-mute)] hover:text-[var(--color-ink)]"
                }`}
                style={{ transitionTimingFunction: "var(--ease-snap)" }}
              >
                {isActive && (
                  <>
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-[var(--color-accent)]" />
                    <motion.span
                      layoutId="nav-pill"
                      className="absolute inset-0 rounded-lg bg-[var(--color-paper-2)]"
                      transition={{ type: "spring", stiffness: 500, damping: 40 }}
                    />
                  </>
                )}
                <Icon className="relative h-4 w-4" strokeWidth={1.75} />
                <span className="relative flex-1">{c.label}</span>
                {count > 0 && (
                  <span className={`relative text-[10px] font-mono font-bold tabular-nums ${
                    isActive ? "text-[var(--color-accent)]" : "text-[var(--color-mute)]"
                  }`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {stats?.trending_entities && stats.trending_entities.length > 0 && (
        <div className="mt-12 px-3 xl:hidden">
          <div className="flex items-center gap-2 mb-3">
            <Flame className="h-3.5 w-3.5 text-[var(--color-neg)]" strokeWidth={2} />
            <span className="font-display text-xs font-bold uppercase tracking-wider text-[var(--color-mute)]">Trending</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {stats.trending_entities.slice(0, 5).map((e) => (
              <div key={e.entity} className="flex items-center justify-between text-xs">
                <span className="truncate text-[var(--color-ink)] opacity-80">{e.entity}</span>
                <span className="font-mono text-[9px] text-[var(--color-mute)]">{e.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}

/* ---------- Tablet Sidebar (icon-only) ---------- */

function TabletSidebar({
  active,
  onSelect,
  counts,
  pipelineRunning,
}: {
  active: string;
  onSelect: (k: string) => void;
  counts: Record<string, number>;
  pipelineRunning: boolean;
}) {
  return (
    <aside className="hidden sm:flex md:hidden w-14 shrink-0 flex-col items-center gap-1 py-6 sticky top-0 h-screen overflow-y-auto border-r border-[var(--color-line)]">
      {/* Logo */}
      <button onClick={() => window.location.reload()} className="h-7 w-7 rounded-md bg-[var(--color-ink)] grid place-items-center mb-8 hover:opacity-80 transition cursor-pointer" title="Reload NewsFlow">
        <Newspaper className="h-4 w-4 text-[var(--color-paper)]" strokeWidth={2.25} />
      </button>
      {CATEGORIES.map((c) => {
        const Icon = c.icon;
        const isActive = active === c.key;
        const count = c.key === "All"
          ? Object.values(counts).reduce((s, n) => s + n, 0)
          : (counts[c.key] ?? 0);
        return (
          <button
            key={c.key}
            onClick={() => onSelect(c.key)}
            title={c.label}
            className={`relative flex h-9 w-9 items-center justify-center rounded-lg transition active:scale-95 ${
              isActive
                ? "bg-[var(--color-paper-2)] text-[var(--color-ink)]"
                : "text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:bg-[var(--color-paper-2)]/50"
            }`}
            style={{ transitionTimingFunction: "var(--ease-snap)" }}
          >
            {isActive && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-[var(--color-accent)]" />
            )}
            <Icon className="h-4 w-4" strokeWidth={1.75} />
            {count > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[var(--color-accent)] text-[8px] font-bold text-white tabular-nums">
                {count > 99 ? "99" : count}
              </span>
            )}
          </button>
        );
      })}
      {/* Pipeline status dot */}
      <div className="mt-auto mb-2">
        <span
          title={pipelineRunning ? "Pipeline running" : "Pipeline idle"}
          className={`flex h-2 w-2 rounded-full ${
            pipelineRunning ? "bg-[var(--color-accent)] animate-pulse" : "bg-[var(--color-mute)]/40"
          }`}
        />
      </div>
    </aside>
  );
}

/* ---------- Mobile Category Dropdown ---------- */

function MobileCategoryDropdown({
  activeCategory,
  onSelectCategory,
}: {
  activeCategory: string;
  onSelectCategory: (c: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener("mousedown", handleOutsideClick);
    }
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [open]);

  const activeLabel = CATEGORIES.find((c) => c.key === activeCategory)?.label ?? "All News";

  return (
    <div className="relative" ref={ref}>
      <button 
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[var(--color-accent)] font-bold outline-none transition active:scale-95"
      >
        <span>{activeLabel}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute top-full left-0 mt-3 w-56 rounded-xl border border-[var(--color-line)] bg-[var(--color-paper-2)] p-1.5 shadow-xl z-50 overflow-hidden"
          >
            {CATEGORIES.map((c) => {
              const Icon = c.icon;
              const isActive = c.key === activeCategory;
              return (
                <button
                  key={c.key}
                  onClick={() => {
                    onSelectCategory(c.key);
                    setOpen(false);
                  }}
                  className={`flex items-center gap-3 w-full rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                    isActive
                      ? "bg-[var(--color-ink)] text-[var(--color-paper)]"
                      : "text-[var(--color-mute)] hover:bg-[var(--color-paper)] hover:text-[var(--color-ink)]"
                  }`}
                >
                  <Icon className="h-4 w-4" strokeWidth={2} />
                  {c.label}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---------- Header ---------- */

function Header({
  activeCategory,
  onSelectCategory,
  onRefresh,
  refreshing,
  lastPipelineAt,
  isDark,
  toggleDark,
  pipelineRunning,
  searchQuery,
  onSearchChange,
}: {
  activeCategory: string;
  onSelectCategory: (c: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
  lastPipelineAt: string | null;
  isDark: boolean;
  toggleDark: () => void;
  pipelineRunning: boolean;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}) {
  const activeLabel = CATEGORIES.find((c) => c.key === activeCategory)?.label ?? "All News";

  return (
    <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-4 sm:gap-6 border-b border-[var(--color-line)] px-6 sm:px-8 pb-6 pt-6 sm:pt-10">
      <div>
        {/* Mobile Breadcrumb */}
        <div className="md:hidden flex items-center gap-2 mb-4 text-sm font-medium text-[var(--color-mute)] bg-[var(--color-paper-2)] border border-[var(--color-line)] rounded-xl px-4 py-2 w-max shadow-sm">
          <button onClick={() => window.location.reload()} className="flex items-center gap-2 hover:opacity-80 transition cursor-pointer">
            <Newspaper className="h-4 w-4 text-[var(--color-ink)]" />
            <span className="text-[var(--color-ink)]">NewsFlow</span>
          </button>
          <ChevronRight className="h-4 w-4" />
          <MobileCategoryDropdown activeCategory={activeCategory} onSelectCategory={onSelectCategory} />
        </div>

        <p className="text-sm text-[var(--color-mute)] mb-1.5 hidden sm:block">
          {new Date().toLocaleDateString(undefined, {
            weekday: "long",
            month: "long",
            day: "numeric",
          })}
        </p>
        <h1
          className="font-display text-3xl sm:text-4xl font-semibold tracking-tight"
          style={{ textWrap: "balance" as never }}
        >
          {activeLabel}
        </h1>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div
          title={pipelineRunning ? "Pipeline is running…" : "Pipeline idle (Runs automatically every 30 mins)"}
          className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider transition ${
            pipelineRunning
              ? "border-[var(--color-accent)]/40 text-[var(--color-accent)]"
              : "border-[var(--color-line)] text-[var(--color-mute)]"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              pipelineRunning ? "bg-[var(--color-accent)] animate-pulse" : "bg-[var(--color-mute)]"
            }`}
          />
          {pipelineRunning ? "Running" : "Idle"}
        </div>
        <span className="text-xs text-[var(--color-mute)] font-mono hidden sm:block">
          {pipelineRunning
            ? "Fetching latest…"
            : lastPipelineAt
              ? `Last run ${relativeTime(lastPipelineAt)}`
              : "No runs yet"}
        </span>
        <button
          onClick={toggleDark}
          className="flex items-center justify-center rounded-lg border border-[var(--color-line)] p-2 transition hover:bg-[var(--color-paper-2)] active:scale-[0.97]"
        >
          {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
        <button
          onClick={onRefresh}
          title="Force refresh data"
          className="flex items-center gap-2 rounded-lg border border-[var(--color-line)] bg-[var(--color-paper)] px-3 py-2 text-sm font-medium transition hover:border-[var(--color-ink)] active:scale-[0.97]"
          style={{ transitionTimingFunction: "var(--ease-snap)" }}
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
            strokeWidth={2}
          />
          <span className="hidden lg:inline">Refresh</span>
        </button>
      </div>
      <div className="w-full xl:w-64 order-last xl:order-none mt-2 xl:mt-0 xl:ml-auto shrink-0 flex items-center gap-2 rounded-xl border border-[var(--color-line)] bg-[var(--color-paper-2)] px-3 py-2 transition focus-within:border-[var(--color-ink)]/40">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter stories…"
          className="w-full bg-transparent text-sm text-[var(--color-ink)] placeholder-[var(--color-mute)] outline-none"
        />
      </div>
    </div>
  );
}

/* ---------- Briefing ---------- */

function Briefing({
  content,
  category,
  generatedAt,
}: {
  content: string | null;
  category: string;
  generatedAt: string | null;
}) {
  // Initialize collapsed on server/client to avoid hydration mismatch;
  // enable expanded state on mount for large screens.
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.innerWidth >= 1024) setExpanded(true);
  }, []);

  const lines = useMemo(() => {
    if (!content) return [];
    return content.split("\n").filter((l) => l.trim().length > 0);
  }, [content]);

  const visibleLines = expanded ? lines : lines.slice(0, 4);
  const hasMore = lines.length > 4;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE }}
      className="relative overflow-hidden rounded-2xl border border-[var(--color-line)] p-8"
      style={{
        backgroundImage: "linear-gradient(135deg, var(--color-paper-2) 0%, var(--color-paper) 100%)",
      }}
    >
      <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-[var(--color-accent)]/10 blur-3xl" />
      <div className="pointer-events-none absolute -left-8 bottom-0 h-40 w-40 rounded-full bg-[var(--color-pos)]/5 blur-2xl" />

      <div className="relative">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20">
              <Zap className="h-4 w-4 text-[var(--color-accent)]" strokeWidth={2} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-base font-bold text-[var(--color-ink)]">
                  AI Briefing
                </h2>
                <span className="rounded-full bg-[var(--color-accent)]/10 px-2 py-0.5 text-[11px] font-semibold text-[var(--color-accent)] uppercase tracking-wider">
                  {category}
                </span>
              </div>
              {generatedAt && (
                <p className="text-[11px] text-[var(--color-mute)] mt-0.5">
                  Generated {relativeTime(generatedAt)}
                </p>
              )}
            </div>
          </div>
        </div>

        {content === null ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-start gap-3">
                <div className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-ink)]/15 animate-pulse" />
                <div className="h-3 flex-1 rounded bg-[var(--color-ink)]/10 animate-pulse" style={{ width: `${75 + i * 5}%` }} />
              </div>
            ))}
          </div>
        ) : !content ? (
          <p className="text-sm text-[var(--color-mute)]">No briefing available for this category yet.</p>
        ) : (
          <div className="flex flex-col gap-2.5 overflow-hidden relative">
            <div className={`transition-all duration-300 ${!expanded ? "max-h-[300px]" : "max-h-[2000px]"}`}>
              <ReactMarkdown 
                className="text-[14.5px] leading-relaxed text-[var(--color-ink)]/80 [&>ul]:list-disc [&>ul]:pl-5 [&>ul]:space-y-2 [&_strong]:text-[var(--color-ink)] [&_a]:text-[var(--color-accent)] space-y-4"
              >
                {content}
              </ReactMarkdown>
              {!expanded && (
                <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-[var(--color-paper-2)] to-transparent pointer-events-none" />
              )}
            </div>
            
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-2 inline-flex items-center gap-1.5 self-start rounded-lg border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/8 px-3.5 py-1.5 text-[13px] font-semibold text-[var(--color-accent)] transition hover:bg-[var(--color-accent)]/15 active:scale-[0.97]"
              style={{ transitionTimingFunction: "var(--ease-snap)" }}
            >
              {expanded ? "Show less" : "Read full briefing"}
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} strokeWidth={2.5} />
            </button>
          </div>
        )}
      </div>
    </motion.section>
  );
}

/* ---------- Stories Grid ---------- */

function StoriesGrid({
  clusters,
  totalCount,
  hasMore,
  loadingMore,
  onLoadMore,
  activeCategory,
  pipelineRunning,
  onOpenStory,
}: {
  clusters: Cluster[] | null;
  totalCount: number | null;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  activeCategory: string;
  pipelineRunning: boolean;
  onOpenStory: (c: Cluster) => void;
}) {
  if (clusters === null) {
    return (
      <div className="grid grid-cols-1 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-paper-2)] animate-pulse h-44" />
        ))}
      </div>
    );
  }

  if (clusters.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE }}
        className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--color-line)] py-24 text-center gap-4"
      >
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--color-paper-2)] border border-[var(--color-line)]">
          {pipelineRunning
            ? <RefreshCw className="h-6 w-6 text-[var(--color-accent)] animate-spin" strokeWidth={1.5} />
            : <Inbox className="h-6 w-6 text-[var(--color-mute)]" strokeWidth={1.5} />}
        </div>
        <div>
          <p className="font-display text-lg font-semibold text-[var(--color-ink)]">
            {pipelineRunning ? "Fetching the latest news…" : "No stories yet"}
          </p>
          <p className="text-sm text-[var(--color-mute)] mt-1 max-w-xs">
            {pipelineRunning
              ? "The pipeline is running for the first time. This takes around 6 minutes. Stories will appear automatically when ready."
              : activeCategory === "All"
                ? "Waiting for the next automated news cycle to ingest and cluster stories."
                : `No ${activeCategory} stories in the current window. Check back later or try switching categories.`}
          </p>
        </div>
      </motion.div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between text-xs text-[var(--color-mute)]">
        <span className="flex items-center gap-1.5">
          <Layers className="h-3.5 w-3.5" strokeWidth={1.75} />
          {totalCount !== null && totalCount > clusters.length
            ? `Showing ${clusters.length} of ${totalCount} stories`
            : `${clusters.length} ${clusters.length === 1 ? "story" : "stories"}`}
        </span>
        <span className="text-[11px] opacity-60 hidden sm:block">Click any story for full detail + AI chat</span>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <AnimatePresence mode="popLayout">
          {clusters.map((c, i) => (
            <StoryCard key={`${c.rep_title}-${i}`} cluster={c} index={i} onOpen={onOpenStory} />
          ))}
        </AnimatePresence>
      </div>

      {hasMore && (
        <button
          onClick={onLoadMore}
          disabled={loadingMore}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-[var(--color-line)] py-3 text-sm font-medium text-[var(--color-mute)] transition hover:border-[var(--color-ink)] hover:text-[var(--color-ink)] disabled:opacity-50 active:scale-[0.98]"
          style={{ transitionTimingFunction: "var(--ease-snap)" }}
        >
          {loadingMore ? <RefreshCw className="h-4 w-4 animate-spin" strokeWidth={2} /> : <ChevronDown className="h-4 w-4" strokeWidth={2} />}
          {loadingMore ? "Loading…" : hasMore ? "Load more" : ""}
        </button>
      )}
    </div>
  );
}

/* ---------- Story Card ---------- */

function StoryCard({ cluster: c, index: i, onOpen }: { cluster: Cluster; index: number; onOpen: (c: Cluster) => void }) {
  const sentColor = sentimentColor(c.sentiment_score ?? 0);
  const sentLbl = c.sentiment_label || sentimentLabel(c.sentiment_score ?? 0);

  return (
    <motion.article
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.4, delay: Math.min(i * 0.04, 0.3), ease: EASE }}
      onClick={() => onOpen(c)}
      className="group relative flex flex-col rounded-2xl border border-[var(--color-line)] bg-[var(--color-paper)] p-6 transition will-change-transform hover:shadow-lg hover:-translate-y-0.5 active:scale-[0.99] cursor-pointer"
      style={{
        transitionTimingFunction: "var(--ease-snap)",
        borderLeft: `3px solid ${sentColor}`,
      }}
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <SentimentDot value={c.sentiment_score ?? 0} />
          <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-mute)]">
            {c.category}
          </span>
        </div>
        {/* On desktop: only show on hover. On mobile: always visible */}
        <div className="flex items-center gap-1.5 transition sm:opacity-0 sm:group-hover:opacity-100">
          <span className="text-[11px] text-[var(--color-mute)] font-medium hidden sm:block">Open detail</span>
          <ChevronRight className="h-3.5 w-3.5 text-[var(--color-mute)]" strokeWidth={2} />
        </div>
      </div>

      {/* Headline */}
      <h3
        className="font-display font-bold tracking-tight text-[20px] leading-snug text-[var(--color-ink)] mb-2"
        style={{ textWrap: "balance" as never }}
      >
        {c.rep_title}
      </h3>

      {/* Summary */}
      <p
        className="text-[13.5px] text-[var(--color-mute)] leading-relaxed line-clamp-2 mb-3"
        style={{ textWrap: "pretty" as never }}
      >
        {c.summary}
      </p>

      {/* Entity tags */}
      {c.entity_union && c.entity_union.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {c.entity_union.slice(0, 5).map((entity, idx) => (
            <span
              key={idx}
              className="inline-flex items-center rounded-md bg-[var(--color-paper-2)] border border-[var(--color-line)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-ink)]/70"
            >
              {entity}
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-y-2 gap-x-4 text-xs border-t border-[var(--color-line)] pt-3">
        <div className="flex flex-wrap items-center gap-2 text-[var(--color-mute)]">
          <span className="font-semibold text-[var(--color-ink)]">{c.rep_source || "Web"}</span>
          <span>·</span>
          <span className="font-mono">{c.source_count} {c.source_count === 1 ? "source" : "sources"}</span>
          <span>·</span>
          {c.published_at && <span className="tabular-nums">{relativeTime(c.published_at)}</span>}
        </div>
        <span
          className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-bold"
          style={{
            background: `${sentColor}18`,
            color: sentColor,
            border: `1px solid ${sentColor}35`,
          }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: sentColor }} />
          {sentLbl.toUpperCase()}
          <span className="font-mono text-[11px] opacity-80">
            {(c.sentiment_score ?? 0) > 0 ? "+" : ""}
            {(c.sentiment_score ?? 0).toFixed(2)}
          </span>
        </span>
      </div>
    </motion.article>
  );
}

/* ---------- Story Drawer ---------- */

function StoryDrawer({
  cluster,
  detail,
  detailLoading,
  onClose,
}: {
  cluster: Cluster | null;
  detail: ClusterDetail | null;
  detailLoading: boolean;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"detail" | "chat">("detail");
  const [chatHistory, setChatHistory] = useState<Record<string, ChatMessage[]>>({});
  const [chatInputMap, setChatInputMap] = useState<Record<string, string>>({});
  const [chatSending, setChatSending] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const clusterId = cluster?.cluster_id;
  const chatMessages = clusterId ? (chatHistory[clusterId] || []) : [];
  const chatInput = clusterId ? (chatInputMap[clusterId] || "") : "";

  const setChatMessages = useCallback((updater: React.SetStateAction<ChatMessage[]>) => {
    if (!clusterId) return;
    setChatHistory((prev) => {
      const next = typeof updater === "function" ? updater(prev[clusterId] || []) : updater;
      return { ...prev, [clusterId]: next };
    });
  }, [clusterId]);

  const setChatInput = useCallback((val: string) => {
    if (!clusterId) return;
    setChatInputMap((prev) => ({ ...prev, [clusterId]: val }));
  }, [clusterId]);

  // Reset tab when cluster changes, but keep history intact
  useEffect(() => {
    setActiveTab("detail");
    setChatSending(false);
  }, [cluster?.cluster_id]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // Focus input when switching to chat tab
  useEffect(() => {
    if (activeTab === "chat") {
      setTimeout(() => inputRef.current?.focus(), 200);
    }
  }, [activeTab]);

  const buildContext = useCallback(() => {
    if (!cluster) return "";
    const parts = [
      `Title: ${cluster.rep_title}`,
      `Category: ${cluster.category}`,
      `Summary: ${cluster.summary}`,
      `Sentiment: ${cluster.sentiment_label ?? sentimentLabel(cluster.sentiment_score ?? 0)} (${(cluster.sentiment_score ?? 0).toFixed(2)})`,
      cluster.entity_union?.length ? `Key entities: ${cluster.entity_union.join(", ")}` : "",
      detail?.articles?.length
        ? `Sources covering this story:\n${detail.articles.map(a => `- ${a.source}: ${a.title}`).join("\n")}`
        : "",
    ];
    return parts.filter(Boolean).join("\n");
  }, [cluster, detail]);

  const sendMessage = useCallback(async () => {
    if (!chatInput.trim() || !cluster?.cluster_id) return;

    const userMsg: ChatMessage = { role: "user", content: chatInput.trim() };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput("");
    setChatSending(true);

    const data = await safeJson<{ reply: string }>(
      `${API}/api/clusters/${cluster.cluster_id}/chat`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg.content,
          cluster_context: buildContext(),
        }),
      }
    );

    const assistantMsg: ChatMessage = {
      role: "assistant",
      content: data?.reply ?? "Sorry, I couldn't get a response. Please try again.",
    };
    setChatMessages((prev) => [...prev, assistantMsg]);
    setChatSending(false);
  }, [chatInput, cluster, buildContext]);

  const sentColor = cluster ? sentimentColor(cluster.sentiment_score ?? 0) : "var(--color-neu)";
  const sentLbl = cluster
    ? cluster.sentiment_label || sentimentLabel(cluster.sentiment_score ?? 0)
    : "";

  return (
    <AnimatePresence>
      {cluster && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.div
            key="drawer"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            className="fixed right-0 top-0 bottom-0 z-50 flex w-full max-w-[600px] flex-col bg-[var(--color-paper)] border-l border-[var(--color-line)] shadow-2xl"
          >
            {/* Drawer header */}
            <div
              className="flex items-start justify-between gap-4 px-6 py-5 border-b border-[var(--color-line)]"
              style={{ borderLeft: `3px solid ${sentColor}` }}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-mute)]">
                    {cluster.category}
                  </span>
                  <span className="text-[var(--color-mute)] text-[11px]">·</span>
                  {cluster.published_at && (
                    <span className="text-[11px] text-[var(--color-mute)]">
                      {relativeTime(cluster.published_at)}
                    </span>
                  )}
                </div>
                <h2
                  className="font-display text-[18px] font-bold leading-snug text-[var(--color-ink)]"
                  style={{ textWrap: "balance" as never }}
                >
                  {cluster.rep_title}
                </h2>
              </div>
              <button
                onClick={onClose}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--color-line)] transition hover:bg-[var(--color-paper-2)] active:scale-95"
              >
                <X className="h-4 w-4" strokeWidth={2} />
              </button>
            </div>

            {/* Tab switcher */}
            <div className="flex border-b border-[var(--color-line)] px-6">
              {(["detail", "chat"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex items-center gap-1.5 px-1 py-3 mr-6 text-sm font-medium border-b-2 transition ${
                    activeTab === tab
                      ? "border-[var(--color-ink)] text-[var(--color-ink)]"
                      : "border-transparent text-[var(--color-mute)] hover:text-[var(--color-ink)]"
                  }`}
                >
                  {tab === "detail" ? (
                    <><BarChart2 className="h-3.5 w-3.5" strokeWidth={2} /> Story Detail</>
                  ) : (
                    <>
                      <MessageSquare className="h-3.5 w-3.5" strokeWidth={2} /> Chat
                      {chatMessages.length > 0 && (
                        <span className="ml-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-accent)] text-[9px] font-bold text-white">
                          {chatMessages.filter(m => m.role === "user").length}
                        </span>
                      )}
                    </>
                  )}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto">
              {activeTab === "detail" ? (
                <DetailTab cluster={cluster} detail={detail} detailLoading={detailLoading} />
              ) : (
                <ChatTab
                  messages={chatMessages}
                  sending={chatSending}
                  input={chatInput}
                  onInputChange={setChatInput}
                  onSend={sendMessage}
                  onOpenChat={() => setActiveTab("chat")}
                  inputRef={inputRef}
                  chatEndRef={chatEndRef}
                  clusterTitle={cluster.rep_title}
                  category={cluster.category}
                  entities={cluster.entity_union}
                />
              )}
            </div>

            {/* Chat about this story button (on detail tab) */}
            {activeTab === "detail" && (
              <div className="px-6 py-4 border-t border-[var(--color-line)] flex items-center gap-3">
                <button
                  onClick={() => setActiveTab("chat")}
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-[var(--color-ink)] px-4 py-3 text-sm font-semibold text-[var(--color-paper)] transition hover:opacity-90 active:scale-[0.97]"
                  style={{ transitionTimingFunction: "var(--ease-snap)" }}
                >
                  <MessageSquare className="h-4 w-4" strokeWidth={2} />
                  Chat about this story
                </button>
                {cluster.representative_url && (
                  <a
                    href={cluster.representative_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="flex items-center justify-center gap-1.5 rounded-xl border border-[var(--color-line)] px-4 py-3 text-sm font-medium text-[var(--color-mute)] transition hover:border-[var(--color-ink)] hover:text-[var(--color-ink)] active:scale-[0.97]"
                    style={{ transitionTimingFunction: "var(--ease-snap)" }}
                  >
                    <ExternalLink className="h-3.5 w-3.5" strokeWidth={2} />
                    Source
                  </a>
                )}
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

/* ---------- Detail Tab ---------- */

function DetailTab({
  cluster,
  detail,
  detailLoading,
}: {
  cluster: Cluster;
  detail: ClusterDetail | null;
  detailLoading: boolean;
}) {
  const sentColor = sentimentColor(cluster.sentiment_score ?? 0);
  const sentLbl = cluster.sentiment_label || sentimentLabel(cluster.sentiment_score ?? 0);
  const score = cluster.sentiment_score ?? 0;
  // sentiment bar: -1..+1 mapped to 0..100%
  const sentPct = Math.max(0, Math.min(100, ((score + 1) / 2) * 100));

  return (
    <div className="p-6 space-y-6">
      {/* Full summary */}
      <div>
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-mute)] mb-2">Summary</h3>
        <p className="text-[14.5px] leading-relaxed text-[var(--color-ink)]/85">
          {cluster.summary || "No summary available."}
        </p>
      </div>

      {/* Sentiment breakdown */}
      <div>
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-mute)] mb-3">
          Sentiment Analysis
        </h3>
        <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-paper-2)] p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-bold"
              style={{ background: `${sentColor}18`, color: sentColor, border: `1px solid ${sentColor}35` }}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: sentColor }} />
              {sentLbl.toUpperCase()}
            </span>
            <span className="font-mono text-sm font-bold" style={{ color: sentColor }}>
              {score > 0 ? "+" : ""}{score.toFixed(3)}
            </span>
          </div>
          {/* Visual bar */}
          <div className="relative h-2 rounded-full bg-[var(--color-paper)]">
            <div className="absolute top-0 left-1/2 h-full w-px bg-[var(--color-line)] z-10" />
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.abs(sentPct - 50)}%`, left: score >= 0 ? "50%" : `${sentPct}%` }}
              transition={{ duration: 0.6, ease: EASE }}
              className="absolute top-0 h-full rounded-full"
              style={{ background: sentColor, opacity: 0.8 }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-[var(--color-mute)] font-mono">
            <span>Very Negative (−1)</span>
            <span>Neutral</span>
            <span>Very Positive (+1)</span>
          </div>
        </div>
      </div>

      {/* Entity tags */}
      {cluster.entity_union && cluster.entity_union.length > 0 && (
        <div>
          <h3 className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-mute)] mb-3 flex items-center gap-1.5">
            <Tag className="h-3 w-3" strokeWidth={2} />
            Key Entities
          </h3>
          <div className="flex flex-wrap gap-2">
            {cluster.entity_union.map((entity, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-lg bg-[var(--color-paper-2)] border border-[var(--color-line)] px-2.5 py-1 text-[12px] font-medium text-[var(--color-ink)]/80"
              >
                {entity}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Source articles */}
      <div>
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-mute)] mb-3">
          {cluster.source_count} Source{cluster.source_count !== 1 ? "s" : ""} Covering This Story
        </h3>
        {detailLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="rounded-xl border border-[var(--color-line)] bg-[var(--color-paper-2)] h-16 animate-pulse" />
            ))}
          </div>
        ) : detail?.articles && detail.articles.length > 0 ? (
          <div className="space-y-2">
            {detail.articles.map((article, i) => (
              <a
                key={i}
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-start gap-3 rounded-xl border border-[var(--color-line)] bg-[var(--color-paper-2)] p-3.5 transition hover:border-[var(--color-ink)]/30 hover:bg-[var(--color-paper)]"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[11px] font-bold text-[var(--color-accent)]">{article.source}</span>
                    <span className="text-[10px] text-[var(--color-mute)]">
                      · {relativeTime(article.published_at)} · {new Date(article.published_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                    </span>
                  </div>
                  <p className="text-[13px] font-medium text-[var(--color-ink)] leading-snug line-clamp-2">
                    {article.title}
                  </p>
                </div>
                <ExternalLink className="h-3.5 w-3.5 shrink-0 mt-0.5 text-[var(--color-mute)] opacity-0 group-hover:opacity-100 transition" strokeWidth={2} />
              </a>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-mute)]">No individual source articles available.</p>
        )}
      </div>
    </div>
  );
}

/* ---------- Chat Tab ---------- */

function ChatTab({
  messages,
  sending,
  input,
  onInputChange,
  onSend,
  inputRef,
  chatEndRef,
  clusterTitle,
  category,
  entities,
}: {
  messages: ChatMessage[];
  sending: boolean;
  input: string;
  onInputChange: (v: string) => void;
  onSend: () => void;
  onOpenChat: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  chatEndRef: React.RefObject<HTMLDivElement | null>;
  clusterTitle: string;
  category: string;
  entities?: string[];
}) {
  const suggestions = useMemo(() => {
    const eStr = (entities && entities.length > 0) ? ` involving ${entities.slice(0, 2).join(" and ")}` : "";
    switch (category) {
      case "Politics": return [`What are the political implications${eStr}?`, `How does this affect current policies?`, `Who are the key political actors here?`];
      case "Economy": return [`What is the economic impact${eStr}?`, `How will this affect markets?`, `What are the financial risks?`];
      case "Conflict": return [`What triggered this conflict${eStr}?`, `Who are the main parties involved?`, `What does this mean for regional stability?`];
      case "Tech": return [`What are the technical innovations here?`, `How does this impact the industry${eStr}?`, `What are the security implications?`];
      default: return [`What are the key implications of this story?`, `Who are the main actors involved?`, `What's the historical context?`];
    }
  }, [category, entities]);

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 min-h-0">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20">
              <Bot className="h-5 w-5 text-[var(--color-accent)]" strokeWidth={1.75} />
            </div>
            <div>
              <p className="font-semibold text-[var(--color-ink)] text-sm">Ask about this story</p>
              <p className="text-[13px] text-[var(--color-mute)] mt-1 max-w-[260px]">
                I have full context for "{clusterTitle.slice(0, 60)}{clusterTitle.length > 60 ? "…" : ""}"
              </p>
            </div>
            <div className="flex flex-col gap-2 w-full max-w-[320px]">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => onInputChange(suggestion)}
                  className="rounded-xl border border-[var(--color-line)] bg-[var(--color-paper-2)] px-4 py-2.5 text-left text-[13px] text-[var(--color-mute)] transition hover:border-[var(--color-ink)]/30 hover:text-[var(--color-ink)]"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: EASE }}
              className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
            >
              <div
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                  msg.role === "user"
                    ? "bg-[var(--color-ink)] text-[var(--color-paper)]"
                    : "bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20 text-[var(--color-accent)]"
                }`}
              >
                {msg.role === "user" ? <User className="h-3.5 w-3.5" strokeWidth={2} /> : <Bot className="h-3.5 w-3.5" strokeWidth={2} />}
              </div>
              <div
                className={`max-w-[78%] rounded-2xl px-4 py-3 text-[14px] leading-relaxed ${
                  msg.role === "user"
                    ? "bg-[var(--color-ink)] text-[var(--color-paper)] rounded-tr-sm"
                    : "bg-[var(--color-paper-2)] border border-[var(--color-line)] text-[var(--color-ink)] rounded-tl-sm"
                }`}
              >
                {msg.content}
              </div>
            </motion.div>
          ))
        )}
        {sending && (
          <div className="flex gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20">
              <Bot className="h-3.5 w-3.5 text-[var(--color-accent)]" strokeWidth={2} />
            </div>
            <div className="rounded-2xl rounded-tl-sm bg-[var(--color-paper-2)] border border-[var(--color-line)] px-4 py-3">
              <div className="flex gap-1 items-center h-5">
                {[0, 1, 2].map((i) => (
                  <motion.span
                    key={i}
                    className="h-1.5 w-1.5 rounded-full bg-[var(--color-mute)]"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input bar */}
      <div className="px-6 py-4 border-t border-[var(--color-line)]">
        <div className="flex gap-2 items-center rounded-xl border border-[var(--color-line)] bg-[var(--color-paper-2)] px-4 py-2.5 focus-within:border-[var(--color-ink)]/40 transition">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
            placeholder="Ask anything about this story…"
            className="flex-1 bg-transparent text-sm text-[var(--color-ink)] placeholder:text-[var(--color-mute)] outline-none"
          />
          <button
            onClick={onSend}
            disabled={!input.trim() || sending}
            className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--color-ink)] text-[var(--color-paper)] transition hover:opacity-80 disabled:opacity-30 active:scale-95"
          >
            <Send className="h-3.5 w-3.5" strokeWidth={2} />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Sentiment helpers ---------- */

function sentimentColor(v: number) {
  if (v > 0.1) return "var(--color-pos)";
  if (v < -0.1) return "var(--color-neg)";
  return "var(--color-neu)";
}
function sentimentLabel(v: number) {
  if (v > 0.5) return "Very Positive";
  if (v > 0.1) return "Positive";
  if (v < -0.5) return "Very Negative";
  if (v < -0.1) return "Negative";
  return "Neutral";
}

function SentimentDot({ value }: { value: number }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 rounded-full shrink-0"
      style={{ background: sentimentColor(value) }}
    />
  );
}

/* ---------- Right Panel ---------- */

function RightPanel({
  stats,
}: {
  stats: DashboardStats | null;
}) {
  return (
    <aside className="hidden xl:flex w-[320px] shrink-0 flex-col gap-8 px-6 py-10 sticky top-0 h-screen overflow-y-auto">
      <Trending stats={stats} />
      <Sentiment stats={stats} />
    </aside>
  );
}

function Trending({ stats }: { stats: DashboardStats | null }) {
  const items = stats?.trending_entities?.slice(0, 8) ?? [];
  const max = items[0]?.count ?? 1;
  return (
    <section>
      <div className="flex items-center gap-2 mb-4">
        <Flame className="h-4 w-4 text-[var(--color-neg)]" strokeWidth={1.75} />
        <h3 className="font-display text-sm font-bold uppercase tracking-wider text-[var(--color-mute)]">Trending</h3>
      </div>
      {stats === null ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-8 rounded-lg bg-[var(--color-paper-2)] animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-[var(--color-mute)]">No trending entities yet.</p>
      ) : (
        <ul className="space-y-1">
          {items.map((e, i) => {
            const barPct = (e.count / max) * 100;
            return (
              <li key={e.entity} className="group relative overflow-hidden rounded-lg">
                <div
                  className="absolute inset-y-0 left-0 rounded-lg bg-[var(--color-paper-2)] transition-all duration-500"
                  style={{ width: `${barPct}%` }}
                />
                <div className="relative flex items-center justify-between px-3 py-2.5 text-sm">
                  <span className="flex items-center gap-3 min-w-0">
                    <span className="font-mono text-[10px] font-bold text-[var(--color-mute)] w-4 shrink-0">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="font-medium truncate text-[13px]">{e.entity}</span>
                  </span>
                  <span
                    className="font-mono text-[11px] font-bold shrink-0 ml-2 tabular-nums"
                    style={{ color: `oklch(0.62 0.13 155 / ${0.5 + barPct / 200})` }}
                  >
                    {e.count}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Sentiment({ stats }: { stats: DashboardStats | null }) {
  const entries = useMemo(
    () => Object.entries(stats?.sentiment_by_category ?? {}),
    [stats],
  );
  return (
    <section>
      <div className="flex items-center gap-2 mb-4">
        <Activity className="h-4 w-4 text-[var(--color-accent)]" strokeWidth={1.75} />
        <h3 className="font-display text-sm font-bold uppercase tracking-wider text-[var(--color-mute)]">Sentiment</h3>
      </div>
      {stats === null ? (
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 rounded bg-[var(--color-paper-2)] animate-pulse" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <p className="text-sm text-[var(--color-mute)]">No sentiment data yet.</p>
      ) : (
        <ul className="space-y-3">
          {entries.map(([cat, val]) => {
            const pct = Math.max(0, Math.min(100, ((val + 1) / 2) * 100));
            const color = sentimentColor(val);
            return (
              <li key={cat}>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="font-medium text-[var(--color-ink)]">{cat}</span>
                  <span className="font-mono font-bold" style={{ color }}>
                    {val > 0 ? "+" : ""}{val.toFixed(2)}
                  </span>
                </div>
                <div className="relative h-2 rounded-full bg-[var(--color-paper-2)]">
                  <div className="absolute top-0 left-1/2 h-full w-px bg-[var(--color-line)] z-10" />
                  <motion.div
                    initial={{ width: 0, left: "50%", x: "0%" }}
                    animate={{
                      width: `${Math.abs(pct - 50)}%`,
                      left: val >= 0 ? "50%" : `${pct}%`,
                      x: "0%",
                    }}
                    transition={{ duration: 0.7, ease: EASE }}
                    className="absolute top-0 h-full rounded-full"
                    style={{ background: color, opacity: 0.8 }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

