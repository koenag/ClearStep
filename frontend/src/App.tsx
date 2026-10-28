import { useEffect, useState, type FormEvent } from "react";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  LayoutDashboard,
  Database,
  GitBranch,
  History,
  ArrowUpRight,
  ArrowRight,
  Plus,
  Upload,
  CheckCircle2,
  Info,
  Sparkles,
  Coffee,
  ChevronDown,
  TrendingUp,
  Wallet,
  ChartNoAxesCombined,
  X,
} from "lucide-react";
import { api, usd, type Kind, type Analysis } from "./api";

type Business = {
  id: number;
  name: string;
  industry: string;
  description: string;
};
type Baseline = {
  revenue: number;
  variable_costs: number;
  contribution_profit: number;
  contribution_margin: number;
  units: number;
  transactions: number | null;
  line_items: number;
  period_start: string;
  period_end: string;
  products: { product: string; revenue: number; units: number; cost: number }[];
  monthly: { month: string; revenue: number }[];
  warnings: string[];
  source_filename: string;
};
type Saved = {
  id: number;
  title: string;
  decision_type: Kind;
  status: string;
  selected_scenario: string;
  created_at: string;
  snapshot: Analysis;
  question: string;
};
type Observation = {
  id: number;
  period: number;
  actual: { net_benefit: number };
  expected: { net_benefit: number; repeat_pending?: boolean; basis: string };
  variance: number;
  notes: string;
};
const supplierDefaults = {
  current_unit_cost: 12,
  new_unit_cost: 10,
  monthly_quantity: 100,
  current_shipping: 40,
  new_shipping: 50,
  switching_cost: 400,
  current_moq: 0,
  new_moq: 0,
  horizon: 12,
  current_escalation: 0,
  new_escalation: 0,
  demand_variation: 0.2,
  cost_variation: 0.05,
};
const eventDefaults = {
  event_cost: 500,
  incremental_visits: 120,
  average_spend: 9,
  contribution_margin: 0.65,
  repeat_rate: 0.2,
  repeat_visits: 2,
  staffing_cost: 150,
  horizon: 12,
  attendance_variation: 0.25,
  spend_variation: 0.1,
  expense_variation: 0.1,
  repeat_variation: 0.25,
};
const labels: Record<string, [string, string]> = {
  current_unit_cost: ["Current unit cost", "USD / unit"],
  new_unit_cost: ["Proposed unit cost", "USD / unit"],
  monthly_quantity: ["Expected monthly demand", "units / month"],
  current_shipping: ["Current shipping", "USD / purchase month"],
  new_shipping: ["Proposed shipping", "USD / purchase month"],
  switching_cost: ["One-time switching cost", "USD"],
  current_moq: ["Current minimum order", "units"],
  new_moq: ["Proposed minimum order", "units"],
  horizon: ["Forecast horizon", "months"],
  current_escalation: ["Current annual escalation", "ratio · 0.05 = 5%"],
  new_escalation: ["Proposed annual escalation", "ratio · 0.05 = 5%"],
  demand_variation: ["Demand sensitivity", "ratio · ± around base"],
  cost_variation: ["Proposed cost sensitivity", "ratio · ± around base"],
  event_cost: ["Event expenses", "USD · excludes extra staffing"],
  incremental_visits: [
    "Incremental customer visits",
    "visits above normal trade",
  ],
  average_spend: ["Average spend per visit", "USD"],
  contribution_margin: ["Contribution margin", "ratio · 0.65 = 65%"],
  repeat_rate: ["Repeat customer rate", "ratio · 0 to 1"],
  repeat_visits: ["Repeat visits per retained customer", "total over horizon"],
  staffing_cost: ["Additional staffing", "USD · not included above"],
  attendance_variation: ["Attendance sensitivity", "ratio · ± around base"],
  spend_variation: ["Spend sensitivity", "ratio · ± around base"],
  expense_variation: ["Expense sensitivity", "ratio · ± around base"],
  repeat_variation: ["Repeat rate sensitivity", "ratio · ± around base"],
};
const nav = [
  ["Overview", LayoutDashboard],
  ["Data Sources", Database],
  ["Analyze Decision", GitBranch],
  ["Decision History", History],
] as const;

