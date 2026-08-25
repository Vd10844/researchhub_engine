// src/qp/orders.js — Orders list, order detail (stage rail + tabs), and the intake form.

const STAGE_ORDER = ["created", "placed", "research", "field_survey", "cad_drafting", "delivered"];
const STAGE_LABEL = {
  created: "Order Created", placed: "Order Placed", research: "Research",
  field_survey: "Field Survey", cad_drafting: "CAD Drafting", delivered: "Delivered",
};

function StageRail({ order }) {
  const cur = STAGE_ORDER.indexOf(order.stage);
  const dates = order.stage_dates || {};
  return (
    <div className="qp-card qp-stages mt20">
      {STAGE_ORDER.map((k, i) => {
        const done = i < cur, isCur = i === cur;
        return (
          <div key={k} className={cx("qp-stage", done && "is-done", isCur && "is-current")}>
            <div className="qp-stage__bar" />
            <div className="qp-stage__label">
              {STAGE_LABEL[k]}
              {(done || isCur) && <I d={ic.info} size={13} />}
            </div>
            {dates[k] && (
              <div className="qp-stage__date">
                <I d={ic.check} size={12} sw={2.6} style={{ color: "var(--b-600)" }} />
                {k === "created" ? "Approved " : ""}{fmtDate(dates[k])}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// The banner is the researcher's single call to action; its wording tracks research_state.
function ResearchBanner({ order, docCounts, onStart, busy }) {
  const st = order.research_state;
  const c = docCounts || {};
  let title, sub, cta;
  if (st === "submitted") {
    title = "Research submitted. The order moved to field survey";
    sub = `${c.locked || 0} file${c.locked === 1 ? "" : "s"} locked in the evidence locker. Handed over `
        + `${fmtDate(order.research_submitted_at)} at ${fmtTime(order.research_submitted_at)}.`;
  } else if (st === "in_progress") {
    title = "Research in progress";
    sub = `${c.locked || 0} of ${c.documents || 0} documents locked · last updated `
        + `${fmtDate(order.updated_at)} at ${fmtTime(order.updated_at)}`;
    cta = "Resume research";
  } else {
    title = "You’re the researcher on this order.";
    sub = "Gather the survey research set for this parcel, review each document, then lock it "
        + "into the Evidence Locker.";
    cta = "Start Research";
  }
  return (
    <div className="qp-banner mt20">
      <span className="qp-banner__icon"><I d={ic.doc} size={19} /></span>
      <div className="grow">
        <div className="qp-banner__title">{title}</div>
        <div className="qp-banner__sub">{sub}</div>
      </div>
      {cta && (
        <Btn variant={st === "in_progress" ? "default" : "primary"} disabled={busy}
             onClick={onStart}>{busy && <Spinner />}{cta}</Btn>
      )}
      {st === "submitted" && (
        <Chip tone="green" dot>Locked &amp; handed over</Chip>
      )}
    </div>
  );
}

const InfoRow = ({ icon, label, value }) => (
  <div className="row between gap16" style={{ padding: "12px 0",
       borderBottom: "1px solid var(--g-200)" }}>
    <span className="row gap10 qp-muted" style={{ fontSize: 14 }}>
      <I d={icon} size={16} />{label}
    </span>
    <span style={{ fontSize: 14, fontWeight: 500 }}>{value}</span>
  </div>
);

// Form field with an inline error message underneath.
const Field2 = ({ label, error, children }) => (
  <label className="qp-field">
    <span className="qp-field__label">{label}</span>
    {children}
    {error && <span className="qp-field__error">{error}</span>}
  </label>
);

const Field = ({ label, children }) => (
  <div style={{ marginBottom: 22 }}>
    <div className="qp-eyebrow">{label}</div>
    <div className="mt4" style={{ fontSize: 14.5, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
      {children || <span className="qp-muted">—</span>}
    </div>
  </div>
);

// -------------------------------------------------------------------- order form
const ORDER_FIELDS = [
  ["title", "Order title"], ["order_no", "Order #"], ["order_type", "Order type"],
  ["address", "Property address"], ["city", "City"], ["county", "County"],
  ["state", "State (USPS)"], ["postal", "ZIP"], ["parcel_id", "Parcel ID"],
  ["buyer_owner", "Buyer / owner / seller"], ["lender", "Lender name"],
  ["title_company", "Title company"], ["underwriter", "Underwriter"],
  ["researcher", "Assigned researcher"],
];

// Mirrors the server-side rules in quickplot/router.py. The server is still the
// authority — this exists so a typo is caught while the user is looking at the field,
// not after a round trip.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

function validateOrder(f) {
  const errs = {};
  const has = (k) => (f[k] || "").trim();
  if (!has("title") && !has("order_no") && !has("address") && !has("parcel_id")) {
    errs.title = "Give the order a title, number, address or parcel ID";
  }
  const recv = (f.received_at || "").slice(0, 10);
  const due = (f.due_at || "").slice(0, 10);
  if (recv && due && due < recv) {
    errs.due_at = "Due date cannot be before the received date";
  }
  if (has("client_email") && !EMAIL_RE.test(f.client_email.trim())) {
    errs.client_email = "That does not look like an email address";
  }
  if (has("state") && !/^[A-Za-z]{2}$/.test(f.state.trim())) {
    errs.state = "Use the two-letter state code, e.g. FL";
  }
  return errs;
}

function OrderFormModal({ open, order, onClose, onSaved }) {
  const [f, setF] = useState({});
  const [errs, setErrs] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setF(order ? { ...order, client_name: (order.client || {}).name || "",
                   client_email: (order.client || {}).email || "",
                   client_phone: (order.client || {}).phone || "",
                   client_role: (order.client || {}).role || "",
                   access_name: (order.access_contact || {}).name || "",
                   access_phone: (order.access_contact || {}).phone || "",
                   scope_text: (order.scope_tags || []).join(", ") }
                : { order_type: "Boundary Survey", state: "FL" });
    setErrs({});
  }, [open, order]);
  if (!open) return null;

  const set = (k) => (e) => {
    setF((s) => ({ ...s, [k]: e.target.value }));
    setErrs((s) => (s[k] ? { ...s, [k]: undefined } : s));
  };

  const save = async () => {
    const found = validateOrder(f);
    if (Object.keys(found).length) {
      setErrs(found);
      toast(Object.values(found)[0], "err");
      return;
    }
    setBusy(true);
    const body = {
      ...Object.fromEntries(ORDER_FIELDS.map(([k]) => [k, f[k] || ""])),
      client: { name: f.client_name || "", role: f.client_role || "",
                email: f.client_email || "", phone: f.client_phone || "" },
      access_contact: { name: f.access_name || "", phone: f.access_phone || "" },
      client_notes: f.client_notes || "",
      legal_description: f.legal_description || "",
      scope_tags: (f.scope_text || "").split(",").map((s) => s.trim()).filter(Boolean),
      due_at: f.due_at || "",
      received_at: f.received_at || "",
    };
    try {
      const saved = order
        ? await api(`/orders/${order.id}`, { method: "PATCH", json: body })
        : await api("/orders", { method: "POST", json: body });
      toast(order ? "Order updated" : "Order created");
      onSaved(saved);
      onClose();
    } catch (e) { toast(e.message, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal open wide title={order ? "Edit order" : "New order"} onClose={onClose} footer={<>
      <Btn onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" disabled={busy} onClick={save}>{busy && <Spinner />}
        {order ? "Save changes" : "Create order"}</Btn>
    </>}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        {ORDER_FIELDS.map(([k, label]) => (
          <Field2 key={k} label={label} error={errs[k]}>
            <input className={cx("qp-input", errs[k] && "is-invalid")}
                   value={f[k] || ""} onChange={set(k)} />
          </Field2>
        ))}
        <Field2 label="Received" error={errs.received_at}>
          <input className="qp-input" type="date" value={(f.received_at || "").slice(0, 10)}
                 onChange={set("received_at")} /></Field2>
        <Field2 label="Due date" error={errs.due_at}>
          <input className={cx("qp-input", errs.due_at && "is-invalid")} type="date"
                 min={(f.received_at || "").slice(0, 10) || undefined}
                 value={(f.due_at || "").slice(0, 10)}
                 onChange={set("due_at")} /></Field2>
      </div>

      <div className="qp-eyebrow mt20 mb8">Client details</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
        {[["client_name", "Name"], ["client_role", "Role"], ["client_email", "Email"],
          ["client_phone", "Phone"]].map(([k, l]) => (
          <Field2 key={k} label={l} error={errs[k]}>
            <input className={cx("qp-input", errs[k] && "is-invalid")}
                   value={f[k] || ""} onChange={set(k)} /></Field2>
        ))}
      </div>

      <div className="qp-eyebrow mt20 mb8">Access contact</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
        {[["access_name", "Name"], ["access_phone", "Phone"]].map(([k, l]) => (
          <label key={k} className="qp-field"><span className="qp-field__label">{l}</span>
            <input className="qp-input" value={f[k] || ""} onChange={set(k)} /></label>
        ))}
      </div>

      <label className="qp-field mt20"><span className="qp-field__label">Scope &amp; conditions
        (comma separated)</span>
        <input className="qp-input" value={f.scope_text || ""} onChange={set("scope_text")}
               placeholder="Structures / Improvements, Easements" /></label>
      <label className="qp-field mt16"><span className="qp-field__label">Client notes</span>
        <textarea className="qp-textarea" value={f.client_notes || ""}
                  onChange={set("client_notes")} /></label>
      <label className="qp-field mt16"><span className="qp-field__label">Legal description</span>
        <textarea className="qp-textarea" value={f.legal_description || ""}
                  onChange={set("legal_description")} /></label>
    </Modal>
  );
}

// ------------------------------------------------------------------ order detail
function OrderDetail({ orderId, nav }) {
  const [order, setOrder] = useState(null);
  const [docs, setDocs] = useState([]);
  const [tab, setTab] = useState("info");
  const [ui, setUi] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [o, d] = await Promise.all([
        api(`/orders/${orderId}`), api(`/orders/${orderId}/documents`)]);
      setOrder(o); setDocs(d.documents || []);
    } catch (e) { setErr(e.message); }
  }, [orderId]);
  useEffect(() => { load(); }, [load]);

  const start = async () => {
    if (order.research_state !== "not_started") return nav(`#/orders/${orderId}/research`);
    setBusy(true);
    try {
      await api(`/orders/${orderId}/research/start`, { method: "POST" });
      nav(`#/orders/${orderId}/research`);
    } catch (e) { toast(e.message, "err"); setBusy(false); }
  };

  if (err) return <div className="qp-page"><div className="qp-note">
    <I d={ic.alert} size={16} className="qp-note__icon" /><span>{err}</span></div></div>;
  if (!order) return <div className="qp-page row gap10 qp-muted"><Spinner /> Loading order…</div>;

  const counts = order.counts || {};
  const client = order.client || {};
  const access = order.access_contact || {};

  return (
    <div className="qp-page">
      <Btn variant="ghost" className="mb16" icon={<I d={ic.back} size={17} />}
           onClick={() => nav("#/orders")}>Back to Orders</Btn>

      <div className="row between wrap gap16 mt12">
        <div>
          <h1 className="qp-h1">{order.title || "Untitled order"}</h1>
          <p className="qp-sub">#{order.order_no || order.id.slice(0, 8)}</p>
        </div>
        <div className="col" style={{ alignItems: "flex-end", gap: 10 }}>
          <Btn icon={<I d={ic.pencil} size={15} />}
               onClick={() => setUi({ edit: true })}>Edit Order</Btn>
          <div className="qp-sub" style={{ margin: 0 }}>
            Created by <b style={{ color: "var(--g-950)" }}>{order.created_by || "—"}</b>
            {" · "}{fmtDate(order.created_at)}
          </div>
        </div>
      </div>

      <ResearchBanner order={order} docCounts={counts} onStart={start} busy={busy} />
      <StageRail order={order} />

      <div className="row gap24 mt24 wrap" style={{ alignItems: "flex-start" }}>
        {/* left: property summary */}
        <div className="qp-card qp-card-pad" style={{ width: 420, flex: "none" }}>
          <InfoRow icon={ic.calendar} label="Received" value={fmtDate(order.received_at)} />
          <InfoRow icon={ic.calendar} label="Due Date" value={fmtDate(order.due_at)} />
          <InfoRow icon={ic.briefcase} label="Order Type" value={order.order_type} />
          <div style={{ padding: "12px 0" }}>
            <span className="row gap10 qp-muted" style={{ fontSize: 14 }}>
              <I d={ic.pin} size={16} />Address</span>
            <div className="qp-card qp-card--flat mt12 row gap12"
                 style={{ padding: 12, alignItems: "flex-start" }}>
              <span style={{ color: "var(--b-600)", marginTop: 2 }}><I d={ic.pin} size={18} /></span>
              <div className="grow">
                <div style={{ fontSize: 14, fontWeight: 500, lineHeight: 1.45 }}>
                  {order.matched_address || order.address || "—"}
                </div>
                <div className="qp-small qp-muted mt4">
                  {[order.city, order.county && order.county + " County", order.state,
                    order.postal].filter(Boolean).join(", ")}
                </div>
              </div>
              <MapThumb lat={order.lat} lon={order.lon} w={88} h={62} />
            </div>
          </div>
          <InfoRow icon={ic.columns} label="Parcel ID" value={order.parcel_id || "—"} />
          <div className="row between gap16" style={{ padding: "12px 0" }}>
            <span className="row gap10 qp-muted" style={{ fontSize: 14 }}>
              <I d={ic.frame} size={16} />Area</span>
            <span style={{ fontSize: 14, fontWeight: 500 }}>
              {order.lot_area_sqft ? `${fmtNum(Math.round(order.lot_area_sqft))} sq ft` : "—"}
            </span>
          </div>
        </div>

        {/* right: tabs */}
        <div className="grow" style={{ minWidth: 420 }}>
          <div className="row between gap16">
            <div className="qp-tabs grow">
              <button className={cx("qp-tab", tab === "info" && "is-active")}
                      onClick={() => setTab("info")}>Order Information</button>
              <button className={cx("qp-tab", tab === "locker" && "is-active")}
                      onClick={() => setTab("locker")}>
                Evidence locker <span className="qp-count">{docs.length}</span></button>
            </div>
            <Btn icon={<I d={ic.clock} size={16} />}
                 onClick={() => setUi({ log: tab === "locker" ? "locker" : "order" })}>
              {tab === "locker" ? "Locker Log" : "Order Log"}</Btn>
          </div>

          {tab === "info" ? (
            <div className="mt24">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 40px" }}>
                <Field label="Client details">
                  {client.name && <>{client.name}<br /></>}
                  {client.role && <>{client.role}<br /></>}
                  {client.email && <>{client.email}<br /></>}
                  {client.phone}
                </Field>
                <Field label="Access contact">
                  {access.name && <>{access.name}<br /></>}
                  {access.phone}
                </Field>
                <Field label="Buyer/Owner/Seller">{order.buyer_owner}</Field>
                <Field label="Lender name">{order.lender}</Field>
                <Field label="Title company">{order.title_company}</Field>
                <Field label="Underwriter">{order.underwriter}</Field>
              </div>
              <Field label="Client notes">{order.client_notes}</Field>
              <Field label="Legal description">{order.legal_description}</Field>
              <div className="qp-eyebrow">Scope &amp; conditions</div>
              <div className="row gap8 wrap mt8">
                {(order.scope_tags || []).length
                  ? order.scope_tags.map((t) => <Chip key={t} tone="green">{t}</Chip>)
                  : <span className="qp-muted">—</span>}
              </div>
            </div>
          ) : (
            <div className="qp-card mt20">
              {!docs.length
                ? <Empty title="No evidence yet"
                    text="Documents appear here once the researcher fetches or uploads them."
                    icon={<I d={ic.lock} size={24} />}>
                    <Btn variant="primary" onClick={start}>
                      {order.research_state === "not_started" ? "Start Research" : "Open research hub"}
                    </Btn>
                  </Empty>
                : <div className="qp-table-wrap scroll"><table className="qp-table">
                    <thead><tr><th>Document</th><th>Type</th><th>Status</th><th></th></tr></thead>
                    <tbody>
                      {docs.map((d) => (
                        <tr key={d.id}>
                          <td><div className="row gap12"><FileIcon name={d.filename} />
                            <div><div className="qp-docname">{d.filename}</div>
                              <div className="qp-docmeta">{fmtStamp(d.retrieved_at)} ·
                                {" "}{fmtBytes(d.size_bytes)}</div></div></div></td>
                          <td>{d.doc_type || <span className="qp-muted">Unclassified</span>}</td>
                          <td>{d.status === "locked"
                            ? <Chip tone="green" dot>Locked</Chip>
                            : <Chip tone="amber" dot>Review Needed</Chip>}</td>
                          <td className="tr">
                            <Btn size="sm" icon={<I d={ic.download} size={15} />}
                              onClick={() => window.open(fileUrl(order.id, d.id, true), "_blank")}>
                              Download</Btn>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table></div>}
            </div>
          )}
        </div>
      </div>

      <LogModal open={!!ui.log} order={order} scope={ui.log || "order"}
                onClose={() => setUi({})} />
      <OrderFormModal open={!!ui.edit} order={order} onClose={() => setUi({})}
                      onSaved={(o) => setOrder(o)} />
    </div>
  );
}

// -------------------------------------------------------------------- orders list
const STAGE_TONE = { created: "plain", placed: "info", research: "green",
                     field_survey: "green", cad_drafting: "green", delivered: "green" };

function OrdersList({ nav }) {
  const [q, setQ] = useState("");
  const [ui, setUi] = useState({});
  const [reload, setReload] = useState(0);
  // Debounced so typing a parcel number is one request, not twenty.
  const dq = useDebounced(q, 300);
  const list = useAsync(() => api(`/orders?q=${encodeURIComponent(dq)}`), [dq, reload]);
  const orders = (list.data && list.data.orders) || [];

  const seed = async () => {
    try { await api("/demo/seed", { method: "POST" }); setReload((r) => r + 1); }
    catch (e) { toast(e.message, "err"); }
  };

  return (
    <div className="qp-page">
      <div className="row between wrap gap16">
        <div>
          <h1 className="qp-h1">Orders</h1>
          <p className="qp-sub">Every survey order and where it sits in the pipeline.</p>
        </div>
        <div className="row gap12">
          <SearchInput value={q} onChange={setQ} width={280}
                       placeholder="Search orders, address, parcel" />
          <Btn variant="primary" icon={<I d={ic.plus} size={16} />}
               onClick={() => setUi({ create: true })}>New Order</Btn>
        </div>
      </div>

      <div className="qp-card mt24">
        {list.loading && <div className="row gap10 qp-muted" style={{ padding: 28 }}>
          <Spinner /> Loading orders…</div>}
        {list.error && <div className="qp-note" style={{ margin: 20 }}>
          <I d={ic.alert} size={16} className="qp-note__icon" /><span>{list.error}</span></div>}
        {!list.loading && !orders.length && (
          <Empty title="No orders yet" icon={<I d={ic.clipboard} size={24} />}
            text="Create an order to start a research file, or seed the sample order to walk
                  through the flow end to end.">
            <Btn variant="primary" onClick={() => setUi({ create: true })}>New Order</Btn>
            <Btn onClick={seed}>Seed sample order</Btn>
          </Empty>
        )}
        {!!orders.length && (
          <div className="qp-table-wrap scroll"><table className="qp-table">
            <thead><tr>
              <th>Order</th><th>Property</th><th>Stage</th><th>Research</th>
              <th>Evidence</th><th>Due</th>
            </tr></thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="is-clickable" onClick={() => nav(`#/orders/${o.id}`)}>
                  <td>
                    <div className="qp-docname">{o.title || "Untitled order"}</div>
                    <div className="qp-docmeta">#{o.order_no || o.id.slice(0, 8)} · {o.order_type}</div>
                  </td>
                  <td>
                    <div style={{ fontSize: 14 }}>{o.matched_address || o.address || "—"}</div>
                    <div className="qp-docmeta">
                      {[o.county && o.county + " County", o.state].filter(Boolean).join(", ")}
                      {o.parcel_id ? ` · ${o.parcel_id}` : ""}
                    </div>
                  </td>
                  <td><Chip tone={STAGE_TONE[o.stage] || "plain"}>{STAGE_LABEL[o.stage]}</Chip></td>
                  <td>
                    {o.research_state === "submitted" ? <Chip tone="green" dot>Submitted</Chip>
                     : o.research_state === "in_progress" ? <Chip tone="amber" dot>In progress</Chip>
                     : <span className="qp-muted qp-small">Not started</span>}
                  </td>
                  <td className="qp-small">
                    <b>{(o.counts || {}).locked || 0}</b> locked
                    <span className="qp-muted"> / {(o.counts || {}).documents || 0} files</span>
                  </td>
                  <td className="qp-small">{fmtDate(o.due_at)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>

      <OrderFormModal open={!!ui.create} order={null} onClose={() => setUi({})}
                      onSaved={(o) => nav(`#/orders/${o.id}`)} />
    </div>
  );
}

Object.assign(window, { OrdersList, OrderDetail, OrderFormModal, StageRail, ResearchBanner });
