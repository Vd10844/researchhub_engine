// src/qp/research.js — "Gather the research set": the Evidence Locker table, the Source
// registry rail, and the auto-fetch progress/empty states.

// -------------------------------------------------------------- source registry rail
const SOURCE_STATE = {
  idle:        { chip: null },
  fetching:    { chip: null },
  fetched:     { chip: ["green", "In locker"] },
  failed:      { chip: ["red", "Auto fetch failed"] },
  unavailable: { chip: ["plain", "Link only"] },
};

function SourceRow({ s, order, onFetch, disabled }) {
  const chip = (SOURCE_STATE[s.state] || {}).chip;
  const fetching = s.state === "fetching";
  const failed = s.state === "failed";
  return (
    <div className="qp-source">
      <div className="qp-source__head">
        <div className="grow">
          <div className="qp-source__title">{s.label}</div>
          <div className="qp-source__blurb">{s.message || "County and federal sources for parcel"}</div>
        </div>
        {chip && <Chip tone={chip[0]} dot={chip[0] === "red"}>{chip[1]}</Chip>}
      </div>
      <div className="qp-source__actions">
        {s.open_url
          ? <a href={s.open_url} target="_blank" rel="noreferrer" className="row gap6"
               style={{ fontSize: 14, fontWeight: 500 }}>
              Open source <I d={ic.external} size={14} />
            </a>
          : <span className="qp-small qp-muted">No direct source link</span>}
        {fetching
          ? <span className="qp-btn qp-btn--soft qp-btn--sm" style={{ pointerEvents: "none" }}>
              <Spinner size={14} />Fetching…</span>
          : failed
            ? <Btn variant="primary" size="sm" disabled={disabled}
                   icon={<I d={ic.refresh} size={15} />}
                   onClick={() => onFetch(s.key)}>Retry</Btn>
            : <Btn size="sm" disabled={disabled} icon={<I d={ic.sparkle} size={15} />}
                   onClick={() => onFetch(s.key)}
                   style={{ color: "var(--b-700)" }}>Auto fetch</Btn>}
      </div>
    </div>
  );
}

function SourceRail({ order, sources, run, onFetch, onFetchAll }) {
  const running = run && run.state === "running";
  return (
    <aside className="qp-rail">
      <div className="qp-note">
        <I d={ic.alert} size={17} className="qp-note__icon" />
        <span>Documents are fetched automatically and may contain errors. Please review each
          one before use.</span>
      </div>

      <div className="qp-card qp-card-pad">
        <h3 className="qp-h2" style={{ fontSize: 18 }}>Source registry</h3>
        <p className="qp-sub" style={{ fontSize: 13.5 }}>
          QuickPlot pulls the research set for {order.parcel_id || "this parcel"} from the
          county and federal sources.
        </p>

        <div className="qp-fetchall mt16">
          <span style={{ color: "var(--b-600)" }}><I d={ic.sparkle} size={18} /></span>
          <span className="grow qp-small" style={{ color: "var(--g-800)" }}>
            {running ? "Fetching from the county and federal sources…"
                     : "Ready to fetch using the order’s address and parcel ID"}
          </span>
          <Btn variant="primary" size="sm" disabled={running}
               icon={running ? <Spinner size={14} /> : <I d={ic.sparkle} size={15} />}
               onClick={onFetchAll}>{running ? "Fetching…" : "Auto-Fetch All"}</Btn>
        </div>

        <div className="mt8">
          {sources.map((s) => (
            <SourceRow key={s.key} s={s} order={order} onFetch={onFetch} disabled={running} />
          ))}
        </div>
      </div>
    </aside>
  );
}

