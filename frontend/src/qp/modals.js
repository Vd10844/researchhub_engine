// src/qp/modals.js — the dialogs of the research flow: review & lock, unlock, upload,
// submit, and the two change logs.

// --------------------------------------------------------------- review & lock
// Two-step on purpose, exactly as designed: the reviewer first confirms the three checks
// against the rendered document, then acknowledges that locking is permanent.
const CONFIRMS = [
  { key: "legible", title: "Legible and complete",
    sub: "Every page is readable and no pages are missing." },
  { key: "matches_parcel", title: "Matches this parcel",
    sub: "Parcel ID, legal description and address match the order." },
  { key: "source_recorded", title: "Source is recorded",
    sub: "The file came from the source shown and is the current version." },
];

function ReviewDocModal({ open, doc, order, onClose, onLocked }) {
  const [checks, setChecks] = useState({});
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setChecks({}); setConfirming(false); }, [doc && doc.id]);
  if (!open || !doc) return null;

  const allOn = CONFIRMS.every((c) => checks[c.key]);
  const src = fileUrl(order.id, doc.id);
  const kind = fileKind(doc.filename);

  const lock = async () => {
    setBusy(true);
    try {
      const updated = await api(`/orders/${order.id}/documents/${doc.id}/lock`, {
        method: "POST",
        json: { legible: !!checks.legible, matches_parcel: !!checks.matches_parcel,
                source_recorded: !!checks.source_recorded },
      });
      toast(`Locked — ${doc.filename}`);
      onLocked && onLocked(updated);
      onClose();
    } catch (e) { toast(e.message, "err"); }
    finally { setBusy(false); setConfirming(false); }
  };

  return (
    <>
      <Modal open wide title="Review document" onClose={onClose}
        footer={<>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn variant={allOn ? "primary" : "soft"} disabled={!allOn}
               onClick={() => setConfirming(true)}>Approve &amp; Lock</Btn>
        </>}>
        <div className="qp-review">
          <div className="qp-review__viewer">
            {kind === "img"
              ? <img src={src} alt={doc.filename} style={{ maxWidth: "100%", borderRadius: 6, background: "#fff" }} />
              : <iframe src={src} title={doc.filename} className="qp-review__frame" />}
            <div className="qp-review__pager">
              {doc.pages ? `${doc.pages} page${doc.pages > 1 ? "s" : ""}` : doc.filename}
            </div>
          </div>

          <div>
            <div className="qp-card qp-card--flat">
              <div className="qp-kv">
                <span className="row gap8" style={{ minWidth: 0 }}>
                  <I d={ic.doc} size={16} className="qp-muted" />
                  <span className="qp-kv__v" style={{ textAlign: "left", overflow: "hidden",
                        textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.filename}</span>
                </span>
                <span className="qp-kv__k nowrap">
                  {fmtBytes(doc.size_bytes)}
                  {doc.pages ? ` · ${doc.pages} page${doc.pages > 1 ? "s" : ""}` : ""}
                </span>
              </div>
              <div className="qp-kv"><span className="qp-kv__k">Source</span>
                <span className="qp-kv__v">{doc.source_label || "—"}</span></div>
              <div className="qp-kv"><span className="qp-kv__k">Retrieved</span>
                <span className="qp-kv__v">{fmtDate(doc.retrieved_at)} {fmtTime(doc.retrieved_at)}</span></div>
              <div className="qp-kv"><span className="qp-kv__k">Retrieved by</span>
                <span className="qp-kv__v">{doc.retrieved_by || "—"}</span></div>
            </div>

            <div className="qp-eyebrow mt20 mb8" style={{ textTransform: "none", letterSpacing: 0,
                 fontSize: 13, color: "var(--g-600)" }}>Confirm before locking</div>

            {CONFIRMS.map((c) => (
              <label key={c.key} className={cx("qp-confirm", checks[c.key] && "is-on")}>
                <input type="checkbox" style={{ display: "none" }} checked={!!checks[c.key]}
                       onChange={(e) => setChecks((s) => ({ ...s, [c.key]: e.target.checked }))} />
                <span className="qp-confirm__box"><I d={ic.check} size={12} sw={3} /></span>
                <span>
                  <span className="qp-confirm__title">{c.title}</span>
                  <span className="qp-confirm__sub" style={{ display: "block" }}>{c.sub}</span>
                </span>
              </label>
            ))}

            <div className="qp-note qp-note--plain mt16">
              <I d={ic.info} size={16} className="qp-note__icon" />
              <span>Locking is permanent. The file becomes read-only evidence and can only be
                replaced through an unlock request.</span>
            </div>
          </div>
        </div>
      </Modal>

      <Modal open={confirming} center hideClose onClose={() => setConfirming(false)}
        footer={<>
          <Btn onClick={() => setConfirming(false)}>Cancel</Btn>
          <Btn variant="primary" disabled={busy} onClick={lock}>
            {busy && <Spinner />}Lock
          </Btn>
        </>}>
        <div className="qp-modal-icon qp-modal-icon--green"><I d={ic.lock} size={22} /></div>
        <h2 className="qp-h1" style={{ fontSize: 24 }}>Confirm Evidence Lock</h2>
        <p className="qp-sub" style={{ marginTop: 12 }}>
          You are about to lock this file in the Evidence Locker.</p>
        <p className="qp-sub">
          The file will be locked as part of the official order record and will become
          immutable. After locking, the file cannot be modified or replaced.</p>
        <p className="qp-sub">Do you want to continue?</p>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------- unlock
function UnlockModal({ open, doc, order, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  useEffect(() => { setReason(""); }, [doc && doc.id]);
  if (!open || !doc) return null;

  const go = async () => {
    setBusy(true);
    try {
      const d = await api(`/orders/${order.id}/documents/${doc.id}/unlock`,
                          { method: "POST", json: { reason } });
      toast(`Unlocked — ${doc.filename}`);
      onDone && onDone(d);
      onClose();
    } catch (e) { toast(e.message, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal open center hideClose onClose={onClose} footer={<>
      <Btn onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" disabled={busy} onClick={go}>{busy && <Spinner />}Unlock</Btn>
    </>}>
      <div className="qp-modal-icon qp-modal-icon--warn"><I d={ic.alert} size={22} /></div>
      <h2 className="qp-h1" style={{ fontSize: 26 }}>Unlock File?</h2>
      <p className="qp-sub" style={{ marginTop: 12 }}>
        This file will be unlocked. Once unlocked, it can be edited, replaced, or deleted and
        will no longer be preserved as the official evidence for this order.</p>
      <p className="qp-sub" style={{ marginTop: 12 }}>Are you sure you want to continue?</p>
      <div className="mt16" style={{ textAlign: "left" }}>
        <label className="qp-field__label">Reason (recorded in the change log)</label>
        <input className="qp-input" value={reason} placeholder="e.g. wrong page range fetched"
               onChange={(e) => setReason(e.target.value)} />
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------- delete
function DeleteDocModal({ open, doc, order, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  useEffect(() => { setReason(""); }, [doc && doc.id]);
  if (!open || !doc) return null;

  const go = async () => {
    setBusy(true);
    try {
      await api(`/orders/${order.id}/documents/${doc.id}?reason=${encodeURIComponent(reason)}`,
                { method: "DELETE" });
      toast(`Removed — ${doc.filename}`);
      onDone && onDone();
      onClose();
    } catch (e) { toast(e.message, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal open center hideClose onClose={onClose} footer={<>
      <Btn onClick={onClose}>Cancel</Btn>
      <Btn variant="danger" disabled={busy} onClick={go}>{busy && <Spinner />}Delete</Btn>
    </>}>
      <div className="qp-modal-icon qp-modal-icon--warn"><I d={ic.trash} size={22} /></div>
      <h2 className="qp-h1" style={{ fontSize: 24 }}>Delete from Locker?</h2>
      <p className="qp-sub" style={{ marginTop: 12 }}>
        <b>{doc.filename}</b> will be removed from this order&rsquo;s Evidence Locker. The
        deletion itself stays in the change log.</p>
      <div className="mt16" style={{ textAlign: "left" }}>
        <label className="qp-field__label">Reason</label>
        <textarea className="qp-textarea" value={reason} style={{ minHeight: 80 }}
                  placeholder="Why is this file being removed?"
                  onChange={(e) => setReason(e.target.value)} />
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------- upload
function UploadModal({ open, order, docTypes, onClose, onDone }) {
  const [rows, setRows] = useState([]);   // {file, type, progress, done}
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => { if (open) setRows([]); }, [open]);
  if (!open) return null;

  // Materialise the FileList *before* handing it to setRows: the input is reset right after
  // this call, and a live FileList read inside the (lazy) updater would already be empty.
  const addFiles = (list) => {
    const picked = Array.from(list).map((f) => ({ file: f, type: "", progress: 0, done: false }));
    if (picked.length) setRows((r) => [...r, ...picked]);
  };

  const upload = async () => {
    if (!rows.length) return;
    setBusy(true);
    let ok = 0;
    // One request per document so a single rejected file does not lose the whole batch,
    // and so each row can carry its own evidence category.
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (row.done) continue;
      const fd = new FormData();
      fd.append("files", row.file);
      fd.append("doc_type", row.type || "");
      try {
        setRows((r) => r.map((x, j) => j === i ? { ...x, progress: 55 } : x));
        await api(`/orders/${order.id}/documents`, { method: "POST", body: fd });
        setRows((r) => r.map((x, j) => j === i ? { ...x, progress: 100, done: true } : x));
        ok++;
      } catch (e) {
        setRows((r) => r.map((x, j) => j === i ? { ...x, error: e.message, progress: 0 } : x));
      }
    }
    setBusy(false);
    if (ok) { toast(`${ok} document${ok > 1 ? "s" : ""} added to the locker`); onDone && onDone(); }
    if (ok === rows.length) onClose();
  };

  return (
    <Modal open title="Upload documents" onClose={onClose} footer={<>
      <Btn onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" disabled={!rows.length || busy} onClick={upload}>
        {busy && <Spinner />}Upload</Btn>
    </>}>
      <div className={cx("qp-dropzone", over && "is-over")}
        onClick={() => inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files); }}>
        <div className="qp-empty__icon" style={{ width: 42, height: 42, marginBottom: 10 }}>
          <I d={ic.upload} size={20} />
        </div>
        <div className="qp-h3">Drop files here or click to browse</div>
        <div className="qp-small qp-muted mt4">PDF, image or document · added as “Review needed”</div>
        <input ref={inputRef} type="file" multiple style={{ display: "none" }}
               onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
      </div>

      <div className="mt20">
        {rows.map((r, i) => (
          <div key={i} className="qp-uprow">
            <span className="qp-uprow__icon"><I d={ic.doc} size={17} /></span>
            <div className="grow">
              <div className="qp-docname">{r.file.name}</div>
              <div className="qp-docmeta">{fmtBytes(r.file.size)}</div>
              {r.progress > 0 && !r.done && (
                <div className="qp-progress mt8"><div className="qp-progress__fill"
                     style={{ width: r.progress + "%" }} /></div>
              )}
              {r.error && <div className="qp-small mt4" style={{ color: "var(--danger)" }}>{r.error}</div>}
            </div>
            {r.done
              ? <span style={{ color: "var(--b-600)" }}><I d={ic.check} size={20} sw={2.4} /></span>
              : <select className="qp-select" style={{ width: 240 }} value={r.type}
                  onChange={(e) => setRows((x) => x.map((y, j) => j === i
                    ? { ...y, type: e.target.value } : y))}>
                  <option value="">Select evidence category</option>
                  {docTypes.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>}
            {!r.done && (
              <Btn variant="ghost" size="sm" aria-label="Remove"
                   onClick={() => setRows((x) => x.filter((_, j) => j !== i))}>
                <I d={ic.x} size={15} /></Btn>
            )}
          </div>
        ))}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------- submit
function SubmitModal({ open, order, onClose, onDone }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const summary = useAsync(() => api(`/orders/${order.id}/research/summary`),
                           [order.id, open], { auto: open });
  if (!open) return null;
  const c = (summary.data && summary.data.counts) || {};
  const assignee = (summary.data && summary.data.assignee) || order.researcher;

  const go = async () => {
    setBusy(true);
    try {
      const r = await api(`/orders/${order.id}/research/submit`,
                          { method: "POST", json: { note } });
      toast("Research submitted — order moved to Field Survey");
      onDone && onDone(r.order);
      onClose();
    } catch (e) { toast(e.message, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} hideClose footer={<>
      <Btn onClick={onClose}>Back</Btn>
      <Btn variant="primary" disabled={busy || !c.locked} onClick={go}>
        {busy && <Spinner />}Submit research</Btn>
    </>}>
      <h2 className="qp-h2">Hand this order to the field survey team?</h2>
      <p className="qp-sub">
        The locked research set becomes read-only evidence and the order status changes from
        In Research to In Survey.{assignee ? ` ${assignee} is notified.` : ""}</p>

      <div className="qp-card qp-card--flat mt20">
        <div className="qp-kv"><span className="qp-kv__k">Documents locked</span>
          <span className="qp-kv__v">{c.locked ?? "—"}</span></div>
        <div className="qp-kv"><span className="qp-kv__k">Files in Evidence Locker</span>
          <span className="qp-kv__v">{c.documents ?? "—"}</span></div>
        <div className="qp-kv"><span className="qp-kv__k">Not reviewed / unlocked files</span>
          <span className="qp-kv__v">{c.review_needed ?? "—"}</span></div>
      </div>

      {!c.locked && (
        <div className="qp-note mt16">
          <I d={ic.alert} size={16} className="qp-note__icon" />
          <span>Lock at least one document before handing the order over — an empty evidence
            set is not a research hand-off.</span>
        </div>
      )}

      <div className="mt20">
        <label className="qp-field__label">Researcher Note</label>
        <textarea className="qp-textarea" value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder="Anything the field crew should know before the site visit." />
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ change logs
const LOG_ICON = {
  uploaded: { d: ic.upload, bg: "var(--info-bg)", fg: "var(--info)" },
  auto_fetched: { d: ic.sparkle, bg: "var(--b-100)", fg: "var(--b-700)" },
  auto_fetch: { d: ic.sparkle, bg: "var(--b-100)", fg: "var(--b-700)" },
  deleted: { d: ic.trash, bg: "var(--danger-bg)", fg: "var(--danger)" },
  locked: { d: ic.lock, bg: "var(--b-100)", fg: "var(--b-700)" },
  unlocked: { d: ic.unlock, bg: "#FEF0C7", fg: "var(--warn)" },
  doc_type_set: { d: ic.list, bg: "var(--g-100)", fg: "var(--g-700)" },
};

const LogRow = ({ e, plain }) => {
  const style = LOG_ICON[e.action] || { d: ic.doc, bg: "var(--g-100)", fg: "var(--g-700)" };
  return (
    <div className="qp-logrow">
      {!plain && (
        <span className="qp-logrow__icon" style={{ background: style.bg, color: style.fg }}>
          <I d={style.d} size={15} />
        </span>
      )}
      <div className="grow">
        <div className="qp-logrow__title">{e.title}</div>
        {e.subtitle && <div className="qp-logrow__sub">{e.subtitle}</div>}
        <div className="qp-logrow__meta">{e.actor}. {fmtStamp(e.ts)}</div>
        {e.reason && (<>
          <div className="qp-logrow__meta mt8" style={{ color: "var(--g-800)" }}>Reason</div>
          <div className="qp-logrow__reason">{e.reason}</div>
        </>)}
      </div>
    </div>
  );
};

function LogModal({ open, order, scope, onClose }) {
  const log = useAsync(() => api(`/orders/${order.id}/log?scope=${scope}`),
                       [order.id, scope, open], { auto: open });
  if (!open) return null;
  const title = scope === "locker" ? "Evidence locker — change log"
                                   : "Order information — change log";
  const events = (log.data && log.data.events) || [];
  return (
    <Modal open title={title} onClose={onClose}>
      {log.loading && <div className="row gap8 qp-muted"><Spinner /> Loading…</div>}
      {!log.loading && !events.length && <p className="qp-sub">Nothing recorded yet.</p>}
      {events.map((e) => <LogRow key={e.id} e={e} plain={scope === "order"} />)}
    </Modal>
  );
}

// --------------------------------------------------------------------- checklist
function ChecklistDrawer({ open, order, onClose, reloadKey }) {
  const cl = useAsync(() => api(`/orders/${order.id}/checklist`),
                      [order.id, open, reloadKey], { auto: open });
  if (!open) return null;
  const d = cl.data || { items: [], percent: 0 };
  return (
    <Drawer open title="Checklist" onClose={onClose}>
      <div className="row gap12">
        <div className="qp-progress grow"><div className="qp-progress__fill"
             style={{ width: d.percent + "%" }} /></div>
        <span className="qp-h3">{d.percent}%</span>
      </div>
      <p className="qp-small qp-muted mt8">
        A row ticks when a <b>locked</b> document of that type is in the Evidence Locker.
      </p>
      <div className="mt12">
        {d.items.map((it) => (
          <div key={it.key} className={cx("qp-checkrow", it.done && "is-done")}>
            <span className="qp-checkrow__mark"><I d={ic.check} size={13} sw={3} /></span>
            <span className="grow" style={{ fontSize: 14.5,
                  color: it.done ? "var(--g-950)" : "var(--g-700)" }}>{it.label}</span>
            {it.requirement !== "mandatory" &&
              <span className="qp-small qp-muted">{it.requirement}</span>}
          </div>
        ))}
      </div>
    </Drawer>
  );
}

Object.assign(window, {
  ReviewDocModal, UnlockModal, DeleteDocModal, UploadModal, SubmitModal,
  LogModal, LogRow, ChecklistDrawer,
});
