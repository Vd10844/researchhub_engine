// src/qp/app.js — QuickPlot shell: header, sidebar, hash router.

const MapPertyLogo = () => (
  <span className="qp-logo">
    <svg className="qp-logo-mark" viewBox="0 0 40 40" aria-hidden="true">
      <defs>
        <linearGradient id="qpg" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#7EFF46" /><stop offset="100%" stopColor="#61D32F" />
        </linearGradient>
      </defs>
      <path d="M20 3.2 34.6 11v18L20 36.8 5.4 29V11Z" fill="url(#qpg)" />
      <path d="M20 3.2 34.6 11 20 18.8 5.4 11Z" fill="#3FA424" opacity=".55" />
      <path d="M13 26V15l7 5.4L27 15v11" stroke="#173D0C" strokeWidth="2.6" fill="none"
            strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    <span className="qp-logo-text"><b>MAPPERTY</b><span>Quickplot</span></span>
  </span>
);

const NAV = [
  ["users", "Users", ic.users],
  ["orders", "Orders", ic.clipboard],
  ["support", "Support", ic.headset],
  ["quote", "Quote hub", ic.dollar],
];

// Screens outside the research flow are placeholders in this build — the Research Hub is the
// slice QuickPlot owns; the rest of Mapperty renders them.
const Placeholder = ({ label }) => (
  <div className="qp-page">
    <h1 className="qp-h1">{label}</h1>
    <Empty title={`${label} lives in the main Mapperty app`}
      icon={<I d={ic.external} size={24} />}
      text="This shell exists so the Research Hub can be reviewed in its real surroundings.
            When QuickPlot is embedded in Mapperty, this navigation is Mapperty’s own." />
  </div>
);

// -------------------------------------------------------------------- routing
function parseHash() {
  const h = (location.hash || "#/orders").replace(/^#\/?/, "");
  const parts = h.split("/").filter(Boolean);
  if (!parts.length) return { view: "orders" };
  if (parts[0] === "orders" && parts[1] && parts[2] === "research")
    return { view: "research", id: parts[1] };
  if (parts[0] === "orders" && parts[1]) return { view: "order", id: parts[1] };
  return { view: parts[0] };
}

function App() {
  const [route, setRoute] = useState(parseHash());
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    const onHash = () => { setRoute(parseHash()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onHash);
    if (!location.hash) location.hash = "#/orders";
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => { api("/meta").then(setMeta).catch(() => {}); }, []);

  const nav = (hash) => { location.hash = hash; };
  const navKey = route.view === "order" || route.view === "research" ? "orders" : route.view;

  return (
    <div className="qp-app">
      <header className="qp-header">
        <a href="#/orders" style={{ textDecoration: "none" }}><MapPertyLogo /></a>
        <div className="qp-header-right">
          {meta && (
            <span className="qp-chip qp-chip--plain" title="Tenant · evidence locker · storage">
              {meta.org_id} · {meta.locker_provider} · {meta.storage_backend}
            </span>
          )}
          <button className="qp-iconbtn" aria-label="Notifications"><I d={ic.bell} size={19} /></button>
          <span className="qp-avatar" title={QP.actor}>{initials(QP.actor)}</span>
        </div>
      </header>

      <div className="qp-body">
        <nav className="qp-sidebar">
          {NAV.map(([k, label, icon]) => (
            <button key={k} className={cx("qp-navitem", navKey === k && "is-active")}
                    onClick={() => nav("#/" + k)}>
              <I d={icon} size={18} />{label}
            </button>
          ))}
          <div className="qp-sidebar-foot">
            Research Hub · QuickPlot<br />
            Public records → Evidence Locker
          </div>
        </nav>

        <main className="qp-main scroll">
          {route.view === "orders" && <OrdersList nav={nav} />}
          {route.view === "order" && <OrderDetail orderId={route.id} nav={nav} key={route.id} />}
          {route.view === "research" && <ResearchHub orderId={route.id} nav={nav} key={route.id} />}
          {route.view === "users" && <Placeholder label="Users" />}
          {route.view === "support" && <Placeholder label="Support" />}
          {route.view === "quote" && <Placeholder label="Quote hub" />}
        </main>
      </div>

      <Toasts />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

Object.assign(window, { App, MapPertyLogo });