// ------------------------------------------------------------------ locker table
function DocRow({ d, order, docTypes, onReview, onUnlock, onDelete, onTypeChange, onRefetch }) {
  const locked = d.status === "locked";
  const typeLabel = (docTypes.find((t) => t.key === d.doc_type) || {}).label;
  return (
    <tr>
      <td>
        <div className="row gap12">
          <FileIcon name={d.filename} />
          <div style={{ minWidth: 0 }}>
            <div className="qp-docname">{d.filename}</div>
            <div className="qp-docmeta">
              <span>{fmtStamp(d.retrieved_at)} · {fmtBytes(d.size_bytes)}</span>
              <Chip tone="info">{d.origin === "auto_fetch" ? "Auto-fetch" : "Manual upload"}</Chip>
            </div>
          </div>
        </div>
      </td>
      <td style={{ width: 244 }}>
        {locked
          ? <span style={{ fontSize: 14 }}>{typeLabel || "—"}</span>
          : <select className="qp-select" value={d.doc_type}
                    onChange={(e) => onTypeChange(d, e.target.value)}>
              <option value="">Select doc type</option>
              {docTypes.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>}
      </td>
      <td style={{ width: 160 }}>
        {locked
          ? <Chip tone="green" dot>Locked</Chip>
          : <Chip tone="amber" dot>Review Needed</Chip>}
      </td>
      <td style={{ width: 312 }}>
        <div className="row gap8">
          <Btn size="sm" aria-label="Download" title="Download"
               onClick={() => window.open(fileUrl(order.id, d.id, true), "_blank")}>
            <I d={ic.download} size={15} /></Btn>
          <Btn size="sm" aria-label="Re-fetch" title={locked ? "Unlock to re-fetch" : "Re-fetch from source"}
               disabled={locked || !d.source_key} onClick={() => onRefetch(d)}>
            <I d={ic.refresh} size={15} /></Btn>
          <Btn size="sm" aria-label="Delete" title={locked ? "Unlock to delete" : "Delete"}
               disabled={locked} onClick={() => onDelete(d)}>
            <I d={ic.trash} size={15} /></Btn>
          {locked
            ? <Btn size="sm" icon={<I d={ic.unlock} size={15} />}
                   onClick={() => onUnlock(d)}>Unlock</Btn>
            : <Btn variant="soft" size="sm" icon={<I d={ic.lock} size={15} />}
                   disabled={!d.doc_type} title={d.doc_type ? "" : "Pick a document type first"}
                   onClick={() => onReview(d)}>Review &amp; lock</Btn>}
        </div>
      </td>
    </tr>
  );
}

// ------------------------------------------------------------------- run states
function RunningPanel({ run, phases }) {
  return (
    <div className="qp-empty">
      <div className="qp-empty__icon"><I d={ic.folder} size={26} /></div>
      <div className="qp-empty__title">Researching your property</div>
      <p className="qp-empty__text">
        Results appear here automatically when it&rsquo;s done. Time can vary with the county
        website&rsquo;s response and your network speed — most searches finish in under a minute.
      </p>
      <ul className="qp-empty__text" style={{ textAlign: "left", maxWidth: 380, marginTop: 16 }}>
        {phases.map((p) => (
          <li key={p.key} style={{ padding: "3px 0",
              color: run.phase === p.label ? "var(--g-950)" : "var(--g-600)",
              fontWeight: run.phase === p.label ? 600 : 400 }}>{p.label}…</li>
        ))}
      </ul>
      <div className="row gap12 mt20" style={{ maxWidth: 700, margin: "20px auto 0" }}>
        <div className="qp-progress grow"><div className="qp-progress__fill"
             style={{ width: (run.percent || 0) + "%" }} /></div>
        <span className="qp-small qp-muted nowrap">{run.percent || 0}%</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------- screen
function ResearchHub({ orderId, nav }) {
  const [order, setOrder] = useState(null);
  const [docs, setDocs] = useState([]);
  const [sources, setSources] = useState([]);
  const [run, setRun] = useState({ state: "idle", percent: 0 });
  const [phases, setPhases] = useState([]);
  const [docTypes, setDocTypes] = useState([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ui, setUi] = useState({});           // which dialog is open + its subject
  const [clKey, setClKey] = useState(0);      // bumps the checklist drawer's reload
  const pollRef = useRef(null);

  const close = () => setUi({});

  const loadDocs = useCallback(async () => {
    const d = await api(`/orders/${orderId}/documents`);
    setDocs(d.documents || []);
    setClKey((k) => k + 1);
  }, [orderId]);

  const loadSources = useCallback(async () => {
    const s = await api(`/orders/${orderId}/sources`);
    setSources(s.sources || []);
    if (s.run) setRun(s.run);
    return s.run;
  }, [orderId]);

  const loadOrder = useCallback(async () => {
    setOrder(await api(`/orders/${orderId}`));
  }, [orderId]);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const [o, dt, st] = await Promise.all([
          api(`/orders/${orderId}`),
          api("/doc-types"),
          api(`/orders/${orderId}/research/status`),
        ]);
        if (!alive) return;
        setOrder(o); setDocTypes(dt.doc_types || []);
        setPhases(st.phases || []); setRun(st.run || { state: "idle" });
        await Promise.all([loadDocs(), loadSources()]);
      } catch (e) { if (alive) setError(e.message); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [orderId, loadDocs, loadSources]);

  // Poll only while a run is in flight, then refresh everything once and stop.
  useEffect(() => {
    if (run.state !== "running") {
      clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const st = await api(`/orders/${orderId}/research/status`);
        setRun(st.run);
        if (st.run.state !== "running") {
          clearInterval(pollRef.current);
          await Promise.all([loadDocs(), loadSources(), loadOrder()]);
          if (st.run.state === "error") toast(st.run.error || "Auto-fetch failed", "err");
          else toast("Auto-fetch finished");
        }
      } catch (_e) { /* transient — the next tick retries */ }
    }, 1800);
    return () => clearInterval(pollRef.current);
  }, [run.state, orderId, loadDocs, loadSources, loadOrder]);

  const fetchOne = async (key) => {
    try {
      const r = await api(`/orders/${orderId}/sources/${key}/fetch`, { method: "POST" });
      setRun(r.run); loadSources();
    } catch (e) { toast(e.message, "err"); }
  };
  const fetchAll = async () => {
    try {
      const r = await api(`/orders/${orderId}/sources/fetch-all`, { method: "POST" });
      setRun(r.run);
    } catch (e) { toast(e.message, "err"); }
  };
  const setType = async (d, doc_type) => {
    setDocs((x) => x.map((y) => y.id === d.id ? { ...y, doc_type } : y));  // optimistic
    try { await api(`/orders/${orderId}/documents/${d.id}`, { method: "PATCH", json: { doc_type } }); }
    catch (e) { toast(e.message, "err"); loadDocs(); }
  };

  if (loading) return <div className="qp-page row gap10 qp-muted"><Spinner /> Loading research hub…</div>;
  if (error) return <div className="qp-page"><div className="qp-note"><I d={ic.alert} size={16}
    className="qp-note__icon" /><span>{error}</span></div></div>;
  if (!order) return null;

  const locked = docs.filter((d) => d.status === "locked").length;
  const review = docs.length - locked;
  const shown = q
    ? docs.filter((d) => (d.filename + " " + d.doc_type).toLowerCase().includes(q.toLowerCase()))
    : docs;
  const running = run.state === "running";

  return (
    <div className="qp-page">
      <Btn variant="ghost" className="mb16" icon={<I d={ic.back} size={17} />}
           onClick={() => nav(`#/orders/${orderId}`)}>Back to Orders Details</Btn>

      <div className="row between wrap gap16 mt12">
        <div>
          <h1 className="qp-h1">Gather the research set</h1>
          <p className="qp-sub">Research · {order.title} #{order.order_no}</p>
        </div>
        <div className="qp-sub">
          {order.research_started_at
            ? `Started ${fmtTime(order.research_started_at)} · ${order.researcher}`
            : order.researcher}
        </div>
      </div>

      {/* matched property */}
      <div className="qp-card qp-card--muted qp-card-pad mt20">
        <div className="row between wrap gap16">
          <div className="row gap16">
            <MapThumb lat={order.lat} lon={order.lon} w={92} h={72} />
            <div>
              <div className="qp-small qp-muted">Matched property address</div>
              <div className="qp-h3 mt4">{order.matched_address || order.address || "—"}</div>
              <div className="qp-sub" style={{ marginTop: 2 }}>
                {[order.city, order.county && order.county + " County", order.state, order.postal]
                  .filter(Boolean).join(", ")} · United States
              </div>
            </div>
          </div>
          <Btn icon={<I d={ic.pin} size={16} />} disabled={order.lat == null}
               onClick={() => window.open(
                 `https://www.google.com/maps/search/?api=1&query=${order.lat},${order.lon}`, "_blank")}>
            View location</Btn>
        </div>
        <div className="row gap16 wrap mt16">
          <div className="qp-readonly"><div className="qp-readonly__label">Parcel ID</div>
            <div className="qp-readonly__value">{order.parcel_id || "—"}</div></div>
          <div className="qp-readonly"><div className="qp-readonly__label">Lot Area</div>
            <div className="qp-readonly__value">
              {order.lot_area_sqft ? `${fmtNum(Math.round(order.lot_area_sqft))} sq ft` : "—"}
              {order.lot_area_acres ? ` (${order.lot_area_acres} ac)` : ""}
            </div></div>
          <div className="qp-readonly"><div className="qp-readonly__label">Order Type</div>
            <div className="qp-readonly__value">{order.order_type}</div></div>
        </div>
      </div>

      {/* locker header */}
      <div className="row between wrap gap16 mt24">
        <div className="row gap12">
          <span className="qp-h2">Evidence locker</span>
          <span className="qp-count">{docs.length}</span>
          {!!docs.length && (
            <span className="qp-sub" style={{ margin: 0 }}>
              {locked} Locked, {review} awaiting review</span>
          )}
        </div>
        <div className="row gap12">
          <Btn icon={<I d={ic.list} size={16} />}
               onClick={() => setUi({ checklist: true })}>Research Checklist</Btn>
          <Btn icon={<I d={ic.clock} size={16} />}
               onClick={() => setUi({ log: "locker" })}>Locker log</Btn>
          <Btn variant="primary" icon={<I d={ic.upload} size={16} />}
               onClick={() => setUi({ upload: true })}>Upload Documents</Btn>
        </div>
      </div>

      {/* body */}
      <div className="row gap20 mt16 qp-research-grid" style={{ alignItems: "flex-start" }}>
        <div className="grow qp-card">
          {running && !docs.length ? <RunningPanel run={run} phases={phases} />
           : !docs.length ? (
            <Empty title="Build a verified record for every order"
              text="The Evidence Locker stores the county documents that support your survey —
                    deeds, plats, easements, prior surveys. Add documents, review them, then lock
                    them. Locked documents can’t be edited or deleted, so your file stays
                    defensible if the order is ever questioned.">
              <Btn variant="primary" icon={<I d={ic.upload} size={16} />}
                   onClick={() => setUi({ upload: true })}>Upload Documents</Btn>
              <Btn variant="soft" icon={<I d={ic.sparkle} size={16} />}
                   onClick={fetchAll}>Auto fetch</Btn>
            </Empty>
          ) : (<>
            {running && (
              <div className="row gap12" style={{ padding: "14px 16px",
                   borderBottom: "1px solid var(--g-200)", background: "var(--b-50)" }}>
                <Spinner size={15} />
                <span className="qp-small grow" style={{ color: "var(--b-700)", fontWeight: 600 }}>
                  {run.phase || "Researching your property"}…
                </span>
                <div className="qp-progress" style={{ width: 220 }}>
                  <div className="qp-progress__fill" style={{ width: (run.percent || 0) + "%" }} />
                </div>
                <span className="qp-small qp-muted nowrap">{run.percent || 0}%</span>
              </div>
            )}
            <div style={{ padding: 16 }}>
              <SearchInput value={q} onChange={setQ} width={320}
                           placeholder="Search documents" />
            </div>
            <div className="qp-table-wrap scroll">
            <table className="qp-table">
              <thead><tr>
                <th>Document</th><th>Document Type</th><th>Status</th><th>Action</th>
              </tr></thead>
              <tbody>
                {shown.map((d) => (
                  <DocRow key={d.id} d={d} order={order} docTypes={docTypes}
                    onReview={(x) => setUi({ review: x })}
                    onUnlock={(x) => setUi({ unlock: x })}
                    onDelete={(x) => setUi({ del: x })}
                    onTypeChange={setType}
                    onRefetch={(x) => fetchOne(x.source_key)} />
                ))}
                {!shown.length && (
                  <tr><td colSpan="4" className="qp-muted" style={{ padding: 28,
                      textAlign: "center" }}>No documents match “{q}”.</td></tr>
                )}
              </tbody>
            </table>
            </div>
          </>)}
        </div>

        <SourceRail order={order} sources={sources} run={run}
                    onFetch={fetchOne} onFetchAll={fetchAll} />
      </div>

      <div className="qp-sticky-foot">
        <Btn onClick={() => nav(`#/orders/${orderId}`)}>Save &amp; Exit</Btn>
        <Btn variant="primary" onClick={() => setUi({ submit: true })}
             disabled={order.research_state === "submitted"}>
          {order.research_state === "submitted" ? "Research submitted" : "Submit Research"}
        </Btn>
      </div>

      {/* dialogs */}
      <ReviewDocModal open={!!ui.review} doc={ui.review} order={order} onClose={close}
        onLocked={() => { loadDocs(); loadOrder(); }} />
      <UnlockModal open={!!ui.unlock} doc={ui.unlock} order={order} onClose={close}
        onDone={() => { loadDocs(); loadOrder(); }} />
      <DeleteDocModal open={!!ui.del} doc={ui.del} order={order} onClose={close}
        onDone={() => { loadDocs(); loadOrder(); }} />
      <UploadModal open={!!ui.upload} order={order} docTypes={docTypes} onClose={close}
        onDone={loadDocs} />
      <SubmitModal open={!!ui.submit} order={order} onClose={close}
        onDone={(o) => { setOrder(o); nav(`#/orders/${orderId}`); }} />
      <LogModal open={!!ui.log} order={order} scope={ui.log || "locker"} onClose={close} />
      <ChecklistDrawer open={!!ui.checklist} order={order} onClose={close} reloadKey={clKey} />
    </div>
  );
}

Object.assign(window, { ResearchHub, SourceRail, SourceRow, DocRow, RunningPanel });