function Metric({
  label,
  value,
  note,
  icon: Icon = Wallet,
  positive = false,
}: {
  label: string;
  value: string;
  note: string;
  icon?: typeof Wallet;
  positive?: boolean;
}) {
  return (
    <div className="metric">
      <div className="metric-top">
        {label}
        <Icon size={17} />
      </div>
      <strong className={positive ? "teal" : ""}>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
function ChartBox({ children }: { children: React.ReactNode }) {
  return <div className="chart">{children}</div>;
}
function Empty({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Database size={32} />
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("Overview"),
    [businesses, setBusinesses] = useState<Business[]>([]),
    [business, setBusiness] = useState<Business | null>(null),
    [baseline, setBaseline] = useState<Baseline | null>(null),
    [sources, setSources] = useState<any[]>([]),
    [history, setHistory] = useState<Saved[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [question, setQuestion] = useState(""),
    [kind, setKind] = useState<Kind>("supplier_switch"),
    [values, setValues] =
      useState<Record<string, string | number>>(supplierDefaults),
    [provenance, setProvenance] = useState<Record<string, string>>({}),
    [analysis, setAnalysis] = useState<Analysis | null>(null),
    [routing, setRouting] = useState(""),
    [title, setTitle] = useState("Coffee bean supplier comparison"),
    [selected, setSelected] = useState<Saved | null>(null),
    [observations, setObservations] = useState<Observation[]>([]),
    [showCreate, setShowCreate] = useState(false),
    [newName, setNewName] = useState(""),
    [scenario, setScenario] = useState("Base case");
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Something went wrong. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function refresh(b: Business) {
    const [m, s, h] = await Promise.all([
      api("/businesses/" + b.id + "/metrics"),
      api("/businesses/" + b.id + "/sources"),
      api("/decisions?business_id=" + b.id),
    ]);
    setBaseline(m.baseline);
    setSources(s);
    setHistory(h);
  }
  useEffect(() => {
    void run(async () => {
      const all = await api<Business[]>("/businesses");
      setBusinesses(all);
      if (all.length) {
        setBusiness(all[0]);
        await refresh(all[0]);
      }
    });
  }, []);
  function chooseKind(k: Kind) {
    setKind(k);
    setValues(k === "supplier_switch" ? supplierDefaults : eventDefaults);
    setProvenance({});
    setAnalysis(null);
    setSelected(null);
    setTitle(
      k === "supplier_switch"
        ? "Coffee bean supplier comparison"
        : "Neighborhood promotional event",
    );
    setRouting("");
    setScenario("Base case");
  }
  async function loadDemo() {
    await run(async () => {
      const b = await api<Business>("/demo/seed", "POST");
      setBusiness(b);
      setAnalysis(null);
      setSelected(null);
      setBusinesses(await api("/businesses"));
      await refresh(b);
      setNotice("Fictional Juniper Coffee data is ready to explore.");
      setPage("Overview");
    });
  }
  async function interpret() {
    if (!business) return;
    await run(async () => {
      const i = await api("/decisions/interpret", "POST", {
        business_id: business.id,
        question,
      });
      if (i.decision_type === "unsupported") {
        setAnalysis(null);
        setSelected(null);
        setRouting(i.message);
        return;
      }
      chooseKind(i.decision_type);
      setRouting(
        i.message +
          " Required: " +
          i.required_inputs.map((k: string) => labels[k]?.[0] || k).join(", ") +
          ". Mode: " +
          i.mode +
          ".",
      );
      if (i.suggested_inputs.contribution_margin !== undefined) {
        setValues({
          ...eventDefaults,
          contribution_margin: i.suggested_inputs.contribution_margin,
        });
        setProvenance({ contribution_margin: "observed" });
      }
    });
  }
  async function calculate() {
    await run(async () => {
      const p = Object.fromEntries(
        Object.keys(values).map((k) => [k, provenance[k] || "assumed"]),
      );
      const a = await api<Analysis>("/decisions/analyze", "POST", {
        decision_type: kind,
        inputs: values,
        provenance: p,
      });
      setAnalysis(a);
      setSelected(null);
    });
  }
  async function reopen(d: Saved) {
    await run(async () => {
      const fresh = await api<Saved>("/decisions/" + d.id);
      setSelected(fresh);
      setAnalysis(fresh.snapshot);
      setKind(fresh.decision_type);
      setValues(fresh.snapshot.inputs);
      setProvenance(
        Object.fromEntries(
          fresh.snapshot.assumptions.map((a) => [a.name, a.provenance]),
        ),
      );
      setTitle(fresh.title);
      setQuestion(fresh.question);
      setScenario(fresh.selected_scenario);
      setObservations(await api("/decisions/" + d.id + "/outcomes"));
      setPage("Analyze Decision");
    });
  }
  const base = analysis?.scenarios.find((s) => s.name === scenario)?.result;
  const cumulative = analysis?.scenarios[1].result.timeline.map((r, i) => ({
    month: r.month,
    ...Object.fromEntries(
      analysis.scenarios.map((s) => [s.name, s.result.timeline[i].cumulative]),
    ),
  }));
  const hasDemo = business?.name.includes("Fictional");
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("Overview");
          }}
        >
          <span className="brand-symbol">
            <ChartNoAxesCombined size={23} />
          </span>
          clarity<span className="brand-dot">.</span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">
            <Coffee size={19} />
          </span>
          <div>
            <strong>{business?.name.split(" •")[0] || "Your workspace"}</strong>
            <small>
              {business ? "Business workspace" : "Get started below"}
            </small>
          </div>
          <ChevronDown size={14} />
        </div>
        {businesses.length > 1 && (
          <select
            aria-label="Select business"
            className="business-select"
            value={business?.id}
            onChange={(e) => {
              const b = businesses.find(
                (b) => b.id === Number(e.target.value),
              )!;
              setBusiness(b);
              setAnalysis(null);
              setSelected(null);
              void run(() => refresh(b));
            }}
          >
            {businesses.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        )}
        <p className="nav-label">WORKSPACE</p>
        <nav>
          {nav.map(([name, Icon]) => (
            <button
              key={name}
              className={page === name ? "active" : ""}
              onClick={() => setPage(name)}
            >
              <Icon size={19} />
              {name}
              {name === "Analyze Decision" && (
                <span className="new-tag">NEW</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="demo-card">
            <span>
              <Sparkles size={16} /> A little clarity goes a long way
            </span>
            <p>Explore real workflows with a fictional neighborhood café.</p>
            <button disabled={busy} onClick={() => void loadDemo()}>
              Load Demo Business <ArrowUpRight size={15} />
            </button>
          </div>
          <button className="create-link" onClick={() => setShowCreate(true)}>
            <Plus size={16} /> Create a business
          </button>
          <div className="local-status">
            <i /> Local workspace <span>v1.0</span>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Workspace <span className="slash">/</span> <b>{page}</b>
          </span>
          <span className="top-right">
            <span className="pill">
              <i /> Deterministic financial engine
            </span>
            <span className="avatar">JC</span>
          </span>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">YOUR BUSINESS, IN FOCUS</div>
              <h1>
                {page === "Overview"
                  ? "A clearer view. Better decisions."
                  : page === "Analyze Decision"
                    ? "Make your next move with confidence."
                    : page === "Data Sources"
                      ? "Good decisions start with good data."
                      : "From a decision to a difference."}
              </h1>
              <p>
                {page === "Overview"
                  ? "Understand where you stand. Explore what comes next."
                  : page === "Data Sources"
                    ? "Bring your records together and see what the numbers tell you."
                    : page === "Decision History"
                      ? "Keep the original forecast. Learn from what actually happened."
                      : "Compare the possibilities, review the assumptions, and follow the numbers."}
              </p>
            </div>
            {page === "Overview" && (
              <button
                className="primary"
                disabled={!business}
                onClick={() => {
                  chooseKind("supplier_switch");
                  setPage("Analyze Decision");
                }}
              >
                <Plus size={17} /> Analyze a decision
              </button>
            )}
          </div>
          {error && (
            <div role="alert" className="alert error">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="alert success">
              <CheckCircle2 size={17} />
              {notice}
            </div>
          )}
          {busy && (
            <div role="status" className="loading">
              <span className="spinner" /> Working on it…
            </div>
          )}
          {showCreate && (
            <form
              className="panel create-form"
              onSubmit={(e) => {
                e.preventDefault();
                void run(async () => {
                  const b = await api("/businesses", "POST", {
                    name: newName,
                    industry: "Coffee shop",
                  });
                  setBusiness(b);
                  setBusinesses(await api("/businesses"));
                  await refresh(b);
                  setAnalysis(null);
                  setSelected(null);
                  setShowCreate(false);
                });
              }}
            >
              <label>
                Business name
                <input
                  required
                  maxLength={120}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </label>
              <button className="primary" disabled={busy}>
                Create workspace
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setShowCreate(false)}
              >
                Cancel
              </button>
            </form>
          )}
          {!business ? (
            <Empty
              title="Your next decision starts here"
              body="Load the fictional café to explore every feature, or create a business and upload your sales."
              action={
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => void loadDemo()}
                >
                  <Sparkles size={17} /> Load Demo Business
                </button>
              }
            />
          ) : (
            <>
              <div className="context-strip">
                <span>
                  <span className="tiny-icon">
                    <Coffee size={14} />
                  </span>
                  <b>{business.name.split(" •")[0]}</b>
                  <span className="muted">{business.industry}</span>
                </span>
                <span>
                  {hasDemo && <b className="demo-badge">FICTIONAL DEMO</b>}
                  {baseline && (
                    <span className="period">
                      {baseline.period_start} — {baseline.period_end}
                      <small> · Recorded period</small>
                    </span>
                  )}
                </span>
              </div>
              {page === "Overview" && (
                <>
                  {baseline ? (
                    <>
                      <div className="metric-grid">
                        <Metric
                          label="Recorded revenue"
                          value={usd(baseline.revenue)}
                          note="Observed · uploaded sales"
                          icon={TrendingUp}
                        />
                        <Metric
                          label="Variable costs"
                          value={usd(baseline.variable_costs)}
                          note="Product costs from recorded sales"
                        />
                        <Metric
                          label="Contribution profit"
                          value={usd(baseline.contribution_profit)}
                          note="Revenue less variable product costs"
                          positive
                          icon={ChartNoAxesCombined}
                        />
                        <Metric
                          label="Contribution margin"
                          value={
                            (baseline.contribution_margin * 100).toFixed(1) +
                            "%"
                          }
                          note="Before fixed operating expenses"
                          positive
                          icon={TrendingUp}
                        />
                      </div>
                      <div className="overview-grid">
                        <section className="panel">
                          <div className="panel-heading">
                            <div>
                              <h2>Revenue over time</h2>
                              <p>Recorded monthly sales · USD</p>
                            </div>
                            <span className="subtle-tag">
                              {baseline.monthly.length} months
                            </span>
                          </div>
                          <ChartBox>
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart
                                data={baseline.monthly}
                                margin={{
                                  left: 4,
                                  right: 15,
                                  top: 18,
                                  bottom: 5,
                                }}
                              >
                                <defs>
                                  <linearGradient
                                    id="revenueFill"
                                    x1="0"
                                    y1="0"
                                    x2="0"
                                    y2="1"
                                  >
                                    <stop
                                      offset="0%"
                                      stopColor="#14867c"
                                      stopOpacity={0.2}
                                    />
                                    <stop
                                      offset="100%"
                                      stopColor="#14867c"
                                      stopOpacity={0}
                                    />
                                  </linearGradient>
                                </defs>
                                <CartesianGrid
                                  vertical={false}
                                  stroke="#edf0f2"
                                />
                                <XAxis
                                  dataKey="month"
                                  axisLine={false}
                                  tickLine={false}
                                  tick={{ fontSize: 12 }}
                                />
                                <YAxis
                                  axisLine={false}
                                  tickLine={false}
                                  tickFormatter={(n) => "$" + n / 1000 + "k"}
                                  tick={{ fontSize: 11 }}
                                />
                                <Tooltip formatter={(v) => usd(Number(v))} />
                                <Area
                                  type="monotone"
                                  dataKey="revenue"
                                  name="Revenue"
                                  stroke="#14867c"
                                  strokeWidth={3}
                                  fill="url(#revenueFill)"
                                  dot={{ r: 4, fill: "#fff", strokeWidth: 2 }}
                                />
                              </AreaChart>
                            </ResponsiveContainer>
                          </ChartBox>
                          <div className="chart-footer">
                            <span className="legend-dot" /> Observed revenue{" "}
                            <span>No extrapolation applied</span>
                          </div>
                        </section>
                        <section className="panel">
                          <div className="panel-heading">
                            <div>
                              <h2>Your product mix</h2>
                              <p>Revenue by product · recorded period</p>
                            </div>
                            <Coffee size={19} className="muted" />
                          </div>
                          <div className="product-list">
                            {[...baseline.products]
                              .sort((a, b) => b.revenue - a.revenue)
                              .map((p, i) => (
                                <div className="product-row" key={p.product}>
                                  <div>
                                    <span>{p.product}</span>
                                    <strong>{usd(p.revenue)}</strong>
                                  </div>
                                  <div className="bar-track">
                                    <span
                                      style={{
                                        width:
                                          (p.revenue /
                                            Math.max(
                                              ...baseline.products.map(
                                                (p) => p.revenue,
                                              ),
                                            )) *
                                            100 +
                                          "%",
                                        background: [
                                          "#16867d",
                                          "#55a69d",
                                          "#82bbb3",
                                          "#b2d1c9",
                                          "#c9dfd7",
                                        ][i % 5],
                                      }}
                                    />
                                  </div>
                                </div>
                              ))}
                          </div>
                          <div className="chart-footer">
                            {baseline.units.toLocaleString()} units sold{" "}
                            <span>{baseline.line_items} sales line items</span>
                          </div>
                        </section>
                      </div>
                      <section className="insight-banner">
                        <div className="insight-icon">
                          <Sparkles size={23} />
                        </div>
                        <div>
                          <h3>What could your next decision unlock?</h3>
                          <p>
                            Compare a supplier quote or model a neighborhood
                            event. Every result starts with transparent
                            assumptions.
                          </p>
                        </div>
                        <button
                          className="secondary"
                          onClick={() => {
                            chooseKind("supplier_switch");
                            setPage("Analyze Decision");
                          }}
                        >
                          Explore a decision <ArrowRight size={16} />
                        </button>
                      </section>
                      <div className="overview-grid lower">
                        <section className="panel">
                          <div className="panel-heading">
                            <div>
                              <h2>Recent decisions</h2>
                              <p>
                                A record of what you planned and what you
                                learned
                              </p>
                            </div>
                            <button
                              className="text-button"
                              onClick={() => setPage("Decision History")}
                            >
                              View all <ArrowRight size={14} />
                            </button>
                          </div>
                          {history.length ? (
                            history.slice(0, 3).map((d) => (
                              <button
                                className="decision-row"
                                key={d.id}
                                onClick={() => void reopen(d)}
                              >
                                <span className="decision-icon">
                                  {d.decision_type === "supplier_switch" ? (
                                    <GitBranch size={19} />
                                  ) : (
                                    <Coffee size={19} />
                                  )}
                                </span>
                                <div>
                                  <strong>{d.title}</strong>
                                  <small>
                                    {d.decision_type === "supplier_switch"
                                      ? "Supplier comparison"
                                      : "Promotional event"}{" "}
                                    · {d.status}
                                  </small>
                                </div>
                                <span className="decision-value">
                                  {usd(
                                    d.snapshot.scenarios[1].result.net_benefit,
                                  )}
                                  <small>base projection</small>
                                </span>
                                <ArrowUpRight size={16} />
                              </button>
                            ))
                          ) : (
                            <p className="muted padded">
                              Your saved analyses will appear here.
                            </p>
                          )}
                        </section>
                        <section className="panel completeness">
                          <div className="panel-heading">
                            <div>
                              <h2>Know your data</h2>
                              <p>Clear inputs. Clear boundaries.</p>
                            </div>
                            <Info size={18} className="muted" />
                          </div>
                          <div className="data-check">
                            <CheckCircle2 size={17} />
                            <span>
                              Sales and product costs <b>Observed</b>
                            </span>
                          </div>
                          <div className="data-check">
                            <Info size={17} />
                            <span>
                              Fixed expenses & net profit{" "}
                              <b className="amber">Missing</b>
                            </span>
                          </div>
                          <div className="data-check">
                            <Info size={17} />
                            <span>
                              Unique transactions{" "}
                              <b className="amber">
                                {baseline.transactions === null
                                  ? "Unavailable"
                                  : baseline.transactions}
                              </b>
                            </span>
                          </div>
                          <p className="fine-print">
                            Your baseline uses {baseline.source_filename}.
                            Contribution profit excludes rent, salaries, and
                            other fixed expenses.
                          </p>
                        </section>
                      </div>
                    </>
                  ) : (
                    <Empty
                      title="Let’s build your financial baseline"
                      body="Upload a sales CSV with dates, products, quantities, prices, and unit costs."
                      action={
                        <button
                          className="primary"
                          onClick={() => setPage("Data Sources")}
                        >
                          Add your data <ArrowRight size={16} />
                        </button>
                      }
                    />
                  )}
                </>
              )}
              {page === "Data Sources" && (
                <>
                  <section className="panel upload-panel">
                    <span className="upload-icon">
                      <Upload size={28} />
                    </span>
                    <h2>Bring your sales into focus</h2>
                    <p>
                      Upload a CSV, up to 5 MB. Each upload replaces the active
                      baseline.
                    </p>
                    <label className="primary upload-label">
                      <Upload size={16} />{" "}
                      {busy ? "Uploading…" : "Choose sales CSV"}
                      <input
                        aria-label="Upload sales CSV"
                        type="file"
                        accept=".csv,text/csv"
                        disabled={busy}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file)
                            void run(async () => {
                              const data = new FormData();
                              data.append("file", file);
                              const result = await api(
                                "/businesses/" + business.id + "/uploads",
                                "POST",
                                data,
                              );
                              await refresh(business);
                              setNotice(
                                "Upload complete. " +
                                  (result.warnings.join(" ") ||
                                    "All rows parsed successfully."),
                              );
                            });
                          e.target.value = "";
                        }}
                      />
                    </label>
                    <code>date, product, quantity, unit_price, unit_cost</code>
                    <small>
                      Optional: transaction_id. Common headers such as qty,
                      price, and order_id are normalized.
                    </small>
                  </section>
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h2>Source library</h2>
                        <p>
                          Previously uploaded snapshots stay available in your
                          local database.
                        </p>
                      </div>
                      <span className="subtle-tag">{sources.length} files</span>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Source</th>
                            <th>Rows</th>
                            <th>Uploaded</th>
                            <th>Status</th>
                            <th>Baseline</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sources.map((s, i) => (
                            <tr key={s.id}>
                              <td>
                                <strong>{s.filename}</strong>
                                {s.warnings.map((w: string) => (
                                  <small className="amber block" key={w}>
                                    {w}
                                  </small>
                                ))}
                              </td>
                              <td>{s.row_count}</td>
                              <td>
                                {new Date(s.uploaded_at).toLocaleDateString()}
                              </td>
                              <td>
                                <span className="status">{s.status}</span>
                              </td>
                              <td>
                                {i === 0 ? "Active snapshot" : "Archived"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                  {baseline && (
                    <section className="panel padded">
                      <h2>Data completeness & parsing notes</h2>
                      {baseline.warnings.map((w) => (
                        <p className="warning-line" key={w}>
                          <Info size={16} />
                          {w}
                        </p>
                      ))}
                    </section>
                  )}
                </>
              )}
              {page === "Analyze Decision" && (
                <>
                  <section className="panel question-panel">
                    <span className="step">1</span>
                    <div>
                      <h2>What are you considering?</h2>
                      <p>
                        Start with a question, or choose a supported decision
                        below.
                      </p>
                      <div className="question-input">
                        <input
                          aria-label="Decision question"
                          value={question}
                          maxLength={2000}
                          onChange={(e) => setQuestion(e.target.value)}
                          placeholder="Should I switch coffee bean suppliers?"
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && question.length >= 3)
                              void interpret();
                          }}
                        />
                        <button
                          className="primary"
                          disabled={busy || question.length < 3}
                          onClick={() => void interpret()}
                        >
                          Understand question <ArrowRight size={16} />
                        </button>
                      </div>
                      {routing && (
                        <p role="status" className="routing">
                          <Info size={15} />
                          {routing}
                        </p>
                      )}
                      <div className="decision-tabs">
                        <button
                          className={kind === "supplier_switch" ? "chosen" : ""}
                          onClick={() => chooseKind("supplier_switch")}
                        >
                          <GitBranch size={16} /> Switch suppliers
                        </button>
                        <button
                          className={
                            kind === "promotional_event" ? "chosen" : ""
                          }
                          onClick={() => chooseKind("promotional_event")}
                        >
                          <Coffee size={16} /> Host a promotional event
                        </button>
                      </div>
                    </div>
                  </section>
                  <section className="panel assumptions-panel">
                    <div className="panel-heading">
                      <div className="step-heading">
                        <span className="step">2</span>
                        <div>
                          <h2>
                            {selected
                              ? "Original saved inputs"
                              : "Review your assumptions"}
                          </h2>
                          <p>
                            {selected
                              ? "Changing these creates a new analysis; the saved forecast is preserved."
                              : "Illustrative defaults are assumptions. Confirm or edit every input before deciding."}
                          </p>
                        </div>
                      </div>
                      <span className="subtle-tag">
                        {kind === "supplier_switch"
                          ? "Cash procurement model"
                          : "Event scenario simulator"}
                      </span>
                    </div>
                    <div className="input-grid">
                      {Object.entries(values).map(([key, value]) => (
                        <label className="input-field" key={key}>
                          <span>
                            {labels[key]?.[0] || key}
                            <b
                              className={
                                "provenance " + (provenance[key] || "assumed")
                              }
                            >
                              {provenance[key] || "assumed"}
                            </b>
                          </span>
                          <div className="number-wrap">
                            <input
                              aria-label={labels[key]?.[0] || key}
                              type="number"
                              min={key === "horizon" ? 1 : 0}
                              max={
                                key === "horizon"
                                  ? 60
                                  : labels[key]?.[1].startsWith("ratio")
                                    ? 1
                                    : undefined
                              }
                              step={
                                ["horizon", "current_moq", "new_moq"].includes(
                                  key,
                                )
                                  ? 1
                                  : "any"
                              }
                              value={value}
                              onChange={(e) => {
                                setValues({ ...values, [key]: e.target.value });
                                setProvenance({ ...provenance, [key]: "user" });
                                setAnalysis(null);
                                setSelected(null);
                              }}
                            />
                            <small>{labels[key]?.[1]}</small>
                          </div>
                          <button
                            className="confirm-input"
                            disabled={provenance[key] === "user"}
                            onClick={() => {
                              setProvenance({ ...provenance, [key]: "user" });
                              setAnalysis(null);
                              setSelected(null);
                            }}
                          >
                            {provenance[key] === "user"
                              ? "Confirmed by you"
                              : "Confirm value"}
                          </button>
                        </label>
                      ))}
                    </div>
                    <div className="form-footer">
                      <span>
                        <Info size={15} /> No AI call is needed for
                        calculations.
                      </span>
                      <button
                        className="primary"
                        disabled={
                          busy || Object.values(values).some((v) => v === "")
                        }
                        onClick={() => void calculate()}
                      >
                        <ChartNoAxesCombined size={17} /> Calculate scenarios
                      </button>
                    </div>
                  </section>
                  {analysis && base && (
                    <>
                      <section className="result-summary">
                        <div className="eyebrow">BASE-CASE CONCLUSION</div>
                        <h2>{analysis.summary}</h2>
                        <p>
                          {selected ? "Original saved forecast · " : ""}Model v
                          {analysis.calculation_version} ·{" "}
                          {analysis.scenario_note}
                        </p>
                      </section>
                      <div className="scenario-picker">
                        {analysis.scenarios.map((s) => (
                          <button
                            key={s.name}
                            className={scenario === s.name ? "chosen" : ""}
                            onClick={() => setScenario(s.name)}
                          >
                            {s.name}
                            <b>{usd(s.result.net_benefit)}</b>
                          </button>
                        ))}
                      </div>
                      <div className="metric-grid">
                        <Metric
                          label="Net projected benefit"
                          value={usd(base.net_benefit)}
                          note={
                            scenario + " · over " + base.horizon + " months"
                          }
                          positive={base.net_benefit > 0}
                        />
                        <Metric
                          label="Return on investment"
                          value={
                            base.roi === null
                              ? "Not defined"
                              : base.roi.toFixed(1) + "%"
                          }
                          note={
                            kind === "supplier_switch"
                              ? "Basis: one-time switching cost"
                              : "Basis: event + staffing costs"
                          }
                        />
                        <Metric
                          label={
                            kind === "supplier_switch"
                              ? "Sustained cash break-even"
                              : "Break-even incremental visits"
                          }
                          value={
                            kind === "supplier_switch"
                              ? base.break_even_month === null
                                ? "Beyond horizon"
                                : "Month " + base.break_even_month
                              : base.break_even_visits === null
                                ? "Not achievable"
                                : base.break_even_visits + " visits"
                          }
                          note={
                            kind === "supplier_switch"
                              ? "After switching cost · within horizon"
                              : "Includes assumed repeat contribution"
                          }
                        />
                        <Metric
                          label="Upfront cash required"
                          value={usd(base.upfront_cash)}
                          note={
                            kind === "supplier_switch"
                              ? "First purchase + switching cost"
                              : "Event + additional staffing"
                          }
                        />
                      </div>
                      <section className="panel">
                        <div className="panel-heading">
                          <div>
                            <h2>
                              {kind === "supplier_switch"
                                ? "Cumulative net cash savings"
                                : "Net benefit by scenario"}
                            </h2>
                            <p>
                              {kind === "supplier_switch"
                                ? "Compared with current supplier · includes switching cost"
                                : "Cumulative over the forecast horizon · no invented monthly timing"}
                            </p>
                          </div>
                        </div>
                        <ChartBox>
                          <ResponsiveContainer width="100%" height="100%">
                            {kind === "supplier_switch" ? (
                              <LineChart data={cumulative}>
                                <CartesianGrid
                                  vertical={false}
                                  stroke="#edf0f2"
                                />
                                <XAxis
                                  dataKey="month"
                                  tickFormatter={(n) => "M" + n}
                                />
                                <YAxis
                                  tickFormatter={(n) => usd(n)}
                                  width={75}
                                />
                                <Tooltip formatter={(v) => usd(Number(v))} />
                                <Legend />
                                {analysis.scenarios.map((s, i) => (
                                  <Line
                                    key={s.name}
                                    dataKey={s.name}
                                    stroke={
                                      ["#b78a56", "#14867c", "#6b8ecc"][i]
                                    }
                                    strokeWidth={s.name === "Base case" ? 3 : 2}
                                    dot={false}
                                  />
                                ))}
                              </LineChart>
                            ) : (
                              <BarChart
                                data={analysis.scenarios.map((s) => ({
                                  name: s.name,
                                  net: s.result.net_benefit,
                                }))}
                              >
                                <CartesianGrid
                                  vertical={false}
                                  stroke="#edf0f2"
                                />
                                <XAxis dataKey="name" />
                                <YAxis
                                  width={75}
                                  tickFormatter={(n) => usd(n)}
                                />
                                <Tooltip formatter={(v) => usd(Number(v))} />
                                <Bar
                                  dataKey="net"
                                  name="Net benefit"
                                  fill="#14867c"
                                  radius={[5, 5, 0, 0]}
                                />
                              </BarChart>
                            )}
                          </ResponsiveContainer>
                        </ChartBox>
                      </section>
                      <div className="two-columns">
                        <section className="panel padded">
                          <h2>
                            {kind === "supplier_switch"
                              ? "Cash cost comparison"
                              : "Where the benefit comes from"}
                          </h2>
                          {kind === "supplier_switch" ? (
                            <>
                              <div className="detail-line">
                                <span>Current average monthly purchases</span>
                                <b>{usd(base.current_monthly_cost!)}</b>
                              </div>
                              <div className="detail-line">
                                <span>Proposed average monthly purchases</span>
                                <b>{usd(base.proposed_monthly_cost!)}</b>
                              </div>
                              <div className="detail-line">
                                <span>Average monthly cash savings</span>
                                <b>{usd(base.monthly_savings!)}</b>
                              </div>
                            </>
                          ) : (
                            <>
                              <div className="detail-line">
                                <span>Initial visit contribution</span>
                                <b>{usd(base.event_contribution!)}</b>
                              </div>
                              <div className="detail-line">
                                <span>Assumed repeat contribution</span>
                                <b>{usd(base.repeat_contribution!)}</b>
                              </div>
                              <div className="detail-line">
                                <span>Event + staffing expenses</span>
                                <b>{usd(base.total_cost!)}</b>
                              </div>
                            </>
                          )}
                        </section>
                        <section className="panel padded">
                          <h2>Risks & modeling boundaries</h2>
                          {analysis.risks.map((r) => (
                            <p className="warning-line" key={r}>
                              <Info size={15} />
                              {r}
                            </p>
                          ))}
                        </section>
                      </div>
                      <section className="panel padded">
                        <h2>Input provenance</h2>
                        <p className="muted">
                          Edit inputs above to recalculate. All non-observed
                          defaults remain clearly labeled assumptions.
                        </p>
                        <div className="provenance-list">
                          {analysis.assumptions.map((a) => (
                            <span key={a.name}>
                              {labels[a.name]?.[0]}: <b>{a.value}</b>{" "}
                              <small className={"provenance " + a.provenance}>
                                {a.provenance}
                              </small>
                            </span>
                          ))}
                        </div>
                      </section>
                      <section className="panel save-panel">
                        <div>
                          <h2>
                            {selected
                              ? "Saved forecast #" + selected.id
                              : "Keep this decision in view"}
                          </h2>
                          <p>
                            Save a reproducible snapshot, then track the
                            results.
                          </p>
                        </div>
                        {selected ? (
                          <select
                            aria-label="Decision status"
                            value={selected.status}
                            onChange={(e) =>
                              void run(async () => {
                                const d = await api(
                                  "/decisions/" + selected.id,
                                  "PATCH",
                                  { status: e.target.value },
                                );
                                setSelected(d);
                                await refresh(business);
                              })
                            }
                          >
                            <option value="planned">Planned</option>
                            <option value="implemented">Implemented</option>
                            <option value="canceled">Canceled</option>
                          </select>
                        ) : (
                          <>
                            <input
                              aria-label="Decision title"
                              value={title}
                              maxLength={200}
                              onChange={(e) => setTitle(e.target.value)}
                            />
                            <button
                              className="primary"
                              disabled={busy || !title.trim()}
                              onClick={() =>
                                void run(async () => {
                                  const d = await api<Saved>(
                                    "/decisions",
                                    "POST",
                                    {
                                      business_id: business.id,
                                      decision_type: kind,
                                      title,
                                      question,
                                      inputs: analysis.inputs,
                                      provenance: Object.fromEntries(
                                        analysis.assumptions.map((a) => [
                                          a.name,
                                          a.provenance,
                                        ]),
                                      ),
                                      selected_scenario: scenario,
                                    },
                                  );
                                  setSelected(d);
                                  setObservations([]);
                                  await refresh(business);
                                  setNotice(
                                    "Decision saved. The original forecast will be preserved.",
                                  );
                                })
                              }
                            >
                              Save decision <ArrowRight size={16} />
                            </button>
                          </>
                        )}
                      </section>
                      {selected && (
                        <Tracking
                          decision={selected}
                          observations={observations}
                          busy={busy}
                          onSubmit={(data) =>
                            run(async () => {
                              await api(
                                "/decisions/" + selected.id + "/outcomes",
                                "POST",
                                data,
                              );
                              setObservations(
                                await api(
                                  "/decisions/" + selected.id + "/outcomes",
                                ),
                              );
                              setNotice(
                                "Outcome recorded against the original forecast.",
                              );
                            })
                          }
                        />
                      )}
                    </>
                  )}
                </>
              )}
              {page === "Decision History" && (
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Your decision ledger</h2>
                      <p>Original projections and manually recorded outcomes</p>
                    </div>
                    <span className="subtle-tag">
                      {history.length} decisions
                    </span>
                  </div>
                  {history.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Decision</th>
                            <th>Status</th>
                            <th>Base projection</th>
                            <th>Created</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {history.map((d) => (
                            <tr key={d.id}>
                              <td>
                                <strong>{d.title}</strong>
                                <small className="block muted">
                                  {d.decision_type === "supplier_switch"
                                    ? "Supplier switch"
                                    : "Promotional event"}{" "}
                                  · {d.selected_scenario}
                                </small>
                              </td>
                              <td>
                                <span className={"status " + d.status}>
                                  {d.status}
                                </span>
                              </td>
                              <td className="teal">
                                {usd(
                                  d.snapshot.scenarios[1].result.net_benefit,
                                )}
                              </td>
                              <td>
                                {new Date(d.created_at).toLocaleDateString()}
                              </td>
                              <td>
                                <button
                                  className="text-button"
                                  onClick={() => void reopen(d)}
                                >
                                  Review & track <ArrowUpRight size={15} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty
                      title="A fresh decision ledger"
                      body="Save your first analysis to start comparing predictions with outcomes."
                      action={
                        <button
                          className="primary"
                          onClick={() => setPage("Analyze Decision")}
                        >
                          Analyze a decision
                        </button>
                      }
                    />
                  )}
                </section>
              )}
            </>
          )}
          <footer>
            <span>
              <span className="brand-mini">clarity.</span> Grounded in your
              numbers.
            </span>
            <span>
              Decision support for a local demo. Review assumptions before
              acting.
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}

function Tracking({
  decision,
  observations,
  busy,
  onSubmit,
}: {
  decision: Saved;
  observations: Observation[];
  busy: boolean;
  onSubmit: (data: unknown) => Promise<void>;
}) {
  const [form, setForm] = useState<Record<string, string>>({
    period: "1",
    notes: "",
  });
  const supplier = decision.decision_type === "supplier_switch";
  useEffect(() => {
    setForm({
      period: String(
        supplier ? Math.max(0, ...observations.map((o) => o.period)) + 1 : 1,
      ),
      notes: "",
    });
  }, [decision.id, observations.length, supplier]);
  function submit(e: FormEvent) {
    e.preventDefault();
    const data = Object.fromEntries(
      Object.entries(form)
        .filter(([, v]) => v !== "")
        .map(([k, v]) => [k, k === "notes" ? v : Number(v)]),
    );
    void onSubmit(data);
  }
  const fields = supplier
    ? [["actual_savings", "Actual monthly procurement savings (USD)"]]
    : [
        ["attendance", "Actual incremental visits"],
        ["revenue", "Actual incremental revenue (USD)"],
        ["costs", "Actual event + staffing costs (USD)"],
        ["repeat_contribution", "Actual repeat contribution (USD, optional)"],
      ];
  return (
    <section className="panel padded tracking">
      <div className="panel-heading">
        <div>
          <h2>Projected vs. actual</h2>
          <p>
            Compared with the original{" "}
            {decision.selected_scenario.toLowerCase()} forecast. Each supplier
            observation is a single month.
          </p>
        </div>
        <span className="subtle-tag">Manual observations</span>
      </div>
      {observations.length > 0 && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Original expected</th>
                  <th>Actual recorded</th>
                  <th>Variance</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {observations.map((o) => (
                  <tr key={o.id}>
                    <td>Month {o.period}</td>
                    <td>
                      {usd(o.expected.net_benefit)}
                      <small className="block muted">{o.expected.basis}</small>
                    </td>
                    <td>
                      {usd(o.actual.net_benefit)}
                      {o.expected.repeat_pending && (
                        <small className="block amber">
                          Repeat visits pending
                        </small>
                      )}
                    </td>
                    <td className={o.variance >= 0 ? "teal" : "amber"}>
                      {o.variance > 0 ? "+" : ""}
                      {usd(o.variance)}
                    </td>
                    <td>{o.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {observations.length > 1 && (
            <ChartBox>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={observations.map((o) => ({
                    period: "Month " + o.period,
                    Expected: o.expected.net_benefit,
                    Actual: o.actual.net_benefit,
                  }))}
                >
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="period" />
                  <YAxis />
                  <Tooltip formatter={(v) => usd(Number(v))} />
                  <Legend />
                  <Bar dataKey="Expected" fill="#b2d1c9" />
                  <Bar dataKey="Actual" fill="#14867c" />
                </BarChart>
              </ResponsiveContainer>
            </ChartBox>
          )}
        </>
      )}
      {!supplier && observations.length > 0 ? (
        <p className="fine-print">
          Event repeat contribution remains pending if not entered. This MVP
          stores one cumulative event observation. Actual contribution still
          uses the original margin assumption; sales changes do not establish
          causal attribution.
        </p>
      ) : (
        <form onSubmit={submit}>
          <h3>Record an outcome</h3>
          <div className="input-grid">
            <label className="input-field">
              Observation month
              <input
                required
                type="number"
                min={1}
                max={decision.snapshot.scenarios[1].result.horizon}
                value={form.period}
                onChange={(e) => setForm({ ...form, period: e.target.value })}
              />
            </label>
            {fields.map(([key, label]) => (
              <label className="input-field" key={key}>
                {label}
                <input
                  required={key !== "repeat_contribution"}
                  type="number"
                  min={key === "actual_savings" ? undefined : 0}
                  step="any"
                  value={form[key] || ""}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                />
              </label>
            ))}
          </div>
          <label className="input-field">
            Notes
            <textarea
              maxLength={2000}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="What happened? What is still uncertain?"
            />
          </label>
          <div className="form-footer">
            <span>
              <Info size={15} />
              {supplier
                ? "Record savings before the one-time switching cost."
                : "Leave unobserved repeat contribution blank to keep it pending."}
            </span>
            <button className="primary" disabled={busy}>
              Record actual outcome
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
